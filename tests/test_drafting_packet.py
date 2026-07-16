"""Tests for the Drafting Packet (milestone 3) context builder."""

import json
from pathlib import Path

import pytest

from app.novel_forge.autonomous import AutonomousWritingService
from app.novel_forge.service import NovelForgeError, NovelForgeService
from app.novel_forge.skill_adapter import main
from tests.conftest import (
    filled_scene_contract_v3,
    filled_scene_contract_v4,
    filled_voice_bible,
    ready_memo,
)


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def _setup_ready_book(svc: NovelForgeService, root: Path) -> None:
    """Create a book/ch1/ch2 with filled Voice Bible and Scene Contracts."""
    svc.init_book("test", "Test Book")

    vb_src = root / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    # Chapter 1: approved body with enough text to test truncation.
    svc.create_chapter("test", 1, "One")
    ch1_body = root / "ch1.md"
    ch1_body.write_text("开始。" + "正文长段落。" * 200 + "结尾。\n", encoding="utf-8")
    svc.write_revision("test", 1, ch1_body)
    svc.lint_chapter("test", 1)
    ready_memo(svc, "test", 1)
    svc.review_chapter("test", 1)
    svc.approve_chapter("test", 1, "ok")

    # Approved canon fact.
    fact_id = svc.add_candidate_fact(
        "test", 1, "trait", "hero", "age", "30", "chapter 1"
    )
    svc.approve_fact(fact_id)

    # Chapter 2: custom scene contract.
    svc.create_chapter("test", 2, "Two")
    sc_src = root / "sc2.md"
    filled_scene_contract_v3(sc_src)
    svc.write_scene_contract("test", 2, sc_src, note="custom")


