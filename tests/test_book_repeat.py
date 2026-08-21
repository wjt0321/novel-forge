from __future__ import annotations

from app.novel_forge.book_repeat import (
    REPEAT_MAX_FINDINGS,
    analyze_cross_chapter_repetition,
)


def test_shared_simile_sentence_is_detected_with_attribution():
    simile = "她的声音像浸了水的棉絮，沉得抬不起来。"
    ch01 = ("ch01", "他推门进去。屋里很暗。" + simile + "他没有开灯。")
    ch02 = ("ch02", "走廊很长。" + simile + "她停在门口。")
    report = analyze_cross_chapter_repetition([ch01, ch02])
    codes = {finding["code"] for finding in report["findings"]}
    assert "repeated-simile" in codes
    assert any(finding["chapter"] == "ch01" for finding in report["findings"])
    assert report["advisory"]
    assert all("advisory" not in str(code) for code in codes)


def test_unique_prose_produces_no_findings():
    ch01 = (
        "ch01",
        "他把伞放在门边，水顺着伞骨滴成一排。窗台上的猫翻了个身，继续睡。",
    )
    ch02 = (
        "ch02",
        "厨房里还亮着灯。锅里的汤已经凉了，浮着一层薄薄的油花。",
    )
    report = analyze_cross_chapter_repetition([ch01, ch02])
    assert report["findings"] == []
    assert report["advisory"] == []


def test_distinctive_phrase_echo_across_distant_chapters_is_detected():
    phrase = "他把硬币在指尖转了半圈才放进募捐箱"
    chapters = [
        ("ch01", phrase + "，然后走开。"),
        ("ch02", "完全不同的内容，讲的是另一条街上的雨和一只湿透的猫。"),
        ("ch09", "多年以后他又想起那天。" + phrase + "。这一次他没有走开。"),
    ]
    report = analyze_cross_chapter_repetition(chapters)
    assert any(
        finding["code"] == "repeated-shingle"
        and finding["chapter"] == "ch01"
        for finding in report["findings"]
    )


def test_phrase_recurring_in_many_chapters_is_treated_as_motif():
    motif = "他把硬币在指尖转了半圈才放进募捐箱"
    chapters = [
        ("ch01", motif),
        ("ch02", motif),
        ("ch03", motif),
    ]
    report = analyze_cross_chapter_repetition(chapters)
    assert not any(
        finding["code"] == "repeated-shingle" for finding in report["findings"]
    )


def test_identical_ending_move_is_detected():
    ending = "灯灭了，他在黑暗里听见自己的心跳。"
    ch01 = ("ch01", "他们吵完架各自回家。" + ending)
    ch02 = ("ch02", "葬礼结束，宾客散去。" + ending)
    report = analyze_cross_chapter_repetition([ch01, ch02])
    assert any(finding["code"] == "repeated-ending" for finding in report["findings"])


def test_single_chapter_has_nothing_to_compare():
    report = analyze_cross_chapter_repetition([("ch01", "只有一章的正文。")])
    assert report == {"findings": [], "advisory": []}


def test_findings_are_capped():
    phrase = "他把硬币在指尖转了半圈才放进募捐箱"
    filler = "这一段讲的是完全无关的日常，买菜做饭洗碗拖地浇花。"
    ch01 = ("ch01", "。".join(phrase + str(i) + filler for i in range(20)))
    ch02 = ("ch02", "。".join(phrase + str(i) + filler for i in range(20)))
    report = analyze_cross_chapter_repetition([ch01, ch02])
    assert len(report["findings"]) <= REPEAT_MAX_FINDINGS
