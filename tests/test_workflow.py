"""Tests for the human-light three-role novel workflow."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.novel_forge.book_evidence import evidence_status
from app.novel_forge.book_project import list_reviews, project_status
from app.novel_forge.chapter_sequence import chapter_sequence_status
from app.novel_forge.workflow import (
    NovelWorkflowOrchestrator,
    ReviewFinding,
    ReviewOutcome,
    SessionIdentity,
    WorkflowRequest,
    runtime_generation_metrics,
)


def _prose(label: str) -> str:
    paragraph = (
        f"林舟握住门把，听见走廊尽头的脚步逼近。他没有回头，"
        f"只是把掌心压得更紧。{label}"
    ) * 240
    return f"# 第一章 门后的雨\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n"


def _second_prose() -> str:
    paragraph = (
        "沈砚沿着积水的台阶往下走，坏掉的应急灯在身后忽明忽暗。"
        "他数着每一次水声，直到地下室里传来一声短促的金属碰撞。"
    ) * 240
    return f"# 第二章 地下室\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n"


def _runtime(session_id: str, capsule_id: str) -> dict:
    return {
        "schema": "novel-forge-runtime/v1",
        "session_id": session_id,
        "scope": {"chapter_count": 1},
        "harness": {"name": "Test Harness", "version": "1"},
        "model": {
            "provider": "writer-provider",
            "name": "writer-model",
            "reasoning_effort": "standard",
        },
        "timing": {"elapsed_seconds": 2.5},
        "usage": {
            "request_count": 1,
            "input_tokens": 100,
            "output_tokens": 6000,
            "cached_input_tokens": 200,
            "total_tokens": 6300,
            "max_request_context_tokens": 8000,
            "context_reset_count": 0,
        },
        "tools": {
            "call_count": 1,
            "failure_count": 0,
            "by_name": {"write": 1},
        },
        "guardian": {
            "capsule_id": capsule_id,
            "workspace_mode": "isolated_writer_capsule",
            "filesystem_scope": "capsule_only",
            "book_control_plane_visible": False,
            "validator_source_visible": False,
            "reported_by": "external_harness",
            "sandbox_implementation": "test-backend",
        },
    }


@dataclass
class WriterStep:
    prose: str
    failure: str | None = None


class ScriptedBackend:
    def __init__(
        self,
        writer_steps: list[WriterStep],
        review_rounds: list[tuple[ReviewOutcome, ReviewOutcome]],
    ):
        self.writer_steps = list(writer_steps)
        self.review_rounds = list(review_rounds)
        self.sessions: list[SessionIdentity] = []
        self.review_contexts: list[tuple[str, set[str]]] = []
        self._role_counts: dict[str, int] = {}
        self._review_index = 0

    def create_session(self, role: str) -> SessionIdentity:
        count = self._role_counts.get(role, 0) + 1
        self._role_counts[role] = count
        session = SessionIdentity(
            session_id=f"native-{role}-{count:02d}",
            provider=f"{role}-provider",
            model=f"{role}-model",
            agent_harness="test-harness/1",
            role=role,
        )
        self.sessions.append(session)
        return session

    def run_writer(
        self,
        session: SessionIdentity,
        *,
        capsule_dir: Path,
        capsule_id: str,
        runtime_path: Path,
        must_findings: tuple[str, ...],
    ) -> None:
        step = self.writer_steps.pop(0)
        (capsule_dir / "draft/正文.md").write_text(
            step.prose,
            encoding="utf-8",
        )
        if step.failure == "unexpected_file":
            (capsule_dir / "runtime.json").write_text(
                "{}",
                encoding="utf-8",
            )
        if step.failure != "missing_runtime_sidecar":
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_path.write_text(
                json.dumps(
                    _runtime(session.session_id, capsule_id),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    def run_review(
        self,
        session: SessionIdentity,
        *,
        role: str,
        context: dict[str, str],
    ) -> ReviewOutcome:
        self.review_contexts.append((role, set(context)))
        round_index = self._review_index // 2
        role_index = 0 if role == "blind-reader" else 1
        outcome = self.review_rounds[round_index][role_index]
        self._review_index += 1
        return outcome


def _pass_reviews() -> tuple[ReviewOutcome, ReviewOutcome]:
    return (
        ReviewOutcome(
            verdict="pass",
            human_likeness="convincing",
            reader_desire="continue",
            emotional_residue="主角已经作出选择，但门后的代价仍悬着。",
            next_chapter_pull="门后的人会要求主角付出什么？",
        ),
        ReviewOutcome(verdict="ready_for_editor_decision"),
    )


def _must_reviews() -> tuple[ReviewOutcome, ReviewOutcome]:
    finding = ReviewFinding(
        severity="MUST",
        location="开场",
        evidence="林舟握住门把",
        reader_effect="阻力出现得太晚。",
        revision_intent="把追兵的压力提前到第一段。",
    )
    return (
        ReviewOutcome(
            verdict="needs_revision",
            findings=(finding,),
            human_likeness="uncertain",
            reader_desire="conditional",
            emotional_residue="场面存在压力，但选择尚未咬紧。",
            next_chapter_pull="修订后才能判断是否愿意继续。",
        ),
        ReviewOutcome(verdict="needs_revision", findings=(finding,)),
    )


def _request() -> WorkflowRequest:
    return WorkflowRequest(
        title="门后的雨",
        genre="现实悬疑",
        protagonist="林舟，一个不愿求助的修锁匠",
        world="当代旧城，暴雨导致街区断电，门禁系统失灵。",
        conflict="林舟必须在追兵赶到前开门，但开门会暴露被他藏起的人。",
        ending_hook="门锁转动后，门内的人先叫出了追兵的名字。",
    )


def _orchestrator(
    tmp_path: Path,
    backend: ScriptedBackend,
    *,
    retries: int = 2,
) -> NovelWorkflowOrchestrator:
    root = tmp_path / "repo"
    capsule_root = tmp_path / "capsules"
    return NovelWorkflowOrchestrator(
        root,
        backend,
        capsule_root=capsule_root,
        max_technical_retries=retries,
    )


def test_normal_workflow_completes_writer_reviews_ready_and_git(tmp_path: Path):
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "chapter_complete"
    assert result.message == "第一章完成，是否继续第二章？"
    status = project_status(orchestrator.root, "demo", 1)
    assert status["chapters"][0]["status"] == "ready"
    sequence = chapter_sequence_status(
        orchestrator.root,
        "demo",
        result.sequence_id,
    )
    assert sequence["effective_status"] == "complete"
    assert result.git_checkpoint_succeeded is True
    assert [item.session_id for item in backend.sessions] == [
        "native-writer-01",
        "native-blind-reader-01",
        "native-chapter-editor-01",
    ]
    assert backend.review_contexts[0] == ("blind-reader", {"prose"})
    assert backend.review_contexts[1][0] == "chapter-editor"
    assert backend.review_contexts[1][1] == {
        "prose",
        "scene_package",
        "canon",
        "blind_review",
    }


def test_completed_first_chapter_can_continue_second_chapter(tmp_path: Path):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("第一章")),
            WriterStep(_second_prose()),
        ],
        [_pass_reviews(), _pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)

    first = orchestrator.start("demo", _request(), chapter=1)
    second = orchestrator.start("demo", _request(), chapter=2)

    assert first.user_state == "chapter_complete"
    assert second.user_state == "chapter_complete"
    assert second.message == "第二章完成，是否继续第三章？"
    second_status = project_status(orchestrator.root, "demo", 2)
    assert second_status["chapters"][0]["status"] == "ready"
    scene = (
        orchestrator.root
        / "books/demo/planning/scene-package-ch02.md"
    ).read_text(encoding="utf-8")
    assert "## 0b. 章际交接" in scene
    assert "deferred_until_drafted" not in scene


def test_guardian_failure_preserves_receipt_and_uses_fresh_session(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("失败稿"), failure="unexpected_file"),
            WriterStep(_prose("重试稿")),
        ],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "chapter_complete"
    assert result.technical_retry_count == 1
    writer_ids = [
        item.session_id for item in backend.sessions if item.role == "writer"
    ]
    assert writer_ids == ["native-writer-01", "native-writer-02"]
    receipts = sorted(
        (
            orchestrator.root
            / "books/demo/evidence/guardian-receipts"
        ).glob("*.json")
    )
    assert len(receipts) == 2
    assert json.loads(receipts[0].read_text(encoding="utf-8"))["status"] in {
        "clean",
        "compromised",
    }
    assert {
        json.loads(path.read_text(encoding="utf-8"))["status"]
        for path in receipts
    } == {"clean", "compromised"}
    assert not (
        orchestrator.root / "books/demo/.local-guardian"
    ).exists()
    assert (
        orchestrator.root / ".local-guardian/demo"
    ).is_dir()


def test_patch_uses_new_writer_session_and_replaces_reviews_without_mutation(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("初稿")),
            WriterStep(_prose("集中修订")),
        ],
        [_must_reviews(), _pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "chapter_complete"
    writer_ids = [
        item.session_id for item in backend.sessions if item.role == "writer"
    ]
    assert writer_ids == ["native-writer-01", "native-writer-02"]
    history = sorted(
        (
            orchestrator.root / "books/demo/reviews/history"
        ).glob("*.md")
    )
    assert len(history) == 4
    assert any("needs_revision" in path.read_text(encoding="utf-8") for path in history)
    assert any("pass" in path.read_text(encoding="utf-8") for path in history)
    status = project_status(orchestrator.root, "demo", 1)
    assert len(status["review_history"]) == 4
    assert sum(item["stale"] for item in status["review_history"]) == 2
    evidence = evidence_status(orchestrator.root, "demo", 1)
    assert evidence["generation_count"] == 2
    assert len(evidence["stale_record_ids"]) == 1
    current_reviews = list_reviews(
        orchestrator.root / "books/demo",
        "ch01",
    )
    assert {item["verdict"] for item in current_reviews} == {
        "pass",
        "ready_for_editor_decision",
    }
    assert not any(item["stale"] for item in current_reviews)


def test_sequence_waiting_for_new_session_never_displays_ready(tmp_path: Path):
    backend = ScriptedBackend(
        [WriterStep(_prose("失败稿"), failure="missing_runtime_sidecar")],
        [],
    )
    orchestrator = _orchestrator(tmp_path, backend, retries=0)

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "decision_required"
    assert result.message != "第一章完成，是否继续第二章？"
    sequence = chapter_sequence_status(
        orchestrator.root,
        "demo",
        result.sequence_id,
    )
    assert sequence["effective_status"] == "awaiting_session"
    status = project_status(orchestrator.root, "demo", 1)
    assert not status["chapters"] or status["chapters"][0]["status"] != "ready"


def test_runtime_unknown_values_remain_null():
    report = {
        "elapsed_seconds": None,
        "request_count": None,
        "tokens": {
            "input": None,
            "output": None,
            "cached_input": None,
            "total": None,
        },
        "max_context_tokens": None,
    }

    metrics = runtime_generation_metrics(report)

    assert metrics == {
        "elapsed_seconds": None,
        "request_count": None,
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "total_tokens": None,
    }


def test_user_is_asked_only_after_two_automatic_retries(tmp_path: Path):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("失败一"), failure="unexpected_file"),
            WriterStep(_prose("失败二"), failure="unexpected_file"),
            WriterStep(_prose("失败三"), failure="unexpected_file"),
        ],
        [],
    )
    orchestrator = _orchestrator(tmp_path, backend, retries=2)

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "decision_required"
    assert result.technical_retry_count == 2
    assert result.options == (
        "A. 保留草稿",
        "B. 重新生成本章",
        "C. 停止任务",
    )
    assert len(
        [item for item in backend.sessions if item.role == "writer"]
    ) == 3


def test_retry_restarts_failed_chapter_with_a_fresh_session(tmp_path: Path):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("失败"), failure="missing_runtime_sidecar"),
            WriterStep(_prose("重试成功")),
        ],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend, retries=0)
    failed = orchestrator.start("demo", _request(), chapter=1)

    result = orchestrator.retry("demo")

    assert failed.user_state == "decision_required"
    assert result.user_state == "chapter_complete"
    assert [
        item.session_id for item in backend.sessions if item.role == "writer"
    ] == ["native-writer-01", "native-writer-02"]


@pytest.mark.parametrize(
    "forbidden",
    (
        "JSON",
        "SHA-256",
        "Session",
        "Guardian",
        "Git",
        "Traceback",
        "runtime",
        "generation",
    ),
)
def test_user_messages_do_not_expose_internal_terms(
    tmp_path: Path,
    forbidden: str,
):
    backend = ScriptedBackend(
        [WriterStep(_prose("失败"), failure="unexpected_file")] * 3,
        [],
    )
    orchestrator = _orchestrator(tmp_path, backend, retries=2)

    result = orchestrator.start("demo", _request(), chapter=1)

    visible = "\n".join((result.message, *result.options))
    assert forbidden.lower() not in visible.lower()


def test_cli_wrapper_runs_without_pythonpath():
    root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [sys.executable, "tools/novel-workflow.py", "--help"],
        cwd=root,
        capture_output=True,
        check=False,
        encoding="utf-8",
        text=True,
    )

    assert completed.returncode == 0
    assert "start" in completed.stdout
    assert "status" in completed.stdout
    assert "retry" in completed.stdout
    assert "stop" in completed.stdout
