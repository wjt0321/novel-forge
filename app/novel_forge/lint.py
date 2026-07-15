"""Prose lint rules for Chinese web fiction.

Rules are intentionally surface-level and advisory-only for stylistic
patterns. They flag *locations* for human review; they do not judge
literary quality and never auto-edit the text.
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LintFinding:
    rule_code: str
    severity: str
    line_number: int | None = None
    message: str = ""
    evidence: str | None = None
    # File-level metrics
    colon_count: int | None = None
    char_count: int | None = None
    colon_density: float | None = None


_RULES = {
    "em-dash": ("blocking", "正文禁止使用破折号 ——"),
    "ellipsis": ("blocking", "正文禁止使用省略号 ……"),
    "not-is-flip": (
        "blocking",
        "禁止连续使用“不是 X，而是 Y / 不是 X，是 Y”式否定翻转",
    ),
    "explanation-tic": (
        "advisory",
        "疑似作者解释 / 总结腔，建议改为动作、对话或物件呈现",
    ),
    "word-count-tic": (
        "advisory",
        "正文内出现具体字数表述，建议改为非数字表达",
    ),
    "rhythm-monotony": (
        "advisory",
        "连续多个段落均为短段（≤2句），节奏可能过于均匀，建议加入长短呼吸变化",
    ),
    "mechanical-triplet": (
        "advisory",
        "连续三句以上同构短句或清单化名词独句，可能像清单而非叙事",
    ),
    "explanatory-punchline": (
        "advisory",
        "出现结论性独词句或解释性收尾，建议改为角色动作/发现过程",
    ),
    "question-mark-mismatch": (
        "advisory",
        "疑问语气词（吗/呢/么/吧）后使用句号，建议检查是否为疑问句",
    ),
    "quote-consistency": (
        "advisory",
        "对话引号数量不成对，请检查对话标点一致性",
    ),
    "common-error": (
        "advisory",
        "疑似常见错字、搭配或病句，请人工复核",
    ),
}

_EXPLANATION_PATTERNS = [
    re.compile(r"这意味着"),
    re.compile(r"真正重要的是"),
    re.compile(r"最重要的是"),
    re.compile(r"他终于明白"),
    re.compile(r"她终于明白"),
    re.compile(r"他终于懂得"),
    re.compile(r"她终于懂得"),
    re.compile(r"这一切说明"),
    re.compile(r"这一切表明"),
    re.compile(r"归根结底"),
    re.compile(r"说到底"),
    re.compile(r"不是告别，是"),
    re.compile(r"不是结束，是"),
]

_WORD_COUNT_RE = re.compile(r"[零一二三四五六七八九十百千万两0-9]{1,4}(?:个|枚|行)?字")

# 不是X，而是Y / 不是X，是Y within a clause.
_NOT_IS_FLIP_RE = re.compile(
    r"不是([^，。；！？\n]{1,25})(?:，(?:而是|是)|(?:而是|是))([^，。；！？\n]{1,25})"
)

# Common proofreading / collocation errors.
# Each entry: (pattern, message_fragment). Patterns are heuristic and
# advisory-only; they may match legitimate usages, so a human must review.
_COMMON_ERRORS = [
    (re.compile(r"入防"), "应为“人防”"),
    (re.compile(r"注浆机[^。！？\n]{0,10}打桩"), "注浆机不会“打桩”，应为“打浆/注浆”"),
    (re.compile(r"[^，。！？\n]{0,6}发的微信语音"), "句子悬空，建议改为“发来微信语音”或“的微信语音传来”"),
    (re.compile(r"、和手机"), "“和”与前面的顿号重复，建议改为“以及手机”"),
    (re.compile(r"平铺开[^开来]"), "“平铺开”生硬，建议“平铺开来”或“展开”"),
]

# Sentence terminators for Chinese prose.
_SENTENCE_END_RE = re.compile(r"[。！？\.\?!]")


def _truncate(line: str, start: int, end: int, max_len: int = 40) -> str:
    half = max_len // 2
    s = max(0, start - half)
    e = min(len(line), end + half)
    prefix = "…" if s > 0 else ""
    suffix = "…" if e < len(line) else ""
    return prefix + line[s:e].strip() + suffix


def _count_cjk_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def _paragraphs_with_lines(text: str) -> list[tuple[list[int], str]]:
    """Split text into paragraphs, returning (line_numbers, paragraph_text)."""
    paragraphs: list[tuple[list[int], str]] = []
    current_lines: list[int] = []
    current_parts: list[str] = []
    for idx, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if stripped == "":
            if current_parts:
                paragraphs.append(
                    (current_lines, "\n".join(current_parts))
                )
                current_lines = []
                current_parts = []
        else:
            current_lines.append(idx)
            current_parts.append(stripped)
    if current_parts:
        paragraphs.append((current_lines, "\n".join(current_parts)))
    return paragraphs


def _sentence_count(text: str) -> int:
    """Count sentences by Chinese/ASCII sentence terminators."""
    if not text.strip():
        return 0
    # Normalize ellipsis and treat each terminator as one sentence end.
    return max(1, len(_SENTENCE_END_RE.findall(text)))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences roughly by terminators."""
    parts = _SENTENCE_END_RE.split(text)
    return [part.strip() for part in parts if part.strip()]


