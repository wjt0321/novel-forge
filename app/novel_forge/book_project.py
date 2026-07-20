"""Operations on the `books/<slug>/` front-of-house workflow (no database).

These functions power the skill adapter's book-project ops
(`project-status`, `set-draft-mode`, `run-gates`, `record-review`,
`advance-state`, `evidence-status`, `record-evidence`, `sync-tools`).
They only read/write Markdown, run canonical gates, and create local-only
per-book Git checkpoints; they never return chapter prose or touch `data/`.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from . import book_gates
from .book_evidence import evidence_status, find_evidence_record
from .book_git import (
    BookGitError,
    book_git_status,
    checkpoint_book,
    initialize_book_git,
)
from .lint import lint_file
from .models import NovelForgeError
from .planning_spec import (
    CHAPTER_STATES,
    DRAFT_MODES,
    EDITORIAL_VERDICTS,
    FORWARD_STATE_TRANSITIONS,
    MAX_DRAFT_MUTATIONS_PER_CHAPTER,
    MAX_REVIEW_CALLS_PER_CHAPTER,
    PASSING_VERDICTS,
    REVIEW_ROLES,
    REVIEW_STATE_FOR_ROLE,
    REVIEW_VERDICTS,
    STATE_BLOCKED,
)
from .project_templates import (
    CREATE_ONLY_FILES,
    REQUIRED_DIRECTORIES,
    SYNCABLE_FILES,
    _planning_chapter_state_template_md,
    render_templates,
)
from .session_audit import (
    SessionAuditError,
    compare_generation_provenance,
    find_runtime_audit,
)
from .voice_signature import analyze_serial_style


class BookProjectError(NovelForgeError):
    """Raised for books/<slug>/ project-level problems."""


def _local_git_checkpoint(
    root: Path,
    slug: str,
    message: str,
    *,
    tag: str | None = None,
) -> dict[str, Any]:
    try:
        return {
            "status": "recorded",
            **checkpoint_book(root, slug, message, tag=tag),
        }
    except BookGitError as exc:
        return {
            "status": "failed",
            "committed": False,
            "commit_hash": None,
            "message": str(exc),
            "tag": None,
        }


BLIND_RECONSTRUCTION_FIELDS: tuple[str, ...] = (
    "reconstruction_space",
    "reconstruction_body",
    "reconstruction_constraints",
    "reconstruction_emotion",
    "reconstruction_dialogue",
    "memorable_image_1",
    "memorable_image_2",
    "memorable_image_3",
)
BLIND_READER_PULL_FIELDS: tuple[str, ...] = (
    "emotional_residue",
    "next_chapter_pull",
)
EDITORIAL_DIMENSION_FIELDS: tuple[str, ...] = (
    "editorial_causality",
    "editorial_agency",
    "editorial_dialogue",
    "editorial_texture",
    "editorial_continuity",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def book_dir_for(root: Path, slug: str) -> Path:
    book_dir = Path(root) / "books" / slug
    if not book_dir.is_dir():
        raise BookProjectError(f"books/ 项目不存在：{book_dir}")
    return book_dir


def _chapter_id(number: int) -> str:
    return f"ch{number:02d}"


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_chapter_file(book_dir: Path, number: int) -> Path:
    chapters_dir = book_dir / "chapters"
    if chapters_dir.is_dir():
        for path in sorted(chapters_dir.glob(f"e*/ch-{number:02d}/正文.md")):
            return path
        for path in sorted(chapters_dir.glob("e*/ch-*/正文.md")):
            m = re.match(r"ch-(\d+)", path.parent.name)
            if m and int(m.group(1)) == number:
                return path
    raise BookProjectError(
        f"找不到第 {number} 章正文：{chapters_dir}/eXX/ch-{number:02d}/正文.md"
    )


def _parse_claude_md(book_dir: Path) -> dict[str, str]:
    path = book_dir / "CLAUDE.md"
    info: dict[str, str] = {}
    if not path.exists():
        return info
    text = path.read_text(encoding="utf-8-sig")
    m = re.search(r"^-\s*标题:\s*《(.+)》", text, re.MULTILINE)
    if m:
        info["title"] = m.group(1).strip()
    m = re.search(r"^-\s*类型:\s*(.+)$", text, re.MULTILINE)
    if m:
        info["genre"] = m.group(1).strip()
    progress = book_gates.section(text, "当前进度")
    if progress:
        lines = [
            re.sub(r"^\s*-\s*", "", l).strip()
            for l in progress.splitlines()
            if l.strip().startswith("-")
        ]
        info["progress"] = " / ".join(l for l in lines if l and "_" not in l)
    return info


# --- chapter-state parsing / updating ---------------------------------------


def _chapter_state_path(book_dir: Path, ch_id: str) -> Path:
    return book_dir / "planning" / "chapter-state" / f"{ch_id}.md"


def _new_chapter_state(number: int) -> str:
    ch_id = _chapter_id(number)
    return (
        _planning_chapter_state_template_md()
        .replace("第XX章", f"第{number:02d}章")
        .replace("chXX", ch_id)
    )


def _read_chapter_state(book_dir: Path, number: int) -> tuple[Path, str, bool]:
    path = _chapter_state_path(book_dir, _chapter_id(number))
    if path.exists():
        return path, path.read_text(encoding="utf-8-sig"), False
    return path, _new_chapter_state(number), True


def parse_chapter_state(text: str) -> dict[str, Any]:
    def _field(name: str) -> str | None:
        m = re.search(rf"^-\s*{re.escape(name)}:\s*(.*)$", text, re.MULTILINE)
        return m.group(1).strip() if m else None

    evidence: list[dict[str, str]] = []
    body = book_gates.section(text, "状态证据")
    if body:
        for line in body.splitlines():
            if not line.startswith("|") or re.fullmatch(r"[| :\-]+", line):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not cells or cells[0] in ("状态", ""):
                continue
            evidence.append(
                {
                    "state": cells[0],
                    "evidence": cells[1] if len(cells) > 1 else "",
                    "result": cells[2] if len(cells) > 2 else "",
                    "time": cells[3] if len(cells) > 3 else "",
                }
            )
    return {
        "status": _field("status"),
        "revision": _field("revision"),
        "updated_at": _field("updated_at"),
        "next_action": _field("next_action"),
        "draft_mode": _field("draft_mode") or "formal",
        "generation_id": _field("generation_id") or "unrecorded",
        "evidence": evidence,
    }


def _update_state_row(text: str, state: str, evidence: str, result: str, when: str) -> str:
    """Replace or append the evidence-table row for `state`."""
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## 状态证据":
            header_idx = i
            break
    if header_idx is None:
        lines += [
            "",
            "## 状态证据",
            "",
            "| 状态 | 证据文件/报告 | verdict/结果 | 时间 | 备注 |",
            "|---|---|---|---|---|",
        ]
        header_idx = len(lines) - 2

    # Walk the table following the section header.
    table_rows_idx = [
        i
        for i in range(header_idx + 1, len(lines))
        if lines[i].startswith("|")
    ]
    # Stop at the first non-table line after the table started.
    if table_rows_idx:
        contiguous: list[int] = []
        started = False
        for i in range(header_idx + 1, len(lines)):
            if lines[i].startswith("|"):
                started = True
                contiguous.append(i)
            elif started:
                break
        table_rows_idx = contiguous or table_rows_idx[:1]

    def _make_row() -> str:
        return f"| {state} | {evidence} | {result} | {when} |  |"

    for i in table_rows_idx:
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if cells and cells[0] == state:
            note = cells[4] if len(cells) > 4 else ""
            lines[i] = f"| {state} | {evidence} | {result} | {when} | {note} |"
            return "\n".join(lines) + "\n"

    if table_rows_idx:
        lines.insert(table_rows_idx[-1] + 1, _make_row())
    else:
        lines.insert(header_idx + 1, _make_row())
    return "\n".join(lines) + "\n"


def _set_fields(text: str, **fields: str) -> str:
    for name, value in fields.items():
        pattern = rf"^-\s*{re.escape(name)}:.*$"
        replacement = f"- {name}: {value}"
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
        else:
            lines = text.splitlines()
            insert_at = 1 if lines else 0
            lines.insert(insert_at, replacement)
            text = "\n".join(lines) + "\n"
    return text


# --- review files ------------------------------------------------------------


SERIAL_REVIEW_ROLES = {"consistency-guard", "chapter-editor"}


def _review_binding_for_book(
    book_dir: Path, number: int, role: str | None = None
) -> dict[str, str]:
    chapter = find_chapter_file(book_dir, number)
    if number == 1:
        previous_chapter_sha256 = "not_applicable"
    else:
        try:
            previous_chapter_sha256 = _sha256_path(
                find_chapter_file(book_dir, number - 1)
            )
        except BookProjectError:
            previous_chapter_sha256 = "missing"
    _, state_text, _ = _read_chapter_state(book_dir, number)
    state = parse_chapter_state(state_text)
    ch_id = _chapter_id(number)
    planning_paths = (
        book_dir / "planning" / f"scene-package-{ch_id}.md",
        book_dir / "planning" / f"action-draft-{ch_id}.md",
        book_dir / "planning" / f"dialogue-ledger-{ch_id}.md",
    )
    planning_sources = {
        path.relative_to(book_dir).as_posix(): (
            _sha256_path(path) if path.exists() else None
        )
        for path in planning_paths
    }
    planning_sha256 = hashlib.sha256(
        json.dumps(
            planning_sources, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    binding_data = {
        "chapter_sha256": _sha256_path(chapter),
        "planning_sha256": planning_sha256,
        "draft_mode": state["draft_mode"],
        "generation_id": state["generation_id"],
    }
    fingerprint_data = dict(binding_data)
    if number > 1 and role in SERIAL_REVIEW_ROLES:
        fingerprint_data["previous_chapter_sha256"] = (
            previous_chapter_sha256
        )
    source_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        **binding_data,
        "previous_chapter_sha256": previous_chapter_sha256,
        "source_fingerprint": source_fingerprint,
    }


def review_binding(
    root: Path,
    slug: str,
    number: int,
    role: str | None = None,
) -> dict[str, str]:
    """Return hashes and state identity a review must bind to."""
    if role is not None and role not in REVIEW_ROLES:
        raise BookProjectError(f"未知审稿角色：{role!r}")
    return _review_binding_for_book(book_dir_for(root, slug), number, role)


def _validate_current_generation(
    root: Path,
    book_dir: Path,
    number: int,
    generation_id: str,
    draft_mode: str,
) -> tuple[Any, Path]:
    record, evidence_path = find_evidence_record(root, book_dir.name, generation_id)
    if record.kind != "generation":
        raise BookProjectError(f"证据 {generation_id} 不是 generation。")
    if record.data["chapter"] != number:
        raise BookProjectError(
            f"generation.chapter={record.data['chapter']} 与目标章节 {number} 不一致。"
        )
    if record.data["draft_mode"] != draft_mode:
        raise BookProjectError(
            "generation.draft_mode 与 chapter-state 不一致。"
        )
    pure = PurePosixPath(record.data["content_path"])
    content_path = (book_dir / Path(*pure.parts)).resolve()
    chapter_path = find_chapter_file(book_dir, number).resolve()
    if content_path != chapter_path:
        raise BookProjectError(
            "generation.content_path 必须指向本章唯一正文。"
        )
    if not content_path.is_file() or (
        _sha256_path(content_path) != record.data["content_sha256"]
    ):
        raise BookProjectError(
            "generation 证据与当前正文哈希不一致；请为修订后的正文记录新 generation。"
        )
    return record, evidence_path


def _review_filename(ch_id: str, role: str) -> str:
    return f"{ch_id}-{role}.md"


def parse_review(text: str) -> dict[str, Any]:
    def _field(name: str) -> str | None:
        m = re.search(
            rf"^-[ \t]*{re.escape(name)}:[ \t]*(.*)$",
            text,
            re.MULTILINE,
        )
        return m.group(1).strip() if m and m.group(1).strip() else None

    def _canonical_value(
        value: str | None, allowed: tuple[str, ...]
    ) -> str | None:
        if value is None:
            return None
        cleaned = value.replace("**", "").replace("`", "").strip()
        for candidate in sorted(allowed, key=len, reverse=True):
            if re.match(
                rf"^{re.escape(candidate)}(?:$|[\s（(：:])",
                cleaned,
            ):
                return candidate
        return cleaned

    must_open = 0
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if "must" in cells and ("open" in cells or "" in cells):
            must_open += 1
    raw_verdict = _field("verdict")
    return {
        "chapter": _field("chapter"),
        "role": _field("role"),
        "verdict": _canonical_value(
            raw_verdict, EDITORIAL_VERDICTS + REVIEW_VERDICTS
        ),
        "raw_verdict": raw_verdict,
        "date": _field("date"),
        "source_fingerprint": _field("source_fingerprint"),
        "chapter_sha256": _field("chapter_sha256"),
        "previous_chapter_sha256": _field("previous_chapter_sha256"),
        "planning_sha256": _field("planning_sha256"),
        "draft_mode": _field("draft_mode"),
        "generation_id": _field("generation_id"),
        "evidence_quote": _field("evidence_quote"),
        "previous_chapter_quote": _field("previous_chapter_quote"),
        "reviewer_type": _field("reviewer_type"),
        "reviewer_id": _field("reviewer_id"),
        "review_session_id": _field("review_session_id"),
        "provider": _field("provider"),
        "model": _field("model"),
        "context_scope": _canonical_value(
            _field("context_scope"),
            (
                "prose_only",
                "simulated_blind",
                "full_review_context",
                "candidate_prose_only",
            ),
        ),
        "independence_note": _field("independence_note"),
        "human_likeness": _canonical_value(
            _field("human_likeness"),
            ("convincing", "uncertain", "synthetic", "not_applicable"),
        ),
        "reader_desire": _canonical_value(
            _field("reader_desire"),
            ("continue", "conditional", "stop", "not_applicable"),
        ),
        "emotional_residue": _field("emotional_residue"),
        "next_chapter_pull": _field("next_chapter_pull"),
        **{
            field: _field(field)
            for field in (
                *BLIND_RECONSTRUCTION_FIELDS,
                *EDITORIAL_DIMENSION_FIELDS,
            )
        },
        "must_open": must_open,
    }


def _review_validation_errors(
    root: Path,
    book_dir: Path,
    number: int,
    role: str,
    parsed: dict[str, Any],
) -> list[str]:
    """Return all structural/source errors for one canonical review."""
    if role not in REVIEW_ROLES:
        return [f"未知审稿角色：{role!r}"]
    errors: list[str] = []
    if parsed["role"] and parsed["role"] != role:
        errors.append(
            f"审稿文件 role={parsed['role']} 与参数 {role} 不一致。"
        )
    valid_verdicts = (
        EDITORIAL_VERDICTS if role == "chapter-editor" else REVIEW_VERDICTS
    )
    if parsed["verdict"] not in valid_verdicts:
        errors.append(
            f"审稿文件缺少合法 verdict（{role} 允许："
            f"{', '.join(valid_verdicts)}）。"
        )
    ch_id = _chapter_id(number)
    if parsed["chapter"] and parsed["chapter"] != ch_id:
        errors.append(
            f"审稿文件 chapter={parsed['chapter']} 与目标 {ch_id} 不一致。"
        )
    if parsed["date"]:
        try:
            review_date = date.fromisoformat(parsed["date"])
        except ValueError:
            errors.append("审稿 date 必须使用 YYYY-MM-DD。")
        else:
            if review_date > datetime.now(timezone.utc).date():
                errors.append("审稿 date 不能是未来日期。")

    try:
        current_binding = _review_binding_for_book(book_dir, number, role)
    except BookProjectError as exc:
        return [*errors, str(exc)]
    if parsed["source_fingerprint"] != current_binding["source_fingerprint"]:
        errors.append(
            "审稿来源指纹与当前章节不一致；正文或规划材料已经变化，"
            "请重读全文后复审。"
        )
    binding_fields = [
        "chapter_sha256",
        "planning_sha256",
        "draft_mode",
        "generation_id",
    ]
    if number > 1 and role in SERIAL_REVIEW_ROLES:
        binding_fields.append("previous_chapter_sha256")
    for field in binding_fields:
        if parsed[field] != current_binding[field]:
            errors.append(
                f"审稿字段 {field} 与当前章节不一致，请基于当前材料重新审稿。"
            )

    generation = None
    if parsed["generation_id"] != "unrecorded":
        try:
            generation, _ = _validate_current_generation(
                root,
                book_dir,
                number,
                parsed["generation_id"],
                parsed["draft_mode"],
            )
        except NovelForgeError as exc:
            errors.append(str(exc))

    if role in {"blind-reader", "consistency-guard", "chapter-editor"}:
        evidence_quote = parsed["evidence_quote"]
        if not evidence_quote:
            errors.append(f"{role} 关键审稿缺少 evidence_quote。")
        else:
            chapter_text = find_chapter_file(
                book_dir, number
            ).read_text(encoding="utf-8-sig")
            if evidence_quote not in chapter_text:
                errors.append(
                    f"{role} 的 evidence_quote 未在当前正文中找到。"
                )
    if number > 1 and role in SERIAL_REVIEW_ROLES:
        previous_quote = parsed["previous_chapter_quote"]
        if not previous_quote:
            errors.append(f"{role} 缺少 previous_chapter_quote。")
        else:
            previous_text = find_chapter_file(
                book_dir, number - 1
            ).read_text(encoding="utf-8-sig")
            if previous_quote not in previous_text:
                errors.append(
                    f"{role} 的 previous_chapter_quote 未在上一章正文中找到。"
                )
    if role in {"blind-reader", "chapter-editor"}:
        substantive_fields = (
            BLIND_RECONSTRUCTION_FIELDS
            if role == "blind-reader"
            else EDITORIAL_DIMENSION_FIELDS
        )
        missing_substantive = [
            field
            for field in substantive_fields
            if not parsed.get(field)
            or parsed[field].strip() in {"-", "null", "unknown", "待填写"}
        ]
        if missing_substantive:
            errors.append(
                f"{role} 缺少实质审稿字段："
                + "、".join(missing_substantive)
            )
        for field in (
            "reviewer_type",
            "reviewer_id",
            "review_session_id",
            "provider",
            "model",
            "context_scope",
        ):
            if not parsed[field]:
                errors.append(f"关键审稿缺少来源字段：{field}")
        if role == "blind-reader" and parsed["context_scope"] not in {
            "prose_only",
            "simulated_blind",
        }:
            errors.append(
                "blind-reader 的 context_scope 必须是 prose_only "
                "或 simulated_blind。"
            )
        if (
            role == "blind-reader"
            and parsed["verdict"] == "pass"
            and parsed["context_scope"] == "simulated_blind"
        ):
            errors.append(
                "simulated_blind 只能记录诊断性 needs_revision，不能作为 pass。"
            )
        if (
            role == "blind-reader"
            and parsed["verdict"] == "pass"
            and parsed["human_likeness"] != "convincing"
        ):
            errors.append(
                "blind-reader 通过时 human_likeness 必须是 convincing；"
                "uncertain/synthetic 应给 needs_revision。"
            )
        if role == "blind-reader" and parsed["verdict"] == "pass":
            if parsed["reader_desire"] != "continue":
                errors.append(
                    "blind-reader 通过时 reader_desire 必须是 continue；"
                    "conditional/stop 应给 needs_revision。"
                )
            missing_pull = [
                field
                for field in BLIND_READER_PULL_FIELDS
                if not parsed.get(field)
                or parsed[field].strip().lower()
                in {"-", "null", "unknown", "待填写"}
            ]
            if missing_pull:
                errors.append(
                    "blind-reader pass 缺少读者追读证据："
                    + "、".join(missing_pull)
                )
        if generation is not None:
            same_origin = (
                parsed["provider"] == generation.data["provider"]
                and parsed["model"] == generation.data["model"]
            )
            if same_origin and not parsed["independence_note"]:
                errors.append(
                    "同 provider/model 的关键审稿必须填写 independence_note；"
                    "角色名不同不等于独立评审。"
                )
            if role == "blind-reader" and parsed["verdict"] == "pass":
                writer_session = str(generation.data.get("run_id") or "").strip()
                review_session = str(
                    parsed.get("review_session_id") or ""
                ).strip()
                if writer_session.lower() in {"", "unknown", "unrecorded"}:
                    errors.append(
                        "blind-reader pass 要求 generation 记录真实 run_id，"
                        "不能使用 unknown。"
                    )
                elif review_session == writer_session:
                    errors.append(
                        "blind-reader pass 必须来自不同于写作 run_id 的独立会话。"
                    )
    return errors


def _future_chapter_reference_errors(
    text: str,
    number: int,
    role: str,
) -> list[str]:
    referenced = {
        int(match)
        for match in re.findall(
            r"(?i)(?<![A-Za-z0-9_])ch-?0*(\d+)(?![A-Za-z0-9_])",
            text,
        )
    }
    future = sorted(chapter for chapter in referenced if chapter > number)
    if future:
        return [
            f"{role} 审稿引用了未来章节："
            + "、".join(f"ch{chapter:02d}" for chapter in future)
        ]
    if role == "blind-reader":
        other = sorted(chapter for chapter in referenced if chapter != number)
        if other:
            return ["blind-reader 只能引用当前章正文，不能引用其他章节。"]
    return []


def list_reviews(book_dir: Path, ch_id: str | None = None) -> list[dict[str, Any]]:
    reviews_dir = book_dir / "reviews"
    out: list[dict[str, Any]] = []
    if not reviews_dir.is_dir():
        return out
    for path in sorted(reviews_dir.glob("ch*-*.md")):
        if path.name == "review-template.md":
            continue
        m = re.match(r"(ch\d+)-(.+)\.md", path.name)
        if not m:
            continue
        if ch_id and m.group(1) != ch_id:
            continue
        review_text = path.read_text(encoding="utf-8-sig")
        parsed = parse_review(review_text)
        parsed["file"] = f"reviews/{path.name}"
        parsed["role"] = parsed["role"] or m.group(2)
        valid_verdicts = (
            EDITORIAL_VERDICTS
            if parsed["role"] == "chapter-editor"
            else REVIEW_VERDICTS
        )
        parsed["verdict_valid"] = parsed["verdict"] in valid_verdicts
        try:
            number = int(m.group(1).removeprefix("ch"))
            current_binding = _review_binding_for_book(
                book_dir, number, parsed["role"]
            )
            parsed["stale"] = (
                parsed["source_fingerprint"]
                != current_binding["source_fingerprint"]
            )
            validation_errors = _review_validation_errors(
                book_dir.parents[1],
                book_dir,
                number,
                parsed["role"],
                parsed,
            )
            validation_errors.extend(
                _future_chapter_reference_errors(
                    review_text,
                    number,
                    parsed["role"],
                )
            )
        except (BookProjectError, ValueError):
            parsed["stale"] = True
            validation_errors = ["无法解析或绑定审稿章节。"]
        parsed["validation_errors"] = validation_errors
        parsed["validation_valid"] = not validation_errors
        parsed["same_provider_model_as_generation"] = False
        parsed["independent"] = None
        parsed["session_isolated"] = None
        generation_id = parsed.get("generation_id")
        if generation_id and generation_id != "unrecorded":
            try:
                generation, _ = find_evidence_record(
                    book_dir.parents[1], book_dir.name, generation_id
                )
                same_origin = (
                    generation.kind == "generation"
                    and bool(parsed.get("provider"))
                    and bool(parsed.get("model"))
                    and parsed.get("provider") == generation.data["provider"]
                    and parsed.get("model") == generation.data["model"]
                )
                parsed["same_provider_model_as_generation"] = same_origin
                if parsed.get("provider") and parsed.get("model"):
                    parsed["independent"] = not same_origin
                writer_session = str(
                    generation.data.get("run_id") or ""
                ).strip()
                review_session = str(
                    parsed.get("review_session_id") or ""
                ).strip()
                if (
                    writer_session.lower()
                    not in {"", "unknown", "unrecorded"}
                    and review_session
                ):
                    parsed["session_isolated"] = (
                        writer_session != review_session
                    )
            except NovelForgeError:
                parsed["stale"] = True
        out.append(parsed)
    return out


def record_review(
    root: Path, slug: str, number: int, role: str, review_file: Path
) -> dict[str, Any]:
    book_dir = book_dir_for(root, slug)
    if role not in REVIEW_ROLES:
        raise BookProjectError(
            f"未知审稿角色：{role!r}；合法角色：{', '.join(REVIEW_ROLES)}"
        )
    review_file = Path(review_file)
    if not review_file.is_absolute():
        raise BookProjectError("--file 必须是绝对路径。")
    if not review_file.exists():
        raise BookProjectError(f"审稿文件不存在：{review_file}")
    try:
        text = review_file.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BookProjectError(f"审稿文件不是有效 UTF-8：{review_file} ({exc})")

    parsed = parse_review(text)
    validation_errors = _review_validation_errors(
        root, book_dir, number, role, parsed
    )
    validation_errors.extend(
        _future_chapter_reference_errors(text, number, role)
    )
    if validation_errors:
        raise BookProjectError(validation_errors[0])

    ch_id = _chapter_id(number)
    target = book_dir / "reviews" / _review_filename(ch_id, role)
    target.parent.mkdir(parents=True, exist_ok=True)
    # The review may already sit at its canonical location (reviewers write
    # directly into reviews/); only copy when source and target differ.
    if review_file.resolve() != target.resolve():
        shutil.copyfile(review_file, target)

    state = REVIEW_STATE_FOR_ROLE[role]
    when = _now()
    state_path, state_text, _ = _read_chapter_state(book_dir, number)
    state_text = _update_state_row(
        state_text, state, f"reviews/{target.name}", parsed["verdict"], when
    )
    state_text = _set_fields(state_text, updated_at=when)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state_text, encoding="utf-8")

    return {
        "review_file": f"reviews/{target.name}",
        "role": role,
        "verdict": parsed["verdict"],
        "must_open": parsed["must_open"],
        "stale": False,
        "chapter_state": f"planning/chapter-state/{ch_id}.md",
        "state": state,
    }


def _runtime_audit_errors(
    book_dir: Path, generation: dict[str, Any]
) -> list[str]:
    """Validate externally observed runtime evidence for one generation."""
    if generation.get("writer_type") == "human":
        return []
    run_id = str(generation.get("run_id") or "").strip()
    if run_id.lower() in {"", "unknown", "unrecorded"}:
        return ["generation.run_id 未绑定真实 Harness 会话。"]
    try:
        audit = find_runtime_audit(book_dir, run_id)
    except SessionAuditError as exc:
        return [str(exc)]
    errors: list[str] = []
    generation_id = str(generation.get("id") or "").strip()
    audit_generation_ids = audit.get("generation_record_ids")
    if (
        not generation_id
        or audit_generation_ids != [generation_id]
    ):
        errors.append(
            "一章 runtime audit 只能绑定当前 generation；"
            f"expected={[generation_id] if generation_id else 'missing-id'}，"
            f"actual={audit_generation_ids!r}。"
        )
    if audit.get("scope_chapter_count") != 1:
        errors.append("formal runtime audit 的 scope_chapter_count 必须为 1。")
    if audit["budget"]["continue_allowed"] is not True:
        errors.append("外部会话预算已超限，continue_allowed=false。")
    elif audit["budget"].get("status") != "within_budget":
        errors.append(
            "formal runtime audit 缺少请求数、缓存输入或最大上下文的完整观测。"
        )
    mismatches = compare_generation_provenance(generation, audit)
    recorded_mismatches = audit.get("provenance_mismatches", [])
    mismatch_fields = sorted(
        {
            str(item.get("field"))
            for item in [*mismatches, *recorded_mismatches]
            if isinstance(item, dict) and item.get("field")
        }
    )
    if mismatch_fields:
        errors.append("外部来源与 generation 不一致：" + "、".join(mismatch_fields))
    mutation_fields = (
        "draft_write_count",
        "draft_edit_count",
        "review_call_count",
    )
    missing_metrics = [
        field
        for field in mutation_fields
        if not isinstance(generation.get(field), int)
        or isinstance(generation.get(field), bool)
    ]
    if missing_metrics:
        errors.append(
            "formal generation 缺少运行计数："
            + "、".join(missing_metrics)
        )
    else:
        draft_mutations = (
            generation["draft_write_count"]
            + generation["draft_edit_count"]
        )
        if draft_mutations > MAX_DRAFT_MUTATIONS_PER_CHAPTER:
            errors.append(
                "draft-mutation-budget 超限："
                f"actual={draft_mutations}，"
                f"limit={MAX_DRAFT_MUTATIONS_PER_CHAPTER}。"
            )
        if generation["review_call_count"] > MAX_REVIEW_CALLS_PER_CHAPTER:
            errors.append(
                "review-call-budget 超限："
                f"actual={generation['review_call_count']}，"
                f"limit={MAX_REVIEW_CALLS_PER_CHAPTER}。"
            )
    chapter = generation.get("chapter")
    if isinstance(chapter, int) and not isinstance(chapter, bool):
        from .guardian import guardian_receipt_errors

        errors.extend(
            guardian_receipt_errors(book_dir, chapter, generation)
        )
    return errors


def _writer_session_reuse_groups(
    root: Path, slug: str
) -> list[dict[str, Any]]:
    """Return writer run IDs reused across more than one chapter."""
    metrics = evidence_status(root, slug, None)["generation_metrics"]
    sessions: dict[str, set[int]] = {}
    record_ids: dict[str, list[str]] = {}
    for generation in metrics:
        run_id = str(generation.get("run_id") or "").strip()
        chapter = generation.get("chapter")
        if (
            run_id.lower() in {"", "unknown", "unrecorded"}
            or not isinstance(chapter, int)
            or isinstance(chapter, bool)
        ):
            continue
        sessions.setdefault(run_id, set()).add(chapter)
        record_ids.setdefault(run_id, []).append(str(generation["id"]))
    return [
        {
            "run_id": run_id,
            "chapters": sorted(chapters),
            "record_ids": sorted(record_ids[run_id]),
        }
        for run_id, chapters in sorted(sessions.items())
        if len(chapters) > 1
    ]


def advance_state(
    root: Path,
    slug: str,
    number: int,
    to_state: str,
    evidence: str | None = None,
    next_action: str | None = None,
) -> dict[str, Any]:
    book_dir = book_dir_for(root, slug)
    if to_state != STATE_BLOCKED and to_state not in CHAPTER_STATES:
        raise BookProjectError(
            f"未知状态：{to_state!r}；合法状态：{', '.join(CHAPTER_STATES)} / {STATE_BLOCKED}"
        )
    ch_id = _chapter_id(number)
    when = _now()
    state_path, state_text, _ = _read_chapter_state(book_dir, number)
    current = parse_chapter_state(state_text)

    if to_state == "surface_checked":
        gates = run_gates(root, slug, number)
        if gates["quality"]["blocking"]:
            codes = ", ".join(
                sorted(
                    {
                        finding["rule_code"]
                        for finding in gates["quality"]["findings"]
                        if finding["severity"] == "blocking"
                    }
                )
            )
            raise BookProjectError(
                f"surface gate 仍有 blocking：{codes}；不得启动后续审稿。"
            )
        if gates["literary"]["blocking"]:
            codes = ", ".join(
                finding["code"]
                for finding in gates["literary"]["blocking"]
            )
            raise BookProjectError(
                f"serial literary gate 仍有 blocking：{codes}；"
                "不得启动后续审稿。"
            )

    if to_state == "ready":
        from .planning_spec import READY_REQUIRED_REVIEWS

        if current["draft_mode"] != "formal":
            raise BookProjectError(
                f"{current['draft_mode']} 稿属于非 formal 模式，不能进入 ready；"
                "请切换为 formal 并重跑全部正式门禁。"
            )
        audit = evidence_status(root, slug, number)
        if audit["arc_audit_due"] and not audit["arc_audit_satisfied"]:
            raise BookProjectError(
                "checkpoint chapter requires a current arc audit with open_must=0."
            )
        if current["generation_id"] == "unrecorded":
            raise BookProjectError(
                "进入 ready 前必须记录并绑定本章 generation evidence。"
            )
        generation, _ = _validate_current_generation(
            root,
            book_dir,
            number,
            current["generation_id"],
            current["draft_mode"],
        )
        reused_session = next(
            (
                group
                for group in _writer_session_reuse_groups(root, slug)
                if group["run_id"] == generation.data.get("run_id")
            ),
            None,
        )
        if reused_session is not None:
            raise BookProjectError(
                "进入 ready 前写作 run_id 必须一章一会话；"
                f"{reused_session['run_id']} 同时绑定章节 "
                + "、".join(
                    f"ch{chapter:02d}"
                    for chapter in reused_session["chapters"]
                )
                + "。"
            )
        reviews = {r["role"]: r for r in list_reviews(book_dir, ch_id)}
        missing = [
            f"{role} verdict={required_verdict}"
            for role, required_verdict in READY_REQUIRED_REVIEWS
            if reviews.get(role, {}).get("verdict") != required_verdict
            or reviews.get(role, {}).get("stale", True)
            or not reviews.get(role, {}).get("validation_valid", False)
        ]
        if missing:
            raise BookProjectError(
                "进入 ready 的前置证据缺失：" + "；".join(missing)
            )
        blind_review = reviews.get("blind-reader", {})
        if blind_review.get("session_isolated") is not True:
            raise BookProjectError(
                "进入 ready 前 blind-reader 必须绑定不同于写作 run_id 的独立会话。"
            )
        runtime_errors = _runtime_audit_errors(book_dir, generation.data)
        if runtime_errors:
            raise BookProjectError(
                "进入 ready 前外部 runtime audit 未通过：" + runtime_errors[0]
            )
        gates = run_gates(root, slug, number, expected_mode="formal")
        if (
            gates["quality"]["blocking"]
            or gates["narrative"]["blocking"]
            or gates["literary"]["blocking"]
        ):
            raise BookProjectError("进入 ready 前 formal gate 仍有 blocking。")
        placeholder_values = {"", "-", "null", "unknown", "待填写"}
        evidence_rows = {
            row["state"]: row for row in current["evidence"]
        }
        placeholder_states = [
            state
            for state in CHAPTER_STATES[1:-1]
            if state not in evidence_rows
            or evidence_rows[state]["evidence"].strip().lower()
            in placeholder_values
        ]
        if placeholder_states:
            raise BookProjectError(
                "进入 ready 前仍有占位证据："
                + "、".join(placeholder_states)
            )
        if evidence is None or evidence.strip().lower() in placeholder_values:
            raise BookProjectError("进入 ready 必须提供非占位 evidence 指针。")

    from_state = current["status"] or "planned"
    if (
        to_state != STATE_BLOCKED
        and from_state != STATE_BLOCKED
        and from_state in CHAPTER_STATES
        and to_state in CHAPTER_STATES
    ):
        from_index = CHAPTER_STATES.index(from_state)
        to_index = CHAPTER_STATES.index(to_state)
        expected = FORWARD_STATE_TRANSITIONS.get(from_state)
        if to_index > from_index and to_state != expected:
            raise BookProjectError(
                f"非法状态迁移：{from_state} → {to_state}；"
                f"下一合法状态为 {expected or '无'}。"
            )
    existing_row = next(
        (
            row
            for row in current["evidence"]
            if row["state"] == to_state
            and row["evidence"].strip().lower()
            not in {"", "-", "null", "unknown", "待填写"}
        ),
        None,
    )
    if evidence is not None or existing_row is None:
        state_text = _update_state_row(
            state_text, to_state, evidence or "-", "advanced", when
        )
    fields: dict[str, str] = {"status": to_state, "updated_at": when}
    if next_action is not None:
        fields["next_action"] = next_action
    state_text = _set_fields(state_text, **fields)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state_text, encoding="utf-8")
    result = {
        "chapter_state": f"planning/chapter-state/{ch_id}.md",
        "from": from_state,
        "to": to_state,
        "author_approval": False,
        "publication_eligibility": False,
    }
    if to_state == "ready":
        tag = None
        if number % 5 == 0:
            start = number - 4
            tag = f"checkpoint/ch{start:02d}-ch{number:02d}"
        result["local_git"] = _local_git_checkpoint(
            root,
            slug,
            f"chapter: {ch_id} ready",
            tag=tag,
        )
    return result


def set_draft_mode(
    root: Path, slug: str, number: int, mode: str
) -> dict[str, Any]:
    """Persist the chapter gate mode; changing it invalidates bound reviews."""
    if mode not in DRAFT_MODES:
        raise BookProjectError(
            f"未知稿件模式：{mode!r}；合法模式：{', '.join(DRAFT_MODES)}"
        )
    book_dir = book_dir_for(root, slug)
    state_path, state_text, _ = _read_chapter_state(book_dir, number)
    current = parse_chapter_state(state_text)
    when = _now()
    state_text = _set_fields(
        state_text,
        draft_mode=mode,
        updated_at=when,
        status="planned" if current["draft_mode"] != mode else current["status"],
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state_text, encoding="utf-8")
    return {
        "chapter_state": state_path.relative_to(book_dir).as_posix(),
        "from": current["draft_mode"],
        "to": mode,
        "reviews_invalidated": current["draft_mode"] != mode,
    }


def bind_generation(
    root: Path, slug: str, number: int, generation_id: str
) -> dict[str, Any]:
    """Bind one recorded generation evidence item to a chapter state."""
    book_dir = book_dir_for(root, slug)
    state_path, state_text, _ = _read_chapter_state(book_dir, number)
    current = parse_chapter_state(state_text)
    _, path = _validate_current_generation(
        root, book_dir, number, generation_id, current["draft_mode"]
    )
    when = _now()
    state_text = _set_fields(
        state_text,
        generation_id=generation_id,
        updated_at=when,
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state_text, encoding="utf-8")
    return {
        "chapter_state": state_path.relative_to(book_dir).as_posix(),
        "generation_id": generation_id,
        "evidence_path": path.relative_to(book_dir).as_posix(),
        "local_git": _local_git_checkpoint(
            root,
            slug,
            f"chapter: {_chapter_id(number)} draft",
        ),
    }


# --- status / gates -----------------------------------------------------------


def project_status(root: Path, slug: str, number: int | None) -> dict[str, Any]:
    book_dir = book_dir_for(root, slug)
    info = _parse_claude_md(book_dir)
    data: dict[str, Any] = {
        "slug": slug,
        "title": info.get("title"),
        "genre": info.get("genre"),
        "progress": info.get("progress"),
        "book_dir": str(book_dir),
        "author_approval": False,
        "publication_eligibility": False,
    }
    try:
        data["local_git"] = book_git_status(root, slug)
    except BookGitError as exc:
        data["local_git"] = {
            "initialized": False,
            "error": str(exc),
        }
    state_dir = book_dir / "planning" / "chapter-state"
    chapter_numbers: set[int] = set()
    if state_dir.is_dir():
        for path in state_dir.glob("ch*.md"):
            match = re.fullmatch(r"ch(\d+)", path.stem)
            if match:
                chapter_numbers.add(int(match.group(1)))
    chapters_dir = book_dir / "chapters"
    if chapters_dir.is_dir():
        for path in chapters_dir.glob("e*/ch-*/正文.md"):
            match = re.fullmatch(r"ch-(\d+)", path.parent.name)
            if match:
                chapter_numbers.add(int(match.group(1)))
    serial_chapter_numbers = {
        chapter_number
        for chapter_number in chapter_numbers
        if number is None or chapter_number <= number
    }
    if number is not None:
        chapter_numbers = {number} if number in chapter_numbers else set()

    chapters: list[dict[str, Any]] = []
    integrity_blockers: list[dict[str, Any]] = []
    integrity_warnings: list[dict[str, Any]] = []

    def _issue(
        target: list[dict[str, Any]],
        chapter_number: int,
        code: str,
        detail: str,
    ) -> None:
        target.append(
            {
                "chapter": _chapter_id(chapter_number),
                "code": code,
                "detail": detail,
            }
        )

    for chapter_number in sorted(chapter_numbers):
        state_path, state_text, missing_state = _read_chapter_state(
            book_dir, chapter_number
        )
        parsed = parse_chapter_state(state_text)
        parsed["chapter"] = _chapter_id(chapter_number)
        parsed["state_file"] = state_path.relative_to(book_dir).as_posix()
        parsed["missing_chapter_state"] = missing_state
        parsed["generation_stale"] = False
        chapter_file: Path | None = None
        try:
            chapter_file = find_chapter_file(book_dir, chapter_number)
        except BookProjectError:
            pass
        parsed["chapter_file"] = (
            chapter_file.relative_to(book_dir).as_posix()
            if chapter_file
            else None
        )
        if missing_state:
            _issue(
                integrity_blockers,
                chapter_number,
                "missing_chapter_state",
                "正文或章节编号存在，但缺少 planning/chapter-state 状态文件。",
            )
        if chapter_file and (parsed["status"] or "planned") == "planned":
            _issue(
                integrity_blockers,
                chapter_number,
                "content_present_while_planned",
                "正文已经存在，但章节状态仍为 planned。",
            )
        if chapter_file and parsed["generation_id"] == "unrecorded":
            _issue(
                integrity_warnings,
                chapter_number,
                "generation_unrecorded",
                "正文存在但尚未绑定 generation evidence。",
            )
        if parsed["generation_id"] != "unrecorded":
            try:
                _validate_current_generation(
                    root,
                    book_dir,
                    chapter_number,
                    parsed["generation_id"],
                    parsed["draft_mode"],
                )
            except NovelForgeError:
                parsed["generation_stale"] = True
                _issue(
                    integrity_blockers,
                    chapter_number,
                    "generation_stale",
                    "绑定的 generation 与当前正文、模式或路径不一致。",
                )
        if any(
            row["state"] != "planned" and row["evidence"] in {"", "-"}
            for row in parsed["evidence"]
        ):
            _issue(
                (
                    integrity_blockers
                    if parsed["status"] == "ready"
                    and parsed["draft_mode"] == "formal"
                    else integrity_warnings
                ),
                chapter_number,
                "placeholder_state_evidence",
                "已推进状态仍使用空值或 '-' 作为证据指针。",
            )
        if chapter_file and parsed["status"] == "ready":
            try:
                current_gates = run_gates(root, slug, chapter_number)
            except BookProjectError as exc:
                _issue(
                    integrity_blockers,
                    chapter_number,
                    "ready_gate_unverifiable",
                    f"ready 章节无法复核当前门禁：{exc}",
                )
            else:
                quality_blocking = current_gates["quality"]["blocking"]
                narrative_blocking = len(
                    current_gates["narrative"]["blocking"]
                )
                literary_blocking = len(
                    current_gates["literary"]["blocking"]
                )
                if quality_blocking or narrative_blocking or literary_blocking:
                    _issue(
                        integrity_blockers,
                        chapter_number,
                        "ready_with_blocking_gates",
                        "章节状态为 ready，但当前门禁已失效："
                        f"quality blocking={quality_blocking}，"
                        f"narrative blocking={narrative_blocking}，"
                        f"literary blocking={literary_blocking}。",
                    )
        chapters.append(parsed)

    if number is not None:
        chapter_file: Path | None = None
        try:
            chapter_file = find_chapter_file(book_dir, number)
        except BookProjectError:
            pass
        data["chapter_file"] = (
            chapter_file.relative_to(book_dir).as_posix() if chapter_file else None
        )
        if chapter_file:
            from .lint import _count_cjk_chars

            data["cjk"] = _count_cjk_chars(
                chapter_file.read_text(encoding="utf-8-sig")
            )
    data["chapters"] = chapters
    data["reviews"] = list_reviews(
        book_dir, _chapter_id(number) if number is not None else None
    )
    duplicate_review_artifacts: list[str] = []
    reviews_dir = book_dir / "reviews"
    if reviews_dir.is_dir():
        for path in sorted(reviews_dir.rglob("*.md")):
            if path.parent == reviews_dir:
                continue
            relative = path.relative_to(reviews_dir)
            chapter_match = next(
                (
                    re.fullmatch(r"ch-?(\d+)", part)
                    for part in relative.parts
                    if re.fullmatch(r"ch-?(\d+)", part)
                ),
                None,
            )
            if chapter_match is None:
                continue
            review_number = int(chapter_match.group(1))
            if number is not None and review_number != number:
                continue
            role = re.sub(r"^ch\d+-", "", path.stem)
            if role not in REVIEW_ROLES:
                continue
            artifact = f"reviews/{relative.as_posix()}"
            duplicate_review_artifacts.append(artifact)
            _issue(
                integrity_warnings,
                review_number,
                "duplicate_review_artifact",
                f"{artifact} 位于非权威嵌套目录；"
                "审稿唯一入口应为 reviews/chXX-<role>.md。",
            )
    for review in data["reviews"]:
        try:
            review_number = int(review["chapter"].removeprefix("ch"))
        except (AttributeError, ValueError):
            review_number = number or 0
        if not review.get("verdict_valid", False):
            _issue(
                integrity_blockers,
                review_number,
                "invalid_review_verdict",
                f"{review['file']} 的 verdict 不是该角色允许的标准值。",
            )
        if not review.get("validation_valid", False):
            _issue(
                integrity_blockers,
                review_number,
                "invalid_review_record",
                f"{review['file']} 未通过完整审稿校验："
                + "；".join(review.get("validation_errors", [])),
            )
        if review.get("stale"):
            _issue(
                integrity_warnings,
                review_number,
                "stale_review",
                f"{review['file']} 未绑定当前正文与规划。",
            )
    data["review_warnings"] = [
        {
            "role": review["role"],
            "warning": "same_provider_model_as_generation",
        }
        for review in data["reviews"]
        if review.get("same_provider_model_as_generation")
    ]
    current_reviews = [
        review
        for review in data["reviews"]
        if not review.get("stale")
        and review.get("verdict_valid")
        and review.get("validation_valid")
    ]
    independent_values = [
        review.get("independent")
        for review in current_reviews
        if review.get("independent") is not None
    ]
    if not independent_values:
        review_confidence = "unassessed"
    elif all(independent_values):
        review_confidence = "independent"
    elif not any(independent_values):
        review_confidence = "single_origin"
    else:
        review_confidence = "mixed_origin"
    critical = {review["role"]: review for review in current_reviews}
    benchmark_requirements = {
        "blind-reader": "pass",
        "chapter-editor": "ready_for_editor_decision",
    }
    benchmark_missing = [
        role
        for role, verdict in benchmark_requirements.items()
        if critical.get(role, {}).get("verdict") != verdict
        or critical.get(role, {}).get("independent") is not True
        or (
            role == "blind-reader"
            and critical.get(role, {}).get("session_isolated") is not True
        )
    ]
    data["review_confidence"] = review_confidence
    if any(
        chapter["draft_mode"] == "degraded_exploration"
        for chapter in chapters
    ):
        benchmark_missing.append("degraded_exploration")
    if duplicate_review_artifacts:
        benchmark_missing.append("duplicate_review_artifact")
    data["duplicate_review_artifacts"] = duplicate_review_artifacts
    data["benchmark_eligible"] = not benchmark_missing
    data["benchmark_missing"] = benchmark_missing
    data["evidence"] = evidence_status(root, slug, number)
    runtime_budget = data["evidence"]["runtime_budget"]
    chapter_status_by_number = {
        int(chapter["chapter"].removeprefix("ch")): chapter["status"]
        for chapter in chapters
        if isinstance(chapter.get("chapter"), str)
        and chapter["chapter"].removeprefix("ch").isdigit()
    }
    for finding in runtime_budget["findings"]:
        target = (
            integrity_blockers
            if chapter_status_by_number.get(finding["chapter"]) == "ready"
            else integrity_warnings
        )
        _issue(
            target,
            finding["chapter"],
            finding["code"],
            f"运行预算超限：actual={finding['actual']}，limit={finding['limit']}。",
        )
    for reuse in _writer_session_reuse_groups(root, slug):
        for chapter_number in reuse["chapters"]:
            _issue(
                integrity_blockers,
                chapter_number,
                "writer_session_reused_across_chapters",
                f"写作 run_id={reuse['run_id']} 同时绑定 "
                + "、".join(
                    f"ch{chapter:02d}" for chapter in reuse["chapters"]
                )
                + "；正式工作流必须一章一原生会话。",
            )
    for cycle in data["evidence"]["generation_cycles"]:
        if cycle["review_cycle_status"] not in {
            "budget_exhausted",
            "budget_exceeded",
        }:
            continue
        target = (
            integrity_blockers
            if cycle["review_cycle_status"] == "budget_exceeded"
            else integrity_warnings
        )
        _issue(
            target,
            cycle["chapter"],
            cycle["review_cycle_status"],
            "自动 generation 预算已耗尽；下一次完整回炉需要明确人工决定。",
        )
    serial_inputs: list[tuple[str, str]] = []
    for chapter_number in sorted(serial_chapter_numbers):
        try:
            chapter_path = find_chapter_file(book_dir, chapter_number)
        except BookProjectError:
            continue
        serial_inputs.append(
            (
                _chapter_id(chapter_number),
                chapter_path.read_text(encoding="utf-8-sig"),
            )
        )
    voice_path = book_dir / "memory/voice-bible.md"
    voice_anchor_text = (
        voice_path.read_text(encoding="utf-8-sig")
        if voice_path.is_file()
        else None
    )
    data["literary_profile"] = (
        analyze_serial_style(
            serial_inputs,
            voice_anchor_text=voice_anchor_text,
        )
        if serial_inputs
        else {
            "chapters": [],
            "findings": [],
            "blocking": [],
            "human_likeness_risk": False,
        }
    )
    if data["literary_profile"]["blocking"]:
        target_chapter = (
            number
            if number is not None
            else max(serial_chapter_numbers, default=0)
        )
        for finding in data["literary_profile"]["blocking"]:
            _issue(
                integrity_blockers,
                target_chapter,
                finding["code"],
                finding["detail"],
            )
    for chapter in chapters:
        if chapter["generation_id"] == "unrecorded":
            continue
        try:
            generation, _ = find_evidence_record(
                root, slug, chapter["generation_id"]
            )
        except NovelForgeError:
            continue
        runtime_errors = _runtime_audit_errors(book_dir, generation.data)
        if not runtime_errors:
            continue
        try:
            chapter_number = int(chapter["chapter"].removeprefix("ch"))
        except (AttributeError, ValueError):
            chapter_number = number or 0
        target = (
            integrity_blockers
            if chapter["status"] == "ready"
            else integrity_warnings
        )
        _issue(
            target,
            chapter_number,
            "runtime_audit_invalid",
            "；".join(runtime_errors),
        )
    data["workflow_integrity"] = {
        "status": (
            "blocked"
            if integrity_blockers
            else "warning"
            if integrity_warnings
            else "clean"
        ),
        "blockers": integrity_blockers,
        "warnings": integrity_warnings,
    }
    return data


def run_gates(
    root: Path,
    slug: str,
    number: int,
    expected_mode: str | None = None,
) -> dict[str, Any]:
    book_dir = book_dir_for(root, slug)
    chapter_file = find_chapter_file(book_dir, number)
    _, state_text, _ = _read_chapter_state(book_dir, number)
    mode = parse_chapter_state(state_text)["draft_mode"]
    if expected_mode is not None and expected_mode != mode:
        raise BookProjectError(
            f"稿件模式不一致：chapter-state={mode}，命令断言={expected_mode}。"
        )
    package = book_dir / "planning" / f"scene-package-{_chapter_id(number)}.md"
    findings = lint_file(chapter_file)
    quality = {
        "blocking": sum(1 for f in findings if f.severity == "blocking"),
        "advisory": sum(1 for f in findings if f.severity != "blocking"),
        "findings": [
            {
                "rule_code": f.rule_code,
                "severity": f.severity,
                "line_number": f.line_number,
                "message": f.message,
                "evidence": f.evidence,
            }
            for f in findings
        ],
    }
    result: dict[str, Any] = {
        "chapter": _chapter_id(number),
        "mode": mode,
        "chapter_file": chapter_file.relative_to(book_dir).as_posix(),
        "cjk": next(
            (f.char_count for f in findings if f.char_count is not None), None
        ),
        "quality": quality,
    }
    if package.exists() or mode != "formal":
        result["narrative"] = book_gates.narrative_report(
            chapter_file, package, mode=mode
        )
    else:
        result["narrative"] = {
            "blocking": [f"缺少场景包：planning/scene-package-{_chapter_id(number)}.md"],
            "advisory": [],
        }
    serial_inputs: list[tuple[str, str]] = []
    for chapter_number in range(1, number + 1):
        try:
            path = find_chapter_file(book_dir, chapter_number)
        except BookProjectError:
            continue
        serial_inputs.append(
            (
                _chapter_id(chapter_number),
                path.read_text(encoding="utf-8-sig"),
            )
        )
    voice_path = book_dir / "memory/voice-bible.md"
    voice_anchor_text = (
        voice_path.read_text(encoding="utf-8-sig")
        if voice_path.is_file()
        else None
    )
    result["literary"] = analyze_serial_style(
        serial_inputs,
        voice_anchor_text=voice_anchor_text,
    )
    result["ready_eligible"] = (
        mode == "formal"
        and quality["blocking"] == 0
        and not result["narrative"]["blocking"]
        and not result["literary"]["blocking"]
    )
    result["author_approval"] = False
    result["publication_eligibility"] = False
    return result


# --- sync-tools ----------------------------------------------------------------


def sync_tools(root: Path, slug: str, dry_run: bool = False) -> dict[str, Any]:
    book_dir = book_dir_for(root, slug)
    info = _parse_claude_md(book_dir)
    title = info.get("title") or slug
    genre = info.get("genre")
    if not genre:
        raise BookProjectError(
            f"无法从 {book_dir}/CLAUDE.md 解析“- 类型:”行，无法渲染模板。"
        )
    templates = render_templates(slug, title, genre)

    for rel_dir in REQUIRED_DIRECTORIES:
        (book_dir / rel_dir).mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    updated: list[str] = []
    identical: list[str] = []
    preserved: list[str] = []
    migrated_states: list[str] = []
    migratable_project_files = {
        "CLAUDE.md": re.compile(
            r"(?m)^-\s*(?:\*\*)?工作流版本(?:\*\*)?\s*:\s*"
            r"(?:v3\.(?:7|8|9)|v4\.(?:0|1|2|3|4))(?:\s|（|\()"
        ),
        "README.md": re.compile(
            r"(?m)^-\s*默认工作流\s*:\s*"
            r"(?:v3\.(?:7|8|9)|v4\.(?:0|1|2|3|4))(?:$|[\s；;。])"
        ),
    }
    refresh_set = (
        set(SYNCABLE_FILES)
        | set(CREATE_ONLY_FILES)
        | set(migratable_project_files)
        | {"memory/voice-bible.md"}
    )
    for rel in sorted(refresh_set):
        content = templates.get(rel)
        if content is None:
            continue
        target = book_dir / rel
        if not target.exists():
            created.append(rel)
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            continue
        if rel == "memory/voice-bible.md" or rel in CREATE_ONLY_FILES:
            # Hand-maintained project assets are only created when missing.
            identical.append(rel)
            continue
        existing = target.read_text(encoding="utf-8-sig")
        if rel in migratable_project_files:
            if migratable_project_files[rel].search(existing) is None:
                if existing == content:
                    identical.append(rel)
                else:
                    preserved.append(rel)
                continue
        if existing == content:
            identical.append(rel)
        else:
            updated.append(rel)
            if not dry_run:
                target.write_text(content, encoding="utf-8")
    legacy_state_map = {
        "action_drafted": "scene_packaged",
        "dialogue_planned": "scene_packaged",
        "causal_reviewed": "surface_checked",
        "line_reviewed": "surface_checked",
        "texture_reviewed": "surface_checked",
        "consistency_checked": "surface_checked",
    }
    state_dir = book_dir / "planning/chapter-state"
    if state_dir.is_dir():
        for state_path in sorted(state_dir.glob("ch*.md")):
            state_text = state_path.read_text(encoding="utf-8-sig")
            old_status = parse_chapter_state(state_text)["status"]
            new_status = legacy_state_map.get(old_status or "")
            if new_status is None:
                continue
            relative = state_path.relative_to(book_dir).as_posix()
            migrated_states.append(relative)
            if not dry_run:
                state_path.write_text(
                    _set_fields(
                        state_text,
                        status=new_status,
                        updated_at=_now(),
                        next_action=(
                            "v4.5 migration: continue from "
                            f"{new_status}"
                        ),
                    ),
                    encoding="utf-8",
                )
    if dry_run:
        try:
            local_git = book_git_status(root, slug)
        except BookGitError:
            local_git = {"initialized": False, "planned": True}
    else:
        try:
            local_git = book_git_status(root, slug)
        except BookGitError:
            local_git = initialize_book_git(root, slug, title)
    return {
        "dry_run": dry_run,
        "created": created,
        "updated": updated,
        "identical": identical,
        "preserved": preserved,
        "migrated_states": migrated_states,
        "local_git": local_git,
    }
