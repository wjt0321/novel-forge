"""Canonical narrative/material gates for the `books/<slug>/` workflow.

The per-book `tools/narrative_gate.py` is a thin shell that delegates here,
so every book always runs the current checks. All functions are pure and
return plain data; `narrative_gate_main` is the CLI adapter used by the
shell script.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

from .planning_spec import (
    BEAT_CHAIN_SECTION,
    CAUSAL_RESPONSIBILITY_SECTION,
    CHAPTER_HANDOFF_FIELDS,
    CHAPTER_HANDOFF_SECTION,
    CHAPTER_HANDOFF_TRANSITIONS,
    COGNITION_LEDGER_SECTION,
    DECISION_QUESTION_FIELDS,
    DECISION_QUESTION_SECTION,
    DRAFT_MODES,
    EXPERTISE_AUDIT_SECTION,
    MATERIAL_WAIVER_MARK,
    MIN_ACTIVE_DECISION_QUESTIONS,
    MIN_BEATS,
    MIN_CAUSAL_RESPONSIBILITY_ROWS,
    MIN_CHAPTER_PARAGRAPHS,
    MIN_FORMAL_CJK,
    PLANNING_FALSIFICATION_FIELDS,
    PLANNING_FALSIFICATION_SECTION,
    PLACEHOLDER_TOKENS,
    SCENE_PACKAGE_REQUIRED_SECTIONS,
    TABLE_HEADER_CELLS,
)

_SECTION_WAIVER_PREFIXES = ("无需", "不适用")


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


def _explicit_section_waiver(body: str) -> bool:
    """Return whether a section contains a human-readable explicit waiver."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith((">", "|")):
            continue
        value = re.sub(r"^\s*[-*]\s*", "", stripped).replace("**", "").strip()
        if value.startswith(_SECTION_WAIVER_PREFIXES):
            return True
    return False


def _decision_field_values(body: str) -> dict[str, str]:
    """Extract canonical decision-question fields from Markdown bullets."""
    values: dict[str, str] = {}
    for line in body.splitlines():
        stripped = re.sub(r"^\s*[-*]\s*", "", line.strip()).replace("**", "")
        if not stripped:
            continue
        parts = re.split(r"[：:]", stripped, maxsplit=1)
        if len(parts) != 2:
            continue
        label, value = (part.strip() for part in parts)
        for aliases in DECISION_QUESTION_FIELDS:
            if label in aliases:
                values[aliases[0]] = value
                break
    return values


def _labeled_field_values(
    body: str, fields: tuple[tuple[str, ...], ...]
) -> dict[str, str]:
    """Extract labeled Markdown bullets using canonical names and aliases."""
    values: dict[str, str] = {}
    for line in body.splitlines():
        stripped = re.sub(r"^\s*[-*]\s*", "", line.strip()).replace("**", "")
        if not stripped:
            continue
        parts = re.split(r"[：:]", stripped, maxsplit=1)
        if len(parts) != 2:
            continue
        label, value = (part.strip() for part in parts)
        for aliases in fields:
            if label in aliases:
                values[aliases[0]] = value
                break
    return values


def _active_decision_questions(body: str) -> int:
    values = _decision_field_values(body)
    active = 0
    for aliases in DECISION_QUESTION_FIELDS:
        value = values.get(aliases[0], "")
        if not _meaningful(value):
            continue
        if re.match(r"^(?:无|无需|不适用)(?:$|[（(:：—-])", value):
            continue
        active += 1
    return active


def _material_filled(text: str, *, allow_waiver: bool = True) -> bool:
    """A memory/planning material file counts as filled when its template
    blanks have been replaced (or carry an explicit waiver mark outside of
    guidance blockquotes)."""
    lines = [l for l in text.splitlines() if not l.strip().startswith(">")]
    body = "\n".join(lines)
    if allow_waiver and MATERIAL_WAIVER_MARK in body:
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


