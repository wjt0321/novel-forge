"""Persistent one-chapter-per-session orchestration for books projects."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import book_project
from .book_evidence import find_evidence_record
from .book_memory import (
    build_context_packet,
    memory_status,
    rebuild_memory_index,
)
from .models import NovelForgeError
from .planning_spec import (
    DEFAULT_CHAPTERS_PER_SEQUENCE,
    MAX_CHAPTERS_PER_SEQUENCE,
    MAX_HANDOFF_MEMORY_CHARS,
    MAX_HANDOFF_PREVIOUS_TAIL_CHARS,
    MAX_HANDOFF_SCENE_PACKAGE_CHARS,
    MAX_HANDOFF_TOTAL_CHARS,
    MAX_HANDOFF_VOICE_EXEMPLAR_CHARS,
    WRITER_VISIBLE_SCENE_SECTIONS,
    render_literary_micro_rules,
)


CHAPTER_SEQUENCE_SCHEMA = "novel-forge-chapter-sequence/v1"
CHAPTER_SEQUENCE_DIRECTORY = Path("planning/chapter-sequences")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_WRITER_HIDDEN_STYLE_METRIC_RE = re.compile(
    r"(?:声音指纹|句长(?:均值|变异|方差|CV)|对白占比|比喻密度|"
    r"段内句数|微段落|问句率|感叹率|metric|per[_ -]?mille|"
    r"\d+(?:\.\d+)?\s*[%‰])",
    re.IGNORECASE,
)


class ChapterSequenceError(NovelForgeError):
    """Raised when a chapter sequence violates session or ready boundaries."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _sequence_path(book_dir: Path, sequence_id: str) -> Path:
    if not _SAFE_ID_RE.fullmatch(sequence_id):
        raise ChapterSequenceError(
            "sequence_id 只能包含字母、数字、点、下划线和连字符，"
            "长度不得超过 96。"
        )
    return book_dir / CHAPTER_SEQUENCE_DIRECTORY / f"{sequence_id}.json"


def _load_sequence(
    root: Path, slug: str, sequence_id: str
) -> tuple[Path, Path, dict[str, Any]]:
    book_dir = book_project.book_dir_for(root, slug)
    path = _sequence_path(book_dir, sequence_id)
    if not path.is_file():
        raise ChapterSequenceError(f"章节序列不存在：{sequence_id}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChapterSequenceError(
            f"章节序列 JSON 损坏：{path.relative_to(book_dir).as_posix()}"
        ) from exc
    if (
        not isinstance(record, dict)
        or record.get("schema") != CHAPTER_SEQUENCE_SCHEMA
        or record.get("sequence_id") != sequence_id
        or record.get("slug") != slug
    ):
        raise ChapterSequenceError(f"章节序列身份不合法：{sequence_id}")
    return book_dir, path, record


def _bounded(text: str, limit: int, *, tail: bool = False) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    if tail:
        return cleaned[-limit:].lstrip()
    return cleaned[:limit].rstrip()


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def _voice_excerpt(book_dir: Path, chapter: int) -> str:
    path = book_dir / "memory/voice-bible.md"
    if not path.is_file():
        raise ChapterSequenceError("缺少 memory/voice-bible.md。")
    text = path.read_text(encoding="utf-8-sig")
    exemplar = _section(text, "exemplar_notes")
    source = exemplar if exemplar else text
    safe_lines: list[str] = []
    in_code_fence = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not stripped:
            continue
        if set(stripped) == {"_"} or stripped.startswith("|"):
            continue
        if stripped.startswith("#"):
            continue
        if _WRITER_HIDDEN_STYLE_METRIC_RE.search(stripped):
            continue
        if stripped.startswith(">"):
            stripped = stripped[1:].strip()
        stripped = re.sub(r"^[-*]\s*", "", stripped).strip()
        if stripped:
            safe_lines.append(stripped)
    usable = "\n".join(safe_lines).strip()
    if chapter > 1 and not usable:
        raise ChapterSequenceError(
            "第 2 章起必须先在 Voice Bible 的 exemplar_notes "
            "填写本书声音范文，才能创建新 writer session。"
        )
    return _bounded(usable, MAX_HANDOFF_VOICE_EXEMPLAR_CHARS)


