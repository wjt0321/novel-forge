"""Persistent pull protocol for visible host-native creative sessions."""

from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import book_project
from .artifact_integrity import record_session_completion
from .chapter_sequence import (
    begin_chapter_sequence,
    chapter_sequence_status,
    claim_chapter_session,
    rotate_chapter_session,
)
from .guardian import (
    GuardianError,
    authorize_regeneration,
    ingest_writer_capsule,
    prepare_writer_capsule,
    record_capsule_runtime,
    reject_writer_capsule,
)
from .review_prompt import (
    render_planning_instructions,
    render_review_instructions,
)
from .session_audit import audit_session_log
from .workspace_integrity import (
    create_workspace_backup,
    remove_created_paths,
    restore_workspace_paths,
    snapshot_workspace,
    workspace_delta,
)
from .workflow import (
    NovelWorkflowOrchestrator,
    PlanningOutcome,
    ReviewFinding,
    ReviewOutcome,
    SessionIdentity,
    WorkflowError,
    WorkflowRequest,
    WorkflowResult,
    _atomic_json,
)


NATIVE_ACTION_SCHEMA = "novel-forge-native-action/v1"
NATIVE_COMPLETION_SCHEMA = "novel-forge-native-completion/v1"
NATIVE_RELAY_SCHEMA = "novel-forge-native-relay/v1"


class NativeWorkspaceMutationError(WorkflowError):
    """Raised after restoring one creative role's project mutation."""

    def __init__(self, reason: str):
        super().__init__("创作角色修改了项目控制面。")
        self.reason = reason


def _result_contract(role: str) -> dict[str, Any]:
    payloads: dict[str, Any] = {
        "writer-planning": {
            "files": {
                "type": "mapping[path, markdown]",
                "allowed": [
                    "memory/worldbuilding.md",
                    "memory/voice-bible.md",
                    "planning/research-boundaries.md",
                    "planning/story-engine.md",
                    "planning/scene-package-chNN.md",
                ],
            }
        },
        "writer-session": {},
        "writer": {
            "artifact_relative_path": {"const": "draft/正文.md"},
        },
        "blind-reader": {
            "required": [
                "verdict",
                "findings",
                "human_likeness",
                "reader_desire",
                "emotional_residue",
                "next_chapter_pull",
                "analysis",
                "evidence_quote",
            ]
        },
        "chapter-editor": {
            "required": [
                "verdict",
                "findings",
                "analysis",
                "evidence_quote",
            ]
        },
    }
    return {
        "completion_schema": NATIVE_COMPLETION_SCHEMA,
        "schema": "novel-forge-role-result/v1",
        "role": role,
        "terminal_binding_required": True,
        "required_completion_fields": [
            "action_id",
            "status=completed",
            "session",
            "operation_handle.kind",
            "operation_handle.value",
            "result_transport",
            "role_result",
        ],
        "payload": payloads[role],
    }


class _RelayOnlyBackend:
    """Reject accidental synchronous role execution from the relay."""

    def __getattr__(self, name: str) -> Any:
        raise WorkflowError(f"原生接力不能同步调用角色方法：{name}")


