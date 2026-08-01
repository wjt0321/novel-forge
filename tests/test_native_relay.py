"""Tests for the persistent native-host workflow relay."""

from __future__ import annotations

import hashlib
import json

import pytest
from dataclasses import asdict
from pathlib import Path

from app.novel_forge import book_project
from app.novel_forge.book_git import book_git_status
from app.novel_forge.native_relay import NativeWorkflowRelay
from app.novel_forge.workflow import (
    NovelWorkflowOrchestrator,
    ReviewFinding,
    ReviewOutcome,
    SessionIdentity,
    WorkflowRequest,
    WorkflowError,
    main,
)
from tests.test_workflow import (
    ScriptedBackend,
    _must_reviews,
    _pass_reviews,
    _prose,
    _runtime,
)


def _request() -> WorkflowRequest:
    return WorkflowRequest(
        title="测试书",
        genre="民俗悬疑",
        protagonist="林舟",
        world="旧城的建筑会保存死者留下的声音。",
        conflict="林舟必须在封锁前打开戏楼暗门。",
        ending_hook="暗门后传来失踪者的敲击声。",
    )


def test_native_start_prepares_writer_planning_action_without_harness(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )

    result = relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")

    assert result.user_state == "running"
    assert result.message == "正在写作。"
    assert action["schema"] == "novel-forge-native-action/v1"
    assert action["kind"] == "run_role"
    assert action["role"] == "writer-planning"
    assert action["session"]["mode"] == "new"
    assert action["reasoning_effort"] == "high"
    assert action["result"]["schema"] == "novel-forge-role-result/v1"
    assert (root / "books/demo").is_dir()
    serialized = json.dumps(action, ensure_ascii=False)
    assert "app/novel_forge" not in serialized
    assert "tests/" not in serialized
    assert "docs/" not in serialized
    assert "NOVEL_FORGE_HARNESS_COMMAND" not in serialized


def test_native_action_is_stored_outside_the_book_project(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )

    relay.start("demo", _request(), chapter=1)

    assert not (
        root / "books/demo/planning/workflow/next-action.json"
    ).exists()
    assert (
        root / ".local-guardian/demo/native-relay/next-action.json"
    ).is_file()


def test_native_snapshot_namespace_separates_same_slug_across_roots(
    tmp_path: Path,
):
    capsule_root = tmp_path / "capsules"
    first = NativeWorkflowRelay(
        tmp_path / "first-repo",
        capsule_root=capsule_root,
        strict_audit=False,
    )
    second = NativeWorkflowRelay(
        tmp_path / "second-repo",
        capsule_root=capsule_root,
        strict_audit=False,
    )

    first.start("demo", _request(), chapter=1)
    second.start("demo", _request(), chapter=1)
    first_action = first.next_action("demo")
    second_action = second.next_action("demo")

    assert first._snapshot_path(
        "demo", first_action["action_id"]
    ).parent != second._snapshot_path(
        "demo", second_action["action_id"]
    ).parent
    assert first._active_snapshot_action_id("demo") == (
        first_action["action_id"]
    )
    assert second._active_snapshot_action_id("demo") == (
        second_action["action_id"]
    )


def test_native_stop_retires_pending_action(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    action_id = action["action_id"]
    assert relay._snapshot_path("demo", action_id).is_file()
    assert relay._control_snapshot_path("demo", action_id).is_file()

    result = relay.stop("demo")

    assert result.user_state == "stopped"
    assert not (
        root / ".local-guardian/demo/native-relay/next-action.json"
    ).exists()
    assert not relay._snapshot_path("demo", action_id).exists()
    assert not relay._backup_path("demo", action_id).exists()
    assert not relay._control_snapshot_path("demo", action_id).exists()
    assert not relay._control_backup_path("demo", action_id).exists()
    assert relay.status("demo").user_state == "stopped"


def test_planning_completion_prepares_reused_writer_capsule(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )
    request = _request()
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    session = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="test-provider",
        model="test-writer",
        agent_harness="test-native-host",
        role="writer",
    )
    planning = ScriptedBackend([], []).run_planning(
        session,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    completion = {
        "schema": "novel-forge-native-completion/v1",
        "action_id": planning_action["action_id"],
        "status": "completed",
        "session": {
            "session_id": session.session_id,
            "session_instance_id": session.session_instance_id,
            "provider": session.provider,
            "model": session.model,
            "agent_harness": session.agent_harness,
        },
        "operation_handle": {
            "kind": planning.operation_kind,
            "value": planning.operation_id,
        },
        "result_transport": planning.result_transport,
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": "writer-planning",
            "payload": {"files": planning.files},
        },
    }

    result = relay.complete_role("demo", completion)
    writer_action = relay.next_action("demo")

    assert result.user_state == "running"
    assert writer_action["kind"] == "run_role"
    assert writer_action["role"] == "writer"
    assert writer_action["session"] == {
        "mode": "reuse",
        "session_id": "native-writer-01",
        "session_instance_id": "writer-instance-01",
    }
    capsule = Path(writer_action["capsule"]["path"])
    assert capsule.is_dir()
    assert not capsule.is_relative_to(root.resolve())
    assert (capsule / "instructions.md").is_file()
    assert (capsule / "handoff.md").is_file()
    assert writer_action["runtime"]["assurance_mode"] == "formal_native"


