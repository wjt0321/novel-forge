"""Tests for the v4 autonomous research-to-fiction service layer."""

import subprocess
from pathlib import Path

import pytest

from app.novel_forge.autonomous import AutonomousError, AutonomousWritingService
from app.novel_forge.models import ScenePlan
from app.novel_forge.service import NovelForgeService
from tests.conftest import (
    filled_scene_contract_v3,
    filled_voice_bible,
    ready_memo,
)


def _make_five_thousand_han() -> str:
    """Return a string with at least 5000 CJK Han characters."""
    return "文字" * 2600


def _make_revision_file(root: Path, slug: str, number: int, body: str) -> Path:
    svc = NovelForgeService(root)
    src = root / f"chapter-{number}-source.md"
    src.write_text(body, encoding="utf-8")
    svc.write_revision(slug, number, src, note="test revision")
    return src


def _filled_book(service: NovelForgeService, slug: str = "auto") -> None:
    """Initialize a book and fill its Voice Bible."""
    service.init_book(slug, "Auto Book")
    vb_src = service.root / "voice-bible.md"
    filled_voice_bible(vb_src)
    service.write_voice_bible(slug, vb_src, note="filled")


def _filled_chapter(
    service: NovelForgeService, slug: str = "auto", number: int = 1
) -> None:
    """Create a chapter with a filled v3 scene contract."""
    service.create_chapter(slug, number, f"Chapter {number}")
    sc_src = service.root / f"scene-contract-{number}.md"
    filled_scene_contract_v3(sc_src)
    service.write_scene_contract(slug, number, sc_src, note="filled")


def _four_scene_plan() -> list[ScenePlan]:
    return [
        ScenePlan(
            scene_ref="s1",
            goal="enter",
            obstacle="guard",
            choice="bribe",
            cost="money",
            ending_change="inside",
            promises=["promise-a"],
        ),
        ScenePlan(
            scene_ref="s2",
            goal="find",
            obstacle="dark",
            choice="light match",
            cost="exposed",
            ending_change="sees clue",
        ),
        ScenePlan(
            scene_ref="s3",
            goal="escape",
            obstacle="trap",
            choice="jump",
            cost="injury",
            ending_change="flees",
        ),
        ScenePlan(
            scene_ref="s4",
            goal="hide",
            obstacle="tracker",
            choice="split up",
            cost="alone",
            ending_change="isolated",
            promises=["promise-a"],
        ),
    ]


# ------------------------------------------------------------------
# Research ledger
# ------------------------------------------------------------------

