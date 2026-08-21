"""Character arc ledger helpers (docs/46 B2).

Arc ledgers live at ``planning/arcs/<角色名>.md`` and are author-maintained
Markdown. Python only reads them: a bounded digest flows into writer handoffs
and planning context so character change stays continuous across chapters.
Writers never write arc files; there is no candidate/promotion machinery —
planning/ is already the author-owned single source.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ARCS_DIRECTORY = "planning/arcs"
ARC_TEMPLATE_NAME = "_template.md"
ARC_POSITION_SECTION = "当前位置"
ARC_BEATS_SECTION = "弧线刻度"

ARC_DIGEST_MAX_CHARS = 1_200

_TABLE_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|")


def arc_files(book_dir: Path) -> list[Path]:
    directory = book_dir / ARCS_DIRECTORY
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob("*.md")
        if path.name != ARC_TEMPLATE_NAME
    )


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def parse_arc_position(text: str) -> str:
    """Return the 当前位置 body's first meaningful line, or empty string."""
    body = _section(text, ARC_POSITION_SECTION)
    for line in body.splitlines():
        stripped = line.strip().lstrip("-* ").strip()
        stripped = re.sub(r"^-\s*", "", stripped).strip()
        value = stripped.split("：", 1)[-1].strip()
        if value and set(value) != {"_"}:
            return value[:80]
    return ""


def parse_arc_beats(text: str) -> list[dict[str, Any]]:
    """Parse 弧线刻度 table rows that name a chapter."""
    beats: list[dict[str, Any]] = []
    body = _section(text, ARC_BEATS_SECTION)
    for line in body.splitlines():
        match = _TABLE_ROW_RE.match(line.strip())
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        chapter_cell = cells[1]
        chapter_match = re.search(r"\d+", chapter_cell)
        beats.append(
            {
                "index": int(match.group(1)),
                "chapter": (
                    f"ch{int(chapter_match.group()):02d}"
                    if chapter_match
                    else ""
                ),
                "event": cells[2][:48],
                "belief_shift": cells[3][:48],
                "cost": cells[4][:32],
            }
        )
    return beats


def arc_digest(book_dir: Path, max_chars: int = ARC_DIGEST_MAX_CHARS) -> str:
    """Bounded cross-chapter summary of all arc ledgers for writer context."""
    blocks: list[str] = []
    for path in arc_files(book_dir):
        text = path.read_text(encoding="utf-8-sig")
        position = parse_arc_position(text)
        beats = parse_arc_beats(text)
        lines = [f"- {path.stem}："]
        if position:
            lines.append(f"  当前位置：{position}")
        if beats:
            latest = beats[-1]
            lines.append(
                f"  最近刻度：{latest['chapter'] or '未标章'} "
                f"{latest['event']}（{latest['belief_shift']}）"
            )
            lines.append(f"  已记刻度 {len(beats)} 格。")
        if len(lines) > 1:
            blocks.append("\n".join(lines))
    if not blocks:
        return ""
    digest = "## 人物弧线（跨章变化，只读）\n\n" + "\n".join(blocks)
    return digest[:max_chars]
