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
        "tbd",
        "待定",
        "待填写",
        "n/a",
    }


# Scene Contract v3 fields. New chapters use v3; legacy v2 contracts get a warning.
_SCENE_CONTRACT_V3_FIELDS = [
    "character_blindspot_or_pressure",
    "irreversible_choice",
    "choice_consequence",
    "detail_payoff_plan",
    "scene_necessity",
    "ending_change",
]


def detect_contract_version(text: str) -> int:
    """Detect Scene Contract version from Markdown text.

    Explicit `contract_version: 3` in YAML-like footer wins. Otherwise,
    presence of any v3-only heading marks the contract as v3.
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
    if any(field in sections for field in _SCENE_CONTRACT_V3_FIELDS):
        return 3
    return 2
