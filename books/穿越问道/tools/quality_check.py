"""Lightweight prose quality checker for a single Markdown file.

This script is intentionally small and rule-based. It flags surface problems
that are cheap to detect and expensive to miss (wrong punctuation, duplicated
quotes, forbidden patterns). It does NOT claim to detect "AI writing" or
literary quality.

Known limitations:
- This script covers only hard surface gates such as em-dashes, ellipses, and negation flips.
- It does not detect whether professional detail serves character action or whether a causal chain is complete.
- It does not judge cross-paragraph near-duplicate meaning; use an independent line editor for that review.
- It does not judge narrative structure; use a scene-level narrative review.
- A passing result does not mean the prose is literary, publishable, or user-approved.

Usage:
    python tools/quality_check.py PATH_TO_CHAPTER.md
"""

import re
import sys
from pathlib import Path
from typing import Any


# CJK Unified Ideographs (Han)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def check(text: str, path: str = "") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        # Blocking / forbidden patterns
        if "——" in line:
            findings.append({
                "line": idx,
                "rule": "em-dash",
                "severity": "blocking",
                "message": "Chinese em-dash '——' is forbidden.",
                "snippet": line.strip(),
            })
        if "……" in line:
            findings.append({
                "line": idx,
                "rule": "ellipsis",
                "severity": "blocking",
                "message": "Chinese ellipsis '……' is forbidden.",
                "snippet": line.strip(),
            })

        # Negation flip patterns
        if re.search(r"不是[^，。！？\n]{1,15}而是", line) or \
           re.search(r"不是[^，。！？\n]{1,15}是[^，。！？\n]{1,15}", line):
            findings.append({
                "line": idx,
                "rule": "negation-flip",
                "severity": "blocking",
                "message": "'不是X而是Y / 不是X是Y' pattern is forbidden.",
                "snippet": line.strip(),
            })

        # Duplicated quotes like ""...""
        if re.search(r'""[^"]*""', line):
            findings.append({
                "line": idx,
                "rule": "quote-duplication",
                "severity": "advisory",
                "message": "Duplicated quotes \"\"...\"\" detected.",
                "snippet": line.strip(),
            })

        # Question particle followed by period
        if re.search(r"[吗呢吧么]。", line) and not re.search(r"[什么怎么这么那么多么要么]。", line):
            findings.append({
                "line": idx,
                "rule": "question-mark-mismatch",
                "severity": "advisory",
                "message": "Question particle followed by period instead of '?'.",
                "snippet": line.strip(),
            })

        # Common word-count tic: explicit quantifier immediately before 字.
        # Excludes ordinals (第...) and classifier 行 (一行字 / 第一行字).
        if re.search(r"(?<![第])[零一二三四五六七八九十百千万两0-9]{1,4}(?:个|枚)?字", line):
            findings.append({
                "line": idx,
                "rule": "word-count-tic",
                "severity": "advisory",
                "message": "Explicit word-count phrase like '五个字' detected.",
                "snippet": line.strip(),
            })

    return findings


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("Usage: python quality_check.py <markdown-file>", file=sys.stderr)
        return 2

    path = Path(argv[0])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8-sig")
    findings = check(text, str(path))
    blocking = [f for f in findings if f["severity"] == "blocking"]
    advisory = [f for f in findings if f["severity"] == "advisory"]

    print(f"File: {path}")
    print(f"CJK characters: {count_cjk(text)}")
    print(f"Blocking: {len(blocking)}, Advisory: {len(advisory)}")
    if findings:
        print("Findings:")
        for f in findings:
            print(f"  L{f['line']} [{f['rule']}] {f['severity']}: {f['message']}")
    else:
        print("No findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
