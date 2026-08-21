"""Regression tests for the 2026-08 audit fixes (#1-#7).

Covers: terminal-phase revival guard, record_review TOCTOU, patch
directive budget derivation, exception-taxonomy hardening, shared slug
validation, and the complete-role state lock.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from app.novel_forge import book_project
from app.novel_forge.models import (
    NovelForgeError,
    validate_book_slug,
)
from app.novel_forge.native_relay import (
    _LOCK_TIMEOUT_SECONDS,
    _StateFileLock,
    NativeWorkflowRelay,
    NATIVE_RELAY_SCHEMA,
)
from app.novel_forge.workflow import WorkflowResult, WorkflowError
from app.novel_forge.writer_prompt import (
    MAX_FORMAL_WRITER_PROMPT_CHARS,
    WriterPromptError,
    patch_directive_budget,
    render_formal_writer_instructions,
)
from tests.test_book_project import _make_book, _review_file
from tests.test_native_relay import _request


def _relay(tmp_path: Path) -> NativeWorkflowRelay:
    return NativeWorkflowRelay(
        tmp_path / "repo",
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )


# ---------------------------------------------------------------------------
# #1: terminal phases must never be revived by a late completion
# ---------------------------------------------------------------------------


def test_late_completion_cannot_revive_stopped_workflow(tmp_path: Path):
    relay = _relay(tmp_path)
    relay.start("demo", _request(), chapter=1)
    relay.stop("demo")

    result = relay.complete_role("demo", {"role_result": {"role": "writer"}})

    assert isinstance(result, WorkflowResult)
    assert result.user_state == "stopped"
    assert relay._load_state("demo")["phase"] == "stopped"


def test_late_completion_on_decision_required_represents_decision(
    tmp_path: Path,
):
    relay = _relay(tmp_path)
    relay_dir = relay._relay_dir("demo")
    relay_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema": NATIVE_RELAY_SCHEMA,
        "slug": "demo",
        "chapter": 1,
        "phase": "decision_required",
        "decision_kind": "native_role_failed",
        "decision_message": "测试决策卡。",
        "sequence_id": "",
    }
    relay._state_path("demo").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )

    result = relay.complete_role("demo", {"role_result": {"role": "writer"}})

    assert result.user_state == "decision_required"
    reloaded = relay._load_state("demo")
    assert reloaded["phase"] == "decision_required"
    assert reloaded["decision_kind"] == "native_role_failed"


def test_technical_recovery_keeps_terminal_phases_terminal(tmp_path: Path):
    relay = _relay(tmp_path)
    relay_dir = relay._relay_dir("demo")
    relay_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema": NATIVE_RELAY_SCHEMA,
        "slug": "demo",
        "chapter": 1,
        "phase": "complete",
        "sequence_id": "",
    }
    relay._state_path("demo").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )

    result = relay._recover_technical_failure(
        "demo", relay._load_state("demo"), failure_reason="test"
    )

    assert result.user_state == "chapter_complete"
    assert relay._load_state("demo")["phase"] == "complete"


# ---------------------------------------------------------------------------
# #2: record_review must seal the validated bytes, not a fresh disk read
# ---------------------------------------------------------------------------


def test_record_review_seals_validated_text_against_midflight_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    book_dir = _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    validated_text = review.read_text(encoding="utf-8-sig")
    real_parse = book_project.parse_review

    def tampering_parse(text: str):
        # Simulate the untrusted role rewriting its result file between
        # validation and the canonical copy.
        review.write_text("# TAMPERED\n", encoding="utf-8")
        return real_parse(text)

    monkeypatch.setattr(book_project, "parse_review", tampering_parse)

    result = book_project.record_review(
        tmp_path, "demo", 1, "blind-reader", review
    )

    canonical = (
        book_dir / "reviews" / result["review_file"].split("/")[-1]
    ).read_text(encoding="utf-8")
    history = (book_dir / result["review_record"]).read_text(
        encoding="utf-8"
    )
    assert canonical == validated_text
    assert history == validated_text
    assert "TAMPERED" not in canonical


# ---------------------------------------------------------------------------
# #4: patch directive budget is derived from the total prompt budget
# ---------------------------------------------------------------------------


def test_patch_directive_budget_derives_from_total_budget():
    budget = patch_directive_budget(3)

    assert 0 < budget < MAX_FORMAL_WRITER_PROMPT_CHARS
    prompt = render_formal_writer_instructions(
        3,
        operation="patch",
        patch_directive="字" * budget,
    )
    assert len(prompt.text) <= MAX_FORMAL_WRITER_PROMPT_CHARS


def test_patch_directive_over_budget_raises_with_clear_message():
    budget = patch_directive_budget(2)

    with pytest.raises(WriterPromptError, match="字符预算") as excinfo:
        render_formal_writer_instructions(
            2,
            operation="patch",
            patch_directive="字" * (budget + 1),
        )
    assert str(budget) in str(excinfo.value)


# ---------------------------------------------------------------------------
# #7: malformed completions route into recovery instead of crashing
# ---------------------------------------------------------------------------


def test_complete_role_tolerates_non_dict_role_result(tmp_path: Path):
    relay = _relay(tmp_path)
    relay.start("demo", _request(), chapter=1)
    relay.next_action("demo")

    result = relay.complete_role("demo", {"role_result": "not-a-dict"})

    assert isinstance(result, WorkflowResult)
    assert result.user_state == "running"


def test_normalize_evidence_quote_handles_empty_list():
    assert NativeWorkflowRelay._normalize_evidence_quote([]) == ""
    assert NativeWorkflowRelay._normalize_evidence_quote(["引句"]) == "引句"
    assert NativeWorkflowRelay._normalize_evidence_quote("直接给") == "直接给"
    assert NativeWorkflowRelay._normalize_evidence_quote(None) is None


# ---------------------------------------------------------------------------
# #5: one shared slug rule blocks path traversal everywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "../evil",
        "..",
        ".",
        "a/b",
        "a\\b",
        "",
        "a b",
        "书名",
        "a\x00b",
    ],
)
def test_validate_book_slug_rejects_unsafe_names(bad: str):
    with pytest.raises(NovelForgeError):
        validate_book_slug(bad)


@pytest.mark.parametrize("good", ["demo", "My-Book_01"])
def test_validate_book_slug_accepts_safe_names(good: str):
    assert validate_book_slug(good) == good


def test_book_dir_for_blocks_traversal(tmp_path: Path):
    with pytest.raises(NovelForgeError):
        book_project.book_dir_for(tmp_path, "../../outside")


def test_relay_rejects_unsafe_slug_before_touching_disk(tmp_path: Path):
    relay = _relay(tmp_path)
    with pytest.raises(NovelForgeError):
        relay.status("../evil")
    with pytest.raises(NovelForgeError):
        relay.start("../evil", _request(), chapter=1)


# ---------------------------------------------------------------------------
# #6: complete-role serialization lock
# ---------------------------------------------------------------------------


def test_state_lock_lives_outside_the_repository(tmp_path: Path):
    relay = _relay(tmp_path)
    lock_path = relay._lock_path("demo")

    repo_root = (tmp_path / "repo").resolve()
    assert not lock_path.is_relative_to(repo_root)


def test_state_lock_breaks_stale_lock(tmp_path: Path, monkeypatch):
    relay = _relay(tmp_path)
    lock_path = relay._lock_path("demo")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("0", encoding="ascii")
    stale = time.time() - 400
    os.utime(lock_path, (stale, stale))

    with _StateFileLock(lock_path):
        assert lock_path.is_file()
    assert not lock_path.exists()


def test_complete_role_times_out_when_lock_is_held_elsewhere(
    tmp_path: Path, monkeypatch
):
    from app.novel_forge import native_relay

    relay = _relay(tmp_path)
    relay.start("demo", _request(), chapter=1)
    monkeypatch.setattr(native_relay, "_LOCK_TIMEOUT_SECONDS", 0.2)

    lock_path = relay._lock_path("demo")
    with _StateFileLock(lock_path):
        with pytest.raises(NovelForgeError, match="complete-role"):
            relay.complete_role("demo", {"role_result": {"role": "writer"}})


def test_original_lock_timeout_constant_is_positive():
    assert _LOCK_TIMEOUT_SECONDS > 0


# ---------------------------------------------------------------------------
# #8: the local-patch path must re-run the full-chapter hard gates
# ---------------------------------------------------------------------------


def test_local_patch_reruns_full_chapter_hard_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from app.novel_forge import native_relay as nr_module
    from dataclasses import asdict
    from tests.test_native_relay import (
        ScriptedBackend,
        _complete_minimal,
        _review_capsule_context,
        _review_capsule_instructions,
    )
    from tests.test_workflow import _must_reviews, _prose
    from app.novel_forge.workflow import ReviewFinding, ReviewOutcome, SessionIdentity

    relay = NativeWorkflowRelay(tmp_path / "repo", strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    prose = (
        _prose("局部修订正文")
        + "\n\n林舟把铜扣放回左侧口袋，这句解释只出现一次。\n"
    )
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(prose, encoding="utf-8")
    _complete_minimal(relay, "demo")

    finding = ReviewFinding(
        severity="MUST",
        location="开场段",
        evidence="林舟把铜扣放回左侧口袋，这句解释只出现一次。",
        reader_effect="局部解释停顿",
        revision_intent="只压缩当前段，不改变核心事件",
        scope="local",
    )
    reviews = _must_reviews()
    local_reviews = (
        ReviewOutcome(**{**asdict(reviews[0]), "findings": (finding,)}),
        ReviewOutcome(**{**asdict(reviews[1]), "findings": (finding,)}),
    )
    backend = ScriptedBackend([], [local_reviews])
    for role in ("blind-reader", "chapter-editor"):
        action = relay.next_action("demo")
        produced = backend.run_review(
            SessionIdentity(
                session_id=f"{role}-session",
                session_instance_id=f"{role}-session",
                provider="unknown", model="unknown",
                agent_harness="native-host", role=role,
            ),
            role=role,
            context=_review_capsule_context(action),
            instructions=_review_capsule_instructions(action),
            reasoning_effort="medium",
        )
        Path(action["result_file"]).write_text(
            json.dumps(asdict(produced), ensure_ascii=False),
            encoding="utf-8",
        )
        _complete_minimal(relay, "demo")

    patch = relay.next_action("demo")
    assert patch["stage"] == "local-patch"
    payload = json.loads(Path(patch["input_file"]).read_text(encoding="utf-8"))
    target = payload["targets"][0]["target"]
    Path(patch["result_file"]).write_text(
        json.dumps(
            {
                "replacements": [
                    {
                        "target": target,
                        "replacement": "林舟把铜扣塞回左侧口袋。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, tuple[str, ...]]] = []
    real_check = nr_module.check_chapter_text

    def spy_check(text: str, mode: str = "formal") -> list[str]:
        result = real_check(text, mode)
        calls.append((mode, tuple(result)))
        return [*result, "正式章节不足 5000 个 CJK 汉字（当前 0）"]

    monkeypatch.setattr(nr_module, "check_chapter_text", spy_check)

    result = _complete_minimal(relay, "demo")

    assert any(mode == "formal" for mode, _ in calls)
    state = relay._load_state("demo")
    assert state["decision_kind"] == "local_patch_hard_gate_failed"
    assert any("CJK" in item for item in state["must_findings"])
    assert result.user_state == "decision_required"


# ---------------------------------------------------------------------------
# #9: an open MUST without evidence is invalid and routes to repair
# ---------------------------------------------------------------------------


def test_open_must_without_evidence_is_invalid(tmp_path: Path):
    from app.novel_forge.workflow import ReviewFinding, ReviewOutcome

    relay = _relay(tmp_path)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    from tests.test_workflow import _prose

    prose = _prose("空引文校验")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(prose, encoding="utf-8")

    outcome = ReviewOutcome(
        verdict="needs_revision",
        findings=(
            ReviewFinding(
                severity="MUST",
                location="开场段",
                evidence="",
                reader_effect="无法核验的断言",
                revision_intent="补充可定位证据",
            ),
        ),
        human_likeness="convincing",
        reader_desire="continue",
        emotional_residue="余味",
        next_chapter_pull="钩子",
        evidence_quote="林舟握住门把，听见走廊尽头的脚步逼近。",
    )

    with pytest.raises(WorkflowError, match="缺少原文引文"):
        relay._assert_review_evidence_quote(
            "demo",
            relay._load_state("demo"),
            "chapter-editor",
            outcome,
        )


def test_closed_must_without_evidence_still_passes_quote_check(
    tmp_path: Path,
):
    from app.novel_forge.workflow import ReviewFinding, ReviewOutcome
    from tests.test_workflow import _prose

    relay = _relay(tmp_path)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    prose = _prose("已关闭引文校验")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(prose, encoding="utf-8")

    outcome = ReviewOutcome(
        verdict="pass",
        findings=(
            ReviewFinding(
                severity="MUST",
                location="开场段",
                evidence="",
                reader_effect="历史问题",
                revision_intent="无需处理",
                status="closed",
            ),
        ),
        human_likeness="convincing",
        reader_desire="continue",
        emotional_residue="余味",
        next_chapter_pull="钩子",
        evidence_quote="林舟握住门把，听见走廊尽头的脚步逼近。",
    )

    # A closed MUST carries no verifiable claim about the current prose;
    # it must not fail the quote check.
    relay._assert_review_evidence_quote(
        "demo",
        relay._load_state("demo"),
        "chapter-editor",
        outcome,
    )
