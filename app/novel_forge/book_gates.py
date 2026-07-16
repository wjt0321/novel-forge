"""Canonical narrative/material gates for the `books/<slug>/` workflow.

The per-book `tools/narrative_gate.py` is a thin shell that delegates here,
so every book always runs the current checks. All functions are pure and
return plain data; `narrative_gate_main` is the CLI adapter used by the
shell script.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from .planning_spec import (
    BEAT_CHAIN_SECTION,
    MATERIAL_WAIVER_MARK,
    MIN_BEATS,
    MIN_CHAPTER_PARAGRAPHS,
    PLACEHOLDER_TOKENS,
    SCENE_PACKAGE_REQUIRED_SECTIONS,
    TABLE_HEADER_CELLS,
)


def section(text: str, heading: str) -> str | None:
    """Return the body of a `## <heading>` section, or None if absent."""
    found = re.search(
        rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE
    )
    return found.group(1) if found else None


def _meaningful(value: str) -> bool:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL).strip()
    if not value or value in PLACEHOLDER_TOKENS:
        return False
    # Runs of underscores are template blanks ("________").
    if re.fullmatch(r"_+", value):
        return False
    return True


def table_rows(text: str) -> int:
    """Count non-header, non-empty data rows across Markdown tables.

    The first content row of each table is treated as its header. Rows whose
    cells are all in TABLE_HEADER_CELLS are also treated as headers.
    """
    rows = 0
    seen_header = False
    for line in text.splitlines():
        if not line.startswith("|"):
            seen_header = False
            continue
        if re.fullmatch(r"[| :\-]+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not any(_meaningful(cell) for cell in cells):
            continue
        if all(cell in TABLE_HEADER_CELLS for cell in cells):
            seen_header = True
            continue
        if not seen_header:
            seen_header = True
            continue
        rows += 1
    return rows


def section_has_content(body: str) -> bool:
    if table_rows(body) > 0:
        return True
    for line in body.splitlines():
        if line.startswith("|"):
            continue
        stripped = line.strip()
        # Blockquote lines are template guidance, not content.
        if stripped.startswith(">"):
            continue
        value = re.sub(r"^\s*[-*]\s*", "", stripped).replace("**", "").strip()
        # A Markdown field label ending in ':' is not a filled field.
        if not value or re.fullmatch(r"[^:：]+[:：]", value):
            continue
        if _meaningful(value):
            return True
    return False


def _material_filled(text: str) -> bool:
    """A memory/planning material file counts as filled when its template
    blanks have been replaced (or carry an explicit waiver mark outside of
    guidance blockquotes)."""
    lines = [l for l in text.splitlines() if not l.strip().startswith(">")]
    body = "\n".join(lines)
    if MATERIAL_WAIVER_MARK in body:
        return True
    # Unreplaced template blanks ("__________") mean the file is untouched.
    if re.search(r"_{3,}", body):
        return False
    # Wholly empty table cells ("|  |  |") mean the table was never filled.
    # Checked per line: `\s` would also match the newline between two adjacent
    # table rows and false-flag every proper Markdown table.
    if any(re.search(r"\|[ \t]*\|", line) for line in body.splitlines()):
        return False
    stripped = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    stripped = re.sub(r"^#.*$", "", stripped, flags=re.MULTILINE)
    meaningful_chars = 0
    for line in stripped.splitlines():
        value = re.sub(r"^\s*[-*|]\s*", "", line).replace("**", "").strip()
        value = re.sub(r"[|\-:：\s]", "", value)
        if value and value not in PLACEHOLDER_TOKENS:
            meaningful_chars += len(re.findall(r"[\u4e00-\u9fff0-9A-Za-z]", value))
    return meaningful_chars >= 20


def _chapter_number(chapter_path: Path, package_path: Path) -> int | None:
    for name in (package_path.name, chapter_path.parent.name, chapter_path.name):
        m = re.search(r"ch-?(\d+)", name)
        if m:
            return int(m.group(1))
    return None


def check_scene_package(package_text: str, ledger_text: str | None) -> list[str]:
    """Blocking problems in the scene package (and dialogue ledger)."""
    blocking: list[str] = []
    for heading in SCENE_PACKAGE_REQUIRED_SECTIONS:
        body = section(package_text, heading)
        if body is None or not section_has_content(body):
            blocking.append(f"scene-package 缺少或未填写章节：{heading}")
    beats = section(package_text, BEAT_CHAIN_SECTION)
    if beats is None or table_rows(beats) < MIN_BEATS:
        blocking.append(f"Beat 因果链少于 {MIN_BEATS} 个可执行 beat")
    if (
        ledger_text is not None
        and re.search(r"本场景是否有关键对白：\s*是", ledger_text)
        and table_rows(ledger_text) < 1
    ):
        blocking.append("关键对白账本未填写")
    return blocking


def check_chapter_text(chapter_text: str) -> list[str]:
    """Blocking problems in the chapter body itself."""
    paragraphs = [
        p
        for p in re.split(r"\n\s*\n", chapter_text)
        if p.strip() and not p.lstrip().startswith("#")
    ]
    if len(paragraphs) < MIN_CHAPTER_PARAGRAPHS:
        return ["正文段落不足，无法验证场景推进"]
    return []


def check_project_materials(
    project_root: Path, chapter_number: int | None
) -> tuple[list[str], list[str]]:
    """Book-level material gates: worldbuilding / research boundaries must be
    filled or explicitly waived; voice-bible is advisory for ch01 and blocking
    (with a filled exemplar) from ch02 onwards."""
    blocking: list[str] = []
    advisory: list[str] = []
    for rel in ("memory/worldbuilding.md", "planning/research-boundaries.md"):
        path = project_root / rel
        if not path.exists():
            blocking.append(f"缺少材料文件：{rel}")
        elif not _material_filled(path.read_text(encoding="utf-8-sig")):
            blocking.append(
                f"{rel} 未填写；请填写世界规则/事实红线，或显式标注“{MATERIAL_WAIVER_MARK}”"
            )
    voice = project_root / "memory" / "voice-bible.md"
    first_chapter = chapter_number in (None, 1)
    if not voice.exists():
        message = "memory/voice-bible.md 不存在；请建立本书声音圣经"
        (advisory if first_chapter else blocking).append(message)
    else:
        body = section(voice.read_text(encoding="utf-8-sig"), "exemplar_notes")
        exemplar_filled = body is not None and section_has_content(body)
        if not exemplar_filled and not first_chapter:
            blocking.append(
                "voice-bible 的 exemplar_notes 未填写；第 2 章起必须以本书已写章节的一段正文作为范文锚定"
            )
        elif not exemplar_filled:
            advisory.append("voice-bible 的 exemplar_notes 未填写（第 2 章起为 blocking）")
    return blocking, advisory


def _derive_project_root(chapter_path: Path) -> Path:
    """Locate the book project root by walking up for its CLAUDE.md marker.

    Falls back to the standard `chapters/eXX/ch-XX/正文.md` depth when no
    marker is found (e.g. ad-hoc files in tests).
    """
    resolved = chapter_path.resolve()
    for ancestor in resolved.parents:
        if (ancestor / "CLAUDE.md").exists() and (ancestor / "planning").is_dir():
            return ancestor
    return resolved.parents[3]


def narrative_report(chapter_path: Path, package_path: Path) -> dict[str, Any]:
    """Full narrative gate result for one chapter."""
    chapter = chapter_path.read_text(encoding="utf-8-sig")
    package = package_path.read_text(encoding="utf-8-sig")
    ledger_path = package_path.with_name(
        package_path.name.replace("scene-package-", "dialogue-ledger-")
    )
    ledger = (
        ledger_path.read_text(encoding="utf-8-sig") if ledger_path.exists() else None
    )
    blocking = check_scene_package(package, ledger)
    blocking.extend(check_chapter_text(chapter))
    if ledger is None:
        advisory = [f"对白账本不存在（如本章无关键对白可忽略）：{ledger_path.name}"]
    else:
        advisory = []
    project_root = _derive_project_root(chapter_path)
    chapter_number = _chapter_number(chapter_path, package_path)
    mat_blocking, mat_advisory = check_project_materials(project_root, chapter_number)
    blocking.extend(mat_blocking)
    advisory.extend(mat_advisory)
    return {"blocking": blocking, "advisory": advisory}


def narrative_gate_main(argv: list[str] | None = None) -> int:
    """CLI used by the per-book thin shell `tools/narrative_gate.py`."""
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print(
            "Usage: python tools/narrative_gate.py <chapter.md> <scene-package.md>",
            file=sys.stderr,
        )
        return 2
    chapter_path, package_path = map(Path, argv)
    if not chapter_path.exists() or not package_path.exists():
        print("Chapter or scene package not found.", file=sys.stderr)
        return 2
    report = narrative_report(chapter_path, package_path)
    blocking, advisory = report["blocking"], report["advisory"]
    print(f"Blocking: {len(blocking)}, Advisory: {len(advisory)}")
    for item in blocking:
        print(f"BLOCKING: {item}")
    for item in advisory:
        print(f"ADVISORY: {item}")
    return 1 if blocking else 0
