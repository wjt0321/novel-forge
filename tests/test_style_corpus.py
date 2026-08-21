"""Tests for the style corpus (positive genes + AI-tell catalog)."""

from __future__ import annotations

import pytest

from app.novel_forge.lint import lint_text
from app.novel_forge.project_templates import _memory_voice_bible_md
from app.novel_forge.style_corpus import (
    AI_TELL_PATTERNS,
    POSITIVE_STYLE_GENES,
    STYLE_CORPUS_VERSION,
    render_ai_tells_brief,
    render_positive_genes_brief,
)


def test_corpus_version_and_structure():
    assert STYLE_CORPUS_VERSION == "style-corpus/v1"
    assert len(POSITIVE_STYLE_GENES) >= 6
    assert len(AI_TELL_PATTERNS) >= 10
    for gene in POSITIVE_STYLE_GENES:
        assert {"id", "source", "principle", "practice", "signal"} <= set(gene)
        assert isinstance(gene["practice"], tuple) and gene["practice"]
    ids = [gene["id"] for gene in POSITIVE_STYLE_GENES]
    assert len(ids) == len(set(ids))
    tell_ids = [tell["id"] for tell in AI_TELL_PATTERNS]
    assert len(tell_ids) == len(set(tell_ids))
    for tell in AI_TELL_PATTERNS:
        assert {"id", "category", "pattern", "fix"} <= set(tell)


def test_corpus_carries_no_long_verbatim_excerpts():
    """Entries describe techniques; they must not embed long quoted prose."""
    for gene in POSITIVE_STYLE_GENES:
        blob = "".join(
            str(part) for part in (
                gene["principle"], *gene["practice"], gene["signal"]
            )
        )
        assert "……" not in blob
        assert len(blob) < 400
    for tell in AI_TELL_PATTERNS:
        assert len(tell["pattern"]) < 160


def test_renderers_are_bounded_and_deduplicated():
    genes = render_positive_genes_brief()
    tells = render_ai_tells_brief()
    assert 0 < len(genes) <= 1500
    assert 0 < len(tells) <= 1200
    # Tight budgets still return a non-empty prefix, never raise.
    assert render_positive_genes_brief(max_chars=200)
    assert render_ai_tells_brief(max_chars=200)
    # Every positive gene id appears in its brief.
    for gene in POSITIVE_STYLE_GENES:
        assert gene["source"] in genes


@pytest.mark.parametrize(
    ("sample", "expected_code"),
    [
        ("一阵深深的悲伤涌上心头，他握紧了拳头。", "emotion-label"),
        ("愤怒攫住了她，她把杯子摔在地上。", "emotion-label"),
        ("这个决定扮演着关键的角色。", "role-playing-tic"),
    ],
)
def test_new_lint_rules_fire_on_tells(sample: str, expected_code: str):
    codes = {f.rule_code for f in lint_text(sample)}
    assert expected_code in codes


def test_connective_tic_is_density_based():
    single = "此外，他把门关上了。"
    assert "connective-tic" not in {
        f.rule_code for f in lint_text(single)
    }
    dense = (
        "此外，他把门关上了。\n"
        "与此同时，街上传来哨声。\n"
        "不仅如此，灯也灭了。\n"
        "值得注意的是，没有人说话。"
    )
    assert "connective-tic" in {
        f.rule_code for f in lint_text(dense)
    }


def test_clean_prose_does_not_trigger_new_rules():
    clean = (
        "# 第一章 门后的雨\n\n"
        "林舟握住门把，听见走廊尽头的脚步逼近。他没有回头，只是把掌心压得更紧。"
        "门锁刚转动，他就松开了手，退到窗边，掀开窗帘一角。\n\n"
        "街上空无一人。卖馄饨的老头收了摊，板车碾过水洼的声音由远及近，又远了。"
        "他数着自己的呼吸，数到第七下，脚步声停在了门外。\n"
    )
    codes = {f.rule_code for f in lint_text(clean)}
    assert not codes & {"emotion-label", "connective-tic", "role-playing-tic"}


def test_voice_bible_template_embeds_both_corpus_sections():
    bible = _memory_voice_bible_md("测试书", "都市")
    assert "## 风格基因库（正例参照）" in bible
    assert "## AI 味对照清单（反例禁则）" in bible
    assert "海明威 · 冰山省略" in bible
    assert "只学叙事功能、不抄任何措辞" in bible
    assert "密度才是破绽" in bible
