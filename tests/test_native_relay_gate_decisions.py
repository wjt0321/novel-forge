"""Regression tests for docs/49 P0-1/P0-2.

P0-1: hard-gate failures on the lean native_relay chain must route to an
author-decidable (authorizable) decision instead of crashing the CLI or
deadlocking the chapter. P0-2: review certification must pass before any
promotion side effect (formal chapter, generation, receipt, checkpoint).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.novel_forge.workflow as workflow_module
from app.novel_forge import book_project
from app.novel_forge.book_git import BookGitError, book_git_status
from app.novel_forge.book_project import BookProjectError
from app.novel_forge.native_relay import NativeWorkflowRelay
from app.novel_forge.workflow import WorkflowError
from tests.test_native_relay import _complete_minimal, _request
from tests.test_workflow import _prose


def _short_prose() -> str:
    return "# 第一章 门后\n\n林舟握住门把，听见脚步逼近。\n\n他没有回头。\n"


def _blind_pass(**overrides) -> dict:
    payload = {
        "verdict": "pass",
        "must": [],
        "human_likeness": "convincing",
        "reader_desire": "continue",
        "emotional_residue": "人物选择留下明确余波。",
        "next_chapter_pull": "下一章的代价仍未揭开。",
        "summary": "空间、行动和情绪都可以重建。",
        "evidence_quote": "林舟握住门把",
    }
    payload.update(overrides)
    return payload


def _editor_pass(**overrides) -> dict:
    payload = {
        "verdict": "pass",
        "must": [],
        "summary": "因果、选择、对白、肌理和连续性成立。",
        "evidence_quote": "林舟握住门把",
    }
    payload.update(overrides)
    return payload


def _start_lean_with_prose(relay: NativeWorkflowRelay, slug: str, prose: str):
    relay.start(slug, _request(), chapter=1)
    action = relay.next_action(slug)
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        prose,
        encoding="utf-8",
    )
    return _complete_minimal(relay, slug)


def _complete_reviews(
    relay: NativeWorkflowRelay,
    slug: str,
    blind_payload: dict | None = None,
    editor_payload: dict | None = None,
):
    result = None
    for role, payload in (
        ("blind-reader", blind_payload or _blind_pass()),
        ("chapter-editor", editor_payload or _editor_pass()),
    ):
        action = relay.next_action(slug)
        assert action["role"] == role
        Path(action["result_file"]).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        result = _complete_minimal(relay, slug)
    return result


def _formal_chapter(root: Path) -> Path:
    return root / "books/demo/chapters/e01/ch-01/正文.md"


def _capsule_control(root: Path, capsule_id: str) -> dict:
    return json.loads(
        (
            root
            / "books/demo/planning/guardian-sessions"
            / f"{capsule_id}.json"
        ).read_text(encoding="utf-8")
    )


def test_short_chapter_gate_reaches_authorizable_surface_decision(
    tmp_path: Path,
):
    """A sub-5000-CJK chapter must end in an authorizable decision, not a
    deadlock; authorizing the revision must recover to a full chapter."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)

    result = _start_lean_with_prose(relay, "demo", _short_prose())
    assert result.user_state == "running"
    for _ in range(3):
        action = relay.next_action("demo")
        assert action["role"] == "writer"
        assert action.get("surface_patch") is True
        assert any("CJK" in item for item in action["must_findings"])
        (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
            _short_prose(),
            encoding="utf-8",
        )
        result = _complete_minimal(relay, "demo")

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "surface_revision_required"
    assert any("CJK" in item for item in state["must_findings"])
    card = relay.next_action("demo")
    assert card["kind"] == "user_decision"
    assert any("authorize-revision" in option for option in card["options"])
    assert not _formal_chapter(root).exists()

    resumed = relay.authorize_revision(
        "demo",
        decision_reference="author-allows-rewrite-for-length",
    )
    assert resumed.user_state == "running"
    patch = relay.next_action("demo")
    assert patch["role"] == "writer"
    assert patch["stage"] == "patch"
    (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("授权修订"),
        encoding="utf-8",
    )
    _complete_minimal(relay, "demo")
    result = _complete_reviews(relay, "demo")
    assert result.user_state == "chapter_complete"
    assert "授权修订" in _formal_chapter(root).read_text(encoding="utf-8")