def check_scene_package(
    package_text: str, ledger_text: str | None, mode: str = "formal"
) -> list[str]:
    """Blocking problems in the scene package (and dialogue ledger)."""
    if mode not in DRAFT_MODES:
        raise ValueError(f"unknown draft mode: {mode}")
    if mode != "formal":
        return []
    blocking: list[str] = []
    for heading in SCENE_PACKAGE_REQUIRED_SECTIONS:
        body = section(package_text, heading)
        if body is None or not section_has_content(body):
            blocking.append(f"scene-package 缺少或未填写章节：{heading}")
    decisions = section(package_text, DECISION_QUESTION_SECTION)
    if (
        decisions is not None
        and _active_decision_questions(decisions) < MIN_ACTIVE_DECISION_QUESTIONS
    ):
        blocking.append(
            f"决策问题至少填写 {MIN_ACTIVE_DECISION_QUESTIONS} 项真实摩擦；"
            "章型不能把拒绝、误读、不能说出口的话与代价全部豁免"
        )
    cognition = section(package_text, COGNITION_LEDGER_SECTION)
    if (
        cognition is not None
        and table_rows(cognition) < 1
        and not _explicit_section_waiver(cognition)
    ):
        blocking.append(
            f"{COGNITION_LEDGER_SECTION} 至少填写 1 条重要推断，"
            "或明确说明本章不依赖推断推动关键行动"
        )
    falsification = section(package_text, PLANNING_FALSIFICATION_SECTION)
    if falsification is not None:
        values = _labeled_field_values(
            falsification, PLANNING_FALSIFICATION_FIELDS
        )
        for aliases in PLANNING_FALSIFICATION_FIELDS:
            canonical = aliases[0]
            if not _meaningful(values.get(canonical, "")):
                blocking.append(
                    f"{PLANNING_FALSIFICATION_SECTION} 未填写：{canonical}"
                )
    responsibility = section(package_text, CAUSAL_RESPONSIBILITY_SECTION)
    if (
        responsibility is not None
        and table_rows(responsibility) < MIN_CAUSAL_RESPONSIBILITY_ROWS
    ):
        blocking.append(
            f"因果归属账本至少填写 {MIN_CAUSAL_RESPONSIBILITY_ROWS} 条"
        )
    expertise = section(package_text, EXPERTISE_AUDIT_SECTION)
    if (
        expertise is not None
        and table_rows(expertise) < 1
        and not _explicit_section_waiver(expertise)
    ):
        blocking.append(
            f"{EXPERTISE_AUDIT_SECTION} 至少填写 1 条专业判断，"
            "或明确说明本章没有依赖专业判断推动的关键行动"
        )
    beats = section(package_text, BEAT_CHAIN_SECTION)
    if beats is None or table_rows(beats) < MIN_BEATS:
        blocking.append(f"Beat 因果链少于 {MIN_BEATS} 个可执行 beat")
    package_without_bold = package_text.replace("**", "")
    key_dialogue_declared = bool(
        re.search(r"关键对白[：:]\s*是", package_without_bold)
    )
    ledger_declares_dialogue = bool(
        ledger_text
        and re.search(r"本场景是否有关键对白[：:]\s*是", ledger_text)
    )
    if key_dialogue_declared and ledger_text is None:
        blocking.append("场景包声明有关键对白，但关键对白账本不存在")
    elif (
        (key_dialogue_declared or ledger_declares_dialogue)
        and ledger_text is not None
        and table_rows(ledger_text) < 1
    ):
        blocking.append("关键对白账本未填写")
    return blocking


def check_chapter_text(chapter_text: str, mode: str = "formal") -> list[str]:
    """Blocking problems in the chapter body itself."""
    if mode not in DRAFT_MODES:
        raise ValueError(f"unknown draft mode: {mode}")
    if mode == "degraded_exploration":
        return []
    blocking: list[str] = []
    if mode == "formal":
        cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", chapter_text))
        if cjk < MIN_FORMAL_CJK:
            blocking.append(
                f"正式章节不足 {MIN_FORMAL_CJK} 个 CJK 汉字（当前 {cjk}）"
            )
    paragraphs = [
        p
        for p in re.split(r"\n\s*\n", chapter_text)
        if p.strip() and not p.lstrip().startswith("#")
    ]
    if len(paragraphs) < MIN_CHAPTER_PARAGRAPHS:
        blocking.append("正文段落不足，无法验证场景推进")
    return blocking


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _chinese_number(value: str) -> int | None:
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def _time_rank(value: str) -> int | None:
    """Return an approximate minute-of-day rank for common Chinese times."""
    match = re.search(r"(?<!\d)([01]?\d|2[0-3])[:：](\d{2})", value)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    hour: int | None = None
    numeric = re.search(r"(?<!\d)(\d{1,2})点", value)
    if numeric:
        hour = int(numeric.group(1))
    else:
        chinese = re.search(r"([零〇一二两三四五六七八九十]{1,3})点", value)
        if chinese:
            hour = _chinese_number(chinese.group(1))
    if hour is not None:
        if any(token in value for token in ("下午", "傍晚", "晚上", "夜里")):
            if hour < 12:
                hour += 12
        elif "中午" in value and hour < 11:
            hour += 12
        elif "深夜" in value and hour < 6:
            hour += 24
        return hour * 60
    period_ranks = (
        ("凌晨", 2 * 60),
        ("清晨", 6 * 60),
        ("早上", 7 * 60),
        ("上午", 9 * 60),
        ("中午", 12 * 60),
        ("下午", 15 * 60),
        ("傍晚", 18 * 60),
        ("晚上", 20 * 60),
        ("夜里", 21 * 60),
        ("深夜", 23 * 60),
    )
    return next((rank for token, rank in period_ranks if token in value), None)