def _is_noun_phrase_like(sentence: str) -> bool:
    """Heuristic: sentence looks like a standalone noun phrase / list item."""
    stripped = sentence.strip("\n\"'")
    if not stripped:
        return False
    # Very short (<=12 chars) and no obvious predicate markers.
    if len(stripped) > 12:
        return False
    # Has verb-like characters? Then it's probably a real sentence.
    verb_markers = set("是有了为在把被说看走站到来去下出进过就做")
    if any(c in verb_markers for c in stripped):
        return False
    return True


def _detect_rhythm_monotony(
    paragraphs: list[tuple[list[int], str]],
) -> list[LintFinding]:
    """Flag sequences of short paragraphs (<=2 sentences)."""
    findings: list[LintFinding] = []
    severity, message = _RULES["rhythm-monotony"]
    run_start = 0
    run_len = 0
    for i, (line_nums, para_text) in enumerate(paragraphs):
        s_count = _sentence_count(para_text)
        if s_count <= 2:
            if run_len == 0:
                run_start = i
            run_len += 1
        else:
            if run_len >= 5:
                start_line = paragraphs[run_start][0][0]
                evidence_lines = [
                    paragraphs[j][1][:30]
                    for j in range(run_start, min(run_start + 3, i))
                ]
                findings.append(
                    LintFinding(
                        rule_code="rhythm-monotony",
                        severity=severity,
                        line_number=start_line,
                        message=f"连续 {run_len} 个段落均为 ≤2 句的短段，节奏可能过于均匀",
                        evidence=" | ".join(evidence_lines) + "...",
                    )
                )
            run_len = 0
    if run_len >= 5:
        start_line = paragraphs[run_start][0][0]
        evidence_lines = [
            paragraphs[j][1][:30]
            for j in range(run_start, min(run_start + 3, len(paragraphs)))
        ]
        findings.append(
            LintFinding(
                rule_code="rhythm-monotony",
                severity=severity,
                line_number=start_line,
                message=f"连续 {run_len} 个段落均为 ≤2 句的短段，节奏可能过于均匀",
                evidence=" | ".join(evidence_lines) + "...",
            )
        )
    return findings


def _detect_mechanical_triplet(
    paragraphs: list[tuple[list[int], str]],
) -> list[LintFinding]:
    """Flag three consecutive structurally similar short sentences/items."""
    findings: list[LintFinding] = []
    severity, message = _RULES["mechanical-triplet"]

    for line_nums, para_text in paragraphs:
        sentences = _split_sentences(para_text)
        if len(sentences) < 3:
            continue
        for i in range(len(sentences) - 2):
            a, b, c = sentences[i], sentences[i + 1], sentences[i + 2]
            # Rule 1: three consecutive noun-phrase standalone items.
            if _is_noun_phrase_like(a) and _is_noun_phrase_like(b) and _is_noun_phrase_like(c):
                findings.append(
                    LintFinding(
                        rule_code="mechanical-triplet",
                        severity=severity,
                        line_number=line_nums[0],
                        message=message,
                        evidence=f"{a} / {b} / {c}",
                    )
                )
                break
            # Rule 2: three consecutive sentences share the same opening prefix.
            # Use a 2-character prefix for Chinese; 4 for mixed/ASCII.
            prefix_len = 2 if re.search(r"[\u4e00-\u9fff]", a[:4]) else 4
            a_prefix = a[:prefix_len]
            b_prefix = b[:prefix_len]
            c_prefix = c[:prefix_len]
            if len(a_prefix) >= prefix_len and a_prefix == b_prefix == c_prefix:
                findings.append(
                    LintFinding(
                        rule_code="mechanical-triplet",
                        severity=severity,
                        line_number=line_nums[0],
                        message=message,
                        evidence=f"{a} / {b} / {c}",
                    )
                )
                break
    return findings


def _detect_explanatory_punchline(
    paragraphs: list[tuple[list[int], str]],
    total_cjk_chars: int,
) -> list[LintFinding]:
    """Flag standalone conclusion sentences in narrative paragraphs."""
    findings: list[LintFinding] = []
    severity, message = _RULES["explanatory-punchline"]
    # Skip very short test fragments and headings.
    if total_cjk_chars < 50:
        return findings
    for line_nums, para_text in paragraphs:
        # Skip markdown headings.
        first_line = para_text.split("\n")[0].strip()
        if first_line.startswith("#"):
            continue
        sentences = _split_sentences(para_text)
        for sentence in sentences:
            stripped = sentence.strip("\n\"'")
            # Standalone short conclusion: <=5 chars and mostly CJK.
            if 1 <= len(stripped) <= 5 and re.match(r"^[\u4e00-\u9fff]+$", stripped):
                findings.append(
                    LintFinding(
                        rule_code="explanatory-punchline",
                        severity=severity,
                        line_number=line_nums[0],
                        message=f"结论性独词句：「{stripped}」，建议通过动作或发现过程呈现",
                        evidence=stripped,
                    )
                )
    return findings


