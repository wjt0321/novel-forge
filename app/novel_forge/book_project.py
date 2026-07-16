"""Operations on the `books/<slug>/` front-of-house workflow (no database).

These functions power the skill adapter's book-project ops
(`project-status`, `run-gates`, `record-review`, `advance-state`,
`sync-tools`). They only read/write Markdown and run the canonical gates;
they never return chapter prose, never touch `data/`, and never perform git
mutations (that stays in `autonomous.git_checkpoint`).
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import book_gates
from .lint import lint_file
from .models import NovelForgeError
from .planning_spec import (
    CHAPTER_STATES,
    EDITORIAL_VERDICTS,
    PASSING_VERDICTS,
    REVIEW_ROLES,
    REVIEW_STATE_FOR_ROLE,
    REVIEW_VERDICTS,
    STATE_BLOCKED,
)
from .project_templates import (
    REQUIRED_DIRECTORIES,
    SYNCABLE_FILES,
    _planning_chapter_state_template_md,
    render_templates,
)


class BookProjectError(NovelForgeError):
    """Raised for books/<slug>/ project-level problems."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def book_dir_for(root: Path, slug: str) -> Path:
    book_dir = Path(root) / "books" / slug
    if not book_dir.is_dir():
        raise BookProjectError(f"books/ 项目不存在：{book_dir}")
    return book_dir


def _chapter_id(number: int) -> str:
    return f"ch{number:02d}"


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


def _review_filename(ch_id: str, role: str) -> str:
    return f"{ch_id}-{role}.md"


def parse_review(text: str) -> dict[str, Any]:
    def _field(name: str) -> str | None:
        m = re.search(rf"^-\s*{re.escape(name)}:\s*(\S+)\s*$", text, re.MULTILINE)
        return m.group(1).strip() if m else None

    must_open = 0
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if "must" in cells and ("open" in cells or "" in cells):
            must_open += 1
    return {
        "chapter": _field("chapter"),
        "role": _field("role"),
        "verdict": _field("verdict"),
        "date": _field("date"),
        "must_open": must_open,
    }


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
        parsed = parse_review(path.read_text(encoding="utf-8-sig"))
        parsed["file"] = f"reviews/{path.name}"
        parsed["role"] = parsed["role"] or m.group(2)
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
    if parsed["role"] and parsed["role"] != role:
        raise BookProjectError(
            f"审稿文件 role={parsed['role']} 与参数 {role} 不一致。"
        )
    valid_verdicts = EDITORIAL_VERDICTS if role == "chapter-editor" else REVIEW_VERDICTS
    if parsed["verdict"] not in valid_verdicts:
        raise BookProjectError(
            f"审稿文件缺少合法 verdict（{role} 允许：{', '.join(valid_verdicts)}）。"
        )
    ch_id = _chapter_id(number)
    if parsed["chapter"] and parsed["chapter"] != ch_id:
        raise BookProjectError(
            f"审稿文件 chapter={parsed['chapter']} 与目标 {ch_id} 不一致。"
        )

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
    fields = {"updated_at": when}
    current = parse_chapter_state(state_text)
    if current["status"] in (None, "", "planned") or current["status"] in CHAPTER_STATES:
        # Reviews move the chapter to the role's mapped state when that is a
        # forward step; regressions stay explicit via advance-state.
        cur_idx = (
            CHAPTER_STATES.index(current["status"])
            if current["status"] in CHAPTER_STATES
            else -1
        )
        if cur_idx < CHAPTER_STATES.index(state):
            fields["status"] = state
    state_text = _set_fields(state_text, **fields)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state_text, encoding="utf-8")

    return {
        "review_file": f"reviews/{target.name}",
        "role": role,
        "verdict": parsed["verdict"],
        "must_open": parsed["must_open"],
        "chapter_state": f"planning/chapter-state/{ch_id}.md",
        "state": state,
    }


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

    if to_state == "ready":
        from .planning_spec import READY_REQUIRED_REVIEWS

        reviews = {r["role"]: r for r in list_reviews(book_dir, ch_id)}
        missing = [
            f"{role} verdict={required_verdict}"
            for role, required_verdict in READY_REQUIRED_REVIEWS
            if reviews.get(role, {}).get("verdict") != required_verdict
        ]
        if missing:
            raise BookProjectError(
                "进入 ready 的前置证据缺失：" + "；".join(missing)
            )

    state_path, state_text, _ = _read_chapter_state(book_dir, number)
    current = parse_chapter_state(state_text)
    from_state = current["status"] or "planned"
    state_text = _update_state_row(
        state_text, to_state, evidence or "-", "advanced", when
    )
    fields: dict[str, str] = {"status": to_state, "updated_at": when}
    if next_action is not None:
        fields["next_action"] = next_action
    state_text = _set_fields(state_text, **fields)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state_text, encoding="utf-8")
    return {
        "chapter_state": f"planning/chapter-state/{ch_id}.md",
        "from": from_state,
        "to": to_state,
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
    }
    state_dir = book_dir / "planning" / "chapter-state"
    chapters: list[dict[str, Any]] = []
    if state_dir.is_dir():
        for path in sorted(state_dir.glob("ch*.md")):
            parsed = parse_chapter_state(path.read_text(encoding="utf-8-sig"))
            parsed["chapter"] = path.stem
            chapters.append(parsed)
    if number is not None:
        ch_id = _chapter_id(number)
        chapters = [c for c in chapters if c["chapter"] == ch_id]
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
    return data


def run_gates(root: Path, slug: str, number: int) -> dict[str, Any]:
    book_dir = book_dir_for(root, slug)
    chapter_file = find_chapter_file(book_dir, number)
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
        "chapter_file": chapter_file.relative_to(book_dir).as_posix(),
        "cjk": next(
            (f.char_count for f in findings if f.char_count is not None), None
        ),
        "quality": quality,
    }
    if package.exists():
        result["narrative"] = book_gates.narrative_report(chapter_file, package)
    else:
        result["narrative"] = {
            "blocking": [f"缺少场景包：planning/scene-package-{_chapter_id(number)}.md"],
            "advisory": [],
        }
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
    refresh_set = set(SYNCABLE_FILES) | {"memory/voice-bible.md"}
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
        if rel == "memory/voice-bible.md":
            # Voice Bible is hand-maintained per book; never overwrite.
            identical.append(rel)
            continue
        existing = target.read_text(encoding="utf-8-sig")
        if existing == content:
            identical.append(rel)
        else:
            updated.append(rel)
            if not dry_run:
                target.write_text(content, encoding="utf-8")
    return {
        "dry_run": dry_run,
        "created": created,
        "updated": updated,
        "identical": identical,
    }
