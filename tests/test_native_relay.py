"""Tests for the persistent native-host workflow relay."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.novel_forge import book_project
from app.novel_forge.book_git import book_git_status
from app.novel_forge.native_relay import NativeWorkflowRelay
from app.novel_forge.workflow import SessionIdentity, WorkflowRequest
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


def test_native_stop_retires_pending_action(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(
        root,
        capsule_root=tmp_path / "capsules",
    )
    relay.start("demo", _request(), chapter=1)

    result = relay.stop("demo")

    assert result.user_state == "stopped"
    assert not (
        root / ".local-guardian/demo/native-relay/next-action.json"
    ).exists()
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
    assert result.message == "审稿会话异常，已自动换新会话重试。"
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

    assert result.message == "审稿会话异常，已自动换新会话重试。"
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

    assert first.message == "审稿会话异常，已自动换新会话重试。"
    assert second.message == "审稿会话异常，已自动换新会话重试。"
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
    assert result.message == "审稿会话异常，已自动换新会话重试。"
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

    assert result.message == "审稿会话异常，已自动换新会话重试。"
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

    assert result.message == "写作会话异常，已自动换新会话重试。"
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
    assert action["capsule"]["output"] == "draft/正文.md"
    assert Path(action["capsule"]["path"]).is_dir()
    assert "result_file" not in action
    assert "planning" not in action


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


def test_lean_style_lint_does_not_force_a_surface_patch(tmp_path: Path):
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

    assert result.message == "正在自动审稿。"
    assert relay.next_action("demo")["role"] == "blind-reader"
    assert staged.read_text(encoding="utf-8") == prose


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
    initial_body = root / "books/demo/.novel-forge/diff/ch01/初稿.md"
    chapter_body = root / "books/demo/chapters/e01/ch-01/正文.md"
    original = staged_body.read_text(encoding="utf-8")
    revised = _prose("审核后在同一暂存正文上修订")

    assert initial_body.read_text(encoding="utf-8") == original
    assert not chapter_body.exists()

    staged_body.write_text(revised, encoding="utf-8")
    relay.complete_minimal("demo")
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
    diff = (
        root / "books/demo/.novel-forge/diff/ch01/修订.diff"
    ).read_text(encoding="utf-8")
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
    staged.write_text(_prose("旧表兼容"), encoding="utf-8")
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
    Path(editor_action["result_file"]).write_text(
        json.dumps(
            {
                "verdict": "ready_for_editor_decision",
                "findings": [],
                "summary": "本章成立。",
                "hard_anchor_coverage": "五项用户硬锚均已交付。",
                "evidence_quote": "林舟握住门把",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = relay.complete_minimal("demo")

    assert result.user_state == "chapter_complete"


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
