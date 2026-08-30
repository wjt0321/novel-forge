"""Tests for the style corpus (positive genes + AI-tell catalog)."""

from __future__ import annotations

import pytest

from app.novel_forge.lint import lint_text
from app.novel_forge.project_templates import _memory_voice_bible_md
from app.novel_forge.style_corpus import (
    AI_TELL_PATTERNS,
    CORE_AI_TELL_IDS,
    CORE_POSITIVE_GENE_IDS,
    POSITIVE_STYLE_GENES,
    STYLE_CORPUS_VERSION,
    gene_checklist_lines,
    render_ai_tells_brief,
    render_positive_genes_brief,
    render_writer_style_brief,
)


def test_corpus_version_and_structure():
    assert STYLE_CORPUS_VERSION == "style-corpus/v2"
    assert len(POSITIVE_STYLE_GENES) >= 18
    assert len(AI_TELL_PATTERNS) >= 24
    for gene in POSITIVE_STYLE_GENES:
        assert {"id", "source", "principle", "practice", "signal"} <= set(gene)
        assert isinstance(gene["practice"], tuple) and gene["practice"]
    ids = [gene["id"] for gene in POSITIVE_STYLE_GENES]
    assert len(ids) == len(set(ids))
    tell_ids = [tell["id"] for tell in AI_TELL_PATTERNS]
    assert len(tell_ids) == len(set(tell_ids))
    for tell in AI_TELL_PATTERNS:
        assert {"id", "category", "pattern", "fix"} <= set(tell)


def test_core_reference_subsets_exist():
    """Capsule injection picks by id, so the core ids must resolve."""
    gene_ids = {gene["id"] for gene in POSITIVE_STYLE_GENES}
    tell_ids = {tell["id"] for tell in AI_TELL_PATTERNS}
    assert CORE_POSITIVE_GENE_IDS and set(CORE_POSITIVE_GENE_IDS) <= gene_ids
    assert CORE_AI_TELL_IDS and set(CORE_AI_TELL_IDS) <= tell_ids
    assert len(CORE_POSITIVE_GENE_IDS) <= 5
    assert len(CORE_AI_TELL_IDS) <= 6


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
    # Author-facing reference keeps the full library, unbounded by default.
    for gene in POSITIVE_STYLE_GENES:
        assert gene["source"] in genes
    for tell in AI_TELL_PATTERNS:
        assert tell["pattern"] in tells
    # An explicit budget keeps the longest whole-line prefix, never raises.
    assert render_positive_genes_brief(max_chars=200)
    assert render_ai_tells_brief(max_chars=200)


def test_writer_style_brief_is_bounded_and_clause_clean():
    brief = render_writer_style_brief()
    assert 0 < len(brief) <= 300
    assert "- 学 " in brief and "- 避 " in brief
    # A gist is cut at a clause boundary, never mid-word.
    for line in brief.splitlines():
        gist = line.split("：", 1)[1] if "：" in line else ""
        assert not gist.endswith(("的", "是", "和", "、", "，"))
    # Adopted labels narrow the positive side to what the author checked.
    adopted = render_writer_style_brief(["贴着人物写"])
    assert "贴着人物写" in adopted and "冰山省略" not in adopted
    # An unresolvable label falls back to the core set; never drops the
    # positive side entirely.
    fallback = render_writer_style_brief(["不存在的基因"])
    assert "- 学 " in fallback and "- 避 " in fallback


def test_voice_bible_checklist_derives_from_corpus():
    """The adoption checklist must not drift from the single-source library."""
    checklist = "\n".join(gene_checklist_lines())
    for gene in POSITIVE_STYLE_GENES:
        assert _gene_label_for_test(gene) in checklist
    bible = _memory_voice_bible_md("测试书", "都市")
    assert "规则怪谈" in bible or "看客留白" in bible
    assert len(gene_checklist_lines()) == len(POSITIVE_STYLE_GENES)


def _gene_label_for_test(gene: dict) -> str:
    return str(gene["source"]).split(" · ")[-1]


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
    """docs/46 A3: full corpus lives in style-reference.md; bible keeps a
    compact adoption checklist pointing at it."""
    from app.novel_forge.project_templates import _memory_style_reference_md

    bible = _memory_voice_bible_md("测试书", "都市")
    assert "## 本书采纳的风格基因" in bible
    assert "memory/style-reference.md" in bible
    assert "风格基因库（正例参照）" not in bible
    assert "AI 味对照清单" not in bible
    assert len(bible) < 3_600

    reference = _memory_style_reference_md()
    assert "## 风格基因库（正例参照）" in reference
    assert "## AI 味对照清单（反例禁则）" in reference
    assert "海明威 · 冰山省略" in reference
    assert "只学叙事功能、不抄任何措辞" in reference
    assert "密度才是破绽" in reference