def test_build_drafting_packet_success(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    output = tmp_path / "drafts" / "ch2-packet.md"
    packet = svc.build_drafting_packet(
        "test", 2, output, note="first pass", previous_context_chars=50
    )

    assert packet.book_slug == "test"
    assert packet.chapter_number == 2
    assert output.exists()
    text = output.read_text(encoding="utf-8")

    assert "# Drafting Packet: Test Book — Chapter 2: Two" in text
    assert "## Writer Operating Contract" in text
    assert "## Voice Bible" in text
    assert "close-third limited" in text
    assert "## Scene Contract" in text
    assert "Can she escape?" in text
    assert "## Approved Canon Facts" in text
    assert "hero age" in text
    assert "object: 30" in text
    assert "## Predecessor Context (approved chapter 1, last 50 characters)" in text
    assert "This is a continuity hand-off fragment" in text
    assert "## Delivery Checklist" in text
    assert "readiness_ready: True" in text

    # Predecessor text is capped.
    code_start = text.find("```", text.find("## Predecessor Context")) + 3
    code_end = text.find("```", code_start)
    predecessor_excerpt = text[code_start:code_end].strip()
    assert len(predecessor_excerpt) <= 50

    # Chapter state unchanged.
    ch2 = svc.get_chapter("test", 2)
    assert ch2.state.value == "draft"

    # Audit recorded.
    events = [e for e in svc.audit("test") if e.action == "build" and e.entity_type == "drafting_packet"]
    assert len(events) == 1
    assert "ch2-packet.md" in events[0].details


def test_build_drafting_packet_external_output_path(tmp_path: Path):
    """External output paths (outside project root) must be supported."""
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    external_dir = tmp_path.parent / "external-drafts"
    output = external_dir / "ch2-packet.md"
    packet = svc.build_drafting_packet(
        "test", 2, output, note="external draft", previous_context_chars=100
    )

    assert output.exists()
    assert Path(packet.absolute_path) == output.resolve()
    # Outside project root: recorded as absolute path.
    assert Path(packet.file_path).is_absolute()
    assert str(output.resolve()) == packet.file_path

    text = output.read_text(encoding="utf-8")
    assert "readiness_ready: True" in text
    assert "## Predecessor Context (approved chapter 1, last 100 characters)" in text

    # Audit records the external path, no traceback.
    events = [e for e in svc.audit("test") if e.action == "build" and e.entity_type == "drafting_packet"]
    assert len(events) == 1
    details = json.loads(events[0].details)
    assert Path(details["output_file"]).is_absolute()
    assert details["output_file"] == str(output.resolve())
    assert details["output_hash"] == packet.content_hash


def test_build_drafting_packet_missing_scene_contract(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    # Remove the scene contract row and file to simulate a corrupted/missing contract.
    import sqlite3
    from app.novel_forge.db import get_db_path

    db_path = get_db_path(tmp_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DELETE FROM scene_contracts WHERE chapter_id = 1")
        conn.execute("DELETE FROM scene_contract_revisions WHERE chapter_id = 1")
        conn.commit()

    output = tmp_path / "drafts" / "ch1-packet.md"
    with pytest.raises(NovelForgeError, match="scene_contract_missing"):
        svc.build_drafting_packet("test", 1, output)


def test_build_drafting_packet_rejects_library_output(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    output = tmp_path / "library" / "packet.md"
    with pytest.raises(NovelForgeError, match="library"):
        svc.build_drafting_packet("test", 1, output, allow_incomplete=True)


def test_build_drafting_packet_rejects_existing_output(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    output = tmp_path / "packet.md"
    output.write_text("already here", encoding="utf-8")
    with pytest.raises(NovelForgeError, match="already exists"):
        svc.build_drafting_packet("test", 1, output, allow_incomplete=True)


def test_build_drafting_packet_rejects_relative_output(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    with pytest.raises(NovelForgeError, match="absolute path"):
        svc.build_drafting_packet("test", 1, Path("packet.md"), allow_incomplete=True)


@pytest.mark.parametrize("chars", [-1, 4001])
def test_build_drafting_packet_rejects_invalid_context_range(tmp_path: Path, chars: int):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    output = tmp_path / "packet.md"
    with pytest.raises(NovelForgeError, match="previous_context_chars"):
        svc.build_drafting_packet("test", 1, output, previous_context_chars=chars, allow_incomplete=True)


def test_build_drafting_packet_skips_unapproved_predecessor(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    # Chapter 1 stays draft.
    svc.create_chapter("test", 1, "One")
    ch1_body = tmp_path / "ch1.md"
    ch1_body.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, ch1_body)

    svc.create_chapter("test", 2, "Two")
    sc_src = tmp_path / "sc2.md"
    filled_scene_contract_v3(sc_src)
    svc.write_scene_contract("test", 2, sc_src)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output, previous_context_chars=50)
    text = output.read_text(encoding="utf-8")
    assert "## Predecessor Context" not in text


def test_default_previous_context_chars_is_1200(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    output = tmp_path / "ch2-packet.md"
    # Do not pass previous_context_chars; should default to 1200.
    svc.build_drafting_packet("test", 2, output)
    text = output.read_text(encoding="utf-8")

    assert "last 1200 characters" in text
    code_start = text.find("```", text.find("## Predecessor Context")) + 3
    code_end = text.find("```", code_start)
    predecessor_excerpt = text[code_start:code_end].strip()
    assert len(predecessor_excerpt) <= 1200
    assert len(predecessor_excerpt) > 100  # sanity: actually got context


def test_upper_bound_4000_allowed(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output, previous_context_chars=4000)
    text = output.read_text(encoding="utf-8")
    assert "last 4000 characters" in text


def test_build_blocked_without_output_or_audit(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    output = tmp_path / "packet.md"
    with pytest.raises(NovelForgeError, match="Drafting readiness gate blocked"):
        svc.build_drafting_packet("test", 1, output)

    assert not output.exists()
    events = [e for e in svc.audit("test") if e.action == "build" and e.entity_type == "drafting_packet"]
    assert len(events) == 0


def test_allow_incomplete_builds_and_marks_packet(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    output = tmp_path / "packet.md"
    packet = svc.build_drafting_packet(
        "test", 1, output, allow_incomplete=True
    )
    assert packet.book_slug == "test"
    assert output.exists()

    text = output.read_text(encoding="utf-8")
    assert "> **READINESS BYPASSED**" in text
    assert "voice_bible_empty_narrative_distance" in text


def test_adapter_build_drafting_packet_requires_confirm_and_no_content(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    output = tmp_path / "packet.md"

    # Missing confirmation.
    code = main(
        [
            "--root",
            str(tmp_path),
            "build-drafting-packet",
            "test",
            "1",
            "--output-file",
            str(output),
            "--allow-incomplete",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"
    assert not output.exists()

    # Confirmed success (with bypass because assets are incomplete).
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "build-drafting-packet",
            "build-drafting-packet",
            "test",
            "1",
            "--output-file",
            str(output),
            "--allow-incomplete",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["operation"] == "build-drafting-packet"
    assert data["state_changed"] is False
    assert "packet" in data["data"]
    assert data["data"]["readiness_bypassed"] is True
    assert data["data"]["packet"]["book_slug"] == "test"
    assert data["data"]["packet"]["chapter_number"] == 1

    # JSON must not contain the packet Markdown body or source contract text.
    json_text = json.dumps(data)
    assert "Writer Operating Contract" not in json_text
    assert "## Scene Contract" not in json_text
    assert output.exists()


def test_adapter_build_drafting_packet_external_output_path(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    # Use a unique sibling directory to avoid collisions with other tests.
    external_dir = tmp_path.parent / f"external-drafts-{tmp_path.name}"
    output = external_dir / "ch2-packet.md"

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "build-drafting-packet",
            "build-drafting-packet",
            "test",
            "2",
            "--output-file",
            str(output),
            "--previous-context-chars",
            "100",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["packet"]["file_path"] == str(output.resolve())
    assert Path(data["data"]["packet"]["absolute_path"]).is_absolute()
    assert data["data"]["readiness_bypassed"] is False

    assert output.exists()
    json_text = json.dumps(data)
    assert "Writer Operating Contract" not in json_text
    assert "## Scene Contract" not in json_text


# ------------------------------------------------------------------
# RTCO P0/P1/P2 layer tests
# ------------------------------------------------------------------

def _auto(root: Path) -> AutonomousWritingService:
    return AutonomousWritingService(root)


def test_packet_has_p0_p1_p2_sections(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output)
    text = output.read_text(encoding="utf-8")

    assert "## P0" in text or "## P0 — Core" in text
    assert "## P1" in text or "## P1 — Important Context" in text
    assert "## P2" in text or "## P2 — Reference" in text


def test_p0_contains_scene_contract_and_predecessor(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output, previous_context_chars=50)
    text = output.read_text(encoding="utf-8")

    # P0 must include the scene contract and predecessor anchor.
    p0_start = text.find("## P0")
    p1_start = text.find("## P1")
    p0_text = text[p0_start:p1_start]
    assert "## Scene Contract" in p0_text
    assert "Can she escape?" in p0_text
    assert "## Predecessor Context" in p0_text
    assert "This is a continuity hand-off fragment" in p0_text


def test_p1_contains_approved_canon(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output)
    text = output.read_text(encoding="utf-8")

    p1_start = text.find("## P1")
    p2_start = text.find("## P2")
    p1_text = text[p1_start:p2_start]
    assert "## Approved Canon Facts" in p1_text
    assert "hero age" in p1_text


def test_p2_lists_unfulfilled_promises_for_this_chapter(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)
    auto = _auto(tmp_path)

    # Promise due in chapter 2 (must resolve now).
    auto.add_promise(
        "test",
        "the back door must be opened",
        target_chapter_number=2,
        target_scene_ref="s2",
    )
    # Promise due in chapter 1 (overdue).
    auto.add_promise(
        "test",
        "the rusty key must be found",
        target_chapter_number=1,
        target_scene_ref="s1",
    )
    # Promise due in chapter 3 (future, should not appear).
    auto.add_promise(
        "test",
        "the pursuers catch up",
        target_chapter_number=3,
        target_scene_ref="s3",
    )

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output)
    text = output.read_text(encoding="utf-8")

    p2_start = text.find("## P2")
    p2_text = text[p2_start:]
    assert "the back door must be opened" in p2_text
    assert "the rusty key must be found" in p2_text
    assert "the pursuers catch up" not in p2_text
    assert "Must Resolve" in p2_text
    assert "Overdue" in p2_text


def test_p2_falls_back_to_all_open_promises_when_no_target(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)
    auto = _auto(tmp_path)

    auto.add_promise("test", "unscoped promise", target_chapter_number=None)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output)
    text = output.read_text(encoding="utf-8")

    p2_start = text.find("## P2")
    p2_text = text[p2_start:]
    assert "unscoped promise" in p2_text
    assert "conservative" in p2_text or "unscoped" in p2_text


def test_build_drafting_packet_includes_scene_embodiment_model_and_constraints(
    tmp_path: Path,
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    vb_src = tmp_path / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    ch1_body = tmp_path / "ch1.md"
    ch1_body.write_text("开始。" + "正文长段落。" * 200 + "结尾。\n", encoding="utf-8")
    svc.write_revision("test", 1, ch1_body)
    svc.lint_chapter("test", 1)
    ready_memo(svc, "test", 1)
    svc.review_chapter("test", 1)
    svc.approve_chapter("test", 1, "ok")

    svc.create_chapter("test", 2, "Two")
    sc_src = tmp_path / "sc2.md"
    filled_scene_contract_v4(sc_src)
    svc.write_scene_contract("test", 2, sc_src)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output)
    text = output.read_text(encoding="utf-8")

    assert "## P0" in text or "## P0 — Core" in text
    assert "### Scene Embodiment Model" in text
    assert "spatial_layout_and_routes" in text
    assert "body_state_and_contacts" in text
    assert "object_affordances" in text
    assert "environmental_constraints" in text
    assert "embodied_action_chain" in text
    assert "不得用参数替代画面" in text
    assert "开场能定位身体与关键物体" in text
    assert "至少一项环境约束真实改变动作" in text
    assert "不可逆选择由连续身体动作触发" in text


def test_scene_embodiment_model_for_legacy_contract_prohibits_inference(
    tmp_path: Path,
):
    svc = NovelForgeService(tmp_path)
    _setup_ready_book(svc, tmp_path)

    output = tmp_path / "ch2-packet.md"
    svc.build_drafting_packet("test", 2, output)
    text = output.read_text(encoding="utf-8")

    sem_start = text.find("### Scene Embodiment Model")
    assert sem_start != -1
    sem_text = text[sem_start: text.find("### Chapter Goal", sem_start)]
    assert "do not infer" in sem_text
    assert "upgrade the Scene Contract" in sem_text
    # Missing-field bullets in a ready/legacy packet must not use exploration-mode wording.
    assert "not specified — do not infer; upgrade the Scene Contract" in sem_text
    assert "not specified — exploration mode" not in sem_text


def test_scene_embodiment_model_in_exploration_mode_marks_gap(
    tmp_path: Path,
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    output = tmp_path / "packet.md"
    svc.build_drafting_packet("test", 1, output, allow_incomplete=True)
    text = output.read_text(encoding="utf-8")

    assert "> **READINESS BYPASSED**" in text
    sem_start = text.find("### Scene Embodiment Model")
    assert sem_start != -1
    sem_text = text[sem_start: text.find("### Chapter Goal", sem_start)]
    assert "exploration mode" in sem_text
    assert "do not infer" in sem_text
    assert "fix before final draft" in sem_text