def test_add_and_list_research_entry(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = AutonomousWritingService(service.root)
    entry = auto.add_research_entry(
        "auto",
        url="https://example.com/fact",
        retrieved_at="2026-07-15T00:00:00Z",
        source_type="official",
        confidence="A",
        claim="Mount Fuji is 3776m.",
        allowed_use="background_only",
        fiction_boundary="Real mountain; fictional climbers may be invented.",
    )
    assert entry.book_id == service.get_book("auto").id
    assert entry.confidence == "A"

    entries = auto.list_research_entries("auto")
    assert len(entries) == 1
    assert entries[0].claim == "Mount Fuji is 3776m."


def test_unresolved_plot_support_blocks_acceptance(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    auto.add_research_entry(
        "auto",
        url="https://example.com/unresolved",
        retrieved_at="2026-07-15T00:00:00Z",
        source_type="news",
        confidence="C",
        claim="A storm will strike.",
        allowed_use="plot_support",
        fiction_boundary="Unresolved; do not hinge plot on it.",
        unresolved=True,
    )
    result = auto.check_auto_acceptance("auto", 1)
    assert result.checks["unresolved_plot_support"] == 1
    assert result.decision == "revision_required"


# ------------------------------------------------------------------
# Story engine
# ------------------------------------------------------------------

def test_set_and_get_story_engine(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = AutonomousWritingService(service.root)
    engine = auto.set_story_engine(
        "auto",
        secret="He is the traitor's son",
        desire="prove loyalty",
        alternative_actions=["flee", "confess", "silence witness"],
        irreversible_choice="warn the target",
        immediate_cost="loses his handler's trust",
        thematic_pressure="no one is allowed a second chance",
    )
    assert engine.secret == "He is the traitor's son"
    assert engine.alternative_actions == ["flee", "confess", "silence witness"]

    fetched = auto.get_story_engine("auto")
    assert fetched is not None
    assert fetched.desire == "prove loyalty"


def test_story_engine_rejects_empty_field(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = AutonomousWritingService(service.root)
    with pytest.raises(AutonomousError, match="cannot be empty"):
        auto.set_story_engine(
            "auto",
            secret="",
            desire="prove loyalty",
            alternative_actions=["flee"],
            irreversible_choice="warn",
            immediate_cost="cost",
            thematic_pressure="pressure",
        )


# ------------------------------------------------------------------
# Chapter plan and promise ledger
# ------------------------------------------------------------------

def test_set_and_get_chapter_plan(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    scenes = _four_scene_plan()
    plan = auto.set_chapter_plan("auto", 1, scenes, status="approved_for_writing")
    assert len(plan.scenes) == 4
    assert plan.status == "approved_for_writing"

    fetched = auto.get_chapter_plan("auto", 1)
    assert fetched is not None
    assert fetched.scenes[0].goal == "enter"


def test_chapter_plan_rejects_too_few_scenes(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    with pytest.raises(AutonomousError, match="4-6 scenes"):
        auto.set_chapter_plan("auto", 1, _four_scene_plan()[:2])


def test_chapter_plan_creates_promises(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    auto.set_chapter_plan("auto", 1, _four_scene_plan())
    promises = auto.list_promises("auto")
    assert any(p.promise_text == "promise-a" for p in promises)


def test_update_promise_status(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    auto.set_chapter_plan("auto", 1, _four_scene_plan())
    promise = next(p for p in auto.list_promises("auto") if p.promise_text == "promise-a")
    updated = auto.update_promise_status(
        "auto", promise.id, "resolved", scene_ref="s4", resolution_note="paid off"
    )
    assert updated.status == "resolved"
    assert updated.resolved_scene_ref == "s4"


# ------------------------------------------------------------------
# Iteration runs
# ------------------------------------------------------------------

def test_record_and_list_iteration_runs(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    run = auto.start_iteration_run(
        "auto",
        1,
        writer_role="writer_v1",
        editor_verdict="revision_required",
        blocking_issues=[
            {
                "location": "line 12",
                "evidence": "too much exposition",
                "effect": "reader loses tension",
                "revision_intent": "compress into action",
            }
        ],
        revision_targets=["trim exposition", "raise stakes"],
        word_count=1200,
        status="completed",
    )
    assert run.round_number == 1
    assert run.editor_role == "independent_reader_editor"

    runs = auto.list_iteration_runs("auto", 1)
    assert len(runs) == 1
    assert runs[0].writer_role == "writer_v1"


# ------------------------------------------------------------------
# Auto acceptance
# ------------------------------------------------------------------

def _four_scene_plan_no_promises() -> list[ScenePlan]:
    return [
        ScenePlan(scene_ref="s1", goal="enter", obstacle="guard", choice="bribe", cost="money", ending_change="inside"),
        ScenePlan(scene_ref="s2", goal="find", obstacle="dark", choice="light match", cost="exposed", ending_change="sees clue"),
        ScenePlan(scene_ref="s3", goal="escape", obstacle="trap", choice="jump", cost="injury", ending_change="flees"),
        ScenePlan(scene_ref="s4", goal="hide", obstacle="tracker", choice="split up", cost="alone", ending_change="isolated"),
    ]


def test_auto_acceptance_ready(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)

    # Plan and revision (no promises so the promise ledger is clean).
    auto.set_chapter_plan("auto", 1, _four_scene_plan_no_promises())
    body = _make_five_thousand_han()
    _make_revision_file(service.root, "auto", 1, body)

    # Editorial memo ready.
    ready_memo(service, "auto", 1)

    # At least one independent edit round is required.
    auto.start_iteration_run(
        "auto",
        1,
        writer_role="writer_v1",
        editor_verdict="ready_for_human_editor_decision",
        blocking_issues=[],
        revision_targets=[],
        word_count=5000,
        status="completed",
    )

    result = auto.check_auto_acceptance("auto", 1)
    assert result.decision == "autonomous_acceptance_complete"
    assert result.checks["word_count_ok"] is True
    assert result.checks["scene_count_ok"] is True
    assert result.checks["independent_editorial_status"] == "ready"
    assert result.checks["promises_ok"] is True


def test_auto_acceptance_detects_prose_edit_concerns(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    auto.set_chapter_plan("auto", 1, _four_scene_plan_no_promises())

    # Body with many short paragraphs to trigger rhythm-monotony / explanatory-punchline.
    body = "\n\n".join(["文字。"] * 2600)
    _make_revision_file(service.root, "auto", 1, body)

    ready_memo(service, "auto", 1)
    auto.start_iteration_run(
        "auto",
        1,
        writer_role="writer_v1",
        editor_verdict="ready_for_human_editor_decision",
        blocking_issues=[],
        revision_targets=[],
        word_count=5200,
        status="completed",
    )

    result = auto.check_auto_acceptance("auto", 1)
    assert result.checks["word_count_ok"] is True
    assert result.checks["prose_edit_status"] == "concerns"
    assert result.checks["prose_edit_findings"] > 0
    assert result.decision == "revision_required"


def test_auto_acceptance_revise_when_missing_plan(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    _make_revision_file(service.root, "auto", 1, _make_five_thousand_han())
    ready_memo(service, "auto", 1)
    auto = AutonomousWritingService(service.root)
    result = auto.check_auto_acceptance("auto", 1)
    assert result.decision == "revision_required"
    assert result.checks["has_plan"] is False


def test_auto_acceptance_fails_after_max_rounds(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    for i in range(3):
        auto.start_iteration_run(
            "auto",
            1,
            writer_role=f"writer_{i}",
            editor_verdict="revision_required",
            blocking_issues=[],
            revision_targets=["fix"],
            word_count=100,
            status="completed",
        )
    result = auto.check_auto_acceptance("auto", 1, max_rounds=3)
    assert result.decision == "failed_needs_human"
    assert result.checks["max_rounds"] == 3


def test_bc_plot_support_without_verified_a_reference_blocks_acceptance(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    auto.set_chapter_plan("auto", 1, _four_scene_plan_no_promises())
    _make_revision_file(service.root, "auto", 1, _make_five_thousand_han())
    ready_memo(service, "auto", 1)
    auto.start_iteration_run(
        "auto",
        1,
        writer_role="writer_v1",
        editor_verdict="ready_for_human_editor_decision",
        blocking_issues=[],
        revision_targets=[],
        word_count=5000,
        status="completed",
    )

    auto.add_research_entry(
        "auto",
        url="https://example.com/bc",
        retrieved_at="2026-07-15T00:00:00Z",
        source_type="news",
        confidence="B",
        claim="A questionable plot fact.",
        allowed_use="plot_support",
        fiction_boundary="Needs corroboration.",
    )

    result = auto.check_auto_acceptance("auto", 1)
    assert result.decision == "revision_required"
    assert result.checks["bc_plot_support_ok"] is False


def test_bc_plot_support_with_verified_a_reference_passes(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    auto.set_chapter_plan("auto", 1, _four_scene_plan_no_promises())
    _make_revision_file(service.root, "auto", 1, _make_five_thousand_han())
    ready_memo(service, "auto", 1)
    auto.start_iteration_run(
        "auto",
        1,
        writer_role="writer_v1",
        editor_verdict="ready_for_human_editor_decision",
        blocking_issues=[],
        revision_targets=[],
        word_count=5000,
        status="completed",
    )

    a_entry = auto.add_research_entry(
        "auto",
        url="https://example.com/a",
        retrieved_at="2026-07-15T00:00:00Z",
        source_type="official",
        confidence="A",
        claim="A verified plot fact.",
        allowed_use="plot_support",
        fiction_boundary="Verified fact.",
        verification_state="verified",
    )
    auto.add_research_entry(
        "auto",
        url="https://example.com/bc",
        retrieved_at="2026-07-15T00:00:00Z",
        source_type="news",
        confidence="B",
        claim="A questionable plot fact.",
        allowed_use="plot_support",
        fiction_boundary="Corroborated by A source.",
        verification_ref=a_entry.id,
    )

    result = auto.check_auto_acceptance("auto", 1)
    assert result.decision == "autonomous_acceptance_complete"
    assert result.checks["bc_plot_support_ok"] is True


def test_writer_role_cannot_be_independent_reader_editor(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    _filled_chapter(service)
    auto = AutonomousWritingService(service.root)
    with pytest.raises(AutonomousError, match="independent_reader_editor"):
        auto.start_iteration_run(
            "auto",
            1,
            writer_role="independent_reader_editor",
            editor_verdict="revision_required",
            blocking_issues=[],
            revision_targets=["fix"],
            word_count=100,
            status="completed",
        )


# ------------------------------------------------------------------
# Git checkpoint
# ------------------------------------------------------------------

def test_git_checkpoint_stages_book_files(service: NovelForgeService) -> None:
    _filled_book(service)
    subprocess.run(
        ["git", "init", "-q"], cwd=str(service.root), check=True, capture_output=True
    )
    auto = AutonomousWritingService(service.root)
    result = auto.git_checkpoint("auto", "test checkpoint")
    assert result["committed"] is True
    assert result["commit_hash"] is not None


def test_git_checkpoint_no_changes(service: NovelForgeService) -> None:
    _filled_book(service)
    subprocess.run(
        ["git", "init", "-q"], cwd=str(service.root), check=True, capture_output=True
    )
    auto = AutonomousWritingService(service.root)
    auto.git_checkpoint("auto", "first")
    result = auto.git_checkpoint("auto", "second")
    assert result["committed"] is False
    assert "No changes" in result["message"]


def test_git_checkpoint_requires_git_repo(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = AutonomousWritingService(service.root)
    with pytest.raises(AutonomousError, match="git worktree"):
        auto.git_checkpoint("auto", "not in repo")


def test_git_checkpoint_rejects_empty_or_control_message(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    subprocess.run(
        ["git", "init", "-q"], cwd=str(service.root), check=True, capture_output=True
    )
    auto = AutonomousWritingService(service.root)
    with pytest.raises(AutonomousError, match="empty"):
        auto.git_checkpoint("auto", "")
    with pytest.raises(AutonomousError, match="control characters"):
        auto.git_checkpoint("auto", "bad\x00message")


def test_git_checkpoint_only_stages_book_scope(service: NovelForgeService) -> None:
    _filled_book(service)
    subprocess.run(
        ["git", "init", "-q"], cwd=str(service.root), check=True, capture_output=True
    )
    # Create a global docs change that should NOT be staged.
    global_doc = service.root / "docs" / "global.md"
    global_doc.parent.mkdir(parents=True, exist_ok=True)
    global_doc.write_text("global change", encoding="utf-8")

    auto = AutonomousWritingService(service.root)
    result = auto.git_checkpoint("auto", "book only")
    assert result["committed"] is True

    # The global docs file must remain untracked/unstaged.
    status_proc = subprocess.run(
        ["git", "status", "--porcelain", "--", str(global_doc)],
        cwd=str(service.root),
        capture_output=True,
        text=True,
        check=False,
    )
    # Untracked files show as "??"; if it had been staged it would be "A".
    assert "??" in status_proc.stdout or status_proc.stdout.strip() == ""


def test_git_checkpoint_rejects_non_empty_index(service: NovelForgeService) -> None:
    _filled_book(service)
    subprocess.run(
        ["git", "init", "-q"], cwd=str(service.root), check=True, capture_output=True
    )

    # Pre-stage an out-of-scope file.
    secret_file = service.root / "data" / "secret.txt"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret_file.write_text("secret", encoding="utf-8")
    subprocess.run(
        ["git", "add", "--", str(secret_file)],
        cwd=str(service.root),
        check=True,
        capture_output=True,
    )

    auto = AutonomousWritingService(service.root)
    with pytest.raises(AutonomousError, match="Git index is not empty"):
        auto.git_checkpoint("auto", "should fail")

    # The pre-staged file must remain staged (we did not reset the index).
    status_proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(service.root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert "secret.txt" in status_proc.stdout
