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

import hashlib
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
_NESTED_SPEAKER_RE = re.compile(
    r'(?P<speaker>[\u4e00-\u9fff]{1,8})(?:说|问|喊|道)'
    r'[：:]?["“][^"”\n]{0,30}(?P=speaker)(?:说|问|喊|道)[：:]'
)
_MIN_COPIED_PARAGRAPH_CJK = 60
_BLOCKING_DUPLICATE_SENTENCE_RATIO = 0.20
_MIN_BLOCKING_DUPLICATE_INSTANCES = 20
_MIN_PATTERN_SENTENCE_REPEATS = 4
_MIN_PATTERN_OPENING_REPEATS = 12
_MIN_PATTERN_OPENING_RATIO = 0.08
_MIN_PATTERN_CLAUSE_REPEATS = 8
_VOICE_COPY_NGRAM_CJK = 8
_MIN_VOICE_COPY_REPEATS = 2
_OPENING_STOPLIST = frozenset(
    {
        "他说",
        "她说",
        "他问",
        "她问",
        "他说道",
        "她说道",
    }
)


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


def _normalized_paragraphs(text: str) -> list[str]:
    return [
        re.sub(r"\s+", "", paragraph)
        for paragraph in _paragraphs(text)
        if _count_cjk(paragraph) >= _MIN_COPIED_PARAGRAPH_CJK
    ]


def _pattern_saturation(
    name: str,
    text: str,
) -> dict[str, Any] | None:
    """Return advisory evidence for repeated local generation habits."""
    sentences = _normalized_sentences(text)
    sentence_counts = Counter(sentences)
    repeated_sentences = [
        {"text": sentence, "count": count}
        for sentence, count in sentence_counts.items()
        if count >= _MIN_PATTERN_SENTENCE_REPEATS
    ]
    repeated_sentences.sort(key=lambda item: (-item["count"], item["text"]))

    opening_counts: Counter[str] = Counter()
    for sentence in sentences:
        cjk = "".join(_CJK_RE.findall(sentence))
        if len(cjk) < 2:
            continue
        opening = cjk[:2]
        if opening in _OPENING_STOPLIST:
            continue
        opening_counts[opening] += 1
    sentence_total = max(len(sentences), 1)
    sentence_openings = [
        {
            "opening": opening,
            "count": count,
            "ratio": round(count / sentence_total, 3),
        }
        for opening, count in opening_counts.items()
        if count >= _MIN_PATTERN_OPENING_REPEATS
        and count / sentence_total >= _MIN_PATTERN_OPENING_RATIO
    ]
    sentence_openings.sort(
        key=lambda item: (-item["count"], item["opening"])
    )

    clause_counts: Counter[str] = Counter()
    for clause in re.split(r"[，。！？；：,\n]+", text):
        normalized = "".join(_CJK_RE.findall(clause))
        if 4 <= len(normalized) <= 16:
            clause_counts[normalized] += 1
    repeated_clauses = [
        {"text": clause, "count": count}
        for clause, count in clause_counts.items()
        if count >= _MIN_PATTERN_CLAUSE_REPEATS
    ]
    repeated_clauses.sort(key=lambda item: (-item["count"], item["text"]))

    if not (repeated_sentences or sentence_openings or repeated_clauses):
        return None
    return {
        "code": "pattern-saturation",
        "severity": "advisory",
        "chapter": name,
        "detail": (
            "检测到章内完整句、句首或短语的高频复用；"
            "请判断它是有意复沓还是模型生成惯性。"
        ),
        "repeated_sentences": repeated_sentences[:5],
        "sentence_openings": sentence_openings[:5],
        "repeated_clauses": repeated_clauses[:5],
    }


def _voice_exemplar(voice_anchor_text: str) -> str:
    """Return only exemplar_notes when a full Voice Bible is provided."""
    lines = voice_anchor_text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if re.match(
            r"^\s*#{1,6}\s*exemplar_notes\s*$",
            line,
            re.IGNORECASE,
        ):
            start = index + 1
            break
    if start is None:
        return voice_anchor_text
    section: list[str] = []
    for line in lines[start:]:
        if re.match(r"^\s*#{1,6}\s+", line):
            break
        section.append(line)
    return "\n".join(section)


