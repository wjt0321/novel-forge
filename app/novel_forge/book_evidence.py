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
        raise BookEvidenceError("generation.draft_mode 必须是 formal 或 exploration。")
    if data.get("writer_type") not in {"human", "agent", "model"}:
        raise BookEvidenceError("generation.writer_type 必须是 human、agent 或 model。")
    _require_string(data, "provider")
    _require_string(data, "model")
    _require_string(data, "content_path")
    digest = _require_string(data, "content_sha256")
    if not SHA256_RE.fullmatch(digest):
        raise BookEvidenceError("generation.content_sha256 必须是 SHA-256。")


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

    for existing in _all_evidence_paths(book_dir):
        existing_record = parse_evidence_markdown(
            existing.read_text(encoding="utf-8-sig")
        )
        if existing_record.id == record.id:
            raise BookEvidenceError(f"证据 id 已存在，不得覆盖：{record.id}")

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
        "arc_audit_due": arc_audit_due,
        "arc_audit_satisfied": arc_audit_satisfied,
        "arc_audit_interval": ARC_AUDIT_INTERVAL,
        "author_approval": False,
        "publication_eligibility": False,
    }