def _chapter_state(
    root: Path, slug: str, chapter: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    status = book_project.project_status(root, slug, chapter)
    row = next(
        (
            item
            for item in status.get("chapters", [])
            if item.get("chapter") == f"ch{chapter:02d}"
        ),
        None,
    )
    if row is None:
        raise ChapterSequenceError(f"第 {chapter:02d} 章没有章节状态。")
    return status, row


def _require_ready(
    root: Path, slug: str, chapter: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        status, state = _chapter_state(root, slug, chapter)
    except ChapterSequenceError as exc:
        raise ChapterSequenceError(
            f"第 {chapter:02d} 章尚未完整 ready；"
            "必须通过当前 generation、runtime、formal gates 与两角色审稿后"
            "才能创建下一章 session。"
        ) from exc
    blockers = status.get("workflow_integrity", {}).get("blockers", [])
    substantive_blockers = [
        item
        for item in blockers
        if item.get("code") != "ready_sequence_incomplete"
    ]
    if state.get("status") != "ready" or substantive_blockers:
        raise ChapterSequenceError(
            f"第 {chapter:02d} 章尚未完整 ready；"
            "必须通过当前 generation、runtime、formal gates 与两角色审稿后"
            "才能创建下一章 session。"
        )
    return status, state


def chapter_sequence_effective_for_chapter(
    root: Path,
    slug: str,
    chapter: int,
    generation_run_id: str | None,
) -> dict[str, Any]:
    """Reconcile a declared ready chapter with raw sequence completion data."""
    book_dir = book_project.book_dir_for(root, slug)
    directory = book_dir / CHAPTER_SEQUENCE_DIRECTORY
    candidates: list[dict[str, Any]] = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if (
                not isinstance(record, dict)
                or record.get("schema") != CHAPTER_SEQUENCE_SCHEMA
                or record.get("slug") != slug
                or chapter not in record.get("chapters", [])
            ):
                continue
            completed_sessions = record.get("completed_sessions")
            if not isinstance(completed_sessions, dict):
                completed_sessions = {}
            structurally_complete = (
                record.get("status") == "complete"
                and record.get("completed_chapters") == record.get("chapters")
                and record.get("current_index") == len(record.get("chapters", []))
                and record.get("active_session_id") is None
                and chapter in record.get("completed_chapters", [])
                and completed_sessions.get(str(chapter)) == generation_run_id
            )
            candidates.append(
                {
                    "sequence_id": record.get("sequence_id"),
                    "declared_status": record.get("status"),
                    "complete": structurally_complete,
                }
            )
    return {
        "effective_status": (
            "complete"
            if any(item["complete"] for item in candidates)
            else "inconsistent"
        ),
        "sequences": candidates,
    }


def _scene_package(book_dir: Path, chapter: int) -> tuple[Path, str]:
    path = book_dir / "planning" / f"scene-package-ch{chapter:02d}.md"
    if not path.is_file():
        raise ChapterSequenceError(
            f"缺少第 {chapter:02d} 章 scene package："
            f"planning/scene-package-ch{chapter:02d}.md"
        )
    source = path.read_text(encoding="utf-8-sig")
    sections: list[str] = []
    for heading in WRITER_VISIBLE_SCENE_SECTIONS:
        content = _section(source, heading)
        if content:
            sections.extend((f"## {heading}", content, ""))
    if not sections:
        raise ChapterSequenceError(
            f"第 {chapter:02d} 章 scene package 没有 Writer 可见的故事内容。"
        )
    brief = (
        "完整 Scene Package 是编辑控制面。以下只是后台故事义务，"
        "不得在正文中逐条证明；审计推理、替代解释和验证清单未传给 Writer。\n\n"
        + "\n".join(sections).strip()
    )
    return path, _bounded(brief, MAX_HANDOFF_SCENE_PACKAGE_CHARS)


def build_chapter_handoff(
    root: Path, slug: str, chapter: int
) -> dict[str, Any]:
    """Build a bounded, disposable handoff for exactly one writer session."""
    if chapter < 1:
        raise ChapterSequenceError("chapter 必须是正整数。")
    book_dir = book_project.book_dir_for(root, slug)
    if chapter > 1:
        _require_ready(root, slug, chapter - 1)

    if memory_status(root, slug)["state"] != "clean":
        rebuild_memory_index(root, slug)
    memory = build_context_packet(root, slug, chapter)
    memory_path = book_dir / memory["context_path"]
    memory_text = _bounded(
        memory_path.read_text(encoding="utf-8-sig"),
        MAX_HANDOFF_MEMORY_CHARS,
    )
    scene_path, scene_text = _scene_package(book_dir, chapter)
    voice_text = _voice_excerpt(book_dir, chapter)

    previous_lines = ["- 第 01 章无上一章正文。"]
    previous_sha256: str | None = None
    previous_path_text: str | None = None
    if chapter > 1:
        previous_path = book_project.find_chapter_file(book_dir, chapter - 1)
        previous_sha256 = _sha256(previous_path)
        previous_path_text = previous_path.relative_to(book_dir).as_posix()
        previous_tail = _bounded(
            previous_path.read_text(encoding="utf-8-sig"),
            MAX_HANDOFF_PREVIOUS_TAIL_CHARS,
            tail=True,
        )
        previous_lines = [
            f"- 上一章正文路径: `{previous_path_text}`",
            f"- 上一章正文 SHA-256: `{previous_sha256}`",
            "",
            "### 上一章末段",
            "",
            previous_tail,
        ]

    lines = [
        f"# 第 {chapter:02d} 章 Writer Handoff",
        "",
        "## 会话边界",
        "",
        f"- 本次 writer scope 仅限第 {chapter:02d} 章。",
        "- 必须使用新的原生 writer session；不得续用上一章 session。",
        "- 正文输出后立即停止角色工作；编排器完成 ready 后退役该 session 身份，"
        "再另行签发下一章。",
        "- 不加载旧会话消息、旧工具输出、旧审稿全文或其他书资产。",
        "- 2,000,000 cached-input tokens 是硬停止上限，不是目标额度。",
        "",
        "## 上一章交接",
        "",
        *previous_lines,
        "",
        "## 本书声音锚",
        "",
        "- 只学习叙事距离、信息释放和节奏功能。",
        "- 不得复用范文的具体名词、标志动作、章末物件或句法骨架。",
        "- Writer 不接收句长、段落、对白占比等数字目标；"
        "这些数字只供审稿诊断。",
        "- 正文默认 standard/medium；规划和疑难因果核验可用 high。",
        "- Max/长思考只处理被明确命名的困难问题，"
        "不得用于整章自由生成。",
        "",
        voice_text,
        "",
        "## Canon 与活跃承诺",
        "",
        memory_text,
        "",
        "## 当前章 Writer Story Brief",
        "",
        f"- 来源 Scene Package: `{scene_path.relative_to(book_dir).as_posix()}`",
        "",
        scene_text,
        "",
        "## 文学微规则",
        "",
        render_literary_micro_rules("writer"),
        "",
        "## 停止规则",
        "",
        "- 只完成本章正文。",
        "- 证据、审稿、状态与 ready 由编排器和独立角色处理；"
        "Writer 不得代做或等待期间越权补做。",
        "- 不提前起草下一章；下一章必须等待新的 launch directive。",
    ]
    text = "\n".join(lines).strip() + "\n"
    if len(text) > MAX_HANDOFF_TOTAL_CHARS:
        raise ChapterSequenceError(
            f"第 {chapter:02d} 章交接包超过 {MAX_HANDOFF_TOTAL_CHARS} 字符；"
            "请压缩 Canon、Voice exemplar 或 scene package。"
        )
    target = (
        book_dir / "memory/context-cache" / f"ch{chapter:02d}-handoff.md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {
        "chapter": chapter,
        "handoff_path": target.relative_to(book_dir).as_posix(),
        "handoff_sha256": _sha256(target),
        "handoff_chars": len(text),
        "memory_context_path": memory["context_path"],
        "previous_chapter_path": previous_path_text,
        "previous_chapter_sha256": previous_sha256,
    }


def _used_session_ids(root: Path) -> dict[str, str]:
    used: dict[str, str] = {}
    books = Path(root) / "books"
    if not books.is_dir():
        return used
    for path in books.glob("*/planning/chapter-sequences/*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        for session_id in record.get("used_session_ids", []):
            if isinstance(session_id, str) and session_id:
                used.setdefault(session_id, str(path))
    return used


def _active_overlap(
    book_dir: Path, chapters: list[int]
) -> str | None:
    requested = set(chapters)
    directory = book_dir / CHAPTER_SEQUENCE_DIRECTORY
    if not directory.is_dir():
        return None
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("status") == "complete":
            continue
        existing = {
            value
            for value in record.get("chapters", [])
            if isinstance(value, int)
        }
        if requested & existing:
            return str(record.get("sequence_id") or path.stem)
    return None


def _launch(record: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    chapter = record["chapters"][record["current_index"]]
    return {
        "launch_next_session": True,
        "chapter": chapter,
        "scope": {"chapter_count": 1},
        "new_native_session_required": True,
        "writer_session_must_end_after_ready": True,
        "previous_chapter_must_be_ready": chapter > 1,
        "handoff_path": handoff["handoff_path"],
        "handoff_sha256": handoff["handoff_sha256"],
        "handoff_chars": handoff["handoff_chars"],
        "forbidden_session_ids": list(record["used_session_ids"]),
        "claim_operation": (
            "claim-chapter-session "
            f"{record['slug']} {record['sequence_id']} "
            "--session-id <native-session-id>"
        ),
    }


def _public(record: dict[str, Any]) -> dict[str, Any]:
    current_index = record["current_index"]
    current_chapter = (
        record["chapters"][current_index]
        if current_index < len(record["chapters"])
        else None
    )
    data = {
        "schema": record["schema"],
        "sequence_id": record["sequence_id"],
        "slug": record["slug"],
        "start_chapter": record["start_chapter"],
        "chapter_count": record["chapter_count"],
        "chapters": list(record["chapters"]),
        "status": record["status"],
        "current_chapter": current_chapter,
        "active_session_id": record["active_session_id"],
        "used_session_ids": list(record["used_session_ids"]),
        "invalidated_session_count": len(
            record.get("invalidated_sessions", [])
        ),
        "completed_chapters": list(record["completed_chapters"]),
        "orchestrator_run_id": record.get("orchestrator_run_id"),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "author_approval": False,
        "publication_eligibility": False,
    }
    if record["status"] == "awaiting_session" and current_chapter is not None:
        handoff = record["handoffs"][str(current_chapter)]
        data["launch"] = _launch(record, handoff)
    else:
        data["launch"] = {"launch_next_session": False}
    return data


def begin_chapter_sequence(
    root: Path,
    slug: str,
    start_chapter: int,
    chapter_count: int = DEFAULT_CHAPTERS_PER_SEQUENCE,
    *,
    sequence_id: str | None = None,
    orchestrator_run_id: str | None = None,
) -> dict[str, Any]:
    """Create a sequential batch and issue only its first chapter launch."""
    if start_chapter < 1:
        raise ChapterSequenceError("start_chapter 必须是正整数。")
    if not isinstance(chapter_count, int) or isinstance(chapter_count, bool):
        raise ChapterSequenceError("chapter_count 必须是整数。")
    if chapter_count < 1 or chapter_count > MAX_CHAPTERS_PER_SEQUENCE:
        raise ChapterSequenceError(
            f"单次自动章节序列只能包含 1 至 {MAX_CHAPTERS_PER_SEQUENCE} 章；"
            f"最多 {MAX_CHAPTERS_PER_SEQUENCE} 章，五章及以上必须拆分。"
        )
    book_dir = book_project.book_dir_for(root, slug)
    chapters = list(range(start_chapter, start_chapter + chapter_count))
    if start_chapter > 1:
        _require_ready(root, slug, start_chapter - 1)
    overlap = _active_overlap(book_dir, chapters)
    if overlap:
        raise ChapterSequenceError(
            f"章节范围已被未完成序列 {overlap} 占用。"
        )
    sequence_id = sequence_id or (
        f"seq-{start_chapter:02d}-{uuid.uuid4().hex[:12]}"
    )
    path = _sequence_path(book_dir, sequence_id)
    if path.exists():
        raise ChapterSequenceError(f"章节序列已存在：{sequence_id}")

    handoff = build_chapter_handoff(root, slug, start_chapter)
    now = _now()
    record: dict[str, Any] = {
        "schema": CHAPTER_SEQUENCE_SCHEMA,
        "sequence_id": sequence_id,
        "slug": slug,
        "start_chapter": start_chapter,
        "chapter_count": chapter_count,
        "chapters": chapters,
        "status": "awaiting_session",
        "current_index": 0,
        "active_session_id": None,
        "used_session_ids": [],
        "invalidated_sessions": [],
        "completed_sessions": {},
        "completed_chapters": [],
        "orchestrator_run_id": (
            orchestrator_run_id.strip() if orchestrator_run_id else None
        ),
        "handoffs": {str(start_chapter): handoff},
        "created_at": now,
        "updated_at": now,
    }
    _atomic_json(path, record)
    return _public(record)


def claim_chapter_session(
    root: Path,
    slug: str,
    sequence_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Bind the current chapter to a real, globally unused native session."""
    session_id = session_id.strip()
    if not session_id:
        raise ChapterSequenceError("session_id 不能为空。")
    _, path, record = _load_sequence(root, slug, sequence_id)
    if record["status"] == "complete":
        raise ChapterSequenceError("章节序列已经完成，不能再 claim session。")
    if record["status"] == "running":
        if record["active_session_id"] == session_id:
            return _public(record)
        raise ChapterSequenceError(
            "当前章节已经绑定另一原生 writer session。"
        )
    if record["status"] != "awaiting_session":
        raise ChapterSequenceError(
            f"章节序列状态 {record['status']} 不能 claim session。"
        )
    used = _used_session_ids(root)
    if session_id in used:
        raise ChapterSequenceError(
            f"原生 writer session {session_id} 已被使用；"
            "每章必须创建新的 session。"
        )
    record["active_session_id"] = session_id
    record["used_session_ids"].append(session_id)
    record["status"] = "running"
    record["updated_at"] = _now()
    _atomic_json(path, record)
    return _public(record)


def advance_chapter_sequence(
    root: Path,
    slug: str,
    sequence_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Complete the active chapter and issue the next fresh-session launch."""
    book_dir, path, record = _load_sequence(root, slug, sequence_id)
    if record["status"] != "running":
        raise ChapterSequenceError(
            "只有已 claim 且正在运行的章节序列可以推进。"
        )
    if record["active_session_id"] != session_id:
        raise ChapterSequenceError(
            "session_id 与当前章节绑定的原生 writer session 不一致。"
        )
    chapter = record["chapters"][record["current_index"]]
    _, state = _require_ready(root, slug, chapter)
    generation_id = state.get("generation_id")
    if not generation_id or generation_id == "unrecorded":
        raise ChapterSequenceError("ready 章节缺少 generation 绑定。")
    generation, _ = find_evidence_record(root, slug, generation_id)
    if generation.data.get("run_id") != session_id:
        raise ChapterSequenceError(
            "ready generation.run_id 与章节序列 claim 的 writer session "
            "不一致。"
        )

    record["completed_chapters"].append(chapter)
    record.setdefault("completed_sessions", {})[str(chapter)] = session_id
    record["active_session_id"] = None
    record["current_index"] += 1
    if record["current_index"] >= len(record["chapters"]):
        record["status"] = "complete"
    else:
        next_chapter = record["chapters"][record["current_index"]]
        # Re-check the exact prior chapter at handoff build time. This also
        # captures its final body hash after all reviews and patches.
        handoff = build_chapter_handoff(root, slug, next_chapter)
        record["handoffs"][str(next_chapter)] = handoff
        record["status"] = "awaiting_session"
    record["updated_at"] = _now()
    _atomic_json(path, record)
    return _public(record)


def invalidate_chapter_session(
    root: Path,
    slug: str,
    sequence_id: str,
    session_id: str,
    *,
    reason: str,
) -> dict[str, Any]:
    """Invalidate a compromised writer session and require a fresh claim."""
    reason = reason.strip()
    if not reason:
        raise ChapterSequenceError("session invalidation reason 不能为空。")
    _, path, record = _load_sequence(root, slug, sequence_id)
    if record.get("status") != "running":
        raise ChapterSequenceError(
            "只有正在运行的章节 session 可以失效。"
        )
    if record.get("active_session_id") != session_id:
        raise ChapterSequenceError(
            "session_id 与当前章节绑定的原生 writer session 不一致。"
        )
    chapter = record["chapters"][record["current_index"]]
    record.setdefault("invalidated_sessions", []).append(
        {
            "session_id": session_id,
            "chapter": chapter,
            "reason": reason,
            "invalidated_at": _now(),
        }
    )
    record["active_session_id"] = None
    record["status"] = "awaiting_session"
    record["updated_at"] = _now()
    _atomic_json(path, record)
    return _public(record)


def rotate_chapter_session(
    root: Path,
    slug: str,
    sequence_id: str,
    session_id: str,
    *,
    reason: str = "consolidated_patch_required",
) -> dict[str, Any]:
    """Retire a valid writer after review and require a fresh patch session."""
    reason = reason.strip()
    if not reason:
        raise ChapterSequenceError("session rotation reason 不能为空。")
    _, path, record = _load_sequence(root, slug, sequence_id)
    if record.get("status") != "running":
        raise ChapterSequenceError("只有正在运行的章节 session 可以轮换。")
    if record.get("active_session_id") != session_id:
        raise ChapterSequenceError(
            "session_id 与当前章节绑定的原生 writer session 不一致。"
        )
    chapter = record["chapters"][record["current_index"]]
    record.setdefault("retired_sessions", []).append(
        {
            "session_id": session_id,
            "chapter": chapter,
            "reason": reason,
            "retired_at": _now(),
        }
    )
    record["active_session_id"] = None
    record["status"] = "awaiting_session"
    record["updated_at"] = _now()
    _atomic_json(path, record)
    return _public(record)


def chapter_sequence_status(
    root: Path, slug: str, sequence_id: str
) -> dict[str, Any]:
    """Return sequence metadata and a launch directive without prose bodies."""
    _, _, record = _load_sequence(root, slug, sequence_id)
    findings: list[str] = []
    status = record.get("status")
    if status not in {"awaiting_session", "running", "complete"}:
        findings.append(f"未知章节序列状态：{status}")
    if status == "complete":
        chapters = list(record.get("chapters", []))
        completed = list(record.get("completed_chapters", []))
        sessions = list(record.get("used_session_ids", []))
        completed_sessions = record.get("completed_sessions")
        if not isinstance(completed_sessions, dict):
            completed_sessions = {}
        if (
            not completed_sessions
            and not record.get("invalidated_sessions")
            and len(sessions) == len(chapters)
        ):
            completed_sessions = {
                str(chapter): sessions[index]
                for index, chapter in enumerate(chapters)
            }
        if completed != chapters:
            findings.append("complete 序列的 completed_chapters 与 chapters 不一致")
        if record.get("current_index") != len(chapters):
            findings.append("complete 序列的 current_index 未越过最后一章")
        if record.get("active_session_id") is not None:
            findings.append("complete 序列仍绑定 active_session_id")
        for index, chapter in enumerate(chapters):
            try:
                _, state = _require_ready(root, slug, chapter)
                generation_id = state.get("generation_id")
                generation, _ = find_evidence_record(
                    root,
                    slug,
                    generation_id,
                )
            except NovelForgeError as exc:
                findings.append(
                    f"第 {chapter:02d} 章无法证明 ready：{exc}"
                )
                continue
            completed_session = completed_sessions.get(str(chapter))
            if not isinstance(completed_session, str) or not completed_session:
                findings.append(
                    f"第 {chapter:02d} 章缺少成功 writer session 绑定"
                )
                continue
            if generation.data.get("run_id") != completed_session:
                findings.append(
                    f"第 {chapter:02d} 章 generation.run_id "
                    "与序列 writer session 不一致"
                )
    data = _public(record)
    data["integrity"] = {
        "status": "blocked" if findings else "clean",
        "findings": findings,
    }
    data["effective_status"] = "inconsistent" if findings else status
    return data