def test_writer_completion_imports_generation_and_requests_blind_review(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )
    request = _request()
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    session = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="test-provider",
        model="test-writer",
        agent_harness="test-native-host",
        role="writer",
    )
    planning = ScriptedBackend([], []).run_planning(
        session,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    relay.complete_role(
        "demo",
        {
            "schema": "novel-forge-native-completion/v1",
            "action_id": planning_action["action_id"],
            "status": "completed",
            "session": {
                "session_id": session.session_id,
                "session_instance_id": session.session_instance_id,
                "provider": session.provider,
                "model": session.model,
                "agent_harness": session.agent_harness,
            },
            "operation_handle": {
                "kind": planning.operation_kind,
                "value": planning.operation_id,
            },
            "result_transport": planning.result_transport,
            "role_result": {
                "schema": "novel-forge-role-result/v1",
                "role": "writer-planning",
                "payload": {"files": planning.files},
            },
        },
    )
    writer_action = relay.next_action("demo")
    capsule = Path(writer_action["capsule"]["path"])
    (capsule / "draft/正文.md").write_text(
        _prose("原生接力"),
        encoding="utf-8",
    )
    runtime = _runtime(session.session_id, writer_action["capsule"]["id"])
    runtime["guardian"].update(
        {
            "assurance_mode": "formal_native",
            "filesystem_scope": "guarded_native",
            "write_scope": "post_execution_verified",
            "repository_snapshot_enforced": True,
            "reported_by": "native_host",
        }
    )

    result = relay.complete_role(
        "demo",
        {
            "schema": "novel-forge-native-completion/v1",
            "action_id": writer_action["action_id"],
            "status": "completed",
            "session": {
                "session_id": session.session_id,
                "session_instance_id": session.session_instance_id,
                "provider": session.provider,
                "model": session.model,
                "agent_harness": session.agent_harness,
            },
            "operation_handle": {
                "kind": "native-task",
                "value": "writer-operation-01",
            },
            "result_transport": "artifact",
            "role_result": {
                "schema": "novel-forge-role-result/v1",
                "role": "writer",
                "payload": {
                    "artifact_relative_path": "draft/正文.md",
                },
            },
            "runtime_snapshot": runtime,
        },
    )
    blind_action = relay.next_action("demo")

    assert result.message == "正在自动审稿。"
    assert blind_action["role"] == "blind-reader"
    assert blind_action["session"]["mode"] == "new"
    assert "context" not in blind_action
    assert _review_capsule_context(blind_action).keys() == {"prose"}
    review_capsule = Path(blind_action["review_capsule"]["path"])
    assert review_capsule.is_dir()
    assert not review_capsule.is_relative_to(root.resolve())
    assert (review_capsule / "manifest.json").is_file()
    assert (
        root / "books/demo/chapters/e01/ch-01/正文.md"
    ).read_text(encoding="utf-8") == _prose("原生接力")
    generations = list(
        (root / "books/demo/evidence/generations").glob("*.md")
    )
    receipts = list(
        (root / "books/demo/evidence/guardian-receipts").glob("*.json")
    )
    audits = list(
        (root / "books/demo/evidence/runtime-audits").glob("*.json")
    )
    assert len(generations) == 1
    assert len(receipts) == 1
    assert len(audits) == 1


def test_native_relay_completes_independent_double_review_and_ready(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )
    request = _request()
    backend = ScriptedBackend([], [_pass_reviews()])
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    writer = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="writer-provider",
        model="writer-model",
        agent_harness="native-host",
        role="writer",
    )
    planning = backend.run_planning(
        writer,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    relay.complete_role(
        "demo",
        _planning_completion(planning_action, writer, planning),
    )
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("双审通过"),
        encoding="utf-8",
    )
    relay.complete_role(
        "demo",
        _writer_completion(writer_action, writer),
    )
    blind_action = relay.next_action("demo")
    blind_session = SessionIdentity(
        session_id="native-blind-01",
        session_instance_id="blind-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        blind_session,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )

    blind_result = relay.complete_role(
        "demo",
        _review_completion(blind_action, blind_session, blind),
    )
    editor_action = relay.next_action("demo")

    assert blind_result.message == "正在自动审稿。"
    assert editor_action["role"] == "chapter-editor"
    assert "context" not in editor_action
    assert set(_review_capsule_context(editor_action)) == {
        "prose",
        "scene_package",
        "story_contract",
        "canon",
        "blind_review",
        "machine_diagnostics",
    }
    editor_session = SessionIdentity(
        session_id="native-editor-01",
        session_instance_id="editor-instance-01",
        provider="editor-provider",
        model="editor-model",
        agent_harness="native-host",
        role="chapter-editor",
    )
    editor = backend.run_review(
        editor_session,
        role="chapter-editor",
        context=_review_capsule_context(editor_action),
        instructions=_review_capsule_instructions(editor_action),
        reasoning_effort="medium",
    )
    result = relay.complete_role(
        "demo",
        _review_completion(editor_action, editor_session, editor),
    )

    status = book_project.project_status(root, "demo", 1)
    assert result.user_state == "chapter_complete"
    assert "第一章完成" in result.message
    assert status["chapters"][0]["status"] == "ready"
    assert len(
        list((root / "books/demo/reviews").glob("ch01-*.md"))
    ) == 2
    assert book_git_status(root, "demo")["dirty"] is False


def test_native_relay_retries_review_after_writer_promotion(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    backend = ScriptedBackend([], [_pass_reviews(), _pass_reviews()])
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("重试收尾"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")
    blind_action = relay.next_action("demo")
    blind_session = SessionIdentity(
        session_id="native-blind-01",
        session_instance_id="blind-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        blind_session,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )
    Path(blind_action["result_file"]).write_text(
        json.dumps(asdict(blind), ensure_ascii=False),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")
    editor_action = relay.next_action("demo")
    editor_session = SessionIdentity(
        session_id="native-editor-01",
        session_instance_id="editor-instance-01",
        provider="editor-provider",
        model="editor-model",
        agent_harness="native-host",
        role="chapter-editor",
    )
    editor = backend.run_review(
        editor_session,
        role="chapter-editor",
        context=_review_capsule_context(editor_action),
        instructions=_review_capsule_instructions(editor_action),
        reasoning_effort="medium",
    )
    Path(editor_action["result_file"]).write_text(
        json.dumps(asdict(editor), ensure_ascii=False),
        encoding="utf-8",
    )
    original_record_review = relay._record_native_review

    def fail_after_promotion(*args, **kwargs):
        raise OSError("simulated review persistence failure")

    monkeypatch.setattr(relay, "_record_native_review", fail_after_promotion)
    repair = relay.complete_minimal("demo")
    assert repair.user_state == "running"
    assert repair.technical_retry_count == 1
    state = relay._load_state("demo")
    capsule_id = state["capsule"]["capsule_id"]
    control = json.loads(
        (
            root
            / "books/demo/planning/guardian-sessions"
            / f"{capsule_id}.json"
        ).read_text(encoding="utf-8")
    )
    assert control["status"] == "imported"

    monkeypatch.setattr(relay, "_record_native_review", original_record_review)
    retry_action = relay.next_action("demo")
    assert retry_action["role"] == "chapter-editor"
    retry_session = SessionIdentity(
        session_id="native-editor-02",
        session_instance_id="editor-instance-02",
        provider="editor-provider",
        model="editor-model",
        agent_harness="native-host",
        role="chapter-editor",
    )
    retry_editor = backend.run_review(
        retry_session,
        role="chapter-editor",
        context=_review_capsule_context(retry_action),
        instructions=_review_capsule_instructions(retry_action),
        reasoning_effort="medium",
    )
    Path(retry_action["result_file"]).write_text(
        json.dumps(asdict(retry_editor), ensure_ascii=False),
        encoding="utf-8",
    )
    result = relay.complete_minimal("demo")

    assert result.user_state == "chapter_complete"
    assert len(
        list((root / "books/demo/evidence/generations").glob("*.md"))
    ) == 1


def test_editor_missing_hard_anchor_requires_a_must_finding(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay, blind_action = _prepare_blind_action(
        root,
        tmp_path / "capsules",
    )
    backend = ScriptedBackend([], [_pass_reviews()])
    blind_session = SessionIdentity(
        session_id="native-blind-01",
        session_instance_id="blind-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        blind_session,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )
    relay.complete_role(
        "demo",
        _review_completion(blind_action, blind_session, blind),
    )
    editor_action = relay.next_action("demo")
    editor_session = SessionIdentity(
        session_id="native-editor-01",
        session_instance_id="editor-instance-01",
        provider="editor-provider",
        model="editor-model",
        agent_harness="native-host",
        role="chapter-editor",
    )
    editor = backend.run_review(
        editor_session,
        role="chapter-editor",
        context=_review_capsule_context(editor_action),
        instructions=_review_capsule_instructions(editor_action),
        reasoning_effort="medium",
    )
    completion = _review_completion(
        editor_action,
        editor_session,
        editor,
    )
    completion["role_result"]["payload"]["hard_anchor_coverage"] = {
        "protagonist": {
            "status": "covered",
            "evidence": "林舟握住门把",
            "reader_reconstruction": "林舟是不愿求助的修锁匠。",
        },
        "world": {
            "status": "covered",
            "evidence": "林舟握住门把",
            "reader_reconstruction": "断电旧城里的门禁已经失灵。",
        },
        "conflict": {
            "status": "covered",
            "evidence": "林舟握住门把",
            "reader_reconstruction": "开门会暴露被藏起来的人。",
        },
        "ending_hook": {
            "status": "missing",
            "evidence": "",
            "reader_reconstruction": "读者无法重建门内人叫出追兵名字。",
        },
    }

    result = relay.complete_role("demo", completion)

    assert result.user_state == "running"
    assert result.message.startswith("审稿结果未被接受，已自动换新会话重试：")
    assert not (
        root / "books/demo/reviews/ch01-chapter-editor.md"
    ).exists()


def test_review_session_cannot_reuse_any_writer_sequence_identity(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay, blind_action = _prepare_blind_action(
        root,
        tmp_path / "capsules",
    )
    state = relay._load_state("demo")
    sequence_path = next(
        (root / "books/demo/planning/chapter-sequences").glob("*.json")
    )
    sequence = json.loads(sequence_path.read_text(encoding="utf-8"))
    sequence["used_session_ids"].append("retired-writer-01")
    sequence.setdefault("invalidated_sessions", []).append(
        {
            "session_id": "retired-writer-01",
            "chapter": 1,
            "reason": "writer_result_invalid",
            "invalidated_at": "2026-07-23T00:00:00+00:00",
        }
    )
    sequence_path.write_text(
        json.dumps(sequence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    relay._write_action("demo", state, blind_action)
    backend = ScriptedBackend([], [_pass_reviews()])
    reused = SessionIdentity(
        session_id="retired-writer-01",
        session_instance_id="fresh-looking-instance",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        reused,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )

    result = relay.complete_role(
        "demo",
        _review_completion(blind_action, reused, blind),
    )

    assert result.message.startswith("审稿结果未被接受，已自动换新会话重试：")
    assert list((root / "books/demo/reviews").glob("ch01-*.md")) == []


def test_failed_review_session_cannot_retry_with_same_identity(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay, blind_action = _prepare_blind_action(
        root,
        tmp_path / "capsules",
    )
    reused = SessionIdentity(
        session_id="native-blind-failed-01",
        session_instance_id="blind-failed-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    invalid = {
        "schema": "novel-forge-native-completion/v1",
        "action_id": blind_action["action_id"],
        "status": "completed",
        "session": asdict(reused),
        "operation_handle": {
            "kind": "native-task",
            "value": "blind-failed-operation-01",
        },
        "result_transport": "inline",
        "review_capsule_id": blind_action["review_capsule"]["id"],
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": "blind-reader",
            "payload": {},
        },
    }
    first = relay.complete_role("demo", invalid)
    retry_action = relay.next_action("demo")
    backend = ScriptedBackend([], [_pass_reviews()])
    blind = backend.run_review(
        reused,
        role="blind-reader",
        context=_review_capsule_context(retry_action),
        instructions=_review_capsule_instructions(retry_action),
        reasoning_effort="medium",
    )

    second = relay.complete_role(
        "demo",
        _review_completion(retry_action, reused, blind),
    )

    assert first.message.startswith("审稿结果未被接受，已自动换新会话重试：")
    assert second.message.startswith("审稿结果未被接受，已自动换新会话重试：")
    assert list((root / "books/demo/reviews").glob("ch01-*.md")) == []


def test_must_findings_create_a_fresh_patch_writer_session(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )
    request = _request()
    backend = ScriptedBackend([], [_must_reviews()])
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    writer = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="writer-provider",
        model="writer-model",
        agent_harness="native-host",
        role="writer",
    )
    planning = backend.run_planning(
        writer,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    relay.complete_role(
        "demo",
        _planning_completion(planning_action, writer, planning),
    )
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("需要修订"),
        encoding="utf-8",
    )
    relay.complete_role("demo", _writer_completion(writer_action, writer))
    blind_action = relay.next_action("demo")
    blind_session = SessionIdentity(
        session_id="native-blind-01",
        session_instance_id="blind-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        blind_session,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )
    relay.complete_role(
        "demo",
        _review_completion(blind_action, blind_session, blind),
    )
    editor_action = relay.next_action("demo")
    editor_session = SessionIdentity(
        session_id="native-editor-01",
        session_instance_id="editor-instance-01",
        provider="editor-provider",
        model="editor-model",
        agent_harness="native-host",
        role="chapter-editor",
    )
    editor = backend.run_review(
        editor_session,
        role="chapter-editor",
        context=_review_capsule_context(editor_action),
        instructions=_review_capsule_instructions(editor_action),
        reasoning_effort="medium",
    )

    result = relay.complete_role(
        "demo",
        _review_completion(editor_action, editor_session, editor),
    )
    create_action = relay.next_action("demo")

    assert result.message == "发现问题，正在自动修订。"
    assert create_action["kind"] == "create_session"
    assert create_action["role"] == "writer"
    patch_session = SessionIdentity(
        session_id="native-patch-01",
        session_instance_id="patch-instance-01",
        provider="writer-provider",
        model="writer-model",
        agent_harness="native-host",
        role="writer",
    )
    relay.complete_role(
        "demo",
        {
            "schema": "novel-forge-native-completion/v1",
            "action_id": create_action["action_id"],
            "status": "completed",
            "session": asdict(patch_session),
            "operation_handle": {
                "kind": "native-session-create",
                "value": "create-patch-session-01",
            },
            "result_transport": "inline",
            "role_result": {
                "schema": "novel-forge-role-result/v1",
                "role": "writer-session",
                "payload": {},
            },
        },
    )
    patch_action = relay.next_action("demo")

    assert patch_action["role"] == "writer"
    assert patch_action["session"]["session_id"] == "native-patch-01"
    assert patch_action["capsule"]["operation"] == "patch"
    assert "阻力出现得太晚" in (
        Path(patch_action["capsule"]["path"]) / "instructions.md"
    ).read_text(encoding="utf-8")


def test_writer_completion_envelope_is_repaired_without_rewriting(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )
    request = _request()
    backend = ScriptedBackend([], [])
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    writer = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="writer-provider",
        model="writer-model",
        agent_harness="native-host",
        role="writer",
    )
    planning = backend.run_planning(
        writer,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    relay.complete_role(
        "demo",
        _planning_completion(planning_action, writer, planning),
    )
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("补交运行证明"),
        encoding="utf-8",
    )
    malformed = _writer_completion(writer_action, writer)
    runtime_snapshot = malformed.pop("runtime_snapshot")
    malformed["runtime"] = runtime_snapshot

    result = relay.complete_role("demo", malformed)
    repair_action = relay.next_action("demo")
    receipts = list(
        (root / "books/demo/evidence/guardian-receipts").glob("*.json")
    )

    assert result.message == "正在确认角色结果。"
    assert result.technical_retry_count == 0
    assert repair_action["action_id"] == writer_action["action_id"]
    assert repair_action["role"] == "writer"
    assert repair_action["session"] == writer_action["session"]
    assert repair_action["capsule"] == writer_action["capsule"]
    assert repair_action["completion_repair"]["attempt"] == 1
    assert "runtime_snapshot" in repair_action["completion_template"]
    assert repair_action["completion_template"]["role_result"][
        "payload"
    ] == {"artifact_relative_path": "draft/正文.md"}
    assert receipts == []
    assert (
        Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    ).is_file()

    corrected = _writer_completion(writer_action, writer)
    completed = relay.complete_role("demo", corrected)

    assert completed.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "blind-reader"
    assert len(
        list((root / "books/demo/evidence/generations").glob("*.md"))
    ) == 1
    assert len(
        list(
            (root / "books/demo/evidence/guardian-receipts").glob(
                "*.json"
            )
        )
    ) == 1


def test_blind_review_retry_budget_is_independent_from_writer_history(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay, blind_action = _prepare_blind_action(
        root,
        tmp_path / "capsules",
    )
    state_path = (
        root / ".local-guardian/demo/native-relay/state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["technical_retry_count"] = 2
    relay._write_action("demo", state, blind_action)
    blind_session = SessionIdentity(
        session_id="native-blind-invalid-01",
        session_instance_id="blind-invalid-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    invalid = {
        "schema": "novel-forge-native-completion/v1",
        "action_id": blind_action["action_id"],
        "status": "completed",
        "session": asdict(blind_session),
        "operation_handle": {
            "kind": "native-task",
            "value": "blind-invalid-operation-01",
        },
        "result_transport": "inline",
        "review_capsule_id": blind_action["review_capsule"]["id"],
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": "blind-reader",
            "payload": {},
        },
    }

    result = relay.complete_role("demo", invalid)
    retry_action = relay.next_action("demo")

    assert result.user_state == "running"
    assert result.message.startswith("审稿结果未被接受，已自动换新会话重试：")
    assert result.technical_retry_count == 1
    assert retry_action["role"] == "blind-reader"
    assert retry_action["session"]["mode"] == "new"
    assert retry_action["action_id"] != blind_action["action_id"]


def test_mutated_review_capsule_is_replaced_before_review_retry(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay, blind_action = _prepare_blind_action(
        root,
        tmp_path / "capsules",
    )
    old_capsule = Path(blind_action["review_capsule"]["path"])
    (old_capsule / "prose.md").write_text(
        _prose("被替换的旧稿"),
        encoding="utf-8",
    )
    blind_session = SessionIdentity(
        session_id="native-blind-mutated-01",
        session_instance_id="blind-mutated-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    completion = {
        "schema": "novel-forge-native-completion/v1",
        "action_id": blind_action["action_id"],
        "status": "completed",
        "session": asdict(blind_session),
        "operation_handle": {
            "kind": "native-task",
            "value": "blind-mutated-operation-01",
        },
        "result_transport": "inline",
        "review_capsule_id": blind_action["review_capsule"]["id"],
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": "blind-reader",
            "payload": asdict(_pass_reviews()[0]),
        },
    }

    result = relay.complete_role("demo", completion)
    retry_action = relay.next_action("demo")
    new_capsule = Path(retry_action["review_capsule"]["path"])
    current_prose = (
        root / "books/demo/chapters/e01/ch-01/正文.md"
    ).read_text(encoding="utf-8")

    assert result.message.startswith("审稿结果未被接受，已自动换新会话重试：")
    assert retry_action["review_capsule"]["id"] != (
        blind_action["review_capsule"]["id"]
    )
    assert new_capsule != old_capsule
    assert (new_capsule / "prose.md").read_text(
        encoding="utf-8"
    ) == current_prose
    assert list((root / "books/demo/reviews").glob("ch01-*.md")) == []


def test_editor_retry_budget_starts_after_blind_reader_success(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay, blind_action = _prepare_blind_action(
        root,
        tmp_path / "capsules",
    )
    state = relay._load_state("demo")
    state["technical_retry_counts"] = {"blind-reader": 2}
    state["technical_retry_count"] = 2
    relay._write_action("demo", state, blind_action)
    backend = ScriptedBackend([], [_pass_reviews()])
    blind_session = SessionIdentity(
        session_id="native-blind-success-01",
        session_instance_id="blind-success-instance-01",
        provider="blind-provider",
        model="blind-model",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        blind_session,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )
    relay.complete_role(
        "demo",
        _review_completion(blind_action, blind_session, blind),
    )
    editor_action = relay.next_action("demo")
    editor_session = SessionIdentity(
        session_id="native-editor-invalid-01",
        session_instance_id="editor-invalid-instance-01",
        provider="editor-provider",
        model="editor-model",
        agent_harness="native-host",
        role="chapter-editor",
    )
    invalid = {
        "schema": "novel-forge-native-completion/v1",
        "action_id": editor_action["action_id"],
        "status": "completed",
        "session": asdict(editor_session),
        "operation_handle": {
            "kind": "native-task",
            "value": "editor-invalid-operation-01",
        },
        "result_transport": "inline",
        "review_capsule_id": editor_action["review_capsule"]["id"],
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": "chapter-editor",
            "payload": {},
        },
    }

    result = relay.complete_role("demo", invalid)
    retry_action = relay.next_action("demo")

    assert result.user_state == "running"
    assert result.technical_retry_count == 1
    assert retry_action["role"] == "chapter-editor"
    assert retry_action["session"]["mode"] == "new"


def test_retry_after_review_transport_exhaustion_preserves_generation(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay, blind_action = _prepare_blind_action(
        root,
        tmp_path / "capsules",
    )
    state_path = (
        root / ".local-guardian/demo/native-relay/state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    generation_id = state["generation_id"]
    body_sha256 = state["body_sha256"]
    writer_session = state["writer_session"]["session_id"]
    state.update(
        {
            "phase": "decision_required",
            "technical_retry_count": 3,
            "decision_kind": "native_role_failed",
            "failed_phase": "awaiting_blind_reader",
        }
    )
    relay._write_action("demo", state, blind_action)
    relay._action_path("demo").unlink()

    result = relay.retry("demo")
    resumed = relay.next_action("demo")
    resumed_state = json.loads(
        state_path.read_text(encoding="utf-8")
    )

    assert result.message == "正在自动审稿。"
    assert resumed["role"] == "blind-reader"
    assert resumed["session"]["mode"] == "new"
    assert resumed_state["generation_id"] == generation_id
    assert resumed_state["body_sha256"] == body_sha256
    assert resumed_state["writer_session"]["session_id"] == writer_session
    assert len(
        list((root / "books/demo/evidence/generations").glob("*.md"))
    ) == 1


def test_lean_retry_after_review_exhaustion_preserves_staged_prose(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    prose = _prose("审稿恢复保留正文")
    staged.write_text(prose, encoding="utf-8")
    relay.complete_minimal("demo")

    state = relay._load_state("demo")
    state.update(
        {
            "phase": "decision_required",
            "decision_kind": "native_role_failed",
            "failed_phase": "awaiting_blind_reader",
            "technical_retry_count": 2,
            "technical_retry_counts": {"blind-reader": 2},
        }
    )
    relay._state_path("demo").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    relay._action_path("demo").unlink(missing_ok=True)

    result = relay.retry("demo")
    action = relay.next_action("demo")

    assert result.message == "正在自动审稿。"
    assert action["role"] == "blind-reader"
    assert staged.read_text(encoding="utf-8") == prose
    assert not (
        root / "books/demo/chapters/e01/ch-01/正文.md"
    ).exists()
    assert list((root / "books/demo/evidence/generations").glob("*.md")) == []
def test_control_plane_mutation_is_restored_before_writer_retry(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    root.mkdir()
    protected = root / "operator-notes.md"
    protected.write_text("用户原始内容\n", encoding="utf-8")
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )
    request = _request()
    backend = ScriptedBackend([], [])
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    writer = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="writer-provider",
        model="writer-model",
        agent_harness="native-host",
        role="writer",
    )
    planning = backend.run_planning(
        writer,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    relay.complete_role(
        "demo",
        _planning_completion(planning_action, writer, planning),
    )
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("控制面恢复"),
        encoding="utf-8",
    )
    protected.write_text("角色越权修改\n", encoding="utf-8")

    result = relay.complete_role(
        "demo",
        _writer_completion(writer_action, writer),
    )
    receipt_path = next(
        (root / "books/demo/evidence/guardian-receipts").glob("*.json")
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert result.message.startswith(
        "写作会话异常，已自动换新会话重试。"
    )
    assert protected.read_text(encoding="utf-8") == "用户原始内容\n"
    assert "control_plane_mutation" in receipt["reasons"]
    assert relay.next_action("demo")["kind"] == "create_session"


def test_native_writer_only_prompts_after_two_automatic_retries(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        max_technical_retries=2,
    )
    request = _request()
    backend = ScriptedBackend([], [])
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    writer = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="writer-provider",
        model="writer-model",
        agent_harness="native-host",
        role="writer",
    )
    planning = backend.run_planning(
        writer,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    relay.complete_role(
        "demo",
        _planning_completion(planning_action, writer, planning),
    )
    writer_action = relay.next_action("demo")
    sessions = [
        writer,
        SessionIdentity(
            session_id="native-writer-02",
            session_instance_id="writer-instance-02",
            provider="writer-provider",
            model="writer-model",
            agent_harness="native-host",
            role="writer",
        ),
        SessionIdentity(
            session_id="native-writer-03",
            session_instance_id="writer-instance-03",
            provider="writer-provider",
            model="writer-model",
            agent_harness="native-host",
            role="writer",
        ),
    ]

    for index, session in enumerate(sessions):
        capsule = Path(writer_action["capsule"]["path"])
        (capsule / "draft/正文.md").write_text(
            _prose(f"失败{index + 1}"),
            encoding="utf-8",
        )
        (capsule / "runtime.json").write_text(
            "{}",
            encoding="utf-8",
        )
        invalid = _writer_completion(writer_action, session)
        result = relay.complete_role("demo", invalid)
        if index < 2:
            assert result.user_state == "running"
            create_action = relay.next_action("demo")
            next_session = sessions[index + 1]
            relay.complete_role(
                "demo",
                {
                    "schema": "novel-forge-native-completion/v1",
                    "action_id": create_action["action_id"],
                    "status": "completed",
                    "session": asdict(next_session),
                    "operation_handle": {
                        "kind": "native-session-create",
                        "value": (
                            f"create-{next_session.session_id}"
                        ),
                    },
                    "result_transport": "inline",
                    "role_result": {
                        "schema": "novel-forge-role-result/v1",
                        "role": "writer-session",
                        "payload": {},
                    },
                },
            )
            writer_action = relay.next_action("demo")

    assert result.user_state == "decision_required"
    assert result.message == "自动重试仍未完成，请选择下一步。"
    assert result.options == (
        "A. 保留草稿",
        "B. 重新生成本章",
        "C. 停止任务",
    )
    visible = "\n".join((result.message, *result.options))
    for forbidden in (
        "session",
        "guardian",
        "sha-256",
        "traceback",
        "json",
    ):
        assert forbidden not in visible.lower()
    assert len(
        list(
            (
                root
                / "books/demo/evidence/guardian-receipts"
            ).glob("*.json")
        )
    ) == 3


def _review_capsule_manifest(action: dict) -> tuple[Path, dict]:
    capsule = Path(action["review_capsule"]["path"])
    manifest = json.loads(
        (capsule / "manifest.json").read_text(encoding="utf-8")
    )
    return capsule, manifest


def _review_capsule_context(action: dict) -> dict[str, str]:
    capsule, manifest = _review_capsule_manifest(action)
    return {
        item["logical_name"]: (capsule / item["path"]).read_text(
            encoding="utf-8"
        )
        for item in manifest["files"]
        if item["logical_name"] != "instructions"
    }


def _review_capsule_instructions(action: dict) -> str:
    capsule, manifest = _review_capsule_manifest(action)
    item = next(
        entry
        for entry in manifest["files"]
        if entry["logical_name"] == "instructions"
    )
    return (capsule / item["path"]).read_text(encoding="utf-8")


def _prepare_blind_action(
    root: Path,
    capsule_root: Path,
) -> tuple[NativeWorkflowRelay, dict]:
    relay = NativeWorkflowRelay(root, capsule_root=capsule_root)
    request = _request()
    backend = ScriptedBackend([], [])
    relay.start("demo", request, chapter=1)
    planning_action = relay.next_action("demo")
    writer = SessionIdentity(
        session_id="native-writer-01",
        session_instance_id="writer-instance-01",
        provider="writer-provider",
        model="writer-model",
        agent_harness="native-host",
        role="writer",
    )
    planning = backend.run_planning(
        writer,
        request=request,
        chapter=1,
        context=planning_action["context"],
        instructions=planning_action["instructions"],
        reasoning_effort="high",
    )
    relay.complete_role(
        "demo",
        _planning_completion(planning_action, writer, planning),
    )
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("封存审稿输入"),
        encoding="utf-8",
    )
    relay.complete_role(
        "demo",
        _writer_completion(writer_action, writer),
    )
    return relay, relay.next_action("demo")


def _planning_completion(
    action: dict,
    session: SessionIdentity,
    planning,
) -> dict:
    return {
        "schema": "novel-forge-native-completion/v1",
        "action_id": action["action_id"],
        "status": "completed",
        "session": asdict(session),
        "operation_handle": {
            "kind": planning.operation_kind,
            "value": planning.operation_id,
        },
        "result_transport": planning.result_transport,
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": "writer-planning",
            "payload": {"files": planning.files},
        },
    }


def _writer_completion(
    action: dict,
    session: SessionIdentity,
) -> dict:
    runtime = _runtime(session.session_id, action["capsule"]["id"])
    runtime["guardian"].update(
        {
            "assurance_mode": "formal_native",
            "filesystem_scope": "guarded_native",
            "write_scope": "post_execution_verified",
            "repository_snapshot_enforced": True,
            "reported_by": "native_host",
        }
    )
    return {
        "schema": "novel-forge-native-completion/v1",
        "action_id": action["action_id"],
        "status": "completed",
        "session": asdict(session),
        "operation_handle": {
            "kind": "native-task",
            "value": f"writer-operation-{session.session_id}",
        },
        "result_transport": "artifact",
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": "writer",
            "payload": {"artifact_relative_path": "draft/正文.md"},
        },
        "runtime_snapshot": runtime,
    }


def _review_completion(
    action: dict,
    session: SessionIdentity,
    outcome,
) -> dict:
    return {
        "schema": "novel-forge-native-completion/v1",
        "action_id": action["action_id"],
        "status": "completed",
        "session": asdict(session),
        "operation_handle": {
            "kind": outcome.operation_kind,
            "value": outcome.operation_id,
        },
        "result_transport": outcome.result_transport,
        "review_capsule_id": action["review_capsule"]["id"],
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": action["role"],
            "payload": asdict(outcome),
        },
    }


def test_lean_native_action_keeps_technical_records_out_of_role_contract(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )

    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    serialized = json.dumps(action, ensure_ascii=False)

    assert action["role"] == "writer"
    assert action["stage"] == "draft"
    assert action["assurance_mode"] == "lean_native"
    assert "completion_template" not in action
    assert "runtime_snapshot" not in serialized
    assert "SHA-256" not in serialized
    assert "generation" not in serialized.lower()
    assert "guardian" not in serialized.lower()
    assert "git" not in serialized.lower()


def test_lean_start_dispatches_prose_capsule_as_first_writer_action(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )

    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")

    assert action["role"] == "writer"
    assert action["stage"] == "draft"
    assert action["session"]["mode"] == "new"
    assert action["session"]["must_be_independent"] is True
    assert action["lead_must_delegate"] is True
    assert action["lead_may_write_role_output"] is False
    assert "禁止亲自写正文" in action["delivery"]
    assert "control_run_id" not in action
    assert action["capsule"]["output"] == "draft/正文.md"
    assert Path(action["capsule"]["path"]).is_dir()
    assert "result_file" not in action
    assert "planning" not in action



def test_lean_writer_capsule_contains_minimal_p0_p1_p2_package(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)

    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    capsule = Path(action["capsule"]["path"])
    context = capsule / "writer-context.md"
    manifest = json.loads((capsule / "capsule.json").read_text(encoding="utf-8"))

    assert context.is_file()
    assert "# P0 必须" in context.read_text(encoding="utf-8")
    assert "# P1 重要" in context.read_text(encoding="utf-8")
    assert "# P2 可裁剪参考" in context.read_text(encoding="utf-8")
    assert action["capsule"]["context"] == "writer-context.md"
    assert manifest["writer_context_mode"] == "minimal"
    assert {
        name: tier["budget_cjk"]
        for name, tier in manifest["writer_context_tiers"].items()
    } == {"P0": 1500, "P1": 850, "P2": 450}

def test_lean_writer_completion_needs_only_the_existing_prose(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    prose = _prose("正文优先")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        prose,
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "blind-reader"
    assert (
        root
        / "books/demo/.novel-forge/diff/ch01/writer/draft/正文.md"
    ).read_text(encoding="utf-8") == prose
    assert not (
        root / "books/demo/chapters/e01/ch-01/正文.md"
    ).exists()

    review_action = relay.next_action("demo")
    assert review_action["session"]["must_be_independent"] is True
    assert review_action["lead_must_delegate"] is True
    assert review_action["lead_may_write_role_output"] is False
    assert "禁止亲自写 result_file" in review_action["delivery"]
    assert "control_run_id" not in review_action


def test_lean_surface_blockers_return_to_same_writer_before_import(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    capsule = Path(writer_action["capsule"]["path"])
    blocked = _prose("表面门修订").replace(
        "林舟握住门把",
        "**林舟握住门把**",
        1,
    )
    (capsule / "draft/正文.md").write_text(
        blocked,
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")
    patch_action = relay.next_action("demo")

    assert result.message == "发现问题，正在自动修订。"
    assert result.technical_retry_count == 0
    assert patch_action["role"] == "writer"
    assert patch_action["stage"] == "patch"
    assert patch_action["session"]["mode"] == "reuse_preferred"
    assert patch_action["session"]["must_be_independent"] is True
    assert patch_action["lead_must_delegate"] is True
    assert patch_action["lead_may_write_role_output"] is False
    assert "control_run_id" not in patch_action
    assert patch_action["capsule"]["path"] == str(capsule)
    assert any(
        "markdown-emphasis" in item
        for item in patch_action["must_findings"]
    )
    assert list((root / "books/demo/evidence/generations").glob("*.md")) == []

    (capsule / "draft/正文.md").write_text(
        _prose("表面门修订完成"),
        encoding="utf-8",
    )
    completed = relay.complete_minimal("demo")

    assert completed.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "blind-reader"
    assert list((root / "books/demo/evidence/generations").glob("*.md")) == []
    assert not (
        root / "books/demo/chapters/e01/ch-01/正文.md"
    ).exists()


def test_lean_surface_patch_can_continue_on_the_same_staged_body(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    blocked = _prose("连续表面修订").replace(
        "林舟握住门把",
        "**林舟握住门把**",
        1,
    )
    staged.write_text(blocked, encoding="utf-8")

    relay.complete_minimal("demo")
    first_patch = relay.next_action("demo")
    staged.write_text(blocked, encoding="utf-8")
    second_result = relay.complete_minimal("demo")
    second_patch = relay.next_action("demo")

    assert second_result.message == "发现问题，正在自动修订。"
    assert second_patch["role"] == "writer"
    assert second_patch["stage"] == "patch"
    assert second_patch["capsule"]["path"] == first_patch["capsule"]["path"]

    staged.write_text(_prose("连续表面修订完成"), encoding="utf-8")
    completed = relay.complete_minimal("demo")

    assert completed.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "blind-reader"


def test_lean_mechanical_language_forces_one_consolidated_surface_patch(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    prose = _prose("风格提示保留").replace(
        "林舟握住门把",
        "林舟——握住门把。那不是门，而是一道伤口……",
        1,
    )
    staged.write_text(prose, encoding="utf-8")

    result = relay.complete_minimal("demo")
    patch_action = relay.next_action("demo")

    assert result.message == "发现问题，正在自动修订。"
    assert patch_action["role"] == "writer"
    assert patch_action["stage"] == "patch"
    assert patch_action["capsule"]["path"] == writer_action["capsule"]["path"]
    findings = "\n".join(patch_action["must_findings"])
    assert "em-dash" in findings
    assert "ellipsis" in findings
    assert "not-is-flip" in findings
    assert staged.read_text(encoding="utf-8") == prose


def test_lean_all_local_must_uses_fragment_replacement_then_full_rereview(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    prose = _prose("局部修订正文") + "\n\n林舟把铜扣放回左侧口袋，这句解释只出现一次。\n"
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(prose, encoding="utf-8")
    relay.complete_minimal("demo")

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
    for role, outcome in zip(("blind-reader", "chapter-editor"), local_reviews):
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
            json.dumps(asdict(produced), ensure_ascii=False), encoding="utf-8"
        )
        result = relay.complete_minimal("demo")

    patch = relay.next_action("demo")
    assert result.message == "发现局部问题，正在精确修订。"
    assert patch["role"] == "writer"
    assert patch["stage"] == "local-patch"
    assert patch["result_file"].endswith("replacements.json")
    payload = json.loads(Path(patch["input_file"]).read_text(encoding="utf-8"))
    target = payload["targets"][0]["target"]
    Path(patch["result_file"]).write_text(
        json.dumps(
            {"replacements": [{"target": target, "replacement": "林舟把铜扣塞回左侧口袋。"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = relay.complete_minimal("demo")

    assert completed.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "blind-reader"
    assert "铜扣塞回左侧口袋" in staged.read_text(encoding="utf-8")
    assert not (root / "books/demo/chapters/e01/ch-01/正文.md").exists()


def test_lean_must_findings_return_directly_to_writer_for_one_patch(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    backend = ScriptedBackend([], [_must_reviews(), _pass_reviews()])
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("待修订正文"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    blind = backend.run_review(
        SessionIdentity(
            session_id="host-review-session",
            session_instance_id="host-review-session",
            provider="unknown",
            model="unknown",
            agent_harness="native-host",
            role="blind-reader",
        ),
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )
    Path(blind_action["result_file"]).write_text(
        json.dumps(asdict(blind), ensure_ascii=False),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    editor_action = relay.next_action("demo")
    editor = backend.run_review(
        SessionIdentity(
            session_id="host-review-session",
            session_instance_id="host-review-session",
            provider="unknown",
            model="unknown",
            agent_harness="native-host",
            role="chapter-editor",
        ),
        role="chapter-editor",
        context=_review_capsule_context(editor_action),
        instructions=_review_capsule_instructions(editor_action),
        reasoning_effort="medium",
    )
    Path(editor_action["result_file"]).write_text(
        json.dumps(asdict(editor), ensure_ascii=False),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")
    patch_action = relay.next_action("demo")

    assert result.message == "发现问题，正在自动修订。"
    assert patch_action["kind"] == "run_role"
    assert patch_action["role"] == "writer"
    assert patch_action["stage"] == "patch"
    assert patch_action["session"]["mode"] == "reuse_preferred"
    assert patch_action["capsule"]["output"] == "draft/正文.md"

    staged_body = Path(patch_action["capsule"]["path"]) / "draft/正文.md"
    initial_body = (
        root
        / "books/demo/.novel-forge/diff/ch01/控制面冻结稿.md"
    )
    chapter_body = root / "books/demo/chapters/e01/ch-01/正文.md"
    original = staged_body.read_text(encoding="utf-8")
    revised = _prose("审核后在同一暂存正文上修订")

    assert initial_body.read_text(encoding="utf-8") == original
    assert not chapter_body.exists()

    state_path = relay._state_path("demo")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["technical_retry_counts"]["blind-reader"] = 2
    state["technical_retry_count"] = 2
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    relay._write_lean_control_snapshot(
        "demo",
        patch_action["action_id"],
    )
    staged_body.write_text(revised, encoding="utf-8")
    relay.complete_minimal("demo")
    refreshed_state = relay._load_state("demo")
    assert refreshed_state["technical_retry_counts"]["blind-reader"] == 0
    assert "must_findings" not in refreshed_state
    diff_path = (
        root / "books/demo/.novel-forge/diff/ch01/修订.diff"
    )
    diff = diff_path.read_text(encoding="utf-8")
    assert "待修订正文" in diff
    assert "审核后在同一暂存正文上修订" in diff
    for index, role in enumerate(("blind-reader", "chapter-editor"), 1):
        action = relay.next_action("demo")
        session = SessionIdentity(
            session_id=f"pass-{role}-{index}",
            session_instance_id=f"pass-{role}-{index}",
            provider="unknown",
            model="unknown",
            agent_harness="native-host",
            role=role,
        )
        outcome = backend.run_review(
            session,
            role=role,
            context=_review_capsule_context(action),
            instructions=_review_capsule_instructions(action),
            reasoning_effort="medium",
        )
        Path(action["result_file"]).write_text(
            json.dumps(asdict(outcome), ensure_ascii=False),
            encoding="utf-8",
        )
        completed = relay.complete_minimal("demo")

    assert completed.user_state == "chapter_complete"
    assert chapter_body.read_text(encoding="utf-8") == revised
    assert initial_body.read_text(encoding="utf-8") == original
    diff = diff_path.read_text(encoding="utf-8")
    assert "待修订正文" in diff
    assert "审核后在同一暂存正文上修订" in diff


def test_lean_completion_uses_session_and_role_payload_only(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("只回传正文"),
        encoding="utf-8",
    )

    result = relay.complete_minimal(
        "demo",
        session_id="host-may-return-any-reference",
    )
    review_action = relay.next_action("demo")

    assert result.message == "正在自动审稿。"
    assert review_action["role"] == "blind-reader"
    assert "completion_template" not in writer_action


def test_lean_native_stages_body_inside_book_until_double_review_passes(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    backend = ScriptedBackend([], [_pass_reviews()])
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged_body = (
        root
        / "books/demo/.novel-forge/diff/ch01/writer/draft/正文.md"
    )

    assert Path(writer_action["capsule"]["path"]) == staged_body.parent.parent

    prose = _prose("双审通过后才进入正式正文")
    staged_body.write_text(prose, encoding="utf-8")
    relay.complete_minimal("demo")

    chapter_body = root / "books/demo/chapters/e01/ch-01/正文.md"
    assert not chapter_body.exists()
    assert list((root / "books/demo/evidence/generations").glob("*.md")) == []

    blind_action = relay.next_action("demo")
    blind_session = SessionIdentity(
        session_id="lean-blind-01",
        session_instance_id="lean-blind-01",
        provider="unknown",
        model="unknown",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        blind_session,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )
    Path(blind_action["result_file"]).write_text(
        json.dumps(asdict(blind), ensure_ascii=False),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    assert not chapter_body.exists()

    editor_action = relay.next_action("demo")
    editor_session = SessionIdentity(
        session_id="lean-editor-01",
        session_instance_id="lean-editor-01",
        provider="unknown",
        model="unknown",
        agent_harness="native-host",
        role="chapter-editor",
    )
    editor = backend.run_review(
        editor_session,
        role="chapter-editor",
        context=_review_capsule_context(editor_action),
        instructions=_review_capsule_instructions(editor_action),
        reasoning_effort="medium",
    )
    Path(editor_action["result_file"]).write_text(
        json.dumps(asdict(editor), ensure_ascii=False),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "chapter_complete"
    assert chapter_body.read_text(encoding="utf-8") == prose
    assert staged_body.read_text(encoding="utf-8") == prose
    assert len(
        list((root / "books/demo/evidence/generations").glob("*.md"))
    ) == 1
    assert len(
        list(
            (
                root
                / ".local-guardian/demo/native-relay/runtime"
            ).glob("*.json")
        )
    ) == 1


def test_lean_review_accepts_compact_result_with_natural_newlines(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("自然换行审稿"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")
    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        """{
  "verdict": "pass",
  "must": [],
  "human_likeness": "convincing",
  "reader_desire": "continue",
  "emotional_residue": "人物的选择留下了明确余波。",
  "next_chapter_pull": "门后的人是谁？
他为何认识追兵？",
  "summary": "空间、身体、约束、情绪、对白和记忆画面均能重建。",
  "evidence_quote": "林舟握住门把"
}
""",
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "chapter-editor"


def test_lean_blind_reader_retries_when_evidence_quote_is_not_in_prose(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("盲审引文校验"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")
    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "结尾留下明确的情绪余波。",
                "next_chapter_pull": "读者想知道门后的人是谁。",
                "summary": "空间、动作与情绪均能重建。",
                "evidence_quote": "这句文字不在当前正文中。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "running"
    assert result.technical_retry_count == 1
    assert relay.next_action("demo")["role"] == "blind-reader"


def test_lean_editor_pass_uses_compact_result_without_a_hard_anchor_table(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(_prose("通用编辑通过"), encoding="utf-8")
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下了后果。",
                "next_chapter_pull": "门后的人将要求什么代价？",
                "summary": "现场、关系和行动均可重建。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    editor_action = relay.next_action("demo")
    editor_instructions = _review_capsule_instructions(editor_action)
    assert editor_action["result"]["required"] == [
        "verdict",
        "must",
        "summary",
        "evidence_quote",
    ]
    assert "hard_anchor_coverage" not in editor_instructions
    Path(editor_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "summary": "因果、选择、对白、肌理和连续性均成立。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "chapter_complete"
    assert (
        root / "books/demo/chapters/e01/ch-01/正文.md"
    ).read_text(encoding="utf-8") == staged.read_text(encoding="utf-8")


def test_lean_editor_repairs_common_unescaped_quotes_in_result_json(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(_prose("引号容错"), encoding="utf-8")
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    assert "result_file" in blind_action["task"]
    assert "official terminal" not in blind_action["task"]
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下了后果。",
                "next_chapter_pull": "门后的人将要求什么代价？",
                "summary": "现场、关系和行动均可重建。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    editor_action = relay.next_action("demo")
    Path(editor_action["result_file"]).write_text(
        """{
  "verdict": "pass",
  "findings": [
    {
      "severity": "MAY",
      "issue": "信息来源可再清楚一点。",
      "evidence": "原文："林舟握住门把""
    }
  ],
  "summary": "本章成立。",
  "evidence_quote": "林舟握住门把"
}
""",
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "chapter_complete"


def test_lean_editor_ignores_legacy_hard_anchor_prose(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    mechanical = "他停了一下，看向门口。这意味着他已经作出决定。"
    staged.write_text(
        "# 第一章\n\n" + "\n\n".join(mechanical for _ in range(420)),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下了后果。",
                "next_chapter_pull": "门后的人将要求什么代价？",
                "summary": "现场、关系和行动均可重建。",
                "evidence_quote": "他停了一下",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    editor_action = relay.next_action("demo")
    editor_context = _review_capsule_context(editor_action)
    assert "machine_diagnostics" in editor_context
    assert "机器纹理提示" in editor_context["machine_diagnostics"]
    assert len(editor_context["machine_diagnostics"]) <= 160
    Path(editor_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "ready_for_editor_decision",
                "findings": [],
                "summary": "本章成立。",
                "hard_anchor_coverage": "五项用户硬锚均已交付。",
                "evidence_quote": "他停了一下",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "chapter_complete"


def test_lean_editor_accepts_a_valid_control_plane_capsule_refresh(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(_prose("控制面刷新"), encoding="utf-8")
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下了后果。",
                "next_chapter_pull": "门后的人将要求什么代价？",
                "summary": "现场、关系和行动均可重建。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    editor_action = relay.next_action("demo")
    capsule = Path(editor_action["review_capsule"]["path"])
    manifest_path = capsule / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene_item = next(
        item
        for item in manifest["files"]
        if item["logical_name"] == "scene_package"
    )
    scene_path = capsule / scene_item["path"]
    scene_text = scene_path.read_text(encoding="utf-8") + "\n控制面刷新。\n"
    scene_payload = scene_text.encode("utf-8")
    scene_path.write_bytes(scene_payload)
    scene_item["bytes"] = len(scene_payload)
    scene_item["sha256"] = hashlib.sha256(scene_payload).hexdigest()
    manifest["capsule_id"] = "review-chapter-editor-refreshed"
    manifest_payload = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_payload)

    descriptor = dict(editor_action["review_capsule"])
    descriptor["id"] = manifest["capsule_id"]
    descriptor["manifest_sha256"] = hashlib.sha256(
        manifest_payload
    ).hexdigest()
    editor_action["review_capsule"] = descriptor
    relay._action_path("demo").write_text(
        json.dumps(editor_action, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    state = relay._load_state("demo")
    state["review_capsule"] = descriptor
    relay._state_path("demo").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    relay._write_lean_control_snapshot(
        "demo",
        editor_action["action_id"],
    )
    Path(editor_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "summary": "因果、选择、对白、肌理和连续性均成立。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "chapter_complete"
    assert editor_action["allowed_project_writes"] == [
        ".novel-forge/diff/ch01/chapter-editor.json"
    ]
    assert set(editor_action["control_plane_managed_paths"]) >= {
        ".novel-forge/diff/ch01/chapter-editor-input/manifest.json",
        ".novel-forge/diff/ch01/chapter-editor-input/scene-package.md",
    }


def test_lean_writer_unknown_runtime_does_not_discard_valid_prose(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    prose = _prose("精简原生流程")
    capsule = Path(writer_action["capsule"]["path"])
    (capsule / "draft/正文.md").write_text(prose, encoding="utf-8")

    result = relay.complete_minimal("demo")

    assert result.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "blind-reader"
    assert (capsule / "draft/正文.md").read_text(encoding="utf-8") == prose
    assert not (
        root / "books/demo/chapters/e01/ch-01/正文.md"
    ).exists()
    assert list((root / "books/demo/evidence/generations").glob("*.md")) == []
    assert list(
        (root / "books/demo/evidence/guardian-receipts").glob("*.json")
    ) == []


def test_lean_integrity_ignores_unrelated_repository_changes(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("仓库外变化"),
        encoding="utf-8",
    )
    (root / "unrelated.txt").write_text(
        "another host changed this file",
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.message == "正在自动审稿。"
    assert (root / "unrelated.txt").is_file()


def test_lean_integrity_restores_protected_source_changes(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    source = root / "app/novel_forge/native_relay.py"
    source.parent.mkdir(parents=True)
    source.write_text("# original control plane\n", encoding="utf-8")
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("代码保护"),
        encoding="utf-8",
    )
    source.write_text("# role changed the rules\n", encoding="utf-8")

    result = relay.complete_minimal("demo")

    assert result.message.startswith(
        "写作会话异常，已自动换新会话重试。"
    )
    assert source.read_text(encoding="utf-8") == "# original control plane\n"
    retry = relay.next_action("demo")
    assert retry["role"] == "writer"
    assert retry["stage"] == "draft"


def test_lean_action_tampering_cannot_expand_book_write_scope(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    staged = Path(action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(_prose("动作防篡改"), encoding="utf-8")
    protected = root / "books/demo/planning/story-engine.md"
    original = protected.read_text(encoding="utf-8")

    tampered = dict(action)
    tampered["allowed_project_writes"] = [
        "planning/story-engine.md",
        ".novel-forge/diff/ch01/writer/draft/正文.md",
    ]
    relay._action_path("demo").write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    protected.write_text("角色改写了故事控制面\n", encoding="utf-8")

    result = relay.complete_minimal("demo")

    assert result.message.startswith(
        "写作会话异常，已自动换新会话重试。"
    )
    assert protected.read_text(encoding="utf-8") == original
    retry = relay.next_action("demo")
    assert "planning/story-engine.md" not in retry[
        "allowed_project_writes"
    ]


def test_lean_state_tampering_uses_restored_state_for_recovery(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("状态防篡改"),
        encoding="utf-8",
    )
    state = relay._load_state("demo")
    state["action_id"] = "forged-action-id"
    state["technical_retry_count"] = 99
    relay._state_path("demo").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "running"
    assert result.technical_retry_count == 1
    restored = relay._load_state("demo")
    assert restored["technical_retry_count"] == 1
    assert restored["action_id"] != "forged-action-id"
    assert relay.next_action("demo")["role"] == "writer"


def test_strict_audit_keeps_full_completion_contract(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=True,
    )

    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")

    assert action["role"] == "writer-planning"
    assert "completion_template" in action


def _complete_lean_chapter_with_passes(
    relay: NativeWorkflowRelay,
    slug: str,
    prose: str,
) -> None:
    writer_action = relay.next_action(slug)
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        prose,
        encoding="utf-8",
    )
    relay.complete_minimal(slug)
    for role, payload in (
        (
            "blind-reader",
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下明确余波。",
                "next_chapter_pull": "下一章的代价仍未揭开。",
                "summary": "空间、行动和情绪都可以重建。",
                "evidence_quote": "林舟握住门把",
            },
        ),
        (
            "chapter-editor",
            {
                "verdict": "pass",
                "must": [],
                "summary": "因果、选择、对白、肌理和连续性成立。",
                "evidence_quote": "林舟握住门把",
            },
        ),
    ):
        action = relay.next_action(slug)
        assert action["role"] == role
        Path(action["result_file"]).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        result = relay.complete_minimal(slug)
    assert result.user_state == "chapter_complete"


def _complete_lean_reviews_without_assert(
    relay: NativeWorkflowRelay, slug: str
) -> WorkflowResult:
    result = None
    for role, payload in (
        (
            "blind-reader",
            {
                "verdict": "pass", "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下明确余波。",
                "next_chapter_pull": "下一章的代价仍未揭开。",
                "summary": "空间、行动和情绪都可以重建。",
                "evidence_quote": "林舟握住门把",
            },
        ),
        (
            "chapter-editor",
            {
                "verdict": "pass", "must": [],
                "summary": "因果、选择、对白、肌理和连续性成立。",
                "evidence_quote": "林舟握住门把",
            },
        ),
    ):
        action = relay.next_action(slug)
        assert action["role"] == role
        Path(action["result_file"]).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        result = relay.complete_minimal(slug)
    assert result is not None
    return result


def test_high_risk_chapter_waits_for_author_before_promotion(tmp_path: Path):
    root = tmp_path / "repo"
    request = WorkflowRequest(
        **{**asdict(_request()), "chapter_risk": "volume_end"}
    )
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", request, chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("高风险章"), encoding="utf-8"
    )
    relay.complete_minimal("demo")

    decision = _complete_lean_reviews_without_assert(relay, "demo")

    assert decision.user_state == "decision_required"
    assert relay._load_state("demo")["decision_kind"] == (
        "high_risk_author_confirmation"
    )
    assert not (root / "books/demo/chapters/e01/ch-01/正文.md").exists()

    completed = relay.approve_high_risk(
        "demo", decision_reference="author-confirmed-volume-end"
    )
    assert completed.user_state == "chapter_complete"
    assert (root / "books/demo/chapters/e01/ch-01/正文.md").is_file()


def test_exploration_capability_never_reaches_formal_ready(tmp_path: Path):
    root = tmp_path / "repo"
    request = WorkflowRequest(
        **{**asdict(_request()), "host_capability": "exploration"}
    )
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", request, chapter=1)
    action = relay.next_action("demo")
    assert action["formal_ready_allowed"] is False
    assert action["lead_involved"] is False
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("探索章"), encoding="utf-8"
    )
    relay.complete_minimal("demo")

    result = _complete_lean_reviews_without_assert(relay, "demo")

    assert result.user_state == "decision_required"
    assert relay._load_state("demo")["decision_kind"] == "exploration_only"
    assert not (root / "books/demo/chapters/e01/ch-01/正文.md").exists()


def test_hard_budget_preserves_double_review_then_waits_before_patch(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    request = WorkflowRequest(
        **{**asdict(_request()), "hard_token_budget": 100}
    )
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", request, chapter=1)
    writer = relay.next_action("demo")
    (Path(writer["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("预算章"), encoding="utf-8"
    )
    relay.complete_minimal(
        "demo", telemetry={"total_tokens": 150}
    )
    backend = ScriptedBackend([], [_must_reviews()])
    for role in ("blind-reader", "chapter-editor"):
        action = relay.next_action("demo")
        outcome = backend.run_review(
            SessionIdentity(
                session_id=f"{role}-budget",
                session_instance_id=f"{role}-budget",
                provider="unknown", model="unknown",
                agent_harness="native-host", role=role,
            ),
            role=role, context=_review_capsule_context(action),
            instructions=_review_capsule_instructions(action),
            reasoning_effort="medium",
        )
        Path(action["result_file"]).write_text(
            json.dumps(asdict(outcome), ensure_ascii=False), encoding="utf-8"
        )
        result = relay.complete_minimal("demo")

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "hard_budget_reached"
    assert state["known_total_tokens"] == 150
    assert not (root / "books/demo/chapters/e01/ch-01/正文.md").exists()

    resumed = relay.continue_after_budget(
        "demo", decision_reference="author-allows-one-patch"
    )
    assert resumed.user_state == "running"
    assert relay.next_action("demo")["stage"] == "patch"


def test_writer_model_switch_stops_before_new_writer_until_author_calibrates(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    first = WorkflowRequest(
        **{**asdict(_request()), "writer_model": "writer-a"}
    )
    switched = WorkflowRequest(
        **{**asdict(_request()), "writer_model": "writer-b"}
    )
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", first, chapter=1)
    _complete_lean_chapter_with_passes(
        relay, "demo", _prose("模型基线章")
    )

    decision = relay.start("demo", switched, chapter=2)

    assert decision.user_state == "decision_required"
    assert relay._load_state("demo")["decision_kind"] == (
        "writer_model_calibration_required"
    )
    assert not relay._action_path("demo").exists()

    from app.novel_forge.workflow_iteration import approve_writer_model_switch

    approve_writer_model_switch(
        root, "demo", volume=1, model="writer-b",
        decision_reference="author-approved-switch-sample",
    )
    resumed = relay.start("demo", switched, chapter=2)
    assert resumed.user_state == "running"
    assert relay.next_action("demo")["session"]["requested_model"] == "writer-b"


def test_writer_action_exposes_requested_model_without_model_self_selection(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    request = WorkflowRequest(
        **{**asdict(_request()), "writer_model": "writer-a"}
    )
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", request, chapter=1)

    action = relay.next_action("demo")

    assert action["session"]["requested_model"] == "writer-a"
    assert action["dispatcher"] == "python_or_host_adapter"
    assert action["lead_involved"] is False


def test_second_chapter_uses_its_own_episode_target_path(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    _complete_lean_chapter_with_passes(relay, "demo", _prose("第一章完成"))

    relay.start("demo", _request(), chapter=2)
    state = relay._load_state("demo")
    control = json.loads(
        (
            root
            / "books/demo/planning/guardian-sessions"
            / f"{state['capsule']['capsule_id']}.json"
        ).read_text(encoding="utf-8")
    )

    assert control["target_path"] == "chapters/e02/ch-02/正文.md"



def test_cli_next_action_prints_a_compact_role_card_by_default(
    tmp_path: Path, capsys
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)

    exit_code = main(["--root", str(root), "next-action", "demo"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "下一步：委派 Writer。" in output
    assert "complete-role demo" in output
    assert '"schema"' not in output
    assert "sha256" not in output.lower()



def test_cli_can_start_the_next_chapter_without_repeating_book_metadata(
    tmp_path: Path, capsys
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    _complete_lean_chapter_with_passes(relay, "demo", _prose("第一章元数据复用"))

    exit_code = main(["--root", str(root), "start", "demo", "--chapter", "2"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "正在写作。" in output
    assert relay.next_action("demo")["role"] == "writer"



def test_native_status_and_next_action_explain_the_current_handoff(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)

    status = relay.status("demo")

    assert status.message == "等待 Writer 完成当前章节。执行 next-action 获取角色任务。"
    _complete_lean_chapter_with_passes(relay, "demo", _prose("第一章已完成"))

    handoff = relay.next_action("demo")

    assert handoff["kind"] == "start_next_chapter"
    assert handoff["chapter"] == 2
    assert "start demo --chapter 2" in handoff["task"]



def test_lean_native_unknown_telemetry_can_finish_double_review_and_ready(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
        strict_audit=False,
    )
    backend = ScriptedBackend([], [_pass_reviews()])
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("Lean 双审通过"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    blind_session = SessionIdentity(
        session_id="lean-blind-01",
        session_instance_id="lean-blind-01",
        provider="unknown",
        model="unknown",
        agent_harness="native-host",
        role="blind-reader",
    )
    blind = backend.run_review(
        blind_session,
        role="blind-reader",
        context=_review_capsule_context(blind_action),
        instructions=_review_capsule_instructions(blind_action),
        reasoning_effort="medium",
    )
    blind_file = tmp_path / "blind.json"
    blind_file.write_text(
        json.dumps(asdict(blind), ensure_ascii=False),
        encoding="utf-8",
    )
    relay.complete_minimal(
        "demo",
        result_file=blind_file,
    )

    editor_action = relay.next_action("demo")
    editor_session = SessionIdentity(
        session_id="lean-editor-01",
        session_instance_id="lean-editor-01",
        provider="unknown",
        model="unknown",
        agent_harness="native-host",
        role="chapter-editor",
    )
    editor = backend.run_review(
        editor_session,
        role="chapter-editor",
        context=_review_capsule_context(editor_action),
        instructions=_review_capsule_instructions(editor_action),
        reasoning_effort="medium",
    )
    editor_file = tmp_path / "editor.json"
    editor_file.write_text(
        json.dumps(asdict(editor), ensure_ascii=False),
        encoding="utf-8",
    )

    result = relay.complete_minimal(
        "demo",
        result_file=editor_file,
    )

    status = book_project.project_status(root, "demo", 1)
    assert result.user_state == "chapter_complete"
    assert status["chapters"][0]["effective_status"] == "ready"
    generation = next(
        (root / "books/demo/evidence/generations").glob("*.md")
    ).read_text(encoding="utf-8")
    assert '"assurance_mode": "lean_native"' in generation
    runtime = next(
        (root / "books/demo/evidence/runtime-audits").glob("*.json")
    )
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    assert payload["budget"]["status"] == "unassessed"
    assert payload["request_count"] is None


def test_lean_blind_normalizes_score_and_legacy_field_aliases_before_caching(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("分数归一化"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must_issues": [],
                "human_likeness": 7,
                "reader_desire": 9,
                "emotional_aftertaste": "人物选择留下具体余味。",
                "next_chapter_pull": "代价尚未揭开。",
                "summary": "现场、行动和情绪均可重建。",
                "quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")
    state = relay._load_state("demo")

    assert result.message == "正在自动审稿。"
    assert state["blind_outcome"]["human_likeness"] == "convincing"
    assert state["blind_outcome"]["reader_desire"] == "continue"
    assert state["blind_outcome"]["emotional_residue"] == "人物选择留下具体余味。"
    assert state["blind_outcome"]["evidence_quote"] == "林舟握住门把"


def test_lean_refreshes_a_changed_blind_result_file_before_reusing_cache(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("刷新盲审缓存"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    blind_payload = {
        "verdict": "pass",
        "must": [],
        "human_likeness": "convincing",
        "reader_desire": "continue",
        "emotional_residue": "旧的余味。",
        "next_chapter_pull": "代价尚未揭开。",
        "summary": "现场、行动和情绪均可重建。",
        "evidence_quote": "林舟握住门把",
    }
    Path(blind_action["result_file"]).write_text(
        json.dumps(blind_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_payload["emotional_residue"] = "刷新后的余味。"
    Path(blind_action["result_file"]).write_text(
        json.dumps(blind_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    state = relay._load_state("demo")

    relay._refresh_blind_outcome_if_changed("demo", state)

    assert state["blind_outcome"]["emotional_residue"] == "刷新后的余味。"
    assert state["blind_outcome_source"]["sha256"] == hashlib.sha256(
        Path(blind_action["result_file"]).read_bytes()
    ).hexdigest()


def test_lean_review_acceptance_writes_a_session_completion_before_promotion(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("审稿回执"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下具体余味。",
                "next_chapter_pull": "代价尚未揭开。",
                "summary": "现场、行动和情绪均可重建。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    relay.complete_minimal("demo")

    completions = list(
        (root / ".local-guardian/demo/session-completions").glob("*.json")
    )
    assert len(completions) == 1
    payload = json.loads(completions[0].read_text(encoding="utf-8"))
    assert payload["role"] == "blind-reader"
    assert payload["provisional"] is True


def test_lean_review_retry_message_exposes_the_invalid_rating_value(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("审稿错误诊断"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")

    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": 11,
                "reader_desire": "continue",
                "emotional_residue": "人物选择留下具体余味。",
                "next_chapter_pull": "代价尚未揭开。",
                "summary": "现场、行动和情绪均可重建。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert "当前值=11" in result.message
    assert "0-10" in result.message


def test_lean_records_writer_observation_with_optional_host_telemetry(
    tmp_path: Path,
):
    from app.novel_forge.workflow_observability import workflow_cost_summary

    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("观测写作调用"),
        encoding="utf-8",
    )

    result = relay.complete_minimal(
        "demo",
        telemetry={
            "input_tokens": 1200,
            "output_tokens": 6100,
            "cached_input_tokens": 300,
            "total_tokens": 7600,
            "request_count": 1,
            "elapsed_seconds": 12.5,
        },
    )

    summary = workflow_cost_summary(root, "demo", chapter=1)
    writer = summary["chapters"][0]["phases"]["writer_draft"]
    assert result.user_state == "running"
    assert writer["call_count"] == 1
    assert writer["total_tokens"] == 7600
    assert writer["elapsed_seconds"] == 12.5
    assert writer["body_change_count"] == 1


def test_lean_malformed_telemetry_is_observational_not_a_retry_trigger(
    tmp_path: Path,
):
    from app.novel_forge.workflow_observability import workflow_cost_summary

    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("坏遥测不重写"),
        encoding="utf-8",
    )

    result = relay.complete_minimal(
        "demo",
        telemetry={"input_tokens": "not-a-number", "elapsed_seconds": -4},
    )

    summary = workflow_cost_summary(root, "demo", chapter=1)
    chapter = summary["chapters"][0]
    assert result.user_state == "running"
    assert result.technical_retry_count == 0
    assert chapter["phases"]["writer_draft"]["unknown_token_calls"] == 1
    observation = json.loads(
        next(
            (
                root
                / ".local-guardian/demo/workflow-observations/ch01"
            ).glob("*.json")
        ).read_text(encoding="utf-8")
    )
    assert observation["telemetry"]["warnings"] == [
        "input_tokens_invalid",
        "elapsed_seconds_invalid",
    ]


def test_lean_failed_writer_call_is_recorded_before_technical_retry(
    tmp_path: Path,
):
    from app.novel_forge.workflow_observability import workflow_cost_summary

    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    first_action = relay.next_action("demo")

    result = relay.complete_minimal("demo")

    summary = workflow_cost_summary(root, "demo", chapter=1)
    chapter = summary["chapters"][0]
    recorded = json.loads(
        (
            root
            / ".local-guardian/demo/workflow-observations/ch01"
            / f"{first_action['action_id']}.json"
        ).read_text(encoding="utf-8")
    )
    assert result.technical_retry_count == 1
    assert recorded["outcome"] == "failed"
    assert recorded["failure_reason"]
    assert chapter["retry_overlay"]["call_count"] == 1


def test_review_scope_is_sampled_without_changing_patch_routing(tmp_path: Path):
    finding = NativeWorkflowRelay._normalized_findings(
        {
            "verdict": "needs_revision",
            "must": [
                {
                    "location": "第九段",
                    "evidence": "门闩响了一声",
                    "reader_effect": "动作重复",
                    "revision_intent": "删去重复动作",
                    "scope": "local",
                },
                "人物选择缺少代价",
            ],
        }
    )

    assert [item.scope for item in finding] == ["local", "unclassified"]
    assert "scope" not in NovelWorkflowOrchestrator._patch_directive(finding[0])


def test_lean_review_observation_counts_sampled_must_scope(tmp_path: Path):
    from app.novel_forge.workflow_observability import workflow_cost_summary

    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    prose = _prose("局部范围抽样")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        prose,
        encoding="utf-8",
    )
    relay.complete_minimal("demo")
    blind_action = relay.next_action("demo")
    quote = "局部范围抽样"
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "needs_revision",
                "must": [
                    {
                        "scope": "local",
                        "location": "开头",
                        "evidence": quote,
                        "reader_effect": "动作重复",
                        "revision_intent": "删去重复动作",
                    }
                ],
                "human_likeness": "uncertain",
                "reader_desire": "conditional",
                "emotional_residue": "紧张感仍在",
                "next_chapter_pull": "想知道门后是谁",
                "summary": "存在一处局部重复。",
                "evidence_quote": quote,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal(
        "demo",
        session_id="blind-scope-01",
        session_instance_id="blind-scope-instance-01",
        provider="blind-provider",
        model="blind-model",
        telemetry={"input_tokens": 5200, "output_tokens": 220},
    )

    summary = workflow_cost_summary(root, "demo", chapter=1)
    chapter = summary["chapters"][0]
    assert result.user_state == "running"
    assert chapter["phases"]["initial_review"]["call_count"] == 1
    assert chapter["must_scope_counts"]["local"] == 1


def test_observation_refresh_failure_rolls_back_local_record_without_breaking_next_role(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("观测失败回滚"),
        encoding="utf-8",
    )
    original_refresh = relay._refresh_active_action_integrity
    monkeypatch.setattr(
        relay,
        "_refresh_active_action_integrity",
        lambda slug: (_ for _ in ()).throw(OSError("disk full")),
    )

    writer_result = relay.complete_minimal("demo")

    assert writer_result.user_state == "running"
    observation_root = root / ".local-guardian/demo/workflow-observations"
    assert not observation_root.exists()

    monkeypatch.setattr(relay, "_refresh_active_action_integrity", original_refresh)
    blind_action = relay.next_action("demo")
    Path(blind_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "pass",
                "must": [],
                "human_likeness": "convincing",
                "reader_desire": "continue",
                "emotional_residue": "门后的敲击声仍压在耳边。",
                "next_chapter_pull": "想知道失踪者是否还活着。",
                "summary": "现场与人物选择均成立。",
                "evidence_quote": "观测失败回滚",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    blind_result = relay.complete_minimal(
        "demo",
        session_id="blind-after-observation-failure",
        session_instance_id="blind-after-observation-failure-instance",
    )

    assert blind_result.technical_retry_count == 0
    assert relay.next_action("demo")["role"] == "chapter-editor"


def test_blind_synthetic_requires_one_structural_must():
    session = SessionIdentity(
        session_id="blind",
        session_instance_id="blind-instance",
        provider="provider",
        model="model",
        agent_harness="host",
        role="blind-reader",
    )
    terminal = {
        "value": "operation",
        "kind": "operation_id",
        "result_transport": "result_file",
    }
    payload = {
        "verdict": "pass",
        "must": [],
        "human_likeness": "synthetic",
        "reader_desire": "stop",
        "emotional_residue": "人物只在完成任务。",
        "next_chapter_pull": "没有形成追读。",
        "summary": "重复反应遍布全文。",
        "evidence_quote": "他停了一下",
    }

    with pytest.raises(WorkflowError, match="synthetic.*structural MUST"):
        NativeWorkflowRelay._review_outcome(
            payload, role="blind-reader", session=session, terminal=terminal
        )

    invalid_verdict = {
        **payload,
        "verdict": "ready_for_editor_decision",
        "must": [
            {
                "severity": "MUST",
                "location": "全文",
                "evidence": "他停了一下",
                "reader_effect": "人物反应趋同",
                "revision_intent": "让反应由具体欲望和关系决定",
                "scope": "structural",
            }
        ],
    }
    with pytest.raises(WorkflowError, match="synthetic.*needs_revision"):
        NativeWorkflowRelay._review_outcome(
            invalid_verdict,
            role="blind-reader",
            session=session,
            terminal=terminal,
        )


def test_blind_uncertain_does_not_require_a_revision_finding():
    session = SessionIdentity(
        session_id="blind",
        session_instance_id="blind-instance",
        provider="provider",
        model="model",
        agent_harness="host",
        role="blind-reader",
    )
    terminal = {
        "value": "operation",
        "kind": "operation_id",
        "result_transport": "result_file",
    }
    payload = {
        "verdict": "pass",
        "must": [],
        "human_likeness": "uncertain",
        "reader_desire": "conditional",
        "emotional_residue": "局部仍然工整。",
        "next_chapter_pull": "人物后果仍可追问。",
        "summary": "可以继续但不自动修订。",
        "evidence_quote": "雨水落在票根上",
    }

    outcome = NativeWorkflowRelay._review_outcome(
        payload, role="blind-reader", session=session, terminal=terminal
    )

    assert outcome.verdict == "pass"
    assert outcome.findings == ()
    assert outcome.human_likeness == "uncertain"


def _drive_lean_reviews_to_must(
    relay: NativeWorkflowRelay,
    slug: str,
) -> WorkflowResult:
    """Run both reviewers with MUST findings and return the last result."""
    backend = ScriptedBackend([], [_must_reviews()])
    result = None
    for role in ("blind-reader", "chapter-editor"):
        action = relay.next_action(slug)
        outcome = backend.run_review(
            SessionIdentity(
                session_id=f"{role}-must",
                session_instance_id=f"{role}-must",
                provider="unknown",
                model="unknown",
                agent_harness="native-host",
                role=role,
            ),
            role=role,
            context=_review_capsule_context(action),
            instructions=_review_capsule_instructions(action),
            reasoning_effort="medium",
        )
        Path(action["result_file"]).write_text(
            json.dumps(asdict(outcome), ensure_ascii=False),
            encoding="utf-8",
        )
        result = relay.complete_minimal(slug)
    return result


def _reach_literary_revision_decision(
    relay: NativeWorkflowRelay,
) -> WorkflowResult:
    """Drive a lean chapter into decision_required(literary_revision_required)."""
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("初稿"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")
    _drive_lean_reviews_to_must(relay, "demo")
    patch = relay.next_action("demo")
    (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("修订稿"),
        encoding="utf-8",
    )
    relay.complete_minimal("demo")
    result = _drive_lean_reviews_to_must(relay, "demo")
    assert result.user_state == "decision_required"
    assert relay._load_state("demo")["decision_kind"] == (
        "literary_revision_required"
    )
    return result


def test_authorize_revision_resumes_staged_literary_patch(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)
    must = list(relay._load_state("demo")["must_findings"])

    result = relay.authorize_revision(
        "demo", decision_reference="author-allows-one-more-round"
    )

    assert result.user_state == "running"
    assert result.message == "发现问题，正在自动修订。"
    patch = relay.next_action("demo")
    assert patch["kind"] == "run_role"
    assert patch["role"] == "writer"
    assert patch["stage"] == "patch"
    assert patch["must_findings"] == must
    state = relay._load_state("demo")
    assert state["phase"] == "awaiting_writer"
    assert state["author_revision_authorized"] is True
    assert state["author_revision_reference"] == (
        "author-allows-one-more-round"
    )
    records = list(
        (root / ".local-guardian/demo/native-relay/author-revisions").glob(
            "*.json"
        )
    )
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["schema"] == "novel-forge-author-revision/v1"
    assert record["chapter"] == 1
    assert record["decision_kind"] == "literary_revision_required"
    assert record["decision_reference"] == "author-allows-one-more-round"
    assert record["must_findings"] == must


def test_authorize_revision_requires_reference_and_revision_decision(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)

    with pytest.raises(WorkflowError, match="续修授权必须提供作者决定依据"):
        relay.authorize_revision("demo", decision_reference="  ")

    relay.stop("demo")
    with pytest.raises(WorkflowError, match="当前没有等待作者授权的续修决策"):
        relay.authorize_revision("demo", decision_reference="not-allowed")


def test_lean_retry_after_second_revision_skips_receipt_gate(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)

    result = relay.retry("demo")

    assert result.user_state == "running"
    action = relay.next_action("demo")
    assert action["kind"] == "run_role"
    assert action["role"] == "writer"
    assert not relay._load_state("demo").get("author_revision_authorized")


def test_decision_required_options_and_message_reflect_revision_round(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)

    status = relay.status("demo")

    assert status.user_state == "decision_required"
    assert "第 1 轮集中修订后仍有 MUST" in status.message
    assert any(
        option.startswith("D. 授权一次集中修订后重新双审")
        for option in status.options
    )
    assert not any(
        option.startswith("B. 重新生成") for option in status.options
    )

    relay.stop("demo")
    stopped = relay.status("demo")
    assert stopped.user_state == "stopped"


def test_next_action_returns_user_decision_card_in_decision_phase(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)

    action = relay.next_action("demo")

    assert action["kind"] == "user_decision"
    assert action["decision_kind"] == "literary_revision_required"
    assert action["options"][0].startswith("D. 授权一次集中修订后重新双审")
    assert action["must_findings"]


def test_complete_minimal_rejected_in_decision_phase(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)

    with pytest.raises(WorkflowError, match="可达命令"):
        relay.complete_minimal("demo")


def test_writer_action_marks_frozen_draft_read_only(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)

    action = relay.next_action("demo")

    assert action["kind"] == "run_role"
    assert action["role"] == "writer"
    read_only = action["read_only_project_files"]
    assert read_only == [
        ".novel-forge/diff/ch01/控制面冻结稿.md"
    ]


def test_authorize_revision_after_local_patch_hard_gate_uses_surface_findings(
    tmp_path: Path,
):
    """K1 regression: authorize-revision after a local-patch hard-gate failure
    must carry the real surface findings, not the stale review MUSTs."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    prose = _prose("局部修订正文") + "\n\n林舟把铜扣放回左侧口袋，这句解释只出现一次。\n"
    staged = Path(writer_action["capsule"]["path"]) / "draft/正文.md"
    staged.write_text(prose, encoding="utf-8")
    relay.complete_minimal("demo")

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
    for role, outcome in zip(("blind-reader", "chapter-editor"), local_reviews):
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
            json.dumps(asdict(produced), ensure_ascii=False), encoding="utf-8"
        )
        relay.complete_minimal("demo")

    patch = relay.next_action("demo")
    assert patch["stage"] == "local-patch"
    payload = json.loads(Path(patch["input_file"]).read_text(encoding="utf-8"))
    target = payload["targets"][0]["target"]
    # replacement 引入阻塞 lint：破折号
    Path(patch["result_file"]).write_text(
        json.dumps(
            {
                "replacements": [
                    {
                        "target": target,
                        "replacement": "林舟把铜扣塞回口袋——他不想被看见。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = relay.complete_minimal("demo")

    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "local_patch_hard_gate_failed"
    assert any("em-dash" in item for item in state["must_findings"])

    resumed = relay.authorize_revision(
        "demo", decision_reference="author-fixes-lint-after-patch"
    )

    assert resumed.user_state == "running"
    patch = relay.next_action("demo")
    assert patch["stage"] == "patch"
    revision = Path(patch["revision_file"]).read_text(encoding="utf-8")
    assert "em-dash" in revision
    assert "铜扣放回左侧口袋" not in revision


def test_retry_regeneration_clears_stale_must_findings(tmp_path: Path):
    """A user-requested regenerate is a fresh draft: stale MUSTs and the
    revision round must not be re-routed as a patch after a technical retry."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)

    result = relay.retry("demo")

    assert result.user_state == "running"
    state = relay._load_state("demo")
    assert "must_findings" not in state
    assert "patch_round" not in state
    action = relay.next_action("demo")
    assert action["stage"] == "draft"


def test_decision_options_reflect_each_decision_kind(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    writer_action = relay.next_action("demo")
    (Path(writer_action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("选项章"), encoding="utf-8"
    )
    relay.complete_minimal("demo")
    _drive_lean_reviews_to_must(relay, "demo")
    patch = relay.next_action("demo")
    (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("修订稿"), encoding="utf-8"
    )
    relay.complete_minimal("demo")
    backend = ScriptedBackend([], [_must_reviews()])
    result = None
    for role in ("blind-reader", "chapter-editor"):
        action = relay.next_action("demo")
        outcome = backend.run_review(
            SessionIdentity(
                session_id=f"{role}-opt",
                session_instance_id=f"{role}-opt",
                provider="unknown", model="unknown",
                agent_harness="native-host", role=role,
            ),
            role=role,
            context=_review_capsule_context(action),
            instructions=_review_capsule_instructions(action),
            reasoning_effort="medium",
        )
        Path(action["result_file"]).write_text(
            json.dumps(asdict(outcome), ensure_ascii=False), encoding="utf-8"
        )
        result = relay.complete_minimal("demo")
    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    state["decision_kind"] = "hard_budget_reached"
    _atomic_write_json(relay._state_path("demo"), state)
    status = relay.status("demo")
    assert any(
        option.startswith("E. 作者授权继续一次修订")
        for option in status.options
    )
    state["decision_kind"] = "high_risk_author_confirmation"
    _atomic_write_json(relay._state_path("demo"), state)
    status = relay.status("demo")
    assert any(
        option.startswith("F. 作者确认后晋升")
        for option in status.options
    )
    state["decision_kind"] = "writer_model_calibration_required"
    _atomic_write_json(relay._state_path("demo"), state)
    status = relay.status("demo")
    assert any(
        option.startswith("G. 批准 Writer 模型校准")
        for option in status.options
    )


def test_user_decision_card_message_matches_status(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_literary_revision_decision(relay)

    card = relay.next_action("demo")
    status = relay.status("demo")

    assert card["message"] == status.message
    assert "第 1 轮集中修订后仍有 MUST" in card["message"]


def _atomic_write_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def test_parallel_double_review_accepts_editor_first_completion(
    tmp_path: Path,
):
    """Both review cards can be claimed up front and completed in any order."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("并行双审"), encoding="utf-8"
    )
    relay.complete_minimal("demo")

    blind = relay.next_action("demo")
    editor = relay.next_action("demo")
    assert blind["role"] == "blind-reader"
    assert editor["role"] == "chapter-editor"
    assert blind["parallel_review"] is True

    state = relay._load_state("demo")
    editor_control_id = state["control_run_ids"]["chapter-editor"]
    blind_control_id = state["control_run_ids"]["blind-reader"]

    # editor 先完成
    Path(editor["result_file"]).write_text(
        json.dumps(
            {"verdict": "pass", "must": [], "summary": "z",
             "evidence_quote": "林舟握住门把"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = relay.complete_minimal(
        "demo",
        session_id=editor_control_id,
    )
    assert result.user_state == "running"
    state = relay._load_state("demo")
    assert state["completed_review_roles"] == ["chapter-editor"]

    # blind 后完成 → 合流晋升
    Path(blind["result_file"]).write_text(
        json.dumps(
            {"verdict": "pass", "must": [], "human_likeness": "convincing",
             "reader_desire": "continue", "emotional_residue": "x",
             "next_chapter_pull": "y", "summary": "z",
             "evidence_quote": "林舟握住门把"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = relay.complete_minimal(
        "demo",
        session_id=blind_control_id,
    )
    assert result.user_state == "chapter_complete"
    assert (root / "books/demo/chapters/e01/ch-01/正文.md").is_file()


def test_staged_prose_survives_writer_technical_retry(tmp_path: Path):
    """The staged draft is never cleared before promotion, even on a
    technical writer retry that re-prepares the capsule."""
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    relay.start("demo", _request(), chapter=1)
    action = relay.next_action("demo")
    prose = _prose("第一版正文")
    (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
        prose, encoding="utf-8"
    )
    relay.complete_minimal("demo")

    staged = Path(action["capsule"]["path"]) / "draft/正文.md"
    assert staged.read_text(encoding="utf-8") == prose

    # 重签发 writer 动作（_prepare_lean_writer_action 路径）不得清除正文
    state = relay._load_state("demo")
    request = relay._request_from_state(state)
    relay._prepare_lean_writer_action(
        "demo",
        state,
        request=request,
        chapter=int(state["chapter"]),
        sequence_id=str(state["sequence_id"]),
    )

    assert staged.is_file()
    assert staged.read_text(encoding="utf-8") == prose
    assert relay.next_action("demo")["role"] == "writer"
