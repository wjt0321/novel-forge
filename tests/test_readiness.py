"""Tests for the Drafting Readiness Gate (milestone 4/5)."""

from pathlib import Path

import pytest

from app.novel_forge.readiness import has_causal_chain, is_parameter_only_spatial_layout
from app.novel_forge.service import NovelForgeService
from app.novel_forge.skill_adapter import main
from tests.conftest import filled_scene_contract_v3, filled_scene_contract_v4, filled_voice_bible


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


def test_v4_contract_is_ready(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    sc_src = tmp_path / "sc.md"
    filled_scene_contract_v4(sc_src)
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is True
    assert readiness.blockers == []
    assert not any(
        w["code"].startswith("scene_contract_upgrade") for w in readiness.warnings
    )


def test_v4_missing_embodied_field_blocks(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    sc_src = tmp_path / "sc.md"
    filled_scene_contract_v4(sc_src)
    text = sc_src.read_text(encoding="utf-8")
    text = text.replace("## body_state_and_contacts\n", "")
    text = text.replace(
        "She is barefoot, shirt torn at the shoulder, left hand pressed against the wall to steady herself.\n\n",
        "",
    )
    sc_src.write_text(text, encoding="utf-8")
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is False
    assert any(
        b["code"] == "scene_contract_missing_body_state_and_contacts"
        for b in readiness.blockers
    )


def test_v4_insufficient_object_affordances_blocks(tmp_path: Path):
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
        "## concrete_anchor\n- a\n- b\n\n"
        "## forbidden_easy_moves\nf\n\n"
        "## ending_pressure\ne\n\n"
        "## character_blindspot_or_pressure\np\n\n"
        "## irreversible_choice\nc\n\n"
        "## choice_consequence\nc\n\n"
        "## detail_payoff_plan\nnone\n\n"
        "## scene_necessity\nn\n\n"
        "## ending_change\nc\n\n"
        "## spatial_layout_and_routes\nleft of the door is the window\n\n"
        "## body_state_and_contacts\nhurt hand\n\n"
        "## object_affordances\n- one object\n\n"
        "## environmental_constraints\nwet floor causes slip\n\n"
        "## embodied_action_chain\n- step one\n- step two\n- step three\n\n"
        "---\n\n"
        "contract_version: 4\n",
        encoding="utf-8",
    )
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is False
    assert any(
        b["code"] == "scene_contract_insufficient_object_affordances"
        for b in readiness.blockers
    )


def test_v4_insufficient_embodied_action_chain_blocks(tmp_path: Path):
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
        "## concrete_anchor\n- a\n- b\n\n"
        "## forbidden_easy_moves\nf\n\n"
        "## ending_pressure\ne\n\n"
        "## character_blindspot_or_pressure\np\n\n"
        "## irreversible_choice\nc\n\n"
        "## choice_consequence\nc\n\n"
        "## detail_payoff_plan\nnone\n\n"
        "## scene_necessity\nn\n\n"
        "## ending_change\nc\n\n"
        "## spatial_layout_and_routes\nleft of the door is the window\n\n"
        "## body_state_and_contacts\nhurt hand\n\n"
        "## object_affordances\n- a\n- b\n\n"
        "## environmental_constraints\nwet floor causes slip\n\n"
        "## embodied_action_chain\n- step one\n- step two\n\n"
        "---\n\n"
        "contract_version: 4\n",
        encoding="utf-8",
    )
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is False
    assert any(
        b["code"] == "scene_contract_insufficient_embodied_action_chain"
        for b in readiness.blockers
    )


def test_v4_parameter_only_spatial_layout_blocks(tmp_path: Path):
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
        "## concrete_anchor\n- a\n- b\n\n"
        "## forbidden_easy_moves\nf\n\n"
        "## ending_pressure\ne\n\n"
        "## character_blindspot_or_pressure\np\n\n"
        "## irreversible_choice\nc\n\n"
        "## choice_consequence\nc\n\n"
        "## detail_payoff_plan\nnone\n\n"
        "## scene_necessity\nn\n\n"
        "## ending_change\nc\n\n"
        "## spatial_layout_and_routes\n"
        "20 square meters. Length 5m, width 4m, height 3m. 100 meters from the exit.\n\n"
        "## body_state_and_contacts\nhurt hand\n\n"
        "## object_affordances\n- a\n- b\n\n"
        "## environmental_constraints\nwet floor causes slip\n\n"
        "## embodied_action_chain\n- s1\n- s2\n- s3\n\n"
        "---\n\n"
        "contract_version: 4\n",
        encoding="utf-8",
    )
    svc.write_scene_contract("test", 1, sc_src)

    readiness = svc.assess_drafting_readiness("test", 1)
    assert readiness.ready is False
    assert any(
        b["code"] == "scene_contract_spatial_layout_parameter_only"
        for b in readiness.blockers
    )


def test_v3_contract_warns_upgrade_to_v4_and_remains_ready(tmp_path: Path):
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
    assert any(
        w["code"] == "scene_contract_upgrade_to_v4" for w in readiness.warnings
    )


def test_fresh_v4_template_blocks_on_embodied_fields(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    readiness = svc.assess_drafting_readiness("test", 1)

    assert readiness.ready is False
    codes = [b["code"] for b in readiness.blockers]
    assert "scene_contract_insufficient_object_affordances" in codes
    assert "scene_contract_insufficient_embodied_action_chain" in codes
    assert "scene_contract_empty_spatial_layout_and_routes" in codes
    assert "scene_contract_empty_body_state_and_contacts" in codes
    assert "scene_contract_empty_environmental_constraints" in codes


def test_chinese_parameter_only_spatial_layout_blocks():
    text = "房间约 20 平方米，长 5 米、宽 4 米，高度 3 米。"
    assert is_parameter_only_spatial_layout(text) is True


def test_chinese_spatial_with_relative_positions_not_blocked():
    text = "主角背对门，左侧三步外是碎玻璃窗台，房间只有 20 平方米。"
    assert is_parameter_only_spatial_layout(text) is False


def test_environmental_constraint_without_causal_marker_is_missing_causal_chain():
    text = "地板很湿，她走得很慢。"
    assert has_causal_chain(text) is False


def test_environmental_constraint_with_arrow_or_因果词_passes():
    assert has_causal_chain("地板潮湿 → 她一步打滑 → 撞碎了窗台。") is True
    assert has_causal_chain("湿地板导致她失去平衡。") is True
