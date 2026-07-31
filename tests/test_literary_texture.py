from __future__ import annotations

from app.novel_forge.literary_texture import analyze_literary_texture


def test_texture_analysis_flags_distributed_mechanical_patterns_without_blocking():
    paragraph = "他停了一下，看向门口。这意味着他已经作出决定。"
    body = "# 第一章\n\n" + "\n\n".join(paragraph for _ in range(10))

    report = analyze_literary_texture(body)

    assert report["schema"] == "novel-forge-literary-texture/v1"
    assert report["risk_level"] == "high"
    assert report["metrics"]["delayed_reaction_count"] >= 10
    assert report["metrics"]["explanatory_echo_count"] >= 10
    assert report["metrics"]["paragraph_opening_share"] >= 0.9
    assert report["hint"].startswith("机器纹理提示：")
    assert len(report["hint"]) <= 120
    assert report["blocking"] is False


def test_texture_analysis_keeps_varied_short_prose_low_risk():
    body = (
        "# 第一章\n\n雨水顺着车窗往下淌。林舟把票根塞进烟盒。\n\n"
        "售票员没问他去哪，只把零钱推回桌边。\n\n"
        "门外有人咳嗽。阿棠侧过身，让出半条路。\n\n"
        "林舟没有道谢。他认出了那双沾白灰的鞋。"
    )

    report = analyze_literary_texture(body)

    assert report["risk_level"] == "low"
    assert report["hint"] == ""
    assert report["blocking"] is False
