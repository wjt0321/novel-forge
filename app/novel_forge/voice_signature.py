"""Voice signature: measurable style fingerprint of a prose text.

Absolute thresholds ("no more than 3 similes") can only catch universal
AI tells. A *relative* signal is stronger: does this chapter sound like the
book's own exemplar? This module extracts a small set of computable style
metrics from a text and compares two fingerprints, producing advisory drift
findings. All metrics are regex-based and language-agnostic within Chinese
prose; no NLP dependencies.

Usage:
    python -m app.novel_forge.voice_signature <file>            # fingerprint
    python -m app.novel_forge.voice_signature <file> --vs <ref> # drift vs ref
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_CJK_RE = re.compile(r"[一-鿿]")
_SENTENCE_END_RE = re.compile(r"[。！？]")
_QUOTE_SPAN_RE = re.compile(r'["“「][^"”」]*["”」]')
_SIMILE_RE = re.compile(r"(?<![想图画录雕影头塑摄])像|仿佛|好似|宛如|犹如")


def _count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_END_RE.split(text)
    return [p.strip() for p in parts if len(_CJK_RE.findall(p)) > 2]


def _paragraphs(text: str) -> list[str]:
    return [
        p.strip()
        for p in re.split(r"\n\s*\n", text)
        if p.strip() and not p.lstrip().startswith("#")
    ]


def extract_signature(text: str) -> dict[str, Any]:
    """Compute the style fingerprint of a prose text.

    Metrics (all rates per 1000 CJK unless noted):
    - sentence stats: count, mean length, length coefficient of variation
    - dialogue_ratio: share of CJK inside quotation marks
    - paragraph stats: count, mean length, micro-paragraph (<=10 CJK) ratio
    - simile/comma-clause rates
    - terminator mix: question and exclamation sentence ratios
    """
    cjk = _count_cjk(text)
    if cjk < 50:
        raise ValueError("text too short for a meaningful signature (<50 CJK)")

    sentences = _sentences(text)
    lengths = [_count_cjk(s) for s in sentences]
    mean_len = statistics.fmean(lengths) if lengths else 0.0
    cv = (
        statistics.pstdev(lengths) / mean_len
        if len(lengths) > 1 and mean_len > 0
        else 0.0
    )

    paragraphs = _paragraphs(text)
    para_lengths = [_count_cjk(p) for p in paragraphs]
    micro = sum(1 for n in para_lengths if n <= 10)

    dialogue_cjk = sum(_count_cjk(m.group(0)) for m in _QUOTE_SPAN_RE.finditer(text))
    comma_clauses = sum(
        len([c for c in re.split(r"[，、；：]", s) if _CJK_RE.findall(c)])
        for s in sentences
    )

    def _per_mille(n: int | float) -> float:
        return round(n / cjk * 1000, 2)

    return {
        "cjk": cjk,
        "sentence_count": len(sentences),
        "sentence_len_mean": round(mean_len, 1),
        "sentence_len_cv": round(cv, 3),
        "dialogue_ratio": round(dialogue_cjk / cjk, 3),
        "paragraph_count": len(paragraphs),
        "paragraph_len_mean": round(
            statistics.fmean(para_lengths) if para_lengths else 0.0, 1
        ),
        "micro_paragraph_ratio": round(micro / len(paragraphs), 3) if paragraphs else 0.0,
        "simile_per_mille": _per_mille(len(_SIMILE_RE.findall(text))),
        "clauses_per_sentence": round(
            comma_clauses / len(sentences), 2
        )
        if sentences
        else 0.0,
        "question_ratio": round(
            len(re.findall(r"？", text)) / max(len(sentences), 1), 3
        ),
        "exclaim_ratio": round(
            len(re.findall(r"！", text)) / max(len(sentences), 1), 3
        ),
    }


# Drift comparison: (metric, relative tolerance). A chapter drifts when its
# metric differs from the exemplar by more than the tolerance (relative to
# the exemplar's own magnitude, with a floor to avoid noise on tiny values).
_TOLERANCES: dict[str, tuple[float, float]] = {
    "sentence_len_mean": (0.35, 4.0),
    "sentence_len_cv": (0.40, 0.12),
    "dialogue_ratio": (0.50, 0.06),
    "paragraph_len_mean": (0.40, 12.0),
    "micro_paragraph_ratio": (0.60, 0.05),
    "simile_per_mille": (1.00, 1.0),
    "clauses_per_sentence": (0.30, 0.5),
}


def compare_signatures(
    chapter: dict[str, Any], exemplar: dict[str, Any]
) -> list[dict[str, Any]]:
    """Advisory drift findings of `chapter` relative to `exemplar`."""
    findings: list[dict[str, Any]] = []
    for metric, (rel_tol, floor) in _TOLERANCES.items():
        ref = float(exemplar.get(metric, 0.0))
        cur = float(chapter.get(metric, 0.0))
        allowed = max(abs(ref) * rel_tol, floor)
        if abs(cur - ref) > allowed:
            findings.append(
                {
                    "metric": metric,
                    "chapter": cur,
                    "exemplar": ref,
                    "tolerance": round(allowed, 3),
                    "message": (
                        f"{metric} 偏离范文：本章 {cur} vs 范文 {ref}"
                        f"（容差 ±{allowed:.2f}）"
                    ),
                }
            )
    return findings


def _normalized_sentences(text: str) -> list[str]:
    return [
        re.sub(r"\s+", "", sentence)
        for sentence in re.findall(r"[^。！？]+[。！？]", text)
        if _count_cjk(sentence) >= 4
    ]


def analyze_serial_style(
    chapters: list[tuple[str, str]],
) -> dict[str, Any]:
    """Detect cross-chapter style collapse without assigning literary value.

    The report catches high-confidence serial symptoms seen in agent demos:
    sentence length collapsing chapter by chapter and exact sentences being
    reused as structural filler. Findings are advisory; the independent blind
    reader remains the human-likeness decision point.
    """
    profiles: list[dict[str, Any]] = []
    for name, text in chapters:
        try:
            signature = extract_signature(text)
        except ValueError:
            profiles.append(
                {
                    "chapter": name,
                    "cjk": _count_cjk(text),
                    "insufficient_for_signature": True,
                }
            )
        else:
            profiles.append({"chapter": name, **signature})
    findings: list[dict[str, Any]] = []
    comparable = [
        profile
        for profile in profiles
        if "sentence_len_mean" in profile
    ]
    if len(comparable) >= 3:
        means = [
            float(profile["sentence_len_mean"])
            for profile in comparable
        ]
        later_mean = statistics.fmean(means[1:])
        if later_mean < means[0] * 0.7:
            findings.append(
                {
                    "code": "sentence-length-collapse",
                    "severity": "advisory",
                    "detail": (
                        "后续章节句长均值相对首章明显下降："
                        + " → ".join(f"{value:.1f}" for value in means)
                    ),
                }
            )

    sentence_chapters: dict[str, set[str]] = {}
    sentence_counts: Counter[str] = Counter()
    for name, text in chapters:
        local = Counter(_normalized_sentences(text))
        for sentence, count in local.items():
            sentence_counts[sentence] += count
            sentence_chapters.setdefault(sentence, set()).add(name)
    repeated = [
        {
            "sentence": sentence,
            "count": sentence_counts[sentence],
            "chapters": sorted(sentence_chapters[sentence]),
        }
        for sentence in sentence_counts
        if sentence_counts[sentence] >= 3
        and len(sentence_chapters[sentence]) >= 2
    ]
    repeated.sort(key=lambda item: (-item["count"], item["sentence"]))
    if repeated:
        findings.append(
            {
                "code": "cross-chapter-repetition",
                "severity": "advisory",
                "detail": f"检测到 {len(repeated)} 个跨章精确复用句。",
                "examples": repeated[:5],
            }
        )
    return {
        "chapters": profiles,
        "findings": findings,
        "human_likeness_risk": len(findings) >= 2,
    }


def signature_report(path: Path, ref_path: Path | None = None) -> str:
    sig = extract_signature(path.read_text(encoding="utf-8-sig"))
    if ref_path is None:
        return json.dumps(sig, ensure_ascii=False, indent=2)
    ref = extract_signature(ref_path.read_text(encoding="utf-8-sig"))
    drift = compare_signatures(sig, ref)
    return json.dumps(
        {"signature": sig, "exemplar": ref, "drift": drift},
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = list(argv)
    ref = None
    if "--vs" in args:
        i = args.index("--vs")
        try:
            ref = Path(args[i + 1])
        except IndexError:
            print("Usage: voice_signature <file> [--vs <exemplar>]", file=sys.stderr)
            return 2
        del args[i : i + 2]
    if len(args) != 1:
        print("Usage: voice_signature <file> [--vs <exemplar>]", file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    print(signature_report(path, ref))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