class NativeWorkflowRelay:
    """Persist the next host action while Python owns workflow state."""

    def __init__(
        self,
        root: Path,
        *,
        capsule_root: Path | None = None,
        max_technical_retries: int = 2,
    ):
        self.root = Path(root).resolve()
        self.orchestrator = NovelWorkflowOrchestrator(
            self.root,
            _RelayOnlyBackend(),  # type: ignore[arg-type]
            capsule_root=(
                Path(capsule_root).resolve()
                if capsule_root is not None
                else Path(tempfile.gettempdir()).resolve()
                / "novel-forge-capsules"
            ),
            max_technical_retries=max_technical_retries,
        )

    def _relay_dir(self, slug: str) -> Path:
        return self.root / ".local-guardian" / slug / "native-relay"

    def _state_path(self, slug: str) -> Path:
        return self._relay_dir(slug) / "state.json"

    def _action_path(self, slug: str) -> Path:
        return self._relay_dir(slug) / "next-action.json"

    def _snapshot_path(self, slug: str, action_id: str) -> Path:
        return (
            self.orchestrator.capsule_root
            / "native-relay-snapshots"
            / slug
            / f"{action_id}.json"
        )

    def _backup_path(self, slug: str, action_id: str) -> Path:
        return (
            self.orchestrator.capsule_root
            / "native-relay-snapshots"
            / slug
            / f"{action_id}.zip"
        )

    def _load_state(self, slug: str) -> dict[str, Any]:
        path = self._state_path(slug)
        if not path.is_file():
            raise WorkflowError("当前没有运行中的原生工作流。")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowError("原生工作流状态损坏。") from exc
        if payload.get("schema") != NATIVE_RELAY_SCHEMA:
            raise WorkflowError("原生工作流状态格式无效。")
        return payload

    @staticmethod
    def _request_from_state(state: dict[str, Any]) -> WorkflowRequest:
        request = state.get("request")
        if not isinstance(request, dict):
            raise WorkflowError("原生工作流缺少用户架构。")
        try:
            result = WorkflowRequest(**request)
        except TypeError as exc:
            raise WorkflowError("原生工作流用户架构无效。") from exc
        result.validate()
        return result

    @staticmethod
    def _completion_session(
        completion: dict[str, Any],
        *,
        role: str,
    ) -> SessionIdentity:
        session = completion.get("session")
        if not isinstance(session, dict):
            raise WorkflowError("原生角色终态缺少真实会话信息。")
        required = (
            "session_id",
            "session_instance_id",
            "provider",
            "model",
            "agent_harness",
        )
        values = {
            name: str(session.get(name) or "").strip()
            for name in required
        }
        if any(not value for value in values.values()):
            raise WorkflowError("原生角色终态的会话信息不完整。")
        return SessionIdentity(role=role, **values)

    def _validate_completion(
        self,
        state: dict[str, Any],
        completion: dict[str, Any],
        *,
        role: str,
    ) -> tuple[SessionIdentity, dict[str, Any], dict[str, str]]:
        if completion.get("schema") != NATIVE_COMPLETION_SCHEMA:
            raise WorkflowError("原生角色终态格式无效。")
        if completion.get("action_id") != state.get("action_id"):
            raise WorkflowError("原生角色终态不属于当前等待动作。")
        if completion.get("status") != "completed":
            raise WorkflowError("原生角色尚未返回宿主官方完成终态。")
        operation = completion.get("operation_handle")
        if not isinstance(operation, dict):
            raise WorkflowError("原生角色终态缺少带类型 operation handle。")
        operation_handle = {
            "kind": str(operation.get("kind") or "").strip(),
            "value": str(operation.get("value") or "").strip(),
        }
        if not all(operation_handle.values()):
            raise WorkflowError("原生角色 operation handle 无效。")
        result_transport = str(
            completion.get("result_transport") or ""
        ).strip()
        if not result_transport:
            raise WorkflowError("原生角色终态缺少正式结果通道。")
        role_result = completion.get("role_result")
        if (
            not isinstance(role_result, dict)
            or role_result.get("schema") != "novel-forge-role-result/v1"
            or role_result.get("role") != role
        ):
            raise WorkflowError("原生角色结果没有绑定当前角色。")
        session = self._completion_session(completion, role=role)
        action = self.next_action(str(state["slug"]))
        expected_session = action.get("session")
        if (
            isinstance(expected_session, dict)
            and expected_session.get("mode") == "reuse"
            and (
                session.session_id != expected_session.get("session_id")
                or session.session_instance_id
                != expected_session.get("session_instance_id")
            )
        ):
            raise WorkflowError("原生角色终态与当前绑定会话不一致。")
        return session, role_result, {
            **operation_handle,
            "result_transport": result_transport,
        }

    def _write_action(
        self,
        slug: str,
        state: dict[str, Any],
        action: dict[str, Any],
    ) -> None:
        state["action_id"] = action["action_id"]
        _atomic_json(self._state_path(slug), state)
        _atomic_json(self._action_path(slug), action)
        _atomic_json(
            self._snapshot_path(slug, action["action_id"]),
            snapshot_workspace(self.root),
        )
        create_workspace_backup(
            self.root,
            self._backup_path(slug, action["action_id"]),
        )

    def _verify_workspace(self, slug: str, action_id: str) -> None:
        snapshot_path = self._snapshot_path(slug, action_id)
        if not snapshot_path.is_file():
            raise WorkflowError("原生角色动作缺少执行前仓库快照。")
        try:
            before = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowError("原生角色仓库快照损坏。") from exc
        if not isinstance(before, dict):
            raise WorkflowError("原生角色仓库快照格式无效。")
        delta = workspace_delta(before, snapshot_workspace(self.root))
        backup_path = self._backup_path(slug, action_id)
        if delta.changed:
            remove_created_paths(self.root, delta.created)
            restore_workspace_paths(
                self.root,
                backup_path,
                before,
                delta.modified + delta.deleted,
            )
            restored = workspace_delta(
                before,
                snapshot_workspace(self.root),
            )
            if restored.changed:
                raise WorkflowError("项目控制面自动恢复失败。")
            snapshot_path.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)
            reason = (
                "control_plane_mutation"
                if delta.modified or delta.deleted
                else "unexpected_project_artifact"
            )
            raise NativeWorkspaceMutationError(reason)
        snapshot_path.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)

    def start(
        self,
        slug: str,
        request: WorkflowRequest,
        *,
        chapter: int = 1,
    ) -> WorkflowResult:
        """Initialize deterministic state and request Writer planning."""
        request.validate()
        self.orchestrator._assert_project_is_managed(slug, chapter)
        book_dir = self.orchestrator._prepare_project(slug, request, chapter)
        action_id = f"native-action-{uuid.uuid4().hex[:16]}"
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": action_id,
            "kind": "run_role",
            "role": "writer-planning",
            "session": {
                "mode": "new",
                "must_be_independent": True,
            },
            "reasoning_effort": "high",
            "instructions": render_planning_instructions().text,
            "context": self.orchestrator._planning_context(
                book_dir,
                chapter,
            ),
            "result": _result_contract("writer-planning"),
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        state = {
            "schema": NATIVE_RELAY_SCHEMA,
            "slug": slug,
            "chapter": chapter,
            "request": asdict(request),
            "phase": "awaiting_writer_planning",
            "action_id": action_id,
            "technical_retry_count": 0,
            "author_approval": False,
            "publication_eligibility": False,
        }
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id="",
            phase="awaiting_native_role",
            retries=0,
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="正在写作。",
            sequence_id="",
        )

    def next_action(self, slug: str) -> dict[str, Any]:
        """Return the current bounded host action."""
        path = self._action_path(slug)
        if not path.is_file():
            raise WorkflowError("当前没有等待执行的原生角色动作。")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != NATIVE_ACTION_SCHEMA:
            raise WorkflowError("原生角色动作格式无效。")
        return payload

    def status(self, slug: str) -> WorkflowResult:
        """Return the existing user-safe workflow status."""
        return self.orchestrator.status(slug)

    def stop(self, slug: str) -> WorkflowResult:
        """Stop the workflow and retire any pending native action."""
        result = self.orchestrator.stop(slug)
        if self._state_path(slug).is_file():
            state = self._load_state(slug)
            state["phase"] = "stopped"
            _atomic_json(self._state_path(slug), state)
        self._action_path(slug).unlink(missing_ok=True)
        return result

    def retry(self, slug: str) -> WorkflowResult:
        """Treat retry as the user's explicit regenerate decision."""
        state = self._load_state(slug)
        if state.get("phase") != "decision_required":
            return self.status(slug)
        request = self._request_from_state(state)
        chapter = int(state["chapter"])
        sequence_id = str(state.get("sequence_id") or "")
        if not sequence_id:
            book_dir = self.root / "books" / slug
            action = {
                "schema": NATIVE_ACTION_SCHEMA,
                "action_id": (
                    f"native-action-{uuid.uuid4().hex[:16]}"
                ),
                "kind": "run_role",
                "role": "writer-planning",
                "session": {
                    "mode": "new",
                    "must_be_independent": True,
                },
                "reasoning_effort": "high",
                "instructions": render_planning_instructions().text,
                "context": self.orchestrator._planning_context(
                    book_dir,
                    chapter,
                ),
                "result": _result_contract("writer-planning"),
                "repository_exploration_forbidden": True,
                "allowed_project_writes": [],
            }
            state.update(
                {
                    "phase": "awaiting_writer_planning",
                    "technical_retry_count": 0,
                }
            )
            self.orchestrator._save_control(
                slug,
                request=request,
                chapter=chapter,
                sequence_id="",
                phase="awaiting_native_role",
                retries=0,
            )
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="正在重新生成本章。",
                sequence_id="",
            )
        sequence = chapter_sequence_status(
            self.root,
            slug,
            sequence_id,
        )
        active_session_id = str(
            sequence.get("active_session_id") or ""
        )
        if sequence.get("status") == "running" and active_session_id:
            rotate_chapter_session(
                self.root,
                slug,
                sequence_id,
                active_session_id,
                reason="user_regeneration",
            )
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
            "kind": "create_session",
            "role": "writer",
            "session": {
                "mode": "new",
                "must_be_independent": True,
            },
            "result": _result_contract("writer-session"),
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        state.update(
            {
                "phase": "awaiting_writer_session",
                "technical_retry_count": 0,
                "human_decision_reference": (
                    f"native-retry-{uuid.uuid4().hex[:16]}"
                ),
                "retry_reason": "user_regeneration",
            }
        )
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="writing",
            retries=0,
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="正在重新生成本章。",
            sequence_id=sequence_id,
        )

    def complete_role(
        self,
        slug: str,
        completion: dict[str, Any],
    ) -> WorkflowResult:
        """Accept one official native terminal and issue the next action."""
        state = self._load_state(slug)
        try:
            self._verify_workspace(
                slug,
                str(state.get("action_id") or ""),
            )
            phase = state.get("phase")
            if phase == "awaiting_writer":
                return self._complete_writer(slug, state, completion)
            if phase in {
                "awaiting_patch_writer_session",
                "awaiting_writer_session",
            }:
                return self._complete_patch_writer_session(
                    slug,
                    state,
                    completion,
                )
            if phase in {
                "awaiting_blind_reader",
                "awaiting_chapter_editor",
            }:
                return self._complete_review(slug, state, completion)
            if phase != "awaiting_writer_planning":
                raise WorkflowError("当前没有等待中的可回传角色。")
            return self._complete_planning(slug, state, completion)
        except NativeWorkspaceMutationError as exc:
            return self._recover_technical_failure(
                slug,
                state,
                failure_reason=exc.reason,
            )
        except (GuardianError, WorkflowError, OSError, ValueError):
            return self._recover_technical_failure(slug, state)

    def _complete_planning(
        self,
        slug: str,
        state: dict[str, Any],
        completion: dict[str, Any],
    ) -> WorkflowResult:
        session, role_result, terminal = self._validate_completion(
            state,
            completion,
            role="writer-planning",
        )
        payload = role_result.get("payload")
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, dict) or not all(
            isinstance(path, str) and isinstance(text, str)
            for path, text in files.items()
        ):
            raise WorkflowError("Writer 规划结果缺少有效文件集合。")
        request = self._request_from_state(state)
        chapter = int(state["chapter"])
        book_dir = self.root / "books" / slug
        planning = PlanningOutcome(
            files=files,
            resolved_model=session.model,
            terminal_role="writer-planning",
            terminal_session_id=session.session_id,
            terminal_session_instance_id=session.session_instance_id,
            operation_id=terminal["value"],
            operation_kind=terminal["kind"],
            result_transport=terminal["result_transport"],
        )
        self.orchestrator._write_writer_planning(
            book_dir,
            chapter,
            request,
            planning,
        )
        sequence_id = f"auto-ch{chapter:02d}-{uuid.uuid4().hex[:10]}"
        begin_chapter_sequence(
            self.root,
            slug,
            chapter,
            1,
            sequence_id=sequence_id,
            orchestrator_run_id=f"workflow-{uuid.uuid4().hex[:12]}",
        )
        book_project.set_draft_mode(
            self.root,
            slug,
            chapter,
            "formal",
        )
        book_project.advance_state(
            self.root,
            slug,
            chapter,
            "context_collected",
            evidence="planning/story-engine.md",
        )
        book_project.advance_state(
            self.root,
            slug,
            chapter,
            "scene_packaged",
            evidence=f"planning/scene-package-ch{chapter:02d}.md",
        )
        claim_chapter_session(
            self.root,
            slug,
            sequence_id,
            session.session_id,
        )
        capsule_dir = (
            self.orchestrator.capsule_root
            / slug
            / sequence_id
            / f"{session.session_id}-{uuid.uuid4().hex[:8]}"
        )
        prepared = prepare_writer_capsule(
            self.root,
            slug,
            sequence_id,
            session.session_id,
            capsule_dir,
            f"chapters/e01/ch-{chapter:02d}/正文.md",
        )
        action_id = f"native-action-{uuid.uuid4().hex[:16]}"
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": action_id,
            "kind": "run_role",
            "role": "writer",
            "session": {
                "mode": "reuse",
                "session_id": session.session_id,
                "session_instance_id": session.session_instance_id,
            },
            "reasoning_effort": "medium",
            "capsule": {
                "id": prepared["capsule_id"],
                "path": prepared["capsule_dir"],
                "operation": prepared["operation"],
                "instructions": "instructions.md",
                "handoff": "handoff.md",
                "output": prepared["draft_output"],
            },
            "runtime": {
                "schema": "novel-forge-runtime/v1",
                "assurance_mode": "formal_native",
                "reported_by": "native_host",
                "filesystem_scope": "guarded_native",
                "write_scope": "post_execution_verified",
                "repository_snapshot_enforced": True,
            },
            "result": {
                **_result_contract("writer"),
                "runtime_snapshot_required": True,
            },
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        state.update(
            {
                "phase": "awaiting_writer",
                "sequence_id": sequence_id,
                "writer_session": asdict(session),
                "capsule": prepared,
            }
        )
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="writing",
            retries=int(state.get("technical_retry_count") or 0),
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="正在写作。",
            sequence_id=sequence_id,
        )

    def _recover_technical_failure(
        self,
        slug: str,
        state: dict[str, Any],
        *,
        failure_reason: str = "writer_result_invalid",
    ) -> WorkflowResult:
        retries = int(state.get("technical_retry_count") or 0) + 1
        state["technical_retry_count"] = retries
        phase = str(state.get("phase") or "")
        sequence_id = str(state.get("sequence_id") or "")
        request = self._request_from_state(state)
        chapter = int(state["chapter"])
        if retries > self.orchestrator.max_technical_retries:
            result = self.orchestrator._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="自动重试仍未完成，请选择下一步。",
                retries=retries - 1,
                decision_kind="native_role_failed",
                parent_generation_id=state.get("generation_id"),
            )
            state["phase"] = "decision_required"
            _atomic_json(self._state_path(slug), state)
            self._action_path(slug).unlink(missing_ok=True)
            return result
        if phase == "awaiting_writer_planning":
            action = self.next_action(slug)
            action["action_id"] = (
                f"native-action-{uuid.uuid4().hex[:16]}"
            )
            action["session"] = {
                "mode": "new",
                "must_be_independent": True,
            }
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="写作会话异常，已自动换新会话重试。",
                sequence_id=sequence_id,
                technical_retry_count=retries,
            )
        if phase in {
            "awaiting_blind_reader",
            "awaiting_chapter_editor",
        }:
            action = self.next_action(slug)
            action["action_id"] = (
                f"native-action-{uuid.uuid4().hex[:16]}"
            )
            action["session"] = {
                "mode": "new",
                "must_be_independent": True,
            }
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="审稿会话异常，已自动换新会话重试。",
                sequence_id=sequence_id,
                technical_retry_count=retries,
            )
        prepared = state.get("capsule")
        if isinstance(prepared, dict):
            capsule_id = str(prepared.get("capsule_id") or "")
            if capsule_id:
                try:
                    reject_writer_capsule(
                        self.root,
                        slug,
                        capsule_id,
                        reason=failure_reason,
                    )
                except GuardianError:
                    pass
        if sequence_id:
            sequence = chapter_sequence_status(
                self.root,
                slug,
                sequence_id,
            )
            active_session_id = str(
                sequence.get("active_session_id") or ""
            )
            if sequence.get("status") == "running" and active_session_id:
                rotate_chapter_session(
                    self.root,
                    slug,
                    sequence_id,
                    active_session_id,
                    reason="technical_retry",
                )
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
            "kind": "create_session",
            "role": "writer",
            "session": {
                "mode": "new",
                "must_be_independent": True,
            },
            "result": _result_contract("writer-session"),
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        state["phase"] = "awaiting_writer_session"
        state["retry_reason"] = "technical"
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="writing",
            retries=retries,
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="写作会话异常，已自动换新会话重试。",
            sequence_id=sequence_id,
            technical_retry_count=retries,
        )

    def _complete_writer(
        self,
        slug: str,
        state: dict[str, Any],
        completion: dict[str, Any],
    ) -> WorkflowResult:
        session, role_result, terminal = self._validate_completion(
            state,
            completion,
            role="writer",
        )
        payload = role_result.get("payload")
        artifact = (
            str(payload.get("artifact_relative_path") or "").strip()
            if isinstance(payload, dict)
            else ""
        )
        if artifact != "draft/正文.md":
            raise WorkflowError("Writer 没有返回唯一允许的正文产物。")
        runtime_snapshot = completion.get("runtime_snapshot")
        if not isinstance(runtime_snapshot, dict):
            raise WorkflowError("Writer 终态缺少原生运行快照。")
        prepared = state.get("capsule")
        if not isinstance(prepared, dict):
            raise WorkflowError("Writer 动作缺少 Capsule 绑定。")
        capsule_id = str(prepared.get("capsule_id") or "")
        runtime_path = (
            self.orchestrator.capsule_root
            / "native-relay-runtime"
            / slug
            / f"{capsule_id}.json"
        )
        _atomic_json(runtime_path, runtime_snapshot)
        try:
            record_capsule_runtime(
                self.root,
                slug,
                capsule_id,
                runtime_path,
            )
            imported = ingest_writer_capsule(
                self.root,
                slug,
                capsule_id,
            )
            report = audit_session_log(runtime_path)
        except Exception:
            try:
                reject_writer_capsule(
                    self.root,
                    slug,
                    capsule_id,
                    reason="writer_result_invalid",
                )
            except Exception:
                pass
            raise
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        generation_id = (
            f"generation.ch{chapter:02d}.{uuid.uuid4().hex[:16]}"
        )
        self.orchestrator._record_generation(
            slug,
            chapter,
            session,
            prepared,
            imported,
            report,
            generation_id,
            parent_generation_id=state.get("parent_generation_id"),
            is_patch=bool(state.get("must_findings")),
        )
        book_dir = self.root / "books" / slug
        record_session_completion(
            self.root,
            slug,
            session_id=session.session_id,
            session_instance_id=session.session_instance_id,
            role="writer",
            provider=session.provider,
            model=session.model,
            agent_harness=session.agent_harness,
            context_scope="writer_capsule_only",
            operation_kind=terminal["kind"],
            operation_id=terminal["value"],
            result_transport=terminal["result_transport"],
            chapter=chapter,
            generation_id=generation_id,
            content_sha256=imported["body_sha256"],
            artifact=book_dir / imported["target_path"],
            workflow_authority=self.orchestrator._workflow_authority,
        )
        self.orchestrator._finalize_scene_handoff(slug, chapter)
        book_project.advance_state(
            self.root,
            slug,
            chapter,
            "drafted",
            evidence=f"evidence/generations/{generation_id}.md",
        )
        book_project.advance_state(
            self.root,
            slug,
            chapter,
            "surface_checked",
            evidence="run-gates/current",
        )
        prose = book_project.find_chapter_file(
            book_dir,
            chapter,
        ).read_text(encoding="utf-8-sig")
        action_id = f"native-action-{uuid.uuid4().hex[:16]}"
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": action_id,
            "kind": "run_role",
            "role": "blind-reader",
            "session": {
                "mode": "new",
                "must_be_independent": True,
            },
            "reasoning_effort": "medium",
            "instructions": render_review_instructions(
                "blind-reader"
            ).text,
            "context": {"prose": prose},
            "result": _result_contract("blind-reader"),
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        state.update(
            {
                "phase": "awaiting_blind_reader",
                "writer_session": asdict(session),
                "generation_id": generation_id,
                "body_sha256": imported["body_sha256"],
                "review_session_ids": [],
            }
        )
        state.pop("blind_outcome", None)
        request = self._request_from_state(state)
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="reviewing",
            retries=int(state.get("technical_retry_count") or 0),
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="正在自动审稿。",
            sequence_id=sequence_id,
        )

    @staticmethod
    def _review_outcome(
        payload: dict[str, Any],
        *,
        role: str,
        session: SessionIdentity,
        terminal: dict[str, str],
    ) -> ReviewOutcome:
        findings_payload = payload.get("findings", ())
        if not isinstance(findings_payload, (list, tuple)):
            raise WorkflowError(f"{role} findings 格式无效。")
        findings: list[ReviewFinding] = []
        for item in findings_payload:
            if not isinstance(item, dict):
                raise WorkflowError(f"{role} finding 格式无效。")
            try:
                findings.append(
                    ReviewFinding(
                        severity=str(item.get("severity") or ""),
                        location=str(item.get("location") or ""),
                        evidence=str(item.get("evidence") or ""),
                        reader_effect=str(
                            item.get("reader_effect") or ""
                        ),
                        revision_intent=str(
                            item.get("revision_intent") or ""
                        ),
                        status=str(item.get("status") or "open"),
                    )
                )
            except TypeError as exc:
                raise WorkflowError(
                    f"{role} finding 字段无效。"
                ) from exc
        analysis = payload.get("analysis", {})
        if not isinstance(analysis, dict) or not all(
            isinstance(name, str) and isinstance(value, str)
            for name, value in analysis.items()
        ):
            raise WorkflowError(f"{role} analysis 格式无效。")
        return ReviewOutcome(
            verdict=str(payload.get("verdict") or ""),
            findings=tuple(findings),
            human_likeness=str(
                payload.get("human_likeness") or "not_applicable"
            ),
            reader_desire=str(
                payload.get("reader_desire") or "not_applicable"
            ),
            emotional_residue=str(
                payload.get("emotional_residue") or "not_applicable"
            ),
            next_chapter_pull=str(
                payload.get("next_chapter_pull") or "not_applicable"
            ),
            analysis=dict(analysis),
            evidence_quote=str(payload.get("evidence_quote") or ""),
            previous_chapter_quote=str(
                payload.get("previous_chapter_quote")
                or "not_applicable"
            ),
            resolved_model=session.model,
            terminal_role=role,
            terminal_session_id=session.session_id,
            terminal_session_instance_id=session.session_instance_id,
            operation_id=terminal["value"],
            operation_kind=terminal["kind"],
            result_transport=terminal["result_transport"],
        )

    def _record_native_review(
        self,
        slug: str,
        state: dict[str, Any],
        role: str,
        session: SessionIdentity,
        outcome: ReviewOutcome,
    ) -> tuple[str, dict[str, Any]]:
        chapter = int(state["chapter"])
        text = self.orchestrator._render_review(
            slug,
            chapter,
            role,
            session,
            outcome,
        )
        recorded = self.orchestrator._record_review_text(
            slug,
            chapter,
            role,
            text,
        )
        binding = book_project.review_binding(
            self.root,
            slug,
            chapter,
            role=role,
        )
        context_scope = (
            "prose_only"
            if role == "blind-reader"
            else "full_review_context"
        )
        record_session_completion(
            self.root,
            slug,
            session_id=session.session_id,
            session_instance_id=session.session_instance_id,
            role=role,
            provider=session.provider,
            model=session.model,
            agent_harness=session.agent_harness,
            context_scope=context_scope,
            operation_kind=str(outcome.operation_kind),
            operation_id=str(outcome.operation_id),
            result_transport=str(outcome.result_transport),
            chapter=chapter,
            generation_id=binding["generation_id"],
            content_sha256=binding["chapter_sha256"],
            artifact=(
                self.root
                / "books"
                / slug
                / recorded["review_file"]
            ),
            workflow_authority=self.orchestrator._workflow_authority,
        )
        return text, recorded

    def _complete_review(
        self,
        slug: str,
        state: dict[str, Any],
        completion: dict[str, Any],
    ) -> WorkflowResult:
        phase = str(state["phase"])
        role = (
            "blind-reader"
            if phase == "awaiting_blind_reader"
            else "chapter-editor"
        )
        session, role_result, terminal = self._validate_completion(
            state,
            completion,
            role=role,
        )
        used_sessions = {
            str(
                (state.get("writer_session") or {}).get("session_id")
                or ""
            ),
            *(
                str(item)
                for item in state.get("review_session_ids", [])
            ),
        }
        if session.session_id in used_sessions:
            raise WorkflowError("三个创作角色必须使用不同的真实会话。")
        payload = role_result.get("payload")
        if not isinstance(payload, dict):
            raise WorkflowError(f"{role} 结果 payload 无效。")
        outcome = self._review_outcome(
            payload,
            role=role,
            session=session,
            terminal=terminal,
        )
        review_text, _ = self._record_native_review(
            slug,
            state,
            role,
            session,
            outcome,
        )
        state.setdefault("review_session_ids", []).append(
            session.session_id
        )
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        request = self._request_from_state(state)
        book_dir = self.root / "books" / slug
        if role == "blind-reader":
            prose = book_project.find_chapter_file(
                book_dir,
                chapter,
            ).read_text(encoding="utf-8-sig")
            scene = (
                book_dir / f"planning/scene-package-ch{chapter:02d}.md"
            ).read_text(encoding="utf-8-sig")
            canon_dir = book_dir / "memory/canon"
            canon = "\n".join(
                path.read_text(encoding="utf-8-sig")
                for path in sorted(canon_dir.rglob("*.md"))
            )[:12000]
            context = {
                "prose": prose,
                "scene_package": scene,
                "story_contract": self.orchestrator._story_contract(
                    request,
                    chapter,
                ),
                "canon": canon,
                "blind_review": review_text,
                "machine_diagnostics": (
                    self.orchestrator._machine_diagnostics(
                        book_project.run_gates(
                            self.root,
                            slug,
                            chapter,
                            expected_mode="formal",
                        )
                    )
                ),
            }
            if chapter > 1:
                previous = book_project.find_chapter_file(
                    book_dir,
                    chapter - 1,
                ).read_text(encoding="utf-8-sig")
                context["previous_chapter_ending"] = previous[
                    max(0, int(len(previous) * 0.8)) :
                ]
            action = {
                "schema": NATIVE_ACTION_SCHEMA,
                "action_id": (
                    f"native-action-{uuid.uuid4().hex[:16]}"
                ),
                "kind": "run_role",
                "role": "chapter-editor",
                "session": {
                    "mode": "new",
                    "must_be_independent": True,
                },
                "reasoning_effort": "medium",
                "instructions": render_review_instructions(
                    "chapter-editor"
                ).text,
                "context": context,
                "result": _result_contract("chapter-editor"),
                "repository_exploration_forbidden": True,
                "allowed_project_writes": [],
            }
            state.update(
                {
                    "phase": "awaiting_chapter_editor",
                    "blind_outcome": asdict(outcome),
                }
            )
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="正在自动审稿。",
                sequence_id=sequence_id,
            )

        blind_payload = state.get("blind_outcome")
        if not isinstance(blind_payload, dict):
            raise WorkflowError("Chapter Editor 前缺少有效 Blind Reader 结果。")
        blind_findings = blind_payload.get("findings", ())
        must = tuple(
            dict.fromkeys(
                self.orchestrator._patch_directive(item)
                for item in (
                    *(
                        ReviewFinding(**item)
                        for item in blind_findings
                        if isinstance(item, dict)
                    ),
                    *outcome.findings,
                )
                if item.severity.upper() == "MUST"
                and item.status.lower() == "open"
            )
        )
        book_project.advance_state(
            self.root,
            slug,
            chapter,
            "blind_read",
            evidence=f"reviews/ch{chapter:02d}-blind-reader.md",
        )
        book_project.advance_state(
            self.root,
            slug,
            chapter,
            "editorial_reviewed",
            evidence=f"reviews/ch{chapter:02d}-chapter-editor.md",
        )
        if must:
            if int(state.get("patch_round") or 0) >= 1:
                rotate_chapter_session(
                    self.root,
                    slug,
                    sequence_id,
                    str(
                        (state.get("writer_session") or {}).get(
                            "session_id"
                        )
                        or ""
                    ),
                    reason="additional_human_regeneration_required",
                )
                result = self.orchestrator._decision_result(
                    slug,
                    request,
                    chapter,
                    sequence_id,
                    message="自动修订后仍有问题，请选择下一步。",
                    retries=int(
                        state.get("technical_retry_count") or 0
                    ),
                    decision_kind="literary_revision_required",
                    must_findings=must,
                    parent_generation_id=str(state["generation_id"]),
                )
                state["phase"] = "decision_required"
                state["must_findings"] = list(must)
                _atomic_json(self._state_path(slug), state)
                self._action_path(slug).unlink(missing_ok=True)
                return result
            writer_session_id = str(
                (state.get("writer_session") or {}).get("session_id")
                or ""
            )
            rotate_chapter_session(
                self.root,
                slug,
                sequence_id,
                writer_session_id,
            )
            action = {
                "schema": NATIVE_ACTION_SCHEMA,
                "action_id": (
                    f"native-action-{uuid.uuid4().hex[:16]}"
                ),
                "kind": "create_session",
                "role": "writer",
                "session": {
                    "mode": "new",
                    "must_be_independent": True,
                },
                "result": _result_contract("writer-session"),
                "repository_exploration_forbidden": True,
                "allowed_project_writes": [],
            }
            state.update(
                {
                    "phase": "awaiting_patch_writer_session",
                    "must_findings": list(must),
                    "parent_generation_id": state["generation_id"],
                    "patch_round": 1,
                }
            )
            self.orchestrator._save_control(
                slug,
                request=request,
                chapter=chapter,
                sequence_id=sequence_id,
                phase="patching",
                retries=int(state.get("technical_retry_count") or 0),
            )
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="发现问题，正在自动修订。",
                sequence_id=sequence_id,
            )
        writer_payload = state.get("writer_session")
        if not isinstance(writer_payload, dict):
            raise WorkflowError("当前章节缺少 Writer 会话绑定。")
        writer_session = SessionIdentity(**writer_payload)
        result = self.orchestrator._finish_chapter(
            slug,
            request,
            chapter,
            sequence_id,
            writer_session,
            int(state.get("technical_retry_count") or 0),
        )
        state["phase"] = (
            "complete"
            if result.user_state == "chapter_complete"
            else "decision_required"
        )
        _atomic_json(self._state_path(slug), state)
        self._action_path(slug).unlink(missing_ok=True)
        return result

    def _complete_patch_writer_session(
        self,
        slug: str,
        state: dict[str, Any],
        completion: dict[str, Any],
    ) -> WorkflowResult:
        session, _, _ = self._validate_completion(
            state,
            completion,
            role="writer-session",
        )
        session = SessionIdentity(
            session_id=session.session_id,
            session_instance_id=session.session_instance_id,
            provider=session.provider,
            model=session.model,
            agent_harness=session.agent_harness,
            role="writer",
        )
        old_writer_id = str(
            (state.get("writer_session") or {}).get("session_id") or ""
        )
        if session.session_id == old_writer_id:
            raise WorkflowError("Patch Writer 必须使用新的真实会话。")
        sequence_id = str(state["sequence_id"])
        chapter = int(state["chapter"])
        claim_chapter_session(
            self.root,
            slug,
            sequence_id,
            session.session_id,
        )
        capsule_dir = (
            self.orchestrator.capsule_root
            / slug
            / sequence_id
            / f"{session.session_id}-{uuid.uuid4().hex[:8]}"
        )
        must_findings = tuple(
            str(item) for item in state.get("must_findings", [])
        )
        authorization_id = None
        human_decision_reference = str(
            state.get("human_decision_reference") or ""
        ).strip()
        if human_decision_reference:
            authorization = authorize_regeneration(
                self.root,
                slug,
                sequence_id,
                session.session_id,
                authority="human_delegate",
                decision_reference=human_decision_reference,
            )
            authorization_id = authorization["authorization_id"]
        prepared = prepare_writer_capsule(
            self.root,
            slug,
            sequence_id,
            session.session_id,
            capsule_dir,
            f"chapters/e01/ch-{chapter:02d}/正文.md",
            regeneration_authorization_id=authorization_id,
            patch_directive="\n".join(
                f"- {item}" for item in must_findings
            )
            or None,
        )
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
            "kind": "run_role",
            "role": "writer",
            "session": {
                "mode": "reuse",
                "session_id": session.session_id,
                "session_instance_id": session.session_instance_id,
            },
            "reasoning_effort": "medium",
            "capsule": {
                "id": prepared["capsule_id"],
                "path": prepared["capsule_dir"],
                "operation": prepared["operation"],
                "instructions": "instructions.md",
                "handoff": "handoff.md",
                "output": prepared["draft_output"],
            },
            "runtime": {
                "schema": "novel-forge-runtime/v1",
                "assurance_mode": "formal_native",
                "reported_by": "native_host",
                "filesystem_scope": "guarded_native",
                "write_scope": "post_execution_verified",
                "repository_snapshot_enforced": True,
            },
            "result": {
                **_result_contract("writer"),
                "runtime_snapshot_required": True,
            },
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        state.update(
            {
                "phase": "awaiting_writer",
                "writer_session": asdict(session),
                "capsule": prepared,
            }
        )
        state.pop("human_decision_reference", None)
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="发现问题，正在自动修订。",
            sequence_id=sequence_id,
        )