_QUESTION_PARTICLE_RE = re.compile(r"([吗呢么吧])([。．\.]|$)")


def lint_text(text: str) -> list[LintFinding]:
    """Run all prose lint rules against raw text.

    Returns a list of LintFinding objects. The final item is a file-level
    colon-density advisory when the text contains CJK characters.
    """
    findings: list[LintFinding] = []
    lines = text.split("\n")
    total_colons = 0

    for idx, line in enumerate(lines, start=1):
        # Count colons (Chinese and ASCII)
        total_colons += len(re.findall(r"[:：]", line))

        # em-dash / ellipsis: report every occurrence
        for code in ("em-dash", "ellipsis"):
            severity, message = _RULES[code]
            for m in re.finditer(r"——" if code == "em-dash" else r"……", line):
                findings.append(
                    LintFinding(
                        rule_code=code,
                        severity=severity,
                        line_number=idx,
                        message=message,
                        evidence=_truncate(line, m.start(), m.end()),
                    )
                )

        # Not-is-flip
        severity, message = _RULES["not-is-flip"]
        for m in _NOT_IS_FLIP_RE.finditer(line):
            findings.append(
                LintFinding(
                    rule_code="not-is-flip",
                    severity=severity,
                    line_number=idx,
                    message=message,
                    evidence=_truncate(line, m.start(), m.end()),
                )
            )

        # Explanation tics
        severity, message = _RULES["explanation-tic"]
        for pattern in _EXPLANATION_PATTERNS:
            for m in pattern.finditer(line):
                findings.append(
                    LintFinding(
                        rule_code="explanation-tic",
                        severity=severity,
                        line_number=idx,
                        message=message,
                        evidence=_truncate(line, m.start(), m.end()),
                    )
                )

        # Word-count tics
        severity, message = _RULES["word-count-tic"]
        for m in _WORD_COUNT_RE.finditer(line):
            findings.append(
                LintFinding(
                    rule_code="word-count-tic",
                    severity=severity,
                    line_number=idx,
                    message=message,
                    evidence=_truncate(line, m.start(), m.end()),
                )
            )

        # Question-mark mismatch: 吗/呢/么/吧 followed by period or line end.
        q_severity, q_message = _RULES["question-mark-mismatch"]
        for m in _QUESTION_PARTICLE_RE.finditer(line):
            findings.append(
                LintFinding(
                    rule_code="question-mark-mismatch",
                    severity=q_severity,
                    line_number=idx,
                    message=q_message,
                    evidence=_truncate(line, m.start(), m.end()),
                )
            )

        # Common errors
        ce_severity, ce_message = _RULES["common-error"]
        for pattern, detail in _COMMON_ERRORS:
            for m in pattern.finditer(line):
                findings.append(
                    LintFinding(
                        rule_code="common-error",
                        severity=ce_severity,
                        line_number=idx,
                        message=f"{ce_message}：{detail}",
                        evidence=_truncate(line, m.start(), m.end()),
                    )
                )

    char_count = _count_cjk_chars(text)
    paragraphs = _paragraphs_with_lines(text)
    findings.extend(_detect_rhythm_monotony(paragraphs))
    findings.extend(_detect_mechanical_triplet(paragraphs))
    findings.extend(_detect_explanatory_punchline(paragraphs, char_count))

    # Quote consistency (file-level heuristic).
    # For straight ASCII quotes, an odd total count is inconsistent because
    # each quote is both opener and closer. For paired quotes, compare counts.
    quote_pairs = [
        ('"', '"', True),   # same char, treat odd total as mismatch
        ("「", "」", False),
        ("『", "』", False),
        ("“", "”", False),
        ("‘", "’", False),
    ]
    for open_q, close_q, is_same_char in quote_pairs:
        open_count = text.count(open_q)
        close_count = text.count(close_q)
        mismatch = False
        if is_same_char:
            total = open_count  # same char counted once
            mismatch = total > 0 and total % 2 == 1
        else:
            mismatch = open_count != close_count and (open_count > 0 or close_count > 0)
        if mismatch:
            q_severity, q_message = _RULES["quote-consistency"]
            findings.append(
                LintFinding(
                    rule_code="quote-consistency",
                    severity=q_severity,
                    line_number=None,
                    message=f"{q_message}：{open_q}{open_count} 个，{close_q}{close_count} 个",
                    evidence=None,
                )
            )

    if char_count > 0:
        density = (total_colons / char_count) * 1000
        findings.append(
            LintFinding(
                rule_code="colon-density",
                severity="advisory",
                message=f"冒号 {total_colons} 个，中文字数 {char_count}，每千字约 {density:.2f} 个",
                colon_count=total_colons,
                char_count=char_count,
                colon_density=density,
            )
        )

    return findings


def lint_file(path: Path) -> list[LintFinding]:
    """Lint a single Markdown file."""
    text = path.read_text(encoding="utf-8")
    return lint_text(text)