def check_chapter_handoff(
    project_root: Path,
    chapter_path: Path,
    package_text: str,
    chapter_text: str,
    chapter_number: int | None,
) -> list[str]:
    """Validate the explicit previous-to-current chapter continuity contract."""
    if chapter_number is None or chapter_number <= 1:
        return []
    body = section(package_text, CHAPTER_HANDOFF_SECTION)
    if body is None:
        return [f"scene-package 缺少章节：{CHAPTER_HANDOFF_SECTION}"]
    values = _labeled_field_values(body, CHAPTER_HANDOFF_FIELDS)
    blocking = [
        f"{CHAPTER_HANDOFF_SECTION} 未填写：{aliases[0]}"
        for aliases in CHAPTER_HANDOFF_FIELDS
        if not _meaningful(values.get(aliases[0], ""))
    ]
    if blocking:
        return blocking
    transition = values["转场类型"]
    if transition not in CHAPTER_HANDOFF_TRANSITIONS:
        blocking.append(
            f"{CHAPTER_HANDOFF_SECTION} 转场类型必须是 "
            + "、".join(CHAPTER_HANDOFF_TRANSITIONS)
        )
    previous_matches = sorted(
        (project_root / "chapters").glob(
            f"e*/ch-{chapter_number - 1:02d}/正文.md"
        )
    )
    if not previous_matches:
        blocking.append(f"找不到上一章正文：ch-{chapter_number - 1:02d}")
        return blocking
    previous_path = previous_matches[0]
    expected_path = previous_path.relative_to(project_root).as_posix()
    if values["上一章正文路径"].replace("\\", "/") != expected_path:
        blocking.append(
            f"{CHAPTER_HANDOFF_SECTION} 上一章正文路径与实际文件不一致"
        )
    if values["上一章正文 SHA-256"].lower() != _sha256(previous_path):
        blocking.append(
            f"{CHAPTER_HANDOFF_SECTION} 上一章正文 SHA-256 与当前文件不一致"
        )
    previous_text = previous_path.read_text(encoding="utf-8-sig")
    previous_quote = values["上一章结尾原文"]
    previous_quote_at = previous_text.rfind(previous_quote)
    if previous_quote_at < 0:
        blocking.append(
            f"{CHAPTER_HANDOFF_SECTION} 上一章结尾原文未在上一章正文中找到"
        )
    elif previous_quote_at + len(previous_quote) < int(len(previous_text) * 0.8):
        blocking.append(
            f"{CHAPTER_HANDOFF_SECTION} 上一章结尾原文不在上一章结尾 20% 内"
        )
    current_quote = values["本章开头原文"]
    current_quote_at = chapter_text.find(current_quote)
    if current_quote_at < 0:
        blocking.append(
            f"{CHAPTER_HANDOFF_SECTION} 本章开头原文未在当前正文中找到"
        )
    elif current_quote_at > int(len(chapter_text) * 0.2):
        blocking.append(
            f"{CHAPTER_HANDOFF_SECTION} 本章开头原文不在当前章开头 20% 内"
        )
    if transition == "same_day_continuous":
        previous_rank = _time_rank(values["上一章结束时间"])
        current_rank = _time_rank(values["本章开始时间"])
        if (
            previous_rank is not None
            and current_rank is not None
            and current_rank < previous_rank
        ):
            blocking.append(
                f"{CHAPTER_HANDOFF_SECTION} 同日连续场景发生时间倒退："
                f"{values['上一章结束时间']} → {values['本章开始时间']}"
            )
    return blocking


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
    story_engine = project_root / "planning/story-engine.md"
    if not story_engine.exists():
        blocking.append("缺少材料文件：planning/story-engine.md")
    elif not _material_filled(
        story_engine.read_text(encoding="utf-8-sig"), allow_waiver=False
    ):
        blocking.append(
            "planning/story-engine.md 未填写；正式稿必须建立欲望、阻力、"
            "不可逆选择、即时代价与未解承诺"
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


def narrative_report(
    chapter_path: Path, package_path: Path, mode: str = "formal"
) -> dict[str, Any]:
    """Full narrative gate result for one chapter."""
    if mode not in DRAFT_MODES:
        raise ValueError(f"unknown draft mode: {mode}")
    chapter = chapter_path.read_text(encoding="utf-8-sig")
    package = (
        package_path.read_text(encoding="utf-8-sig")
        if package_path.exists()
        else ""
    )
    ledger_path = package_path.with_name(
        package_path.name.replace("scene-package-", "dialogue-ledger-")
    )
    ledger = (
        ledger_path.read_text(encoding="utf-8-sig") if ledger_path.exists() else None
    )
    project_root = _derive_project_root(chapter_path)
    chapter_number = _chapter_number(chapter_path, package_path)
    blocking = check_scene_package(package, ledger, mode=mode)
    blocking.extend(check_chapter_text(chapter, mode=mode))
    if ledger is None:
        advisory = [f"对白账本不存在（如本章无关键对白可忽略）：{ledger_path.name}"]
    else:
        advisory = []
    if mode == "formal":
        blocking.extend(
            check_chapter_handoff(
                project_root,
                chapter_path,
                package,
                chapter,
                chapter_number,
            )
        )
        mat_blocking, mat_advisory = check_project_materials(
            project_root, chapter_number
        )
        blocking.extend(mat_blocking)
        advisory.extend(mat_advisory)
    elif mode == "degraded_exploration":
        advisory.append(
            "降级运行：工具或沙箱能力受限；本稿仅作探索样本，"
            "必须记录 tool_capabilities/tool_failures，且不得进入 ready。"
        )
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