def test_promote_gate_error_becomes_authorizable_decision(
    tmp_path: Path,
    monkeypatch,
):
    """A BookProjectError raised during promotion must surface as an
    authorizable hard-gate decision instead of crashing complete-role."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("硬门章"))

    def boom(self, slug, state):
        raise BookProjectError("forced surface gate failure")

    monkeypatch.setattr(NativeWorkflowRelay, "_promote_staged_writer", boom)
    result = _complete_reviews(relay, "demo")

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "hard_gate_failed"
    assert any("forced surface gate" in item for item in state["must_findings"])
    assert not _formal_chapter(root).exists()
    card = relay.next_action("demo")
    assert card["kind"] == "user_decision"
    assert any("authorize-revision" in option for option in card["options"])

    monkeypatch.undo()
    resumed = relay.authorize_revision(
        "demo",
        decision_reference="author-allows-one-revision",
    )
    assert resumed.user_state == "running"
    patch = relay.next_action("demo")
    (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("授权修复"),
        encoding="utf-8",
    )
    _complete_minimal(relay, "demo")
    result = _complete_reviews(relay, "demo")
    assert result.user_state == "chapter_complete"


def test_hard_gate_after_partial_promotion_has_no_silent_retry_loop(
    tmp_path: Path,
    monkeypatch,
):
    """If a gate fails after the capsule was already imported, authorize must
    refuse the unsafe staged-patch replay with a clear message."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("部分晋升"))

    def boom(*args, **kwargs):
        raise BookProjectError("forced literary gate failure")

    monkeypatch.setattr(book_project, "run_gates", boom)
    result = _complete_reviews(relay, "demo")

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "hard_gate_failed"
    assert _formal_chapter(root).is_file()
    with pytest.raises(WorkflowError, match="已部分晋升"):
        relay.authorize_revision(
            "demo",
            decision_reference="author-tries-revision",
        )


def test_git_checkpoint_failure_is_retryable_by_author(
    tmp_path: Path,
    monkeypatch,
):
    """A failing chapter checkpoint must become a retryable author decision;
    authorizing retries only the ready/checkpoint tail."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("检查点"))

    def boom(*args, **kwargs):
        raise BookGitError("forced checkpoint failure")

    monkeypatch.setattr(workflow_module, "checkpoint_book", boom)
    result = _complete_reviews(relay, "demo")

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "git_checkpoint_failed"
    # Double review passed and promotion succeeded; only the checkpoint failed.
    assert _formal_chapter(root).is_file()
    card = relay.next_action("demo")
    assert card["kind"] == "user_decision"
    assert card["decision_kind"] == "git_checkpoint_failed"
    assert any("authorize-revision" in option for option in card["options"])

    monkeypatch.undo()
    finished = relay.authorize_revision(
        "demo",
        decision_reference="author-retries-checkpoint",
    )
    assert finished.user_state == "chapter_complete"
    assert relay._load_state("demo")["phase"] == "complete"
    assert book_git_status(root, "demo")["dirty"] is False


def test_invalid_blind_pass_blocks_promotion_and_formal_side_effects(
    tmp_path: Path,
):
    """P0-2: a blind pass that record_review would reject (uncertain
    human_likeness) must fail before any promotion side effect."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("认证门禁"))
    capsule_id = relay._load_state("demo")["capsule"]["capsule_id"]

    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(human_likeness="uncertain"),
    )

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "hard_gate_failed"
    assert any("human_likeness" in item for item in state["must_findings"])
    assert not _formal_chapter(root).exists()
    assert not list((root / "books/demo/evidence").glob("generations/*.md"))
    assert not (root / "books/demo/reviews/ch01-blind-reader.md").exists()
    assert not (root / "books/demo/reviews/ch01-chapter-editor.md").exists()
    assert _capsule_control(root, capsule_id)["status"] == "prepared"

    # The capsule is untouched, so one authorized revision round recovers.
    resumed = relay.authorize_revision(
        "demo",
        decision_reference="author-orders-fresh-round",
    )
    assert resumed.user_state == "running"
    patch = relay.next_action("demo")
    (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("重新修订"),
        encoding="utf-8",
    )
    _complete_minimal(relay, "demo")
    result = _complete_reviews(relay, "demo")
    assert result.user_state == "chapter_complete"


def test_normalized_only_evidence_quote_blocks_promotion(tmp_path: Path):
    """P0-2: an evidence quote that only matches via _quote_matches
    normalization (record_review requires an exact substring) must fail
    before promotion, not after."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("引文门禁"))

    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(evidence_quote="林舟 握住门把"),
    )

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "hard_gate_failed"
    assert any("evidence_quote" in item for item in state["must_findings"])
    assert not _formal_chapter(root).exists()
    assert not list((root / "books/demo/evidence").glob("generations/*.md"))
