"""Markdown-authoritative creative evidence for `books/<slug>/` projects."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .models import NovelForgeError
from .planning_spec import (
    ARC_AUDIT_INTERVAL,
    DRAFT_MODES,
    EVIDENCE_DIRECTORIES,
    EVIDENCE_KINDS,
    GENERATION_METRICS_SOURCES,
    GENERATION_REASONING_EFFORTS,
    GENERATION_SANDBOX_PROFILES,
    GENERATION_STAGES,
    MAX_CACHED_INPUT_TOKENS_PER_CHAPTER,
    MAX_DRAFT_MUTATIONS_PER_CHAPTER,
    MAX_REQUESTS_PER_CHAPTER,
    MAX_REVIEW_CALLS_PER_CHAPTER,
    MAX_AUTOMATIC_GENERATIONS,
    PROVENANCE_CONFIDENCE_LEVELS,
)


EVIDENCE_SCHEMA_VERSION = 1
MARKER = "<!-- novel-forge-evidence:v1 -->"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AUTHORITIES = {
    "author",
    "human_delegate",
    "human_reviewer",
    "agent",
    "model",
    "mixed",
}
FORBIDDEN_CLAIMS = {"author_approved", "publication_eligibility"}
FORBIDDEN_HUMANIZATION = {"deliberate_typo", "random_defect", "fact_error"}


class BookEvidenceError(NovelForgeError):
    """Raised when a creative evidence record is invalid."""


@dataclass(frozen=True)
class EvidenceRecord:
    """Validated evidence metadata extracted from Markdown."""

    data: dict[str, Any]

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def kind(self) -> str:
        return self.data["kind"]


def _require_string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BookEvidenceError(f"证据字段 {field} 必须是非空字符串。")
    return value.strip()


def _require_string_list(
    data: Mapping[str, Any], field: str, *, minimum: int = 1
) -> list[str]:
    value = data.get(field)
    if (
        not isinstance(value, list)
        or len(value) < minimum
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise BookEvidenceError(
            f"证据字段 {field} 必须是至少 {minimum} 项的非空字符串数组。"
        )
    return [item.strip() for item in value]


def _require_chapter(data: Mapping[str, Any], field: str = "chapter") -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise BookEvidenceError(f"证据字段 {field} 必须是正整数。")
    return value


def _optional_nonnegative_int(data: Mapping[str, Any], field: str) -> None:
    value = data.get(field)
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise BookEvidenceError(f"generation.{field} 必须是非负整数或 null。")


def _optional_nonnegative_number(data: Mapping[str, Any], field: str) -> None:
    value = data.get(field)
    if value is not None and (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value < 0
    ):
        raise BookEvidenceError(f"generation.{field} 必须是非负数或 null。")


def _optional_string_list(data: Mapping[str, Any], field: str) -> None:
    value = data.get(field)
    if value is not None and (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise BookEvidenceError(
            f"generation.{field} 必须是非空字符串组成的数组或 null。"
        )


def _validate_common(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    for forbidden in FORBIDDEN_CLAIMS:
        if forbidden in data:
            raise BookEvidenceError(
                f"证据不得声明 {forbidden}；模型或流程记录不能冒充作者批准。"
            )
    if data.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise BookEvidenceError(
            f"不支持的证据 schema_version：{data.get('schema_version')!r}"
        )
    record_id = _require_string(data, "id")
    if not ID_RE.fullmatch(record_id):
        raise BookEvidenceError(
            "证据 id 只能包含 ASCII 字母、数字、点、下划线和连字符。"
        )
    if data.get("kind") not in EVIDENCE_KINDS:
        raise BookEvidenceError(f"未知证据 kind：{data.get('kind')!r}")
    _require_string(data, "created_at")
    if data.get("authority") not in AUTHORITIES:
        raise BookEvidenceError(
            f"未知 authority：{data.get('authority')!r}"
        )
    _require_string_list(data, "source_paths")
    _require_string(data, "summary")
    return data


def _validate_generation(data: dict[str, Any]) -> None:
    _require_chapter(data)
    if data.get("draft_mode") not in DRAFT_MODES:
        raise BookEvidenceError(
            "generation.draft_mode 必须是 " + "、".join(DRAFT_MODES) + "。"
        )
    if data.get("writer_type") not in {"human", "agent", "model"}:
        raise BookEvidenceError("generation.writer_type 必须是 human、agent 或 model。")
    if (
        data.get("writer_type") == "human"
        and data.get("authority") not in {"author", "human_delegate"}
    ):
        raise BookEvidenceError(
            "generation.writer_type=human 时 authority 必须是 "
            "author 或 human_delegate。"
        )
    _require_string(data, "provider")
    _require_string(data, "model")
    _require_string(data, "content_path")
    digest = _require_string(data, "content_sha256")
    if not SHA256_RE.fullmatch(digest):
        raise BookEvidenceError("generation.content_sha256 必须是 SHA-256。")
    _optional_nonnegative_number(data, "elapsed_seconds")
    for field in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "request_count",
        "draft_write_count",
        "draft_edit_count",
        "review_call_count",
        "pause_count",
        "interaction_count",
        "review_round",
    ):
        _optional_nonnegative_int(data, field)
    metrics_source = data.get("metrics_source")
    if (
        metrics_source is not None
        and metrics_source not in GENERATION_METRICS_SOURCES
    ):
        raise BookEvidenceError(
            "generation.metrics_source 必须是 "
            + "、".join(GENERATION_METRICS_SOURCES)
            + "。"
        )
    stage = data.get("generation_stage")
    if stage is not None and stage not in GENERATION_STAGES:
        raise BookEvidenceError(
            "generation.generation_stage 必须是 "
            + "、".join(GENERATION_STAGES)
            + "。"
        )
    confidence = data.get("provenance_confidence")
    if (
        confidence is not None
        and confidence not in PROVENANCE_CONFIDENCE_LEVELS
    ):
        raise BookEvidenceError(
            "generation.provenance_confidence 必须是 "
            + "、".join(PROVENANCE_CONFIDENCE_LEVELS)
            + "。"
        )
    if confidence == "user_attested" and data.get("authority") not in {
        "author",
        "human_delegate",
    }:
        raise BookEvidenceError(
            "generation.provenance_confidence=user_attested 时，"
            "authority 必须是 author 或 human_delegate。"
        )
    reasoning_effort = data.get("reasoning_effort")
    if (
        reasoning_effort is not None
        and reasoning_effort not in GENERATION_REASONING_EFFORTS
    ):
        raise BookEvidenceError(
            "generation.reasoning_effort 必须是 "
            + "、".join(GENERATION_REASONING_EFFORTS)
            + "。"
        )
    sandbox_profile = data.get("sandbox_profile")
    if (
        sandbox_profile is not None
        and sandbox_profile not in GENERATION_SANDBOX_PROFILES
    ):
        raise BookEvidenceError(
            "generation.sandbox_profile 必须是 "
            + "、".join(GENERATION_SANDBOX_PROFILES)
            + "。"
        )
    _optional_string_list(data, "tool_capabilities")
    _optional_string_list(data, "tool_failures")
    if data.get("draft_mode") == "degraded_exploration":
        _require_string(data, "agent_harness")
        if sandbox_profile not in {"restricted", "no_shell"}:
            raise BookEvidenceError(
                "degraded_exploration generation.sandbox_profile "
                "必须是 restricted 或 no_shell。"
            )
        _require_string_list(data, "tool_capabilities")
        _require_string_list(data, "tool_failures")
    human_authorized = data.get("human_regeneration_authorized")
    if human_authorized is not None and human_authorized is not True:
        raise BookEvidenceError(
            "generation.human_regeneration_authorized 只能为 true 或省略。"
        )
    if human_authorized is True:
        if data.get("authority") not in {"author", "human_delegate"}:
            raise BookEvidenceError(
                "人工回炉授权的 authority 必须是 author 或 human_delegate。"
            )
        _require_string(data, "human_decision_reference")
    if confidence == "harness_exposed":
        _require_string(data, "run_id")
        _require_string(data, "agent_harness")
        _require_string_list(data, "tool_capabilities")
        if metrics_source != "harness_reported":
            raise BookEvidenceError(
                "harness_exposed generation 的 metrics_source "
                "必须是 harness_reported。"
            )
    parent = data.get("parent_generation_id")
    if parent is not None and (
        not isinstance(parent, str)
        or not ID_RE.fullmatch(parent)
        or parent == data["id"]
    ):
        raise BookEvidenceError(
            "generation.parent_generation_id 必须是另一条合法 generation id 或 null。"
        )


def _validate_branch(data: dict[str, Any]) -> None:
    _require_chapter(data)
    _require_string(data, "experiment_id")
    candidates = _require_string_list(data, "candidates", minimum=2)
    _require_string_list(data, "evaluation_ids")
    if len(candidates) != len(set(candidates)):
        raise BookEvidenceError("branch.candidates 不得重复。")
    if data.get("selection_mode") != "single_winner":
        raise BookEvidenceError(
            "branch.selection_mode 必须是 single_winner，不得静默混合全部候选。"
        )
    winner = data.get("winner")
    if not isinstance(winner, str) or not winner.strip():
        raise BookEvidenceError("branch.winner 必须是单一候选标签。")
    if winner not in candidates:
        raise BookEvidenceError("branch.winner 必须存在于 candidates。")
    tradeoffs = data.get("discarded_tradeoffs")
    losers = {candidate for candidate in candidates if candidate != winner}
    if (
        not isinstance(tradeoffs, dict)
        or set(tradeoffs) != losers
        or not all(
            isinstance(value, str) and value.strip() for value in tradeoffs.values()
        )
    ):
        raise BookEvidenceError(
            "branch.discarded_tradeoffs 必须逐项记录所有未胜出候选的代价。"
        )


def _validate_evaluation(data: dict[str, Any]) -> None:
    _require_chapter(data)
    _require_string(data, "experiment_id")
    labels = _require_string_list(data, "candidate_labels", minimum=2)
    if data.get("blinded") is not True:
        raise BookEvidenceError("evaluation.blinded 必须为 true。")
    preferred = _require_string(data, "preferred_label")
    if preferred not in labels:
        raise BookEvidenceError("evaluation.preferred_label 必须属于 candidate_labels。")
    if data.get("reviewer_type") not in {"human", "agent", "model"}:
        raise BookEvidenceError(
            "evaluation.reviewer_type 必须是 human、agent 或 model。"
        )
    for field in ("reviewer_id", "provider", "model", "context_scope"):
        _require_string(data, field)
    questions = data.get("questions")
    required = {
        "desire",
        "concealment",
        "relationship_change",
        "memorable_images",
        "next_question",
    }
    if not isinstance(questions, dict) or not required.issubset(questions):
        raise BookEvidenceError(
            "evaluation.questions 缺少人物欲望、隐瞒、关系变化、画面或下一问题。"
        )
    for field in required - {"memorable_images"}:
        _require_string(questions, field)
    images = questions["memorable_images"]
    if (
        not isinstance(images, list)
        or not images
        or not all(isinstance(item, str) and item.strip() for item in images)
    ):
        raise BookEvidenceError(
            "evaluation.questions.memorable_images 必须是非空字符串数组。"
        )


def _validate_preference(data: dict[str, Any]) -> None:
    _require_chapter(data)
    _require_string(data, "branch_id")
    _require_string_list(data, "evaluation_ids")
    _require_string(data, "selected_id")
    _require_string_list(data, "rejected_ids")
    _require_string_list(data, "accepted_qualities")
    _require_string_list(data, "rejected_qualities")
    if data.get("authority") not in {"author", "human_delegate"}:
        raise BookEvidenceError(
            "preference.authority 必须是 author 或 human_delegate。"
        )
    if data.get("decision_authority") not in {"author", "human_delegate"}:
        raise BookEvidenceError(
            "preference.decision_authority 必须是 author 或 human_delegate。"
        )


def _validate_arc_audit(data: dict[str, Any]) -> None:
    if data.get("scope") not in {"checkpoint", "volume"}:
        raise BookEvidenceError("arc_audit.scope 必须是 checkpoint 或 volume。")
    start = _require_chapter(data, "start_chapter")
    end = _require_chapter(data, "end_chapter")
    if end < start:
        raise BookEvidenceError("arc_audit.end_chapter 不能早于 start_chapter。")
    if data["scope"] == "volume":
        _require_string(data, "volume_id")
    if data.get("verdict") not in {"continue", "replan"}:
        raise BookEvidenceError("arc_audit.verdict 必须是 continue 或 replan。")
    open_must = data.get("open_must")
    if not isinstance(open_must, int) or isinstance(open_must, bool) or open_must < 0:
        raise BookEvidenceError("arc_audit.open_must 必须是非负整数。")
    source_sha256 = data.get("source_sha256")
    source_paths = data.get("source_paths", [])
    if (
        not isinstance(source_sha256, dict)
        or set(source_sha256) != set(source_paths)
        or not all(
            isinstance(value, str) and SHA256_RE.fullmatch(value)
            for value in source_sha256.values()
        )
    ):
        raise BookEvidenceError(
            "arc_audit.source_sha256 必须逐项覆盖 source_paths 的 SHA-256。"
        )
    covered_chapters = {
        int(match.group(1))
        for value in source_paths
        if (
            match := re.fullmatch(
                r"chapters/e\d+/ch-(\d+)/正文\.md",
                value,
            )
        )
    }
    required_chapters = set(range(start, end + 1))
    if not required_chapters.issubset(covered_chapters):
        missing = ", ".join(
            f"ch{number:02d}"
            for number in sorted(required_chapters - covered_chapters)
        )
        raise BookEvidenceError(
            f"arc_audit.source_paths 未覆盖审计范围内章节：{missing}"
        )


def _validate_rule_decision(data: dict[str, Any]) -> None:
    _require_string(data, "rule_id")
    _require_string(data, "hypothesis")
    lifecycle = data.get("lifecycle")
    if lifecycle not in {"experimental", "advisory", "blocking", "retired"}:
        raise BookEvidenceError(
            "rule_decision.lifecycle 必须是 experimental、advisory、blocking 或 retired。"
        )
    _require_string_list(data, "tested_works")
    _require_string_list(data, "tested_genres")
    _require_string_list(data, "tested_models")
    intervention = _require_string(data, "intervention_type")
    if intervention in FORBIDDEN_HUMANIZATION:
        raise BookEvidenceError(
            f"禁止把 {intervention} 登记为人类化策略。"
        )
    if lifecycle == "retired":
        _require_string(data, "retirement_reason")
    if lifecycle == "blocking":
        for field in ("tested_works", "tested_genres", "tested_models"):
            if len(set(data[field])) < 3:
                raise BookEvidenceError(
                    f"规则升级为 blocking 前，{field} 至少需要 3 个独立证据。"
                )


def _validate_data(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = _validate_common(raw)
    validators = {
        "generation": _validate_generation,
        "branch": _validate_branch,
        "evaluation": _validate_evaluation,
        "preference": _validate_preference,
        "arc_audit": _validate_arc_audit,
        "rule_decision": _validate_rule_decision,
    }
    validators[data["kind"]](data)
    return data


def parse_evidence_markdown(text: str) -> EvidenceRecord:
    """Parse and validate the marked JSON metadata block."""
    marker_pos = text.find(MARKER)
    if marker_pos < 0:
        raise BookEvidenceError(f"证据 Markdown 缺少标记：{MARKER}")
    tail = text[marker_pos + len(MARKER) :]
    match = re.search(r"```json\s*\n(.*?)\n```", tail, re.DOTALL | re.IGNORECASE)
    if not match:
        raise BookEvidenceError("证据 Markdown 缺少标记后的 fenced JSON 元数据块。")
    try:
        raw = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise BookEvidenceError(f"证据 JSON 无法解析：{exc}") from exc
    if not isinstance(raw, dict):
        raise BookEvidenceError("证据 JSON 顶层必须是对象。")
    return EvidenceRecord(_validate_data(raw))


def render_evidence_markdown(
    record: EvidenceRecord | Mapping[str, Any], title: str | None = None
) -> str:
    """Render a validated evidence record into reviewable Markdown."""
    data = record.data if isinstance(record, EvidenceRecord) else dict(record)
    validated = _validate_data(data)
    heading = title or validated["id"]
    payload = json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True)
    return f"# {heading}\n\n{MARKER}\n```json\n{payload}\n```\n"


def _book_dir(root: Path, slug: str) -> Path:
    book_dir = Path(root) / "books" / slug
    if not book_dir.is_dir():
        raise BookEvidenceError(f"books/ 项目不存在：{book_dir}")
    return book_dir


def _resolve_book_source(book_dir: Path, value: str, field: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise BookEvidenceError(f"{field} 必须是本书目录内的相对路径。")
    resolved = (book_dir / Path(*pure.parts)).resolve()
    try:
        resolved.relative_to(book_dir.resolve())
    except ValueError as exc:
        raise BookEvidenceError(f"{field} 不能逃逸本书目录。") from exc
    if not resolved.is_file():
        raise BookEvidenceError(f"{field} 引用的文件不存在：{value}")
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_book_sources(book_dir: Path, record: EvidenceRecord) -> None:
    for value in record.data["source_paths"]:
        _resolve_book_source(book_dir, value, "source_paths")
    kind = record.kind
    if kind == "generation":
        content = _resolve_book_source(
            book_dir, record.data["content_path"], "content_path"
        )
        if _sha256(content) != record.data["content_sha256"]:
            raise BookEvidenceError(
                "generation.content_sha256 与当前 content_path 内容不一致。"
            )
    if kind == "arc_audit":
        for value, expected in record.data["source_sha256"].items():
            source = _resolve_book_source(book_dir, value, "source_sha256")
            if _sha256(source) != expected:
                raise BookEvidenceError(
                    f"arc_audit.source_sha256 与当前来源不一致：{value}"
                )
    if kind in {"branch", "evaluation"}:
        experiment_id = record.data["experiment_id"]
        labels = (
            record.data["candidates"]
            if kind == "branch"
            else record.data["candidate_labels"]
        )
        for label in labels:
            path = (
                book_dir
                / "evaluation"
                / "experiments"
                / experiment_id
                / "candidates"
                / f"{label}.md"
            )
            if not path.is_file():
                raise BookEvidenceError(
                    f"{kind} 候选文件不存在："
                    f"evaluation/experiments/{experiment_id}/candidates/{label}.md"
                )
    if kind == "branch":
        for evaluation_id in record.data["evaluation_ids"]:
            evaluation, _ = find_evidence_record(
                book_dir.parents[1], book_dir.name, evaluation_id
            )
            if (
                evaluation.kind != "evaluation"
                or evaluation.data["chapter"] != record.data["chapter"]
                or evaluation.data["experiment_id"]
                != record.data["experiment_id"]
                or set(evaluation.data["candidate_labels"])
                != set(record.data["candidates"])
            ):
                raise BookEvidenceError(
                    "branch.evaluation_ids 必须指向同章、同实验、同候选集的盲评证据。"
                )
    if kind == "preference":
        branch, _ = find_evidence_record(
            book_dir.parents[1], book_dir.name, record.data["branch_id"]
        )
        if branch.kind != "branch" or branch.data["chapter"] != record.data["chapter"]:
            raise BookEvidenceError(
                "preference.branch_id 必须指向同章的 branch 证据。"
            )
        if record.data["selected_id"] != branch.data["winner"]:
            raise BookEvidenceError(
                "preference.selected_id 必须与 branch.winner 一致。"
            )
        branch_losers = {
            candidate
            for candidate in branch.data["candidates"]
            if candidate != branch.data["winner"]
        }
        if set(record.data["rejected_ids"]) != branch_losers:
            raise BookEvidenceError(
                "preference.rejected_ids 必须覆盖 branch 的全部未胜出候选。"
            )
        if set(record.data["evaluation_ids"]) != set(
            branch.data["evaluation_ids"]
        ):
            raise BookEvidenceError(
                "preference.evaluation_ids 必须与 branch 使用的盲评证据一致。"
            )


def _all_evidence_paths(book_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in EVIDENCE_DIRECTORIES.values():
        evidence_dir = book_dir / "evidence" / directory
        if evidence_dir.is_dir():
            paths.extend(sorted(evidence_dir.glob("*.md")))
    return paths


def _record_is_stale(book_dir: Path, record: EvidenceRecord) -> bool:
    try:
        if record.kind == "generation":
            content = _resolve_book_source(
                book_dir, record.data["content_path"], "content_path"
            )
            return _sha256(content) != record.data["content_sha256"]
        if record.kind == "arc_audit":
            return any(
                _sha256(
                    _resolve_book_source(book_dir, value, "source_sha256")
                )
                != expected
                for value, expected in record.data["source_sha256"].items()
            )
    except BookEvidenceError:
        return True
    return False


def find_evidence_record(
    root: Path, slug: str, record_id: str
) -> tuple[EvidenceRecord, Path]:
    """Find one immutable evidence record by globally unique ID."""
    book_dir = _book_dir(root, slug)
    for path in _all_evidence_paths(book_dir):
        record = parse_evidence_markdown(path.read_text(encoding="utf-8-sig"))
        if record.id == record_id:
            return record, path
    raise BookEvidenceError(f"证据 id 不存在：{record_id}")


def record_evidence(root: Path, slug: str, source_file: Path) -> dict[str, Any]:
    """Validate and atomically store one immutable creative evidence record."""
    book_dir = _book_dir(root, slug)
    source_file = Path(source_file)
    if not source_file.is_absolute():
        raise BookEvidenceError("--file 必须是绝对路径。")
    if not source_file.is_file():
        raise BookEvidenceError(f"证据文件不存在：{source_file}")
    try:
        text = source_file.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BookEvidenceError(f"证据文件不是有效 UTF-8：{exc}") from exc
    record = parse_evidence_markdown(text)
    _validate_book_sources(book_dir, record)

    existing_generation_hashes: set[str] = set()
    for existing in _all_evidence_paths(book_dir):
        existing_record = parse_evidence_markdown(
            existing.read_text(encoding="utf-8-sig")
        )
        if existing_record.id == record.id:
            raise BookEvidenceError(f"证据 id 已存在，不得覆盖：{record.id}")
        if (
            record.kind == "generation"
            and existing_record.kind == "generation"
            and existing_record.data["chapter"] == record.data["chapter"]
            and existing_record.data["content_sha256"]
            == record.data["content_sha256"]
        ):
            raise BookEvidenceError(
                "相同正文版本已有 generation 证据："
                f"{existing_record.id}；不得通过更换 id 重复计入生成轮次。"
            )
        if (
            record.kind == "generation"
            and existing_record.kind == "generation"
            and existing_record.data["chapter"] == record.data["chapter"]
        ):
            existing_generation_hashes.add(
                existing_record.data["content_sha256"]
            )
    if (
        record.kind == "generation"
        and len(existing_generation_hashes) >= MAX_AUTOMATIC_GENERATIONS
        and not (
            record.data.get("human_regeneration_authorized") is True
            and record.data.get("authority") in {"author", "human_delegate"}
            and isinstance(record.data.get("human_decision_reference"), str)
            and record.data["human_decision_reference"].strip()
        )
    ):
        raise BookEvidenceError(
            f"第 {MAX_AUTOMATIC_GENERATIONS + 1} 个不同正文版本需要明确人工授权；"
            "请由 author/human_delegate 设置 human_regeneration_authorized=true "
            "并填写 human_decision_reference。"
        )

    directory = EVIDENCE_DIRECTORIES[record.kind]
    target = book_dir / "evidence" / directory / f"{record.id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise BookEvidenceError(f"证据文件已存在，不得覆盖：{target.name}")
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{record.id}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            raise BookEvidenceError(f"证据文件已存在，不得覆盖：{target.name}")
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    result: dict[str, Any] = {
        "record_id": record.id,
        "kind": record.kind,
        "evidence_path": target.relative_to(book_dir).as_posix(),
    }
    if "chapter" in record.data:
        result["chapter"] = record.data["chapter"]
    return result


def evidence_status(
    root: Path, slug: str, chapter: int | None = None
) -> dict[str, Any]:
    """Return evidence inventory without returning record bodies."""
    book_dir = _book_dir(root, slug)
    records: list[tuple[EvidenceRecord, Path]] = []
    for path in _all_evidence_paths(book_dir):
        record = parse_evidence_markdown(path.read_text(encoding="utf-8-sig"))
        if chapter is not None:
            record_chapter = record.data.get("chapter")
            in_arc_range = (
                record.kind == "arc_audit"
                and record.data["start_chapter"] <= chapter <= record.data["end_chapter"]
            )
            if record_chapter not in (None, chapter) and not in_arc_range:
                continue
        records.append((record, path))
    records.sort(key=lambda item: item[0].id)
    counts = {kind: 0 for kind in EVIDENCE_KINDS}
    for record, _ in records:
        counts[record.kind] += 1
    stale_by_id = {
        record.id: _record_is_stale(book_dir, record)
        for record, _ in records
    }
    resolved_experiments = sorted(
        {
            record.data["experiment_id"]
            for record, _ in records
            if record.kind == "branch"
        }
    )
    experiment_root = book_dir / "evaluation" / "experiments"
    if chapter is None:
        candidate_experiments = sorted(
            path.parent.name
            for path in experiment_root.glob("*/candidates")
            if path.is_dir() and any(path.glob("*.md"))
        )
    else:
        candidate_experiments = sorted(
            {
                record.data["experiment_id"]
                for record, _ in records
                if record.kind in {"evaluation", "branch"}
            }
        )
    recent_preferences = sorted(
        (
            record
            for record, _ in records
            if record.kind == "preference"
        ),
        key=lambda record: (record.data["created_at"], record.id),
        reverse=True,
    )[:5]
    generation_origins: dict[int, set[tuple[str, str]]] = {}
    for record, _ in records:
        if record.kind == "generation":
            generation_origins.setdefault(record.data["chapter"], set()).add(
                (record.data["provider"], record.data["model"])
            )
    provenance_warnings = [
        {
            "record_id": record.id,
            "warning": "same_provider_model_as_generation",
        }
        for record, _ in records
        if record.kind == "evaluation"
        and (record.data["provider"], record.data["model"])
        in generation_origins.get(record.data["chapter"], set())
    ]
    arc_audit_due = (
        chapter is not None and chapter % ARC_AUDIT_INTERVAL == 0
    )
    arc_audit_satisfied = not arc_audit_due or any(
        record.kind == "arc_audit"
        and record.data["scope"] == "checkpoint"
        and record.data["end_chapter"] == chapter
        and record.data["open_must"] == 0
        and not stale_by_id[record.id]
        for record, _ in records
    )
    generation_records = [
        record for record, _ in records if record.kind == "generation"
    ]
    generation_groups: dict[
        tuple[int, str], list[EvidenceRecord]
    ] = {}
    for record in generation_records:
        generation_groups.setdefault(
            (record.data["chapter"], record.data["content_sha256"]), []
        ).append(record)
    semantic_generation_records = [
        sorted(group, key=lambda record: record.id)[0]
        for group in generation_groups.values()
    ]
    semantic_generation_records.sort(
        key=lambda record: (
            record.data["chapter"],
            record.data["content_sha256"],
            record.id,
        )
    )
    duplicate_generation_groups = [
        {
            "chapter": generation_chapter,
            "content_sha256": content_sha256,
            "record_ids": sorted(record.id for record in group),
        }
        for (
            generation_chapter,
            content_sha256,
        ), group in sorted(generation_groups.items())
        if len(group) > 1
    ]

    def _review_cycle(count: int) -> str:
        if count == 0:
            return "unrecorded"
        if count == 1:
            return "initial"
        if count < MAX_AUTOMATIC_GENERATIONS:
            return "consolidated_patch"
        if count == MAX_AUTOMATIC_GENERATIONS:
            return "budget_exhausted"
        return "budget_exceeded"

    generations_by_chapter: dict[int, list[EvidenceRecord]] = {}
    for record in semantic_generation_records:
        generations_by_chapter.setdefault(record.data["chapter"], []).append(
            record
        )
    generation_cycles = [
        {
            "chapter": generation_chapter,
            "generation_count": len(chapter_records),
            "review_cycle_status": _review_cycle(len(chapter_records)),
            "another_generation_requires_human": (
                len(chapter_records) >= MAX_AUTOMATIC_GENERATIONS
            ),
        }
        for generation_chapter, chapter_records in sorted(
            generations_by_chapter.items()
        )
    ]
    generation_record_count = len(generation_records)
    generation_count = len(semantic_generation_records)
    review_cycle_status = (
        _review_cycle(generation_count)
        if chapter is not None
        else "not_applicable"
    )
    metric_fields = (
        "chapter",
        "writer_type",
        "provider",
        "model",
        "elapsed_seconds",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "request_count",
        "draft_write_count",
        "draft_edit_count",
        "review_call_count",
        "metrics_source",
        "pause_count",
        "interaction_count",
        "review_round",
        "parent_generation_id",
        "generation_stage",
        "provenance_confidence",
        "run_id",
        "agent_harness",
        "reasoning_effort",
        "sandbox_profile",
        "tool_capabilities",
        "tool_failures",
        "human_regeneration_authorized",
        "human_decision_reference",
    )
    runtime_findings: list[dict[str, Any]] = []
    runtime_chapters: list[dict[str, Any]] = []
    runtime_groups: dict[int, list[EvidenceRecord]] = {}
    for record in semantic_generation_records:
        runtime_groups.setdefault(record.data["chapter"], []).append(record)
    for generation_chapter, chapter_records in sorted(runtime_groups.items()):
        def _sum_complete(field: str) -> int | None:
            values = [record.data.get(field) for record in chapter_records]
            if any(value is None for value in values):
                return None
            return sum(int(value) for value in values)

        writes = _sum_complete("draft_write_count")
        edits = _sum_complete("draft_edit_count")
        totals = {
            "cached_input_tokens": _sum_complete("cached_input_tokens"),
            "request_count": _sum_complete("request_count"),
            "draft_mutations": (
                writes + edits
                if writes is not None and edits is not None
                else None
            ),
            "review_calls": _sum_complete("review_call_count"),
        }
        checks = (
            (
                "cached-context-budget",
                totals["cached_input_tokens"],
                MAX_CACHED_INPUT_TOKENS_PER_CHAPTER,
            ),
            (
                "request-budget",
                totals["request_count"],
                MAX_REQUESTS_PER_CHAPTER,
            ),
            (
                "draft-mutation-budget",
                totals["draft_mutations"],
                MAX_DRAFT_MUTATIONS_PER_CHAPTER,
            ),
            (
                "review-call-budget",
                totals["review_calls"],
                MAX_REVIEW_CALLS_PER_CHAPTER,
            ),
        )
        chapter_findings: list[dict[str, Any]] = []
        for code, actual, limit in checks:
            if actual is not None and actual > limit:
                finding = {
                    "record_ids": [
                        record.id for record in chapter_records
                    ],
                    "chapter": generation_chapter,
                    "code": code,
                    "actual": actual,
                    "limit": limit,
                }
                runtime_findings.append(finding)
                chapter_findings.append(finding)
        assessed = sum(value is not None for value in totals.values())
        chapter_status = (
            "exceeded"
            if chapter_findings
            else "within_budget"
            if assessed == len(totals)
            else "partial"
            if assessed
            else "unassessed"
        )
        runtime_chapters.append(
            {
                "chapter": generation_chapter,
                "record_ids": [
                    record.id for record in chapter_records
                ],
                "status": chapter_status,
                "totals": totals,
            }
        )
    assessed_runtime_fields = sum(
        value is not None
        for chapter_data in runtime_chapters
        for value in chapter_data["totals"].values()
    )
    runtime_status = (
        "exceeded"
        if runtime_findings
        else "within_budget"
        if runtime_chapters
        and all(
            chapter_data["status"] == "within_budget"
            for chapter_data in runtime_chapters
        )
        else "partial"
        if assessed_runtime_fields
        else "unassessed"
    )
    return {
        "slug": slug,
        "chapter": chapter,
        "counts": counts,
        "record_ids": [record.id for record, _ in records],
        "records": [
            {
                "id": record.id,
                "kind": record.kind,
                "path": path.relative_to(book_dir).as_posix(),
                "stale": stale_by_id[record.id],
            }
            for record, path in records
        ],
        "stale_record_ids": sorted(
            record_id for record_id, stale in stale_by_id.items() if stale
        ),
        "resolved_branch_experiments": resolved_experiments,
        "unresolved_branch_experiments": [
            experiment_id
            for experiment_id in candidate_experiments
            if experiment_id not in resolved_experiments
        ],
        "recent_preference_ids": [
            record.id for record in recent_preferences
        ],
        "provenance_warnings": provenance_warnings,
        "generation_record_count": generation_record_count,
        "generation_count": generation_count,
        "duplicate_generation_groups": duplicate_generation_groups,
        "automatic_generation_limit": MAX_AUTOMATIC_GENERATIONS,
        "review_cycle_status": review_cycle_status,
        "another_generation_requires_human": (
            chapter is not None
            and generation_count >= MAX_AUTOMATIC_GENERATIONS
        ),
        "generation_cycles": generation_cycles,
        "generation_metrics": [
            {
                "id": record.id,
                **{
                    field: record.data.get(field)
                    for field in metric_fields
                    if field in record.data
                },
            }
            for record in generation_records
        ],
        "runtime_budget": {
            "status": runtime_status,
            "findings": runtime_findings,
            "chapters": runtime_chapters,
            "limits": {
                "cached_input_tokens": MAX_CACHED_INPUT_TOKENS_PER_CHAPTER,
                "request_count": MAX_REQUESTS_PER_CHAPTER,
                "draft_mutations": MAX_DRAFT_MUTATIONS_PER_CHAPTER,
                "review_calls": MAX_REVIEW_CALLS_PER_CHAPTER,
            },
        },
        "arc_audit_due": arc_audit_due,
        "arc_audit_satisfied": arc_audit_satisfied,
        "arc_audit_interval": ARC_AUDIT_INTERVAL,
        "author_approval": False,
        "publication_eligibility": False,
    }
