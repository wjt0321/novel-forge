"""Tests for the voice-signature style fingerprint module."""

import json
from pathlib import Path

import pytest

from app.novel_forge.voice_signature import (
    analyze_serial_style,
    compare_signatures,
    extract_signature,
    signature_report,
)


KIMI_LIKE = (
    "他把卡递进去。卡片贴着凹槽滑过去的那几厘米，他感觉自己心跳得很快，但手是稳的。\n\n"
    '"先缴两万。"\n\n'
    "吴姐把卡在机器上按了一下，输入金额，把键盘转向他。他输密码，六个数字，按得很慢。"
    "打印机响起来，凭条吐出来，她撕下来，盖章，从窗口推出来。\n\n"
    '"先生？"吴姐在窗口里看他，"凭条，拿好。"\n\n'
    '"哦。"他接过那张还带着打印机温度的纸。\n\n'
    "手机在他手心里震了。\n\n"
) * 12

AI_LIKE = (
    "灵压骤降。他坐直了。面板上的曲线跳动。周期从八秒缩到五秒。像冰下暗河被搅动。\n\n"
    "他盯着屏幕。他看着读数。他感到不安。像钝刀切冻肉。像老旧的示波器。像将断的丝线。\n\n"
    "陆渊坐直了。\n\n循环泵还在敲。第七下。\n\n"
) * 12


def test_extract_signature_basic_metrics():
    sig = extract_signature(KIMI_LIKE)
    assert sig["cjk"] > 500
    assert sig["sentence_count"] > 0
    assert 0 < sig["dialogue_ratio"] < 1
    assert sig["sentence_len_cv"] > 0


def test_signature_too_short_raises():
    with pytest.raises(ValueError):
        extract_signature("太短了。")


def test_self_drift_is_zero():
    sig = extract_signature(KIMI_LIKE)
    assert compare_signatures(sig, sig) == []


def test_drift_detects_ai_like_text():
    kimi = extract_signature(KIMI_LIKE)
    ai = extract_signature(AI_LIKE)
    drift = compare_signatures(ai, kimi)
    metrics = {f["metric"] for f in drift}
    # AI-like text should drift on at least simile density and dialogue ratio.
    assert "simile_per_mille" in metrics
    assert "dialogue_ratio" in metrics
    assert all("message" in f for f in drift)


def test_similar_texts_do_not_drift():
    a = extract_signature(KIMI_LIKE)
    b = extract_signature(KIMI_LIKE + "\n\n他点点头，没说话。" * 3)
    assert compare_signatures(b, a) == []


def test_signature_report_json(tmp_path: Path):
    chapter = tmp_path / "c.md"
    chapter.write_text(KIMI_LIKE, encoding="utf-8")
    report = json.loads(signature_report(chapter))
    assert "sentence_len_cv" in report
    ref = tmp_path / "ref.md"
    ref.write_text(AI_LIKE, encoding="utf-8")
    compared = json.loads(signature_report(chapter, ref))
    assert "drift" in compared


def test_serial_style_detects_cross_chapter_collapse_and_repetition():
    chapters = [
        (
            "第一章",
            (
                "她沿着河岸往前走，鞋底沾着昨夜的泥，"
                "每到一盏路灯下面才抬头看一次门牌。"
                "客厅里很安静。"
            )
            * 30,
        ),
        (
            "第二章",
            ("她起身。她开门。她没有说话。客厅里很安静。") * 60,
        ),
        (
            "第三章",
            ("她坐下。她看手机。她没有起身。客厅里很安静。") * 70,
        ),
    ]

    report = analyze_serial_style(chapters)
    codes = {finding["code"] for finding in report["findings"]}

    assert "sentence-length-collapse" in codes
    assert "cross-chapter-repetition" in codes
    assert report["human_likeness_risk"] is True
    assert report["blocking"]


def test_serial_style_keeps_varied_chapters_advisory_free():
    chapters = [
        ("第一章", KIMI_LIKE),
        (
            "第二章",
            (
                "老周把账册摊在桌上，先核对日期，再把每一笔欠款抄到便签。"
                "窗外有人收伞，水顺着台阶流进排水沟。"
                '"数目对不上。"他说，手指停在最后一行。'
                "她没有接话，只把缴费单转过来，看见背面留下半枚蓝色印章。"
                "楼道里的灯亮了一次，很快又暗下去。"
            )
            * 16,
        ),
    ]

    report = analyze_serial_style(chapters)

    assert report["human_likeness_risk"] is False
    assert report["blocking"] == []


def test_serial_style_blocks_extreme_exact_sentence_coverage():
    repeated = "她走到门边。她没有开门。她回头看了一眼。"
    chapters = [
        ("第一章", (repeated + "雨落在窗台上，留下细密水痕。") * 80),
        ("第二章", (repeated + "楼道的灯坏了，墙上只有灰白天光。") * 80),
    ]

    report = analyze_serial_style(chapters)
    finding = next(
        item
        for item in report["blocking"]
        if item["code"] == "serial-duplicate-coverage"
    )

    assert finding["duplicate_sentence_ratio"] >= 0.5
    assert report["human_likeness_risk"] is True


def test_serial_style_blocks_long_cross_chapter_paragraph_copy():
    copied = (
        "罗闻把水表前的锈屑拨开，看见齿轮仍在缓慢移动。"
        "她关掉总阀，又等了两分钟，表盘上的红针依旧越过刻度。"
        "楼上传来拖动椅子的声音，她没有立刻抬头。"
    )
    chapters = [
        ("第一章", copied + "\n\n" + KIMI_LIKE),
        ("第二章", copied + "\n\n" + AI_LIKE),
    ]

    report = analyze_serial_style(chapters)

    assert any(
        item["code"] == "cross-chapter-paragraph-copy"
        for item in report["blocking"]
    )


def test_serial_style_blocks_malformed_nested_dialogue_labels():
    malformed = (
        '周蓉说："周蓉说：你别再查了。"\n\n'
        '罗闻说："罗闻说：我只看水表。"\n\n'
    ) * 20

    report = analyze_serial_style([("第三章", malformed)])

    assert any(
        item["code"] == "malformed-dialogue-structure"
        for item in report["blocking"]
    )
