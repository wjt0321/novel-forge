"""Tests for the voice-signature style fingerprint module."""

import json
from pathlib import Path

import pytest

from app.novel_forge.voice_signature import (
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
