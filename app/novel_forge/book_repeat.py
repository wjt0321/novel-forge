"""Cross-chapter repetition detection (docs/46 B1).

Advisory-only diagnostics for book-scale self-repetition that single-chapter
review cannot see: re-used simile phrasing, near-duplicate distinctive
phrases, and identical chapter-ending moves. Findings name the earlier
chapter so editors can judge intentional motif versus mechanical tic.
This module never blocks and never certifies AI origin or literary value.
"""

from __future__ import annotations

import re
from typing import Any

from .lint import _SIMILE_RE

REPEAT_SHINGLE_SIZE = 8
REPEAT_MAX_FINDINGS = 8
# Per-detector cap so a single noisy detector cannot starve the others.
REPEAT_MAX_PER_DETECTOR = 3
# A phrase echoed by exactly one earlier chapter reads as an echo; a phrase
# already present in two or more earlier chapters is treated as motif.
REPEAT_MOTIF_TOLERANCE = 1
_MAX_CJK_KEY_CHARS = 30_000
_MIN_SIMILE_CORE_CHARS = 10
_MIN_ENDING_CORE_CHARS = 8

_CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_SENTENCE_RE = re.compile(r"[^。！？!?\n]+")


def _cjk_key(text: str) -> str:
    return "".join(_CJK_CHAR_RE.findall(text))[:_MAX_CJK_KEY_CHARS]


def _sentences(text: str) -> list[str]:
    return [
        match.group().strip()
        for match in _SENTENCE_RE.finditer(text)
        if match.group().strip()
    ]


def _simile_findings(
    earlier: list[tuple[str, str]], current_text: str
) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    for name, text in earlier:
        for sentence in _sentences(text):
            if not _SIMILE_RE.search(sentence):
                continue
            key = _cjk_key(sentence)
            if len(key) >= _MIN_SIMILE_CORE_CHARS:
                seen.setdefault(key, name)
    findings: list[dict[str, Any]] = []
    matched: set[str] = set()
    for sentence in _sentences(current_text):
        if not _SIMILE_RE.search(sentence):
            continue
        key = _cjk_key(sentence)
        if (
            len(key) >= _MIN_SIMILE_CORE_CHARS
            and key in seen
            and key not in matched
        ):
            matched.add(key)
            findings.append(
                {
                    "code": "repeated-simile",
                    "chapter": seen[key],
                    "detail": f"比喻句与第 {seen[key]} 章几乎相同：{sentence[:40]}",
                }
            )
    return findings


def _shingle_findings(
    earlier: list[tuple[str, str]], current_text: str
) -> list[dict[str, Any]]:
    current_key = _cjk_key(current_text)
    grams = {
        current_key[i : i + REPEAT_SHINGLE_SIZE]
        for i in range(len(current_key) - REPEAT_SHINGLE_SIZE + 1)
    }
    if not grams:
        return []
    counts: dict[str, int] = {}
    owners: dict[str, tuple[str, str]] = {}
    for name, text in earlier:
        key = _cjk_key(text)
        for i in range(len(key) - REPEAT_SHINGLE_SIZE + 1):
            gram = key[i : i + REPEAT_SHINGLE_SIZE]
            count = counts.get(gram, 0)
            counts[gram] = count + 1
            if gram not in owners:
                index = key.find(gram)
                context = key[
                    max(0, index - 6) : index + REPEAT_SHINGLE_SIZE + 6
                ]
                owners[gram] = (name, context)
    findings: list[dict[str, Any]] = []
    for gram in grams:
        if counts.get(gram, 0) != REPEAT_MOTIF_TOLERANCE:
            continue
        name, context = owners[gram]
        findings.append(
            {
                "code": "repeated-shingle",
                "chapter": name,
                "detail": f"「{gram}」与第 {name} 章措辞几乎相同：…{context}…",
            }
        )
        if len(findings) >= REPEAT_MAX_FINDINGS:
            break
    return findings


def _ending_findings(
    earlier: list[tuple[str, str]], current_text: str
) -> list[dict[str, Any]]:
    current_sentences = _sentences(current_text)
    if not current_sentences:
        return []
    current_core = _cjk_key(current_sentences[-1])
    if len(current_core) < _MIN_ENDING_CORE_CHARS:
        return []
    endings: dict[str, str] = {}
    for name, text in earlier:
        sentences = _sentences(text)
        if not sentences:
            continue
        core = _cjk_key(sentences[-1])
        if len(core) >= _MIN_ENDING_CORE_CHARS:
            endings.setdefault(core[:40], name)
    owner = endings.get(current_core[:40])
    if owner is None:
        return []
    return [
        {
            "code": "repeated-ending",
            "chapter": owner,
            "detail": f"章末收束与第 {owner} 章几乎相同：{current_sentences[-1][:40]}",
        }
    ]


def analyze_cross_chapter_repetition(
    chapters: list[tuple[str, str]],
) -> dict[str, Any]:
    """Compare the staged chapter (last item) against earlier chapters.

    Returns ``{"findings": [...], "advisory": [...]}``; findings are advisory
    samples only and never contribute to blocking results.
    """
    if len(chapters) < 2:
        return {"findings": [], "advisory": []}
    earlier = chapters[:-1]
    _, current_text = chapters[-1]
    findings = (
        _simile_findings(earlier, current_text)[:REPEAT_MAX_PER_DETECTOR]
        + _shingle_findings(earlier, current_text)[:REPEAT_MAX_PER_DETECTOR]
        + _ending_findings(earlier, current_text)[:REPEAT_MAX_PER_DETECTOR]
    )
    findings = findings[:REPEAT_MAX_FINDINGS]
    advisory = [
        f"跨章重复(advisory)：{item['detail']}（最早出现于 {item['chapter']}）"
        for item in findings
    ]
    return {"findings": findings, "advisory": advisory}
