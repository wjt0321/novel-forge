"""Tests for the Drafting Readiness Gate (milestone 4/5)."""

from pathlib import Path

import pytest

from app.novel_forge.service import NovelForgeService
from app.novel_forge.skill_adapter import main
from tests.conftest import filled_scene_contract_v3, filled_voice_bible


def test_fresh_templates_are_not_ready(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is False
    assert any(b["code"] == "voice_bible_empty_narrative_distance" for b in readiness.blockers)
    assert any(b["code"] == "scene_contract_empty_scene_question" for b in readiness.blockers)
    # v3 template also blocks on new v3 fields.
    assert any(
        b["code"] == "scene_contract_empty_character_blindspot_or_pressure"
        for b in readiness.blockers
    )


def test_filled_assets_are_ready(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    sc_src = tmp_path / "sc.md"
    filled_scene_contract_v3(sc_src)
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is True
    assert readiness.blockers == []


def test_two_concrete_anchors_required(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    sc_src = tmp_path / "sc.md"
    sc_src.write_text(
        "# Scene Contract\n\n"
        "## scene_question\nq\n\n"
        "## viewpoint_character\nh\n\n"
        "## present_want\nw\n\n"
        "## opposing_force\no\n\n"
        "## irreversible_turn\ni\n\n"
        "## cost_or_tradeoff\nc\n\n"
        "## information_change\ni\n\n"
        "## emotional_shift\ne\n\n"
        "## concrete_anchor\n- one anchor\n\n"
        "## forbidden_easy_moves\nf\n\n"
        "## ending_pressure\ne\n\n"
        "## character_blindspot_or_pressure\np\n\n"
        "## irreversible_choice\nc\n\n"
        "## choice_consequence\nc\n\n"
        "## detail_payoff_plan\nnone\n\n"
        "## scene_necessity\nn\n\n"
        "## ending_change\nc\n\n"
        "---\n\n"
        "contract_version: 3\n",
        encoding="utf-8",
    )
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is False
    assert any(
        b["code"] == "scene_contract_insufficient_anchors" for b in readiness.blockers
    )


def test_v2_contract_warns_but_does_not_block_v3_fields(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    sc_src = tmp_path / "sc.md"
    # A v2 contract with all v2 fields filled.
    sc_src.write_text(
        "# Scene Contract\n\n"
        "## scene_question\nq\n\n"
        "## viewpoint_character\nh\n\n"
        "## present_want\nw\n\n"
        "## opposing_force\no\n\n"
        "## irreversible_turn\ni\n\n"
        "## cost_or_tradeoff\nc\n\n"
        "## information_change\ni\n\n"
        "## emotional_shift\ne\n\n"
        "## concrete_anchor\n- a\n- b\n\n"
        "## entry_late_exit_early_note\nn\n\n"
        "## continuity_dependencies\nn\n\n"
        "## forbidden_easy_moves\nf\n\n"
        "## ending_pressure\ne\n",
        encoding="utf-8",
    )
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is True
    assert any(w["code"] == "scene_contract_legacy_v2" for w in readiness.warnings)


def test_adapter_readiness_endpoint(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    code = main(["--root", str(tmp_path), "drafting-readiness", "test", "1"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    data = __import__("json").loads(out)
    assert data["ok"] is True
    assert data["data"]["readiness"]["ready"] is False
    assert "voice_bible_empty_narrative_distance" in [
        b["code"] for b in data["data"]["readiness"]["blockers"]
    ]
    # No asset full text in JSON.
    assert "close-third" not in out


def test_status_chapter_includes_readiness_summary(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    code = main(["--root", str(tmp_path), "status", "test", "1"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    data = __import__("json").loads(out)
    assert data["ok"] is True
    assert "drafting_readiness" in data["data"]
    assert data["data"]["drafting_readiness"]["ready"] is False
    assert "voice_bible_empty_narrative_distance" in data["data"]["drafting_readiness"]["blocker_codes"]
