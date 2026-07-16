"""Structural narrative gate; it does not score literary quality.

Usage: python tools/narrative_gate.py CHAPTER.md SCENE_PACKAGE.md
"""
from __future__ import annotations
import re
import sys
from pathlib import Path


def _section(text: str, heading: str) -> str | None:
    found = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    return found.group(1) if found else None


def _meaningful(value: str) -> bool:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL).strip()
    return bool(value) and value not in {"待填", "TODO", "TBD", "无"}


def _rows(text: str) -> int:
    rows = 0
    for line in text.splitlines():
        if not line.startswith("|") or re.fullmatch(r"[| :\-]+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if any(_meaningful(cell) for cell in cells) and not all(cell in {"#", "信息", "人物", "触发"} for cell in cells):
            rows += 1
    return max(0, rows - 1)


def _section_has_content(body: str) -> bool:
    if _rows(body) > 0:
        return True
    for line in body.splitlines():
        if line.startswith("|"):
            continue
        value = re.sub(r"^\s*[-*]\s*", "", line).replace("**", "").strip()
        # A Markdown field label ending in ':' is not a filled field.
        if not value or re.fullmatch(r"[^:：]+[:：]", value):
            continue
        if _meaningful(value):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        print("Usage: python tools/narrative_gate.py <chapter.md> <scene-package.md>", file=sys.stderr)
        return 2
    chapter_path, package_path = map(Path, argv)
    if not chapter_path.exists() or not package_path.exists():
        print("Chapter or scene package not found.", file=sys.stderr)
        return 2
    chapter = chapter_path.read_text(encoding="utf-8-sig")
    package = package_path.read_text(encoding="utf-8-sig")
    blocking, advisory = [], []
    for heading in ["1. 场景压力", "2. 在场者状态", "3. Beat 因果链", "4. 信息账本", "5. 信息预算"]:
        body = _section(package, heading)
        if body is None or not _section_has_content(body):
            blocking.append(f"scene-package 缺少或未填写章节：{heading}")
    beats = _section(package, "3. Beat 因果链")
    if beats is None or _rows(beats) < 2:
        blocking.append("Beat 因果链少于 2 个可执行 beat")
    if len([p for p in re.split(r"\n\s*\n", chapter) if p.strip() and not p.lstrip().startswith("#")]) < 3:
        blocking.append("正文段落不足，无法验证场景推进")
    ledger_path = package_path.with_name(package_path.name.replace("scene-package-", "dialogue-ledger-"))
    if ledger_path.exists():
        ledger = ledger_path.read_text(encoding="utf-8-sig")
        if re.search(r"本场景是否有关键对白：\s*是", ledger) and _rows(ledger) < 1:
            blocking.append(f"关键对白账本未填写：{ledger_path.name}")
    print(f"Blocking: {len(blocking)}, Advisory: {len(advisory)}")
    for item in blocking: print(f"BLOCKING: {item}")
    for item in advisory: print(f"ADVISORY: {item}")
    return 1 if blocking else 0

if __name__ == "__main__":
    raise SystemExit(main())
