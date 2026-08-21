"""Cheap, non-blocking prose texture telemetry for staged chapters."""

from __future__ import annotations

from collections import Counter
import math
import re
from typing import Any

from .planning_spec import CJK_CHAR_RE

TEXTURE_SCHEMA = "novel-forge-literary-texture/v1"
_CJK_RE = CJK_CHAR_RE  # shared single-source CJK metric (planning_spec)
_DELAYED_REACTIONS = re.compile(
    r"停了一下|停住(?:了)?|没有立刻|看了很久|沉默(?:了)?(?:片刻|一会儿)?|"
    r"怔了一下|愣了一下|过了一会儿|慢慢(?:地)?"
)
_EXPLANATORY_ECHOES = re.compile(
    r"这意味着|这说明|也就是说|换句话说|他(?:已经)?明白|她(?:已经)?明白|"
    r"他(?:已经)?知道|她(?:已经)?知道|从此(?:以后)?"
)


def _paragraphs(text: str) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"\n\s*\n", text)
        if value.strip() and not value.lstrip().startswith("#")
    ]


def _sentences(text: str) -> list[str]:
    return [value.strip() for value in re.split(r"[。！？!?]+", text) if value.strip()]


def _cjk_count(text: str) -> int:
    return len(_CJK_RE.findall(text))


def _sentence_uniformity(sentences: list[str]) -> float | None:
    lengths = [_cjk_count(sentence) for sentence in sentences]
    lengths = [value for value in lengths if value > 0]
    if len(lengths) < 8:
        return None
    mean = sum(lengths) / len(lengths)
    variance = sum((value - mean) ** 2 for value in lengths) / len(lengths)
    return round(math.sqrt(variance) / mean, 4) if mean else None


# Minimum repeat counts per n-gram size. Sizes 2-3 catch two/three-char
# refrains ("沉默……沉默"); their thresholds are higher because short
# collocations repeat legitimately. Function-word-only grams are excluded.
_NGRAM_MIN_COUNT = {2: 8, 3: 6, 4: 4, 5: 4, 6: 4}
_FUNCTION_CHARS = frozenset(
    "的了着过在是我就你他她它们这那有没不也都还很又再把被让"
    "和与或但因为所以如果虽然么呢吧啊吗一个"
)


def _repeated_ngrams(text: str) -> list[dict[str, Any]]:
    compact = "".join(_CJK_RE.findall(text))
    candidates: Counter[str] = Counter()
    for size, min_count in _NGRAM_MIN_COUNT.items():
        for index in range(max(0, len(compact) - size + 1)):
            value = compact[index : index + size]
            if len(set(value)) <= 1:
                continue
            if size <= 3 and all(char in _FUNCTION_CHARS for char in value):
                continue
            candidates[value] += 1
    repeated = [
        {"text": value, "count": count}
        for value, count in candidates.most_common()
        if count >= _NGRAM_MIN_COUNT[len(value)]
    ]
    chosen: list[dict[str, Any]] = []
    for item in repeated:
        if any(
            item["text"] in prior["text"] or prior["text"] in item["text"]
            for prior in chosen
        ):
            continue
        chosen.append(item)
        if len(chosen) == 3:
            break
    return chosen


def analyze_literary_texture(text: str) -> dict[str, Any]:
    """Return advisory texture signals without asserting authorship or quality."""
    paragraphs = _paragraphs(text)
    sentences = _sentences(text)
    opening_counts = Counter()
    for paragraph in paragraphs:
        opening = "".join(_CJK_RE.findall(paragraph[:12]))[:1]
        if opening:
            opening_counts[opening] += 1
    opening_share = (
        max(opening_counts.values()) / len(paragraphs)
        if paragraphs and opening_counts
        else 0.0
    )
    delayed = len(_DELAYED_REACTIONS.findall(text))
    explanatory = len(_EXPLANATORY_ECHOES.findall(text))
    uniformity = _sentence_uniformity(sentences)
    repeated = _repeated_ngrams(text)

    signals: list[str] = []
    if len(paragraphs) >= 6 and opening_share >= 0.65:
        signals.append("段首主语高度集中")
    if delayed >= max(4, math.ceil(len(paragraphs) * 0.4)):
        signals.append("延迟反应近义结构重复")
    if explanatory >= 3:
        signals.append("动作后的解释性回声集中")
    if uniformity is not None and uniformity <= 0.12:
        signals.append("句长分布过度均匀")
    if repeated and repeated[0]["count"] >= 5:
        signals.append("局部短语重复集中")

    risk = "high" if len(signals) >= 3 else "medium" if len(signals) == 2 else "low"
    hint = ""
    if risk == "high":
        hint = "机器纹理提示：" + "；".join(signals[:2]) + "。仅供核对，不是文学结论。"
        hint = hint[:120]
    return {
        "schema": TEXTURE_SCHEMA,
        "risk_level": risk,
        "blocking": False,
        "hint": hint,
        "signals": signals,
        "metrics": {
            "paragraph_count": len(paragraphs),
            "sentence_count": len(sentences),
            "paragraph_opening_share": round(opening_share, 4),
            "delayed_reaction_count": delayed,
            "explanatory_echo_count": explanatory,
            "sentence_length_cv": uniformity,
            "repeated_ngrams": repeated,
        },
    }
