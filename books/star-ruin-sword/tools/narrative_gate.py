"""Narrative gate for a chapter and its scene package.

This is deliberately a structural gate, not a claim to score literary merit.
It rejects missing causal planning and reports lightweight prose signals that
must be reviewed by causal-editor and line-editor.

Usage:
    python tools/narrative_gate.py CHAPTER.md SCENE_PACKAGE.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def section_body(text: str, heading: str) -> str | None:
    match = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    return match.group(1) if match else None


def has_meaningful_text(value: str) -> bool:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL).strip()
    return bool(value) and value not in {"待填", "TODO", "TBD", "无"}


def nonempty_after(text: str, heading: str) -> bool:
    body = section_body(text, heading)
    if body is None:
        return False
    non_table_lines = [line.strip(" -\t") for line in body.splitlines() if not line.startswith("|")]
    return any(has_meaningful_text(line) for line in non_table_lines) or table_data_rows(body) > 0


def table_data_rows(text: str, heading: str | None = None) -> int:
    body = section_body(text, heading) if heading else text
    if body is None:
        return 0
    rows = 0
    for line in body.splitlines():
        if not line.startswith("|") or re.fullmatch(r"[| :\-]+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and any(has_meaningful_text(cell) for cell in cells) and not all(cell in {"#", "信息", "人物", "触发"} for cell in cells):
            rows += 1
    return max(0, rows - 1)


def paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip() and not part.lstrip().startswith("#")]


def normalized_terms(paragraph: str) -> set[str]:
    return {
        term for term in re.findall(r"[\u4e00-\u9fff]{2,8}", paragraph)
        if term not in {"第一章", "第二章", "说道", "一个", "没有", "什么", "时候", "已经"}
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        print("Usage: python tools/narrative_gate.py <chapter.md> <scene-package.md>", file=sys.stderr)
        return 2

    chapter_path, package_path = map(Path, argv)
    if not chapter_path.exists() or not package_path.exists():
        missing = chapter_path if not chapter_path.exists() else package_path
        print(f"File not found: {missing}", file=sys.stderr)
        return 2

    chapter = chapter_path.read_text(encoding="utf-8-sig")
    package = package_path.read_text(encoding="utf-8-sig")
    blocking: list[str] = []
    advisory: list[str] = []

    required_sections = ["1. 场景压力", "2. 在场者状态", "3. Beat 因果链", "4. 信息账本", "5. 信息预算"]
    for heading in required_sections:
        if not nonempty_after(package, heading):
            blocking.append(f"scene-package 缺少或未填写章节：{heading}")

    if table_data_rows(package, "3. Beat 因果链") < 2:
        blocking.append("Beat 因果链少于 2 个可执行 beat")
    if table_data_rows(package, "4. 信息账本") < 1:
        advisory.append("信息账本没有登记重点信息；确认本场景确实不引入需追踪的新信息")

    paras = paragraphs(chapter)
    if len(paras) < 3:
        blocking.append("正文段落不足，无法验证场景推进")

    for index, (left, right) in enumerate(zip(paras, paras[1:]), start=1):
        overlap = normalized_terms(left) & normalized_terms(right)
        if len(overlap) >= 4 and len(left) > 80 and len(right) > 80:
            advisory.append(f"相邻段 {index}-{index + 1} 共享较多词簇：{sorted(overlap)[:6]}；由 line-editor 判断是否为无后果重复")

    dialogue_lines = [line for line in chapter.splitlines() if '"' in line or '“' in line]
    unattributed = [line for line in dialogue_lines if not re.search(r"(说|问|答|道|喊|叫|声音|看着|抬手|转身|对着)", line)]
    if len(unattributed) >= 3:
        advisory.append(f"检测到 {len(unattributed)} 行可能缺少归属锚点的对白；请核对 dialogue ledger")

    ledger_path = package_path.with_name(package_path.name.replace("scene-package-", "dialogue-ledger-"))
    if ledger_path.exists():
        ledger = ledger_path.read_text(encoding="utf-8-sig")
        has_key_dialogue = bool(re.search(r"本场景是否有关键对白：\s*是", ledger))
        explicitly_no_dialogue = bool(re.search(r"本场景是否有关键对白：\s*否", ledger))
        if has_key_dialogue and table_data_rows(ledger) < 1:
            blocking.append(f"关键对白账本未填写：{ledger_path.name}")
        if dialogue_lines and explicitly_no_dialogue:
            advisory.append("正文含引号但对白账本声明无关键对白；由 line-editor 确认这些引号不是未登记的关键对白")
    elif dialogue_lines:
        advisory.append(f"正文含引号但未提供对白账本：{ledger_path.name}；由 line-editor 判断是否存在关键对白")

    print(f"Chapter: {chapter_path}")
    print(f"Scene package: {package_path}")
    print(f"Blocking: {len(blocking)}, Advisory: {len(advisory)}")
    for item in blocking:
        print(f"BLOCKING: {item}")
    for item in advisory:
        print(f"ADVISORY: {item}")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
