"""Lightweight Markdown heading parser for drafting readiness assessment.

No external dependencies. Only handles the subset of Markdown used by
Voice Bible and Scene Contract v2 assets: level-2 headings and simple lists.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MarkdownSection:
    """A section parsed from a Markdown document."""

    key: str
    title: str
    content: str


def parse_markdown_sections(text: str) -> list[MarkdownSection]:
    """Split a Markdown document into level-2 heading sections.

    The section key is the English identifier inside parentheses if present,
    otherwise a normalized version of the heading text.
    """
    sections: list[MarkdownSection] = []
    lines = text.splitlines()
    current_title: str | None = None
    content_lines: list[str] = []

    for line in lines:
        match = re.match(r"^##\s+(.+)$", line)
        if match:
            if current_title is not None:
                sections.append(_make_section(current_title, content_lines))
            current_title = match.group(1).strip()
            content_lines = []
        elif current_title is not None:
            content_lines.append(line)

    if current_title is not None:
        sections.append(_make_section(current_title, content_lines))

    return sections


def _make_section(title: str, content_lines: list[str]) -> MarkdownSection:
    key = _extract_key(title)
    content = "\n".join(content_lines).strip()
    return MarkdownSection(key=key, title=title, content=content)


def _extract_key(title: str) -> str:
    match = re.search(r"\(\s*([a-z_][a-z0-9_]*)\s*\)", title)
    if match:
        return match.group(1)
    # Fallback: normalize the heading text itself.
    return title.strip().lower().replace(" ", "_").replace("/", "_")


_PLACEHOLDER_CONTENTS = {
    "",
    "本场读者想知道什么？",
    "tbd",
    "待定",
    "待填写",
    "n/a",
}


def is_missing_content(content: str) -> bool:
    """Return True if a section contains only whitespace or placeholder text."""
    cleaned = content.strip()
    if not cleaned:
        return True
    if cleaned.lower() in _PLACEHOLDER_CONTENTS:
        return True
    non_empty_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not non_empty_lines:
        return True
    return all(_is_placeholder_line(line) for line in non_empty_lines)


def _is_placeholder_line(line: str) -> bool:
    """A line is a placeholder if it is an empty list item or known filler."""
    stripped = line.lstrip("- ").strip()
    return stripped in _PLACEHOLDER_CONTENTS


def count_concrete_anchors(content: str) -> int:
    """Count non-placeholder list items in the concrete_anchor section."""
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if item and not _is_placeholder_item(item):
                count += 1
    return count


def _is_placeholder_item(item: str) -> bool:
    return item in {
        "锚点 1：",
        "锚点 2：",
        "物体 1：可做什么 / 不可做什么 / 何时改变行动",
        "物体 2：可做什么 / 不可做什么 / 何时改变行动",
        "第一步：感知/接触 → 动作 → 环境反馈/代价",
        "第二步：感知/接触 → 动作 → 环境反馈/代价",
        "第三步：感知/接触 → 动作 → 环境反馈/代价",
        "tbd",
        "待定",
        "待填写",
        "n/a",
    }


# Scene Contract v3 fields. New chapters use v4; legacy v2/v3 contracts get upgrade warnings.
_SCENE_CONTRACT_V3_FIELDS = [
    "character_blindspot_or_pressure",
    "irreversible_choice",
    "choice_consequence",
    "detail_payoff_plan",
    "scene_necessity",
    "ending_change",
]

# Scene Contract v4 embodied fields.
_SCENE_CONTRACT_V4_FIELDS = [
    "spatial_layout_and_routes",
    "body_state_and_contacts",
    "object_affordances",
    "environmental_constraints",
    "embodied_action_chain",
]


def detect_contract_version(text: str) -> int:
    """Detect Scene Contract version from Markdown text.

    Explicit `contract_version: N` in YAML-like footer wins. Otherwise,
    presence of any version-only heading marks the contract as that version.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("contract_version:"):
            value = stripped.split(":", 1)[1].strip()
            try:
                return int(value)
            except ValueError:
                pass
    sections = {section.key for section in parse_markdown_sections(text)}
    if any(field in sections for field in _SCENE_CONTRACT_V4_FIELDS):
        return 4
    if any(field in sections for field in _SCENE_CONTRACT_V3_FIELDS):
        return 3
    return 2


def count_valid_list_items(content: str) -> int:
    """Count non-placeholder list items in a section."""
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if item and not _is_placeholder_item(item):
                count += 1
    return count


# Heuristic checks for Scene Contract v4 embodied fields.
_DIMENSION_RE = re.compile(
    r"(\d+[\d\s,]*\s*(?:米|平方米|平米|m|㎡|cm|公里|km|尺|寸|亩|"
    r"square\s*meter|square\s*metre|square|area|长度|宽度|高度|深度|厚度))",
    re.IGNORECASE,
)
_POSITION_ROUTE_RE = re.compile(
    r"(左边|右边|左侧|右侧|左方|右方|前面|后面|前方|后方|"
    r"上面|下面|上方|下方|之内|之中|之外|以外|之间|中间|"
    r"旁边|侧边|边缘|背面|背对|面对|面前|迎面|朝向|面向|"
    r"方位|距离|相距|对面|对侧|内侧|外侧|里外|"
    r"出口|入口|门口|窗口|门边|窗边|通道|走廊|墙角|拐角|转角|转弯|"
    r"路线|路径|走向|走到|走回|走过|走动|行走|移动|"
    r"穿过|越过|绕过|经过|通过|靠近|远离|接近|逼近|退向|后退|"
    r"站立|站着|站住|站起|坐下|躺下|趴下|蹲下|蹲伏|"
    r"倚靠|紧靠|紧贴|抵住|贴着|踩着|踏着|踩上)",
)
_CAUSAL_RE = re.compile(
    r"(因为|所以|导致|因此|由于|从而|迫使|使得|造成|引发|"
    r"→|->|"
    r"\bbecause\b|\btherefore\b|\bthus\b|\bhence\b|"
    r"\bcauses?\b|\bcaused\b|\bcausing\b|"
    r"\bforces?\b|\bforced\b|\bforcing\b|"
    r"\bleads?\s+to\b|\bled\s+to\b|\bresults?\s+in\b)",
    re.IGNORECASE,
)


def is_parameter_only_spatial_layout(content: str) -> bool:
    """Return True if the spatial layout only states dimensions/numbers.

    This is intentionally a simple, testable heuristic rather than a
    full NLP pipeline. A valid layout must contain relative position or
    movement/ route language; a string dominated by measurements without
    such language is flagged.
    """
    nonempty = [line.strip() for line in content.splitlines() if line.strip()]
    if not nonempty:
        return False
    dimension_hits = sum(1 for line in nonempty if _DIMENSION_RE.search(line))
    position_hits = sum(1 for line in nonempty if _POSITION_ROUTE_RE.search(line))
    # If there are measurements and almost no spatial/movement language,
    # the writer has likely pasted parameters instead of an embodied layout.
    if dimension_hits >= 2 and position_hits == 0:
        return True
    if dimension_hits > position_hits and position_hits < 2:
        return True
    return False


def has_causal_chain(content: str) -> bool:
    """Return True if the environmental constraints contain a causal marker."""
    return bool(_CAUSAL_RE.search(content))