def _voice_anchor_surface_copy(
    chapters: list[tuple[str, str]],
    voice_anchor_text: str | None,
) -> dict[str, Any] | None:
    """Detect later chapters copying the Voice anchor's surface wording."""
    if not voice_anchor_text or len(chapters) < 2:
        return None
    voice_cjk = "".join(_CJK_RE.findall(_voice_exemplar(voice_anchor_text)))
    if len(voice_cjk) < _VOICE_COPY_NGRAM_CJK:
        return None
    voice_ngrams = {
        voice_cjk[index : index + _VOICE_COPY_NGRAM_CJK]
        for index in range(len(voice_cjk) - _VOICE_COPY_NGRAM_CJK + 1)
    }
    matches: list[dict[str, Any]] = []
    for name, text in chapters[1:]:
        prose_cjk = "".join(_CJK_RE.findall(text))
        prose_ngrams = Counter(
            prose_cjk[index : index + _VOICE_COPY_NGRAM_CJK]
            for index in range(
                max(0, len(prose_cjk) - _VOICE_COPY_NGRAM_CJK + 1)
            )
        )
        for phrase in voice_ngrams & prose_ngrams.keys():
            count = prose_ngrams[phrase]
            if count >= _MIN_VOICE_COPY_REPEATS:
                matches.append(
                    {
                        "chapter": name,
                        "phrase": phrase,
                        "count": count,
                    }
                )
    if not matches:
        return None
    matches.sort(
        key=lambda item: (-item["count"], item["chapter"], item["phrase"])
    )
    return {
        "code": "voice-anchor-surface-copy",
        "severity": "advisory",
        "detail": (
            "后续章节反复复用 Voice exemplar 的连续表层措辞；"
            "范文只能校准叙事功能，不得成为名词、动作或句法模板。"
        ),
        "examples": matches[:5],
    }


def analyze_serial_style(
    chapters: list[tuple[str, str]],
    *,
    voice_anchor_text: str | None = None,
) -> dict[str, Any]:
    """Detect serial drift and high-confidence structural prose failures.

    Sentence-length drift and low-volume repetition remain advisory. Exact
    reuse covering a material share of the manuscript, long paragraph copying,
    and malformed nested speaker labels are blocking because they are
    mechanically verifiable manuscript corruption rather than literary taste.
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
    for name, text in chapters:
        saturation = _pattern_saturation(name, text)
        if saturation is not None:
            findings.append(saturation)
    voice_copy = _voice_anchor_surface_copy(chapters, voice_anchor_text)
    if voice_copy is not None:
        findings.append(voice_copy)
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
    total_sentence_instances = sum(sentence_counts.values())
    duplicate_sentence_instances = sum(
        sentence_counts[sentence]
        for sentence in sentence_counts
        if len(sentence_chapters[sentence]) >= 2
    )
    duplicate_sentence_ratio = (
        duplicate_sentence_instances / total_sentence_instances
        if total_sentence_instances
        else 0.0
    )
    if (
        duplicate_sentence_instances >= _MIN_BLOCKING_DUPLICATE_INSTANCES
        and duplicate_sentence_ratio >= _BLOCKING_DUPLICATE_SENTENCE_RATIO
    ):
        findings.append(
            {
                "code": "serial-duplicate-coverage",
                "severity": "blocking",
                "detail": (
                    "跨章逐字复用句覆盖正文句子实例比例过高："
                    f"{duplicate_sentence_ratio:.1%}。"
                ),
                "duplicate_sentence_instances": duplicate_sentence_instances,
                "total_sentence_instances": total_sentence_instances,
                "duplicate_sentence_ratio": round(
                    duplicate_sentence_ratio, 3
                ),
                "examples": repeated[:5],
            }
        )

    paragraph_chapters: dict[str, set[str]] = {}
    paragraph_counts: Counter[str] = Counter()
    for name, text in chapters:
        local = Counter(_normalized_paragraphs(text))
        for paragraph, count in local.items():
            paragraph_counts[paragraph] += count
            paragraph_chapters.setdefault(paragraph, set()).add(name)
    copied_paragraphs = [
        {
            "paragraph_sha256": hashlib.sha256(
                paragraph.encode("utf-8")
            ).hexdigest(),
            "cjk": _count_cjk(paragraph),
            "count": paragraph_counts[paragraph],
            "chapters": sorted(paragraph_chapters[paragraph]),
        }
        for paragraph in paragraph_counts
        if len(paragraph_chapters[paragraph]) >= 2
    ]
    copied_paragraphs.sort(
        key=lambda item: (-item["cjk"], -item["count"], item["paragraph_sha256"])
    )
    if copied_paragraphs:
        findings.append(
            {
                "code": "cross-chapter-paragraph-copy",
                "severity": "blocking",
                "detail": (
                    f"检测到 {len(copied_paragraphs)} 个跨章逐字复制的长段落。"
                ),
                "examples": copied_paragraphs[:5],
            }
        )

    malformed_by_chapter = [
        {
            "chapter": name,
            "count": len(_NESTED_SPEAKER_RE.findall(text)),
        }
        for name, text in chapters
    ]
    malformed_by_chapter = [
        item for item in malformed_by_chapter if item["count"] > 0
    ]
    malformed_count = sum(item["count"] for item in malformed_by_chapter)
    if malformed_count:
        findings.append(
            {
                "code": "malformed-dialogue-structure",
                "severity": (
                    "blocking" if malformed_count >= 2 else "advisory"
                ),
                "detail": (
                    "检测到对白内部重复嵌套说话人标签："
                    f"{malformed_count} 处。"
                ),
                "chapters": malformed_by_chapter,
            }
        )
    blocking = [
        finding for finding in findings if finding["severity"] == "blocking"
    ]
    return {
        "chapters": profiles,
        "findings": findings,
        "blocking": blocking,
        "human_likeness_risk": bool(blocking) or len(findings) >= 2,
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
