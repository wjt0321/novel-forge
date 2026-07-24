"""Persistent pull protocol for visible host-native creative sessions."""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
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
from .lint import lint_file
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
from .review_capsule import (
    ReviewCapsuleError,
    prepare_review_capsule,
    verify_review_capsule,
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
    REVIEW_ANALYSIS_FIELDS,
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
MAX_LEAN_SURFACE_PATCH_ROUNDS = 3


class NativeWorkspaceMutationError(WorkflowError):
    """Raised after restoring one creative role's project mutation."""

    def __init__(self, reason: str):
        super().__init__("创作角色修改了项目控制面。")
        self.reason = reason


class NativeCompletionRepairError(WorkflowError):
    """Raised when an official terminal only needs envelope repair."""

    def __init__(self, reason: str):
        super().__init__("原生角色完成信息需要补交。")
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
                "hard_anchor_coverage",
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


def _completion_payload_template(role: str) -> dict[str, Any]:
    """Return a fillable payload, distinct from the validation contract."""
    if role == "writer-planning":
        return {"files": {}}
    if role == "writer-session":
        return {}
    if role == "writer":
        return {"artifact_relative_path": "draft/正文.md"}
    if role == "blind-reader":
        return {
            "verdict": "<pass-or-needs_revision>",
            "findings": [],
            "human_likeness": "<convincing-uncertain-or-synthetic>",
            "reader_desire": "<continue-conditional-or-stop>",
            "emotional_residue": "<specific-reader-residue>",
            "next_chapter_pull": "<specific-reason-to-continue>",
            "analysis": {},
            "evidence_quote": "<exact-current-prose-quote>",
        }
    if role == "chapter-editor":
        return {
            "verdict": "<ready_for_editor_decision-or-revision_required>",
            "findings": [],
            "analysis": {},
            "hard_anchor_coverage": {
                "protagonist": {
                    "status": "<covered-implicit_but_unambiguous-missing-conflicted>",
                    "evidence": "<exact-current-prose-quote-or-empty>",
                    "reader_reconstruction": "<ordinary-reader-reconstruction>",
                },
                "world": {
                    "status": "<covered-implicit_but_unambiguous-missing-conflicted-or-deferred_by_scene_boundary>",
                    "evidence": "<exact-current-prose-quote-or-empty>",
                    "reader_reconstruction": "<ordinary-reader-reconstruction>",
                },
                "conflict": {
                    "status": "<covered-implicit_but_unambiguous-missing-conflicted>",
                    "evidence": "<exact-current-prose-quote-or-empty>",
                    "reader_reconstruction": "<ordinary-reader-reconstruction>",
                },
                "ending_hook": {
                    "status": "<covered-implicit_but_unambiguous-missing-conflicted>",
                    "evidence": "<exact-current-prose-quote-or-empty>",
                    "reader_reconstruction": "<ordinary-reader-reconstruction>",
                },
            },
            "evidence_quote": "<exact-current-prose-quote>",
            "previous_chapter_quote": "<exact-quote-or-not_applicable>",
        }
    raise WorkflowError(f"未知原生角色：{role}")


def _completion_template(action: dict[str, Any]) -> dict[str, Any]:
    """Compile an exact host completion envelope for the current action."""
    role = str(action["role"])
    session_action = action.get("session")
    session = {
        "session_id": "<official-session-id>",
        "session_instance_id": "<official-session-instance-id>",
        "provider": "<resolved-provider>",
        "model": "<resolved-model>",
        "agent_harness": "<native-host>",
    }
    if (
        isinstance(session_action, dict)
        and session_action.get("mode") == "reuse"
    ):
        session["session_id"] = str(session_action["session_id"])
        session["session_instance_id"] = str(
            session_action["session_instance_id"]
        )
    template: dict[str, Any] = {
        "schema": NATIVE_COMPLETION_SCHEMA,
        "action_id": action["action_id"],
        "status": "completed",
        "session": session,
        "operation_handle": {
            "kind": "<official-handle-kind>",
            "value": "<official-handle-value>",
        },
        "result_transport": "<official-result-transport>",
        "role_result": {
            "schema": "novel-forge-role-result/v1",
            "role": role,
            "payload": _completion_payload_template(role),
        },
    }
    review_capsule = action.get("review_capsule")
    if isinstance(review_capsule, dict):
        template["review_capsule_id"] = review_capsule["id"]
    capsule = action.get("capsule")
    if role == "writer" and isinstance(capsule, dict):
        template["runtime_snapshot"] = {
            "schema": "novel-forge-runtime/v1",
            "session_id": session["session_id"],
            "scope": {"chapter_count": 1},
            "harness": {
                "name": "<native-host>",
                "version": "<version-or-unknown>",
            },
            "model": {
                "provider": session["provider"],
                "name": session["model"],
                "reasoning_effort": "<actual-or-null>",
            },
            "timing": {"elapsed_seconds": None},
            "usage": {
                "request_count": None,
                "input_tokens": None,
                "output_tokens": None,
                "cached_input_tokens": None,
                "total_tokens": None,
                "max_request_context_tokens": None,
                "context_reset_count": None,
            },
            "tools": {
                "call_count": None,
                "failure_count": None,
                "by_name": {},
            },
            "guardian": {
                "capsule_id": capsule["id"],
                "workspace_mode": "isolated_writer_capsule",
                "assurance_mode": "formal_native",
                "filesystem_scope": "guarded_native",
                "write_scope": "post_execution_verified",
                "repository_snapshot_enforced": True,
                "book_control_plane_visible": False,
                "validator_source_visible": False,
                "reported_by": "native_host",
            },
        }
    return template


def _lean_result_contract(role: str) -> dict[str, Any]:
    """Describe only the creative artifact a role must deliver."""
    if role == "writer-planning":
        return {
            "format": "json",
            "required": ["files"],
            "purpose": "写作前的内部规划附属产物",
        }
    if role == "writer-session":
        return {"format": "none"}
    if role == "writer":
        return {
            "format": "markdown",
            "output": "draft/正文.md",
            "purpose": "本章正文",
        }
    required = (
        [
            "verdict",
            "must",
            "human_likeness",
            "reader_desire",
            "emotional_residue",
            "next_chapter_pull",
            "summary",
            "evidence_quote",
        ]
        if role == "blind-reader"
        else ["verdict", "must", "summary", "evidence_quote"]
    )
    return {
        "format": "json",
        "required": required,
        "purpose": (
            "盲读结论"
            if role == "blind-reader"
            else "章节编辑结论"
        ),
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
        strict_audit: bool = True,
    ):
        self.root = Path(root).resolve()
        self.strict_audit = strict_audit
        self.assurance_mode = (
            "strict_audit" if strict_audit else "lean_native"
        )
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

    def _integrity_root(self, slug: str) -> Path:
        """Limit routine role mutation checks to the current book."""
        if self.strict_audit:
            return self.root
        return self.root / "books" / slug

    def _diff_dir(self, slug: str, chapter: int) -> Path:
        return (
            self.root
            / "books"
            / slug
            / ".novel-forge"
            / "diff"
            / f"ch{chapter:02d}"
        )

    def _staged_body_path(self, state: dict[str, Any]) -> Path:
        prepared = state.get("capsule")
        if not isinstance(prepared, dict):
            raise WorkflowError("Writer 动作缺少临时正文绑定。")
        return Path(str(prepared["capsule_dir"])) / str(
            prepared.get("draft_output") or "draft/正文.md"
        )

    @staticmethod
    def _reset_transient_dir(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)

    def _freeze_initial_draft(self, state: dict[str, Any]) -> None:
        source = self._staged_body_path(state)
        initial = self._diff_dir(
            str(state["slug"]), int(state["chapter"])
        ) / "初稿.md"
        if not initial.exists():
            initial.write_bytes(source.read_bytes())

    def _write_staged_diff(self, state: dict[str, Any]) -> None:
        diff_dir = self._diff_dir(
            str(state["slug"]), int(state["chapter"])
        )
        initial = diff_dir / "初稿.md"
        current = self._staged_body_path(state)
        before = initial.read_text(encoding="utf-8-sig").splitlines(
            keepends=True
        )
        after = current.read_text(encoding="utf-8-sig").splitlines(
            keepends=True
        )
        patch = "".join(
            difflib.unified_diff(
                before,
                after,
                fromfile="初稿.md",
                tofile="最终稿.md",
            )
        )
        (diff_dir / "修订.diff").write_text(patch, encoding="utf-8")

    @staticmethod
    def _phase_role(state: dict[str, Any]) -> str:
        phase = str(state.get("phase") or "")
        if phase == "awaiting_writer_planning":
            return "writer-planning"
        if phase in {
            "awaiting_writer_session",
            "awaiting_patch_writer_session",
        }:
            return "writer-session"
        if phase == "awaiting_blind_reader":
            return "blind-reader"
        if phase == "awaiting_chapter_editor":
            return "chapter-editor"
        return "writer"

    @staticmethod
    def _repair_common_json_quotes(text: str) -> str:
        """Escape prose quotes that a role left unescaped inside JSON."""
        repaired: list[str] = []
        in_string = False
        escaped = False
        length = len(text)
        for index, char in enumerate(text):
            if not in_string:
                repaired.append(char)
                if char == '"':
                    in_string = True
                continue
            if escaped:
                repaired.append(char)
                escaped = False
                continue
            if char == "\\":
                repaired.append(char)
                escaped = True
                continue
            if char != '"':
                repaired.append(char)
                continue
            cursor = index + 1
            while cursor < length and text[cursor].isspace():
                cursor += 1
            if cursor >= length or text[cursor] in {",", "}", "]", ":"}:
                repaired.append(char)
                in_string = False
            else:
                repaired.append('\\"')
        return "".join(repaired)

    @classmethod
    def _result_payload(
        cls,
        result_file: Path | None,
        *,
        repair_common_quotes: bool = False,
    ) -> dict[str, Any]:
        if result_file is None:
            return {}
        try:
            text = Path(result_file).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise WorkflowError("角色结果文件不存在或不是有效 JSON。") from exc
        try:
            payload = json.loads(text, strict=False)
        except json.JSONDecodeError as exc:
            if not repair_common_quotes:
                raise WorkflowError(
                    "角色结果文件不存在或不是有效 JSON。"
                ) from exc
            try:
                payload = json.loads(
                    cls._repair_common_json_quotes(text),
                    strict=False,
                )
            except json.JSONDecodeError as repaired_exc:
                raise WorkflowError(
                    "角色结果文件不存在或不是有效 JSON。"
                ) from repaired_exc
        if not isinstance(payload, dict):
            raise WorkflowError("角色结果文件顶层必须是 JSON 对象。")
        role_result = payload.get("role_result")
        if isinstance(role_result, dict):
            nested = role_result.get("payload")
            if isinstance(nested, dict):
                return dict(nested)
        nested = payload.get("payload")
        if isinstance(nested, dict):
            return dict(nested)
        return dict(payload)

    @staticmethod
    def _lean_runtime_snapshot(
        session: SessionIdentity,
        capsule_id: str,
    ) -> dict[str, Any]:
        """Record unknown telemetry truthfully without asking the role."""
        return {
            "schema": "novel-forge-runtime/v1",
            "session_id": session.session_id,
            "scope": {"chapter_count": 1},
            "harness": {
                "name": session.agent_harness,
                "version": "unknown",
            },
            "model": {
                "provider": session.provider,
                "name": session.model,
                "reasoning_effort": "unknown",
            },
            "timing": {"elapsed_seconds": None},
            "usage": {
                "request_count": None,
                "input_tokens": None,
                "output_tokens": None,
                "cached_input_tokens": None,
                "total_tokens": None,
                "max_request_context_tokens": None,
                "context_reset_count": None,
            },
            "tools": {
                "call_count": None,
                "failure_count": None,
                "by_name": {},
            },
            "guardian": {
                "capsule_id": capsule_id,
                "workspace_mode": "isolated_writer_capsule",
                "assurance_mode": "lean_native",
                "filesystem_scope": "capsule_output",
                "write_scope": "post_execution_verified",
                "repository_snapshot_enforced": False,
                "book_control_plane_visible": False,
                "validator_source_visible": False,
                "reported_by": "deterministic_control_plane",
            },
        }

    def complete_minimal(
        self,
        slug: str,
        *,
        session_id: str | None = None,
        result_file: Path | None = None,
        session_instance_id: str | None = None,
        provider: str = "unknown",
        model: str = "unknown",
        agent_harness: str = "native-host",
    ) -> WorkflowResult:
        """Complete the current Lean action without a technical envelope."""
        state = self._load_state(slug)
        if self.strict_audit:
            raise WorkflowError("严格审计模式必须提交完整角色终态。")
        action = self.next_action(slug)
        role = self._phase_role(state)
        expected = action.get("session")
        control_run_id = str(action.get("control_run_id") or "").strip()
        if control_run_id:
            session_id = control_run_id
            session_instance_id = control_run_id
        elif (
            isinstance(expected, dict)
            and expected.get("mode") == "reuse"
        ):
            session_id = str(expected["session_id"])
            session_instance_id = str(expected["session_instance_id"])
        else:
            session_id = str(session_id or "").strip()
        session = SessionIdentity(
            session_id=str(session_id or "").strip(),
            session_instance_id=(
                str(session_instance_id or session_id or "").strip()
            ),
            provider=provider.strip() or "unknown",
            model=model.strip() or "unknown",
            agent_harness=agent_harness.strip() or "native-host",
            role="writer" if role == "writer-planning" else role,
        )
        if not session.session_id or not session.session_instance_id:
            raise WorkflowError("角色完成必须提供真实会话 ID。")
        if result_file is None and action.get("result_file"):
            result_file = Path(str(action["result_file"]))
        payload = self._result_payload(
            result_file,
            repair_common_quotes=True,
        )
        if role == "writer":
            payload = {"artifact_relative_path": "draft/正文.md"}
        completion: dict[str, Any] = {
            "schema": NATIVE_COMPLETION_SCHEMA,
            "action_id": action["action_id"],
            "status": "completed",
            "session": {
                "session_id": session.session_id,
                "session_instance_id": session.session_instance_id,
                "provider": session.provider,
                "model": session.model,
                "agent_harness": session.agent_harness,
            },
            "operation_handle": {
                "kind": "native-session",
                "value": session.session_id,
            },
            "result_transport": "artifact",
            "role_result": {
                "schema": "novel-forge-role-result/v1",
                "role": role,
                "payload": payload,
            },
        }
        review_capsule = action.get("review_capsule")
        if isinstance(review_capsule, dict):
            completion["review_capsule_id"] = review_capsule["id"]
        capsule = action.get("capsule")
        if role == "writer" and isinstance(capsule, dict):
            completion["runtime_snapshot"] = self._lean_runtime_snapshot(
                session,
                str(capsule["id"]),
            )
        return self.complete_role(slug, completion)

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

    def _result_path(self, slug: str, action_id: str) -> Path:
        return (
            self.orchestrator.capsule_root
            / "native-role-results"
            / slug
            / f"{action_id}.json"
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
        mode = str(payload.get("assurance_mode") or "")
        if mode in {"strict_audit", "lean_native"}:
            self.assurance_mode = mode
            self.strict_audit = mode == "strict_audit"
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
            raise NativeCompletionRepairError("missing_session")
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
            raise NativeCompletionRepairError("incomplete_session")
        return SessionIdentity(role=role, **values)

    @staticmethod
    def _completion_identity(
        completion: dict[str, Any],
    ) -> dict[str, str] | None:
        session = completion.get("session")
        if not isinstance(session, dict):
            return None
        session_id = str(session.get("session_id") or "").strip()
        session_instance_id = str(
            session.get("session_instance_id") or ""
        ).strip()
        if not session_id or not session_instance_id:
            return None
        return {
            "session_id": session_id,
            "session_instance_id": session_instance_id,
        }

    @staticmethod
    def _remember_session(
        state: dict[str, Any],
        session: dict[str, Any] | SessionIdentity,
        *,
        role: str,
        status: str,
    ) -> None:
        if isinstance(session, SessionIdentity):
            session_id = session.session_id
            session_instance_id = session.session_instance_id
        else:
            session_id = str(session.get("session_id") or "").strip()
            session_instance_id = str(
                session.get("session_instance_id") or ""
            ).strip()
        if not session_id or not session_instance_id:
            return
        history = state.setdefault("role_session_history", [])
        if not isinstance(history, list):
            history = []
            state["role_session_history"] = history
        record = {
            "session_id": session_id,
            "session_instance_id": session_instance_id,
            "role": role,
            "status": status,
        }
        if not any(
            isinstance(item, dict)
            and item.get("session_id") == session_id
            and item.get("session_instance_id") == session_instance_id
            and item.get("role") == role
            and item.get("status") == status
            for item in history
        ):
            history.append(record)

    def _remember_failed_completion_session(
        self,
        state: dict[str, Any],
        completion: dict[str, Any],
    ) -> None:
        identity = self._completion_identity(completion)
        if identity is None:
            return
        self._remember_session(
            state,
            identity,
            role=self._retry_bucket(state),
            status="failed",
        )

    def _used_session_identity_values(
        self,
        slug: str,
        state: dict[str, Any],
    ) -> set[str]:
        values: set[str] = set()
        for key in ("writer_session",):
            item = state.get(key)
            if isinstance(item, dict):
                values.update(
                    str(item.get(name) or "").strip()
                    for name in ("session_id", "session_instance_id")
                )
        for key in ("role_session_history",):
            items = state.get(key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        values.update(
                            str(item.get(name) or "").strip()
                            for name in (
                                "session_id",
                                "session_instance_id",
                            )
                        )
        for key in ("review_session_ids", "review_session_instance_ids"):
            items = state.get(key)
            if isinstance(items, list):
                values.update(str(item).strip() for item in items)
        sequence_id = str(state.get("sequence_id") or "").strip()
        if sequence_id:
            try:
                sequence = chapter_sequence_status(
                    self.root,
                    slug,
                    sequence_id,
                )
            except Exception:
                sequence = {}
            values.update(
                str(item).strip()
                for item in sequence.get("used_session_ids", [])
            )
        return {value for value in values if value}

    def _assert_fresh_session(
        self,
        slug: str,
        state: dict[str, Any],
        session: SessionIdentity,
    ) -> None:
        incoming = {
            session.session_id.strip(),
            session.session_instance_id.strip(),
        }
        overlap = incoming & self._used_session_identity_values(slug, state)
        if overlap:
            raise WorkflowError(
                "原生角色会话身份已经使用或废弃，必须创建新会话。"
            )

    def _validate_completion(
        self,
        state: dict[str, Any],
        completion: dict[str, Any],
        *,
        role: str,
    ) -> tuple[SessionIdentity, dict[str, Any], dict[str, str]]:
        if completion.get("schema") != NATIVE_COMPLETION_SCHEMA:
            raise NativeCompletionRepairError("invalid_completion_schema")
        if completion.get("action_id") != state.get("action_id"):
            raise NativeCompletionRepairError("action_id_mismatch")
        if completion.get("status") != "completed":
            raise NativeCompletionRepairError("terminal_not_completed")
        operation = completion.get("operation_handle")
        if not isinstance(operation, dict):
            raise NativeCompletionRepairError("missing_operation_handle")
        operation_handle = {
            "kind": str(operation.get("kind") or "").strip(),
            "value": str(operation.get("value") or "").strip(),
        }
        if not all(operation_handle.values()):
            raise NativeCompletionRepairError("invalid_operation_handle")
        result_transport = str(
            completion.get("result_transport") or ""
        ).strip()
        if not result_transport:
            raise NativeCompletionRepairError("missing_result_transport")
        role_result = completion.get("role_result")
        if (
            not isinstance(role_result, dict)
            or role_result.get("schema") != "novel-forge-role-result/v1"
            or role_result.get("role") != role
        ):
            raise NativeCompletionRepairError("invalid_role_result_binding")
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
            raise NativeCompletionRepairError("session_binding_mismatch")
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
        action["assurance_mode"] = self.assurance_mode
        if self.strict_audit:
            action["completion_template"] = _completion_template(action)
        else:
            action.pop("completion_template", None)
            role = self._phase_role(state)
            action["result"] = _lean_result_contract(role)
            if role in {
                "writer-planning",
                "blind-reader",
                "chapter-editor",
            }:
                result_path = (
                    self._diff_dir(slug, int(state["chapter"]))
                    / f"{role}.json"
                    if role in {"blind-reader", "chapter-editor"}
                    else self._result_path(
                        slug,
                        str(action["action_id"]),
                    )
                )
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.unlink(missing_ok=True)
                action["result_file"] = str(result_path)
                if role in {"blind-reader", "chapter-editor"}:
                    action["allowed_project_writes"] = [
                        result_path.relative_to(
                            self._integrity_root(slug)
                        ).as_posix()
                    ]
                action["delivery"] = (
                    "角色只把创作结论写入 result_file；"
                    "Lead 等待角色完成后执行 complete-role；无需填写技术表单。"
                )
            else:
                action.pop("result_file", None)
                action["delivery"] = (
                    "Writer 只写 capsule 内的 draft/正文.md；"
                    "Lead 等待正文落盘后执行 complete-role；无需填写技术表单。"
                )
        state["action_id"] = action["action_id"]
        state["assurance_mode"] = self.assurance_mode
        _atomic_json(self._state_path(slug), state)
        _atomic_json(self._action_path(slug), action)
        integrity_root = self._integrity_root(slug)
        _atomic_json(
            self._snapshot_path(slug, action["action_id"]),
            snapshot_workspace(integrity_root),
        )
        create_workspace_backup(
            integrity_root,
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
        integrity_root = self._integrity_root(slug)
        delta = workspace_delta(before, snapshot_workspace(integrity_root))
        try:
            action = json.loads(
                self._action_path(slug).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowError("原生角色动作记录损坏。") from exc
        allowed = {
            str(path)
            for path in action.get("allowed_project_writes", [])
            if isinstance(path, str)
        }
        unexpected_created = tuple(
            path for path in delta.created if path not in allowed
        )
        unexpected_modified = tuple(
            path for path in delta.modified if path not in allowed
        )
        unexpected_deleted = tuple(
            path for path in delta.deleted if path not in allowed
        )
        backup_path = self._backup_path(slug, action_id)
        if unexpected_created or unexpected_modified or unexpected_deleted:
            remove_created_paths(integrity_root, unexpected_created)
            restore_workspace_paths(
                integrity_root,
                backup_path,
                before,
                unexpected_modified + unexpected_deleted,
            )
            restored = workspace_delta(
                before,
                snapshot_workspace(integrity_root),
            )
            restored_unexpected = (
                tuple(path for path in restored.created if path not in allowed)
                + tuple(
                    path for path in restored.modified if path not in allowed
                )
                + tuple(path for path in restored.deleted if path not in allowed)
            )
            if restored_unexpected:
                raise WorkflowError("项目控制面自动恢复失败。")
            snapshot_path.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)
            reason = (
                "control_plane_mutation"
                if unexpected_modified or unexpected_deleted
                else "unexpected_project_artifact"
            )
            raise NativeWorkspaceMutationError(reason)
        snapshot_path.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)

    @staticmethod
    def _control_session(role: str, chapter: int) -> SessionIdentity:
        run_id = (
            f"relay-{role}-ch{chapter:02d}-{uuid.uuid4().hex[:16]}"
        )
        return SessionIdentity(
            session_id=run_id,
            session_instance_id=run_id,
            provider="unknown",
            model="unknown",
            agent_harness="deterministic-control-plane",
            role=role,
        )

    def _prepare_lean_writer_action(
        self,
        slug: str,
        state: dict[str, Any],
        *,
        request: WorkflowRequest,
        chapter: int,
        sequence_id: str,
        must_findings: tuple[str, ...] = (),
        parent_generation_id: str | None = None,
        reuse_preferred: bool = False,
    ) -> dict[str, Any]:
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
                reason=(
                    "literary_patch"
                    if must_findings
                    else "technical_retry"
                ),
            )
        session = self._control_session("writer", chapter)
        claim_chapter_session(
            self.root,
            slug,
            sequence_id,
            session.session_id,
        )
        capsule_dir = self._diff_dir(slug, chapter) / "writer"
        self._reset_transient_dir(capsule_dir)
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
            patch_directive=(
                "\n".join(f"- {item}" for item in must_findings)
                if must_findings
                else None
            ),
        )
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
            "kind": "run_role",
            "role": "writer",
            "stage": "patch" if must_findings else "draft",
            "control_run_id": session.session_id,
            "session": {
                "mode": (
                    "reuse_preferred" if reuse_preferred else "new"
                ),
                "must_be_independent": False,
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
                "assurance_mode": "lean_native",
                "reported_by": "deterministic_control_plane",
                "filesystem_scope": "capsule_output",
                "write_scope": "post_execution_verified",
                "repository_snapshot_enforced": False,
            },
            "result": {
                **_result_contract("writer"),
                "runtime_snapshot_required": False,
            },
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [
                (
                    Path(prepared["capsule_dir"])
                    / prepared["draft_output"]
                )
                .relative_to(self._integrity_root(slug))
                .as_posix()
            ],
        }
        state.update(
            {
                "phase": "awaiting_writer",
                "sequence_id": sequence_id,
                "writer_session": asdict(session),
                "capsule": prepared,
                "parent_generation_id": parent_generation_id,
            }
        )
        state.pop("human_decision_reference", None)
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="patching" if must_findings else "writing",
            retries=int(state.get("technical_retry_count") or 0),
        )
        self._write_action(slug, state, action)
        return action

    def start(
        self,
        slug: str,
        request: WorkflowRequest,
        *,
        chapter: int = 1,
    ) -> WorkflowResult:
        """Initialize deterministic state and dispatch the first creative role."""
        request.validate()
        self.orchestrator._assert_project_is_managed(slug, chapter)
        book_dir = self.orchestrator._prepare_project(slug, request, chapter)
        if not self.strict_audit:
            planning = self.orchestrator._prose_first_control_planning(
                book_dir,
                chapter,
                request,
            )
            self.orchestrator._write_writer_planning(
                book_dir,
                chapter,
                request,
                planning,
            )
            sequence_id = (
                f"auto-ch{chapter:02d}-{uuid.uuid4().hex[:10]}"
            )
            begin_chapter_sequence(
                self.root,
                slug,
                chapter,
                1,
                sequence_id=sequence_id,
                orchestrator_run_id=(
                    f"workflow-{uuid.uuid4().hex[:12]}"
                ),
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
            state = {
                "schema": NATIVE_RELAY_SCHEMA,
                "slug": slug,
                "chapter": chapter,
                "request": asdict(request),
                "phase": "awaiting_writer",
                "action_id": "",
                "technical_retry_count": 0,
                "technical_retry_counts": {},
                "delivery_repair_counts": {},
                "author_approval": False,
                "publication_eligibility": False,
            }
            self._prepare_lean_writer_action(
                slug,
                state,
                request=request,
                chapter=chapter,
                sequence_id=sequence_id,
            )
            return WorkflowResult(
                user_state="running",
                message="正在写作。",
                sequence_id=sequence_id,
            )
        action_id = f"native-action-{uuid.uuid4().hex[:16]}"
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": action_id,
            "kind": "run_role",
            "role": (
                "writer-planning" if self.strict_audit else "writer"
            ),
            **({"stage": "planning"} if not self.strict_audit else {}),
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
            "technical_retry_counts": {},
            "delivery_repair_counts": {},
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
        decision_kind = str(state.get("decision_kind") or "")
        if (
            sequence_id
            and state.get("generation_id")
            and state.get("body_sha256")
            and not state.get("must_findings")
            and decision_kind in {"", "native_role_failed"}
        ):
            failed_phase = str(state.get("failed_phase") or "")
            role = (
                "chapter-editor"
                if (
                    failed_phase == "awaiting_chapter_editor"
                    or isinstance(state.get("blind_outcome"), dict)
                )
                else "blind-reader"
            )
            bucket = role
            counts = state.get("technical_retry_counts")
            if not isinstance(counts, dict):
                counts = {}
                state["technical_retry_counts"] = counts
            counts[bucket] = 0
            state["technical_retry_count"] = 0
            state["phase"] = f"awaiting_{role.replace('-', '_')}"
            state.pop("decision_kind", None)
            state.pop("failed_phase", None)
            state.pop("retry_reason", None)
            action = self._review_action(slug, state, role)
            self.orchestrator._save_control(
                slug,
                request=request,
                chapter=chapter,
                sequence_id=sequence_id,
                phase="reviewing",
                retries=0,
            )
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="正在自动审稿。",
                sequence_id=sequence_id,
            )
        if not sequence_id:
            if not self.strict_audit:
                book_dir = self.root / "books" / slug
                planning = self.orchestrator._prose_first_control_planning(
                    book_dir,
                    chapter,
                    request,
                )
                self.orchestrator._write_writer_planning(
                    book_dir,
                    chapter,
                    request,
                    planning,
                )
                sequence_id = (
                    f"auto-ch{chapter:02d}-{uuid.uuid4().hex[:10]}"
                )
                begin_chapter_sequence(
                    self.root,
                    slug,
                    chapter,
                    1,
                    sequence_id=sequence_id,
                    orchestrator_run_id=(
                        f"workflow-{uuid.uuid4().hex[:12]}"
                    ),
                )
                state.update(
                    {
                        "technical_retry_count": 0,
                        "human_decision_reference": (
                            f"native-retry-{uuid.uuid4().hex[:16]}"
                        ),
                    }
                )
                self._prepare_lean_writer_action(
                    slug,
                    state,
                    request=request,
                    chapter=chapter,
                    sequence_id=sequence_id,
                )
                return WorkflowResult(
                    user_state="running",
                    message="正在重新生成本章。",
                    sequence_id=sequence_id,
                )
            book_dir = self.root / "books" / slug
            action = {
                "schema": NATIVE_ACTION_SCHEMA,
                "action_id": (
                    f"native-action-{uuid.uuid4().hex[:16]}"
                ),
                "kind": "run_role",
                "role": (
                    "writer-planning" if self.strict_audit else "writer"
                ),
                **(
                    {"stage": "planning"}
                    if not self.strict_audit
                    else {}
                ),
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
        if not self.strict_audit:
            state.update(
                {
                    "technical_retry_count": 0,
                    "human_decision_reference": (
                        f"native-retry-{uuid.uuid4().hex[:16]}"
                    ),
                    "retry_reason": "user_regeneration",
                }
            )
            self._prepare_lean_writer_action(
                slug,
                state,
                request=request,
                chapter=chapter,
                sequence_id=sequence_id,
                parent_generation_id=state.get("generation_id"),
            )
            return WorkflowResult(
                user_state="running",
                message="正在重新生成本章。",
                sequence_id=sequence_id,
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
        except NativeCompletionRepairError as exc:
            return self._request_completion_repair(
                slug,
                state,
                reason=exc.reason,
            )
        except NativeWorkspaceMutationError as exc:
            self._remember_failed_completion_session(state, completion)
            return self._recover_technical_failure(
                slug,
                state,
                failure_reason=exc.reason,
            )
        except (GuardianError, WorkflowError, OSError, ValueError):
            self._remember_failed_completion_session(state, completion)
            return self._recover_technical_failure(slug, state)

    @staticmethod
    def _retry_bucket(state: dict[str, Any]) -> str:
        phase = str(state.get("phase") or "")
        if phase == "awaiting_writer_planning":
            return "writer-planning"
        if phase == "awaiting_blind_reader":
            return "blind-reader"
        if phase == "awaiting_chapter_editor":
            return "chapter-editor"
        if phase == "awaiting_patch_writer_session":
            return "patch-writer"
        if phase == "awaiting_writer" and state.get("must_findings"):
            return "patch-writer"
        return "writer"

    def _next_retry_count(self, state: dict[str, Any]) -> tuple[str, int]:
        bucket = self._retry_bucket(state)
        counts = state.get("technical_retry_counts")
        if not isinstance(counts, dict):
            counts = {}
            state["technical_retry_counts"] = counts
        current = int(counts.get(bucket) or 0)
        retries = current + 1
        counts[bucket] = retries
        state["technical_retry_count"] = retries
        return bucket, retries

    @staticmethod
    def _reset_active_retry(
        state: dict[str, Any],
        bucket: str,
    ) -> None:
        counts = state.get("technical_retry_counts")
        if not isinstance(counts, dict):
            counts = {}
            state["technical_retry_counts"] = counts
        counts.setdefault(bucket, 0)
        state["technical_retry_count"] = int(counts[bucket])

    def _request_completion_repair(
        self,
        slug: str,
        state: dict[str, Any],
        *,
        reason: str,
    ) -> WorkflowResult:
        action_id = str(state.get("action_id") or "")
        counts = state.get("delivery_repair_counts")
        if not isinstance(counts, dict):
            counts = {}
            state["delivery_repair_counts"] = counts
        attempt = int(counts.get(action_id) or 0) + 1
        counts[action_id] = attempt
        if attempt > self.orchestrator.max_technical_retries:
            return self._recover_technical_failure(
                slug,
                state,
                failure_reason="writer_terminal_failure",
            )
        action = self.next_action(slug)
        action["completion_repair"] = {
            "attempt": attempt,
            "reason": reason,
            "instruction": (
                "Do not rerun the role. Resubmit the same official terminal "
                "using completion_template."
            ),
        }
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="正在确认角色结果。",
            sequence_id=str(state.get("sequence_id") or ""),
            technical_retry_count=int(
                state.get("technical_retry_count") or 0
            ),
        )

    def _review_inputs(
        self,
        slug: str,
        state: dict[str, Any],
        role: str,
    ) -> dict[str, str]:
        chapter = int(state["chapter"])
        request = self._request_from_state(state)
        book_dir = self.root / "books" / slug
        if not self.strict_audit and isinstance(state.get("capsule"), dict):
            prose = self._staged_body_path(state).read_text(
                encoding="utf-8-sig"
            )
        else:
            prose = book_project.find_chapter_file(
                book_dir,
                chapter,
            ).read_text(encoding="utf-8-sig")
        if role == "blind-reader":
            return {"prose": prose}
        scene = (
            book_dir / f"planning/scene-package-ch{chapter:02d}.md"
        ).read_text(encoding="utf-8-sig")
        canon_dir = book_dir / "memory/canon"
        blind_path = book_dir / f"reviews/ch{chapter:02d}-blind-reader.md"
        blind_outcome = state.get("blind_outcome")
        if self.strict_audit:
            if not blind_path.is_file():
                raise WorkflowError(
                    "Chapter Editor 前缺少有效 Blind Reader 记录。"
                )
            blind_review = blind_path.read_text(encoding="utf-8-sig")
        elif isinstance(blind_outcome, dict):
            blind_review = json.dumps(
                blind_outcome,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        else:
            raise WorkflowError(
                "Chapter Editor 前缺少有效 Blind Reader 结果。"
            )
        inputs = {
            "prose": prose,
            "scene_package": scene,
            "story_contract": self.orchestrator._story_contract(
                request,
                chapter,
            ),
            "canon": "\n".join(
                path.read_text(encoding="utf-8-sig")
                for path in sorted(canon_dir.rglob("*.md"))
            )[:12000],
            "blind_review": blind_review,
        }
        if self.strict_audit:
            inputs["machine_diagnostics"] = (
                self.orchestrator._machine_diagnostics(
                    book_project.run_gates(
                        self.root,
                        slug,
                        chapter,
                        expected_mode="formal",
                    )
                )
            )
        if chapter > 1:
            previous = book_project.find_chapter_file(
                book_dir,
                chapter - 1,
            ).read_text(encoding="utf-8-sig")
            inputs["previous_chapter_ending"] = previous[
                max(0, int(len(previous) * 0.8)) :
            ]
        return inputs

    def _review_action(
        self,
        slug: str,
        state: dict[str, Any],
        role: str,
    ) -> dict[str, Any]:
        prompt = render_review_instructions(
            role,
            lean=not self.strict_audit,
        ).text
        action_id = f"native-action-{uuid.uuid4().hex[:16]}"
        review_dir = self._diff_dir(
            slug, int(state["chapter"])
        ) / f"{role}-input"
        if not self.strict_audit:
            self._reset_transient_dir(review_dir)
        descriptor = prepare_review_capsule(
            self.orchestrator.capsule_root,
            slug,
            role,
            instructions=prompt,
            inputs=self._review_inputs(slug, state, role),
            body_sha256=str(state["body_sha256"]),
            capsule_dir=None if self.strict_audit else review_dir,
        )
        state["review_capsule"] = descriptor
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": action_id,
            "kind": "run_role",
            "role": role,
            "session": {
                "mode": "new",
                "must_be_independent": True,
            },
            "reasoning_effort": "medium",
            "review_capsule": descriptor,
            "task": (
                "Read only the sealed review capsule and return the "
                "structured role result through the official terminal."
            ),
            "result": {
                **_result_contract(role),
                "review_capsule_id_required": True,
            },
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        if not self.strict_audit:
            action["control_run_id"] = self._control_session(
                role,
                int(state["chapter"]),
            ).session_id
            action["session"]["must_be_independent"] = False
        return action

    def _verify_current_review_capsule(
        self,
        state: dict[str, Any],
        completion: dict[str, Any],
        role: str,
    ) -> None:
        descriptor = state.get("review_capsule")
        if not isinstance(descriptor, dict):
            raise NativeWorkspaceMutationError(
                "missing_review_capsule"
            )
        if completion.get("review_capsule_id") != descriptor.get("id"):
            raise NativeCompletionRepairError(
                "review_capsule_id_mismatch"
            )
        try:
            verify_review_capsule(
                descriptor,
                expected_role=role,
                expected_body_sha256=str(state["body_sha256"]),
                require_machine_diagnostics=self.strict_audit,
            )
        except ReviewCapsuleError as exc:
            raise NativeWorkspaceMutationError(
                "review_capsule_mutation"
            ) from exc

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
        self._assert_fresh_session(slug, state, session)
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
            **({"stage": "draft"} if not self.strict_audit else {}),
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
                "assurance_mode": (
                    "formal_native"
                    if self.strict_audit
                    else "lean_native"
                ),
                "reported_by": (
                    "native_host"
                    if self.strict_audit
                    else "deterministic_control_plane"
                ),
                "filesystem_scope": (
                    "guarded_native"
                    if self.strict_audit
                    else "capsule_output"
                ),
                "write_scope": "post_execution_verified",
                "repository_snapshot_enforced": self.strict_audit,
            },
            "result": {
                **_result_contract("writer"),
                "runtime_snapshot_required": self.strict_audit,
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
        _, retries = self._next_retry_count(state)
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
            state["decision_kind"] = "native_role_failed"
            state["failed_phase"] = phase
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
            role = (
                "blind-reader"
                if phase == "awaiting_blind_reader"
                else "chapter-editor"
            )
            action = self._review_action(slug, state, role)
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
        if not self.strict_audit and sequence_id:
            self._prepare_lean_writer_action(
                slug,
                state,
                request=request,
                chapter=chapter,
                sequence_id=sequence_id,
                must_findings=tuple(
                    str(item) for item in state.get("must_findings", [])
                ),
                parent_generation_id=state.get("parent_generation_id"),
                reuse_preferred=bool(state.get("must_findings")),
            )
            return WorkflowResult(
                user_state="running",
                message="写作会话异常，已自动换新会话重试。",
                sequence_id=sequence_id,
                technical_retry_count=retries,
            )
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

    @staticmethod
    def _capsule_surface_findings(
        prepared: dict[str, Any],
    ) -> tuple[str, ...]:
        capsule_dir = Path(str(prepared.get("capsule_dir") or ""))
        draft_output = str(
            prepared.get("draft_output") or "draft/正文.md"
        )
        draft_path = capsule_dir / draft_output
        return tuple(
            (
                f"{finding.rule_code}（第 {finding.line_number} 行）："
                f"{finding.message}；原文：{finding.evidence}"
            )
            for finding in lint_file(draft_path)
            if finding.severity == "blocking"
        )

    def _request_surface_patch(
        self,
        slug: str,
        state: dict[str, Any],
        findings: tuple[str, ...],
    ) -> WorkflowResult:
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        request = self._request_from_state(state)
        round_number = int(state.get("surface_patch_round") or 0)
        if round_number >= MAX_LEAN_SURFACE_PATCH_ROUNDS:
            state.update(
                {
                    "phase": "decision_required",
                    "decision_kind": "surface_revision_required",
                    "surface_findings": list(findings),
                }
            )
            _atomic_json(self._state_path(slug), state)
            self._action_path(slug).unlink(missing_ok=True)
            return self.orchestrator._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="表面规则修订后仍有问题，请选择下一步。",
                retries=int(state.get("technical_retry_count") or 0),
                decision_kind="surface_revision_required",
                must_findings=findings,
                resume_context={
                    "capsule_path": str(
                        (state.get("capsule") or {}).get("capsule_dir")
                        or ""
                    ),
                },
            )
        action = self.next_action(slug)
        action.update(
            {
                "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
                "stage": "patch",
                "session": {
                    "mode": "reuse_preferred",
                    "must_be_independent": False,
                },
                "must_findings": list(findings),
                "surface_patch": True,
            }
        )
        action.pop("completion_repair", None)
        state["surface_patch_round"] = round_number + 1
        state["surface_findings"] = list(findings)
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="patching",
            retries=int(state.get("technical_retry_count") or 0),
            must_findings=findings,
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="发现问题，正在自动修订。",
            sequence_id=sequence_id,
            technical_retry_count=int(
                state.get("technical_retry_count") or 0
            ),
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
            raise NativeCompletionRepairError(
                "writer_artifact_path_invalid"
            )
        runtime_snapshot = completion.get("runtime_snapshot")
        if not isinstance(runtime_snapshot, dict) and self.strict_audit:
            raise NativeCompletionRepairError(
                "missing_runtime_snapshot"
            )
        prepared = state.get("capsule")
        if not isinstance(prepared, dict):
            raise WorkflowError("Writer 动作缺少 Capsule 绑定。")
        if not self.strict_audit:
            surface_findings = self._capsule_surface_findings(prepared)
            if surface_findings:
                return self._request_surface_patch(
                    slug,
                    state,
                    surface_findings,
                )
            self._freeze_initial_draft(state)
            staged_body = self._staged_body_path(state)
            body_sha256 = hashlib.sha256(staged_body.read_bytes()).hexdigest()
            if not isinstance(runtime_snapshot, dict):
                runtime_snapshot = self._lean_runtime_snapshot(
                    session,
                    str(prepared.get("capsule_id") or ""),
                )
            state.update(
                {
                    "phase": "awaiting_blind_reader",
                    "writer_session": asdict(session),
                    "body_sha256": body_sha256,
                    "pending_runtime_snapshot": runtime_snapshot,
                    "pending_writer_terminal": terminal,
                    "review_session_ids": [],
                    "review_session_instance_ids": [],
                }
            )
            self._remember_session(
                state,
                session,
                role="writer",
                status="completed",
            )
            self._reset_active_retry(state, "blind-reader")
            state.pop("blind_outcome", None)
            state.pop("blind_session", None)
            state.pop("editor_outcome", None)
            state.pop("editor_session", None)
            state.pop("surface_findings", None)
            action = self._review_action(slug, state, "blind-reader")
            request = self._request_from_state(state)
            self.orchestrator._save_control(
                slug,
                request=request,
                chapter=int(state["chapter"]),
                sequence_id=str(state["sequence_id"]),
                phase="reviewing",
                retries=0,
            )
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="正在自动审稿。",
                sequence_id=str(state["sequence_id"]),
            )
        state.pop("surface_findings", None)
        capsule_id = str(prepared.get("capsule_id") or "")
        runtime_path = (
            self.orchestrator.capsule_root
            / "native-relay-runtime"
            / slug
            / f"{capsule_id}.json"
        )
        if not isinstance(runtime_snapshot, dict):
            runtime_snapshot = self._lean_runtime_snapshot(
                session,
                capsule_id,
            )
        _atomic_json(runtime_path, runtime_snapshot)
        try:
            record_capsule_runtime(
                self.root,
                slug,
                capsule_id,
                runtime_path,
                require_complete_budget=self.strict_audit,
            )
        except GuardianError as exc:
            raise NativeCompletionRepairError(
                "invalid_runtime_snapshot"
            ) from exc
        imported = ingest_writer_capsule(
            self.root,
            slug,
            capsule_id,
        )
        report = audit_session_log(runtime_path)
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
            assurance_mode=self.assurance_mode,
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
        state.update(
            {
                "phase": "awaiting_blind_reader",
                "writer_session": asdict(session),
                "generation_id": generation_id,
                "body_sha256": imported["body_sha256"],
                "review_session_ids": [],
                "review_session_instance_ids": [],
            }
        )
        self._remember_session(
            state,
            session,
            role="writer",
            status="completed",
        )
        self._reset_active_retry(state, "blind-reader")
        state.pop("blind_outcome", None)
        action = self._review_action(slug, state, "blind-reader")
        request = self._request_from_state(state)
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="reviewing",
            retries=0,
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="正在自动审稿。",
            sequence_id=sequence_id,
        )

    def _promote_staged_writer(
        self,
        slug: str,
        state: dict[str, Any],
    ) -> SessionIdentity:
        prepared = state.get("capsule")
        writer_payload = state.get("writer_session")
        runtime_snapshot = state.get("pending_runtime_snapshot")
        terminal = state.get("pending_writer_terminal")
        if not isinstance(prepared, dict):
            raise WorkflowError("当前章节缺少临时正文绑定。")
        if not isinstance(writer_payload, dict):
            raise WorkflowError("当前章节缺少 Writer 会话绑定。")
        if not isinstance(runtime_snapshot, dict):
            raise WorkflowError("当前章节缺少 Writer 运行记录。")
        if not isinstance(terminal, dict):
            raise WorkflowError("当前章节缺少 Writer 完成记录。")
        session = SessionIdentity(**writer_payload)
        capsule_id = str(prepared.get("capsule_id") or "")
        runtime_path = (
            self._relay_dir(slug)
            / "runtime"
            / f"{capsule_id}.json"
        )
        _atomic_json(runtime_path, runtime_snapshot)
        try:
            record_capsule_runtime(
                self.root,
                slug,
                capsule_id,
                runtime_path,
                require_complete_budget=False,
            )
        except GuardianError as exc:
            raise NativeCompletionRepairError(
                "invalid_runtime_snapshot"
            ) from exc
        imported = ingest_writer_capsule(self.root, slug, capsule_id)
        report = audit_session_log(runtime_path)
        chapter = int(state["chapter"])
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
            is_patch=bool(state.get("patch_round")),
            assurance_mode=self.assurance_mode,
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
            context_scope="book_diff_workspace",
            operation_kind=str(terminal["kind"]),
            operation_id=str(terminal["value"]),
            result_transport=str(terminal["result_transport"]),
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
        state["generation_id"] = generation_id
        state["body_sha256"] = imported["body_sha256"]
        state.pop("pending_runtime_snapshot", None)
        state.pop("pending_writer_terminal", None)
        self._write_staged_diff(state)
        return session

    @staticmethod
    def _result_text(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            return "\n".join(
                text
                for item in value
                if (text := NativeWorkflowRelay._result_text(item))
            )
        if isinstance(value, dict):
            return "\n".join(
                f"{name}: {text}"
                for name, item in value.items()
                if (text := NativeWorkflowRelay._result_text(item))
            )
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _normalized_findings(
        payload: dict[str, Any],
    ) -> tuple[ReviewFinding, ...]:
        def items(value: Any) -> tuple[Any, ...]:
            if value is None:
                return ()
            if isinstance(value, (list, tuple)):
                return tuple(value)
            return (value,)

        entries: list[tuple[str, Any]] = []
        raw = payload.get("findings")
        if isinstance(raw, dict):
            entries.extend(("MUST", item) for item in items(raw.get("must")))
            entries.extend(("MAY", item) for item in items(raw.get("may")))
        elif isinstance(raw, (list, tuple)):
            default = (
                "MAY"
                if str(payload.get("verdict") or "")
                in {"pass", "ready_for_editor_decision"}
                else "MUST"
            )
            entries.extend((default, item) for item in raw)
        entries.extend(("MUST", item) for item in items(payload.get("must")))
        entries.extend(("MAY", item) for item in items(payload.get("may")))
        findings: list[ReviewFinding] = []
        for default_severity, item in entries:
            if isinstance(item, dict):
                note = NativeWorkflowRelay._result_text(
                    item.get("revision_intent")
                    or item.get("note")
                    or item.get("message")
                    or item.get("reader_effect")
                )
                findings.append(
                    ReviewFinding(
                        severity=str(
                            item.get("severity") or default_severity
                        ).upper(),
                        location=NativeWorkflowRelay._result_text(
                            item.get("location") or "全文"
                        ),
                        evidence=NativeWorkflowRelay._result_text(
                            item.get("evidence") or ""
                        ),
                        reader_effect=NativeWorkflowRelay._result_text(
                            item.get("reader_effect") or note
                        ),
                        revision_intent=note,
                        status=str(item.get("status") or "open"),
                    )
                )
            else:
                note = NativeWorkflowRelay._result_text(item)
                if note:
                    findings.append(
                        ReviewFinding(
                            severity=default_severity,
                            location="全文",
                            evidence="",
                            reader_effect=note,
                            revision_intent=note,
                            status="open",
                        )
                    )
        return tuple(findings)

    @staticmethod
    def _review_outcome(
        payload: dict[str, Any],
        *,
        role: str,
        session: SessionIdentity,
        terminal: dict[str, str],
        strict_audit: bool = False,
    ) -> ReviewOutcome:
        findings = NativeWorkflowRelay._normalized_findings(payload)
        raw_analysis = payload.get("analysis", {})
        analysis = (
            {
                str(name): NativeWorkflowRelay._result_text(value)
                for name, value in raw_analysis.items()
            }
            if isinstance(raw_analysis, dict)
            else {}
        )
        summary = NativeWorkflowRelay._result_text(
            payload.get("summary") or raw_analysis
        )
        if summary:
            for name in REVIEW_ANALYSIS_FIELDS[role]:
                analysis.setdefault(name, summary)
        coverage_payload = (
            payload.get("hard_anchor_coverage", {}) if strict_audit else {}
        )
        if coverage_payload is None:
            coverage_payload = {}
        if not isinstance(coverage_payload, dict):
            raise WorkflowError(f"{role} hard_anchor_coverage 格式无效。")
        hard_anchor_coverage: dict[str, dict[str, str]] = {}
        for name, item in coverage_payload.items():
            if not isinstance(name, str) or not isinstance(item, dict):
                raise WorkflowError(
                    f"{role} hard_anchor_coverage 字段无效。"
                )
            if not all(
                isinstance(field_name, str)
                and isinstance(field_value, str)
                for field_name, field_value in item.items()
            ):
                raise WorkflowError(
                    f"{role} hard_anchor_coverage 字段无效。"
                )
            hard_anchor_coverage[name] = dict(item)
        verdict = str(payload.get("verdict") or "").strip()
        if role == "chapter-editor" and verdict == "pass":
            verdict = "ready_for_editor_decision"
        return ReviewOutcome(
            verdict=verdict,
            findings=findings,
            human_likeness=str(
                payload.get("human_likeness") or "not_applicable"
            ),
            reader_desire=str(
                payload.get("reader_desire") or "not_applicable"
            ),
            emotional_residue=NativeWorkflowRelay._result_text(
                payload.get("emotional_residue") or "not_applicable"
            ),
            next_chapter_pull=NativeWorkflowRelay._result_text(
                payload.get("next_chapter_pull") or "not_applicable"
            ),
            analysis=dict(analysis),
            hard_anchor_coverage=hard_anchor_coverage,
            evidence_quote=(
                NativeWorkflowRelay._result_text(
                    payload.get("evidence_quote", [""])[0]
                )
                if isinstance(payload.get("evidence_quote"), list)
                else NativeWorkflowRelay._result_text(
                    payload.get("evidence_quote") or ""
                )
            ),
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
            require_hard_anchor_coverage=self.strict_audit,
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

    @staticmethod
    def _stored_outcome(payload: dict[str, Any]) -> ReviewOutcome:
        values = dict(payload)
        values["findings"] = tuple(
            ReviewFinding(**item)
            for item in payload.get("findings", [])
            if isinstance(item, dict)
        )
        return ReviewOutcome(**values)

    def _combined_must_findings(
        self,
        blind: ReviewOutcome,
        editor: ReviewOutcome,
    ) -> tuple[str, ...]:
        must = [
            self.orchestrator._patch_directive(item)
            for item in (*blind.findings, *editor.findings)
            if item.severity.upper() == "MUST"
            and item.status.lower() == "open"
        ]
        if blind.verdict != "pass" and not must:
            must.append("Blind Reader 判定需要修订，请按其审稿总结处理。")
        if editor.verdict != "ready_for_editor_decision" and not must:
            must.append("Chapter Editor 判定需要修订，请按其审稿总结处理。")
        return tuple(dict.fromkeys(must))

    def _request_staged_literary_patch(
        self,
        slug: str,
        state: dict[str, Any],
        must: tuple[str, ...],
    ) -> WorkflowResult:
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        request = self._request_from_state(state)
        prepared = state.get("capsule")
        writer = state.get("writer_session")
        if not isinstance(prepared, dict) or not isinstance(writer, dict):
            raise WorkflowError("临时正文缺少 Writer 绑定。")
        revision_path = self._diff_dir(slug, chapter) / "修订要求.md"
        revision_path.write_text(
            "# 修订要求\n\n" + "\n".join(f"- {item}" for item in must) + "\n",
            encoding="utf-8",
        )
        draft_path = self._staged_body_path(state)
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
            "kind": "run_role",
            "role": "writer",
            "stage": "patch",
            "control_run_id": str(writer["session_id"]),
            "session": {
                "mode": "reuse_preferred",
                "must_be_independent": False,
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
            "revision_file": str(revision_path),
            "must_findings": list(must),
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [
                draft_path.relative_to(
                    self._integrity_root(slug)
                ).as_posix()
            ],
        }
        state.update(
            {
                "phase": "awaiting_writer",
                "must_findings": list(must),
                "patch_round": 1,
            }
        )
        state.pop("blind_outcome", None)
        state.pop("blind_session", None)
        self._reset_active_retry(state, "patch-writer")
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="patching",
            retries=0,
            must_findings=must,
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="发现问题，正在自动修订。",
            sequence_id=sequence_id,
        )

    def _complete_staged_review(
        self,
        slug: str,
        state: dict[str, Any],
        role: str,
        session: SessionIdentity,
        outcome: ReviewOutcome,
    ) -> WorkflowResult:
        state.setdefault("review_session_ids", []).append(session.session_id)
        state.setdefault("review_session_instance_ids", []).append(
            session.session_instance_id
        )
        self._remember_session(
            state,
            session,
            role=role,
            status="completed",
        )
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        request = self._request_from_state(state)
        if role == "blind-reader":
            state.update(
                {
                    "phase": "awaiting_chapter_editor",
                    "blind_outcome": asdict(outcome),
                    "blind_session": asdict(session),
                }
            )
            self._reset_active_retry(state, "chapter-editor")
            action = self._review_action(slug, state, "chapter-editor")
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="正在自动审稿。",
                sequence_id=sequence_id,
            )

        blind_payload = state.get("blind_outcome")
        blind_session_payload = state.get("blind_session")
        if not isinstance(blind_payload, dict) or not isinstance(
            blind_session_payload, dict
        ):
            raise WorkflowError("Chapter Editor 前缺少 Blind Reader 结果。")
        blind = self._stored_outcome(blind_payload)
        must = self._combined_must_findings(blind, outcome)
        if must:
            if int(state.get("patch_round") or 0) >= 1:
                result = self.orchestrator._decision_result(
                    slug,
                    request,
                    chapter,
                    sequence_id,
                    message="自动修订后仍有问题，请选择下一步。",
                    retries=int(state.get("technical_retry_count") or 0),
                    decision_kind="literary_revision_required",
                    must_findings=must,
                    parent_generation_id=None,
                )
                state["phase"] = "decision_required"
                state["decision_kind"] = "literary_revision_required"
                state["must_findings"] = list(must)
                _atomic_json(self._state_path(slug), state)
                self._action_path(slug).unlink(missing_ok=True)
                return result
            return self._request_staged_literary_patch(slug, state, must)

        self._promote_staged_writer(slug, state)
        blind_session = SessionIdentity(**blind_session_payload)
        self._record_native_review(
            slug,
            state,
            "blind-reader",
            blind_session,
            blind,
        )
        self._record_native_review(
            slug,
            state,
            "chapter-editor",
            session,
            outcome,
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
        writer_payload = state.get("writer_session")
        if not isinstance(writer_payload, dict):
            raise WorkflowError("当前章节缺少 Writer 会话绑定。")
        result = self.orchestrator._finish_chapter(
            slug,
            request,
            chapter,
            sequence_id,
            SessionIdentity(**writer_payload),
            int(
                (
                    state.get("technical_retry_counts")
                    if isinstance(state.get("technical_retry_counts"), dict)
                    else {}
                ).get("chapter-editor")
                or 0
            ),
        )
        state["phase"] = (
            "complete"
            if result.user_state == "chapter_complete"
            else "decision_required"
        )
        _atomic_json(self._state_path(slug), state)
        self._action_path(slug).unlink(missing_ok=True)
        return result

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
        self._verify_current_review_capsule(
            state,
            completion,
            role,
        )
        session, role_result, terminal = self._validate_completion(
            state,
            completion,
            role=role,
        )
        self._assert_fresh_session(slug, state, session)
        payload = role_result.get("payload")
        if not isinstance(payload, dict):
            raise WorkflowError(f"{role} 结果 payload 无效。")
        outcome = self._review_outcome(
            payload,
            role=role,
            session=session,
            terminal=terminal,
            strict_audit=self.strict_audit,
        )
        if not self.strict_audit:
            return self._complete_staged_review(
                slug,
                state,
                role,
                session,
                outcome,
            )
        self._record_native_review(
            slug,
            state,
            role,
            session,
            outcome,
        )
        state.setdefault("review_session_ids", []).append(
            session.session_id
        )
        state.setdefault("review_session_instance_ids", []).append(
            session.session_instance_id
        )
        self._remember_session(
            state,
            session,
            role=role,
            status="completed",
        )
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        request = self._request_from_state(state)
        if role == "blind-reader":
            state.update(
                {
                    "phase": "awaiting_chapter_editor",
                    "blind_outcome": asdict(outcome),
                }
            )
            self._reset_active_retry(state, "chapter-editor")
            action = self._review_action(
                slug,
                state,
                "chapter-editor",
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
                state["decision_kind"] = (
                    "literary_revision_required"
                )
                state["must_findings"] = list(must)
                _atomic_json(self._state_path(slug), state)
                self._action_path(slug).unlink(missing_ok=True)
                return result
            if not self.strict_audit:
                state.update(
                    {
                        "must_findings": list(must),
                        "parent_generation_id": state["generation_id"],
                        "patch_round": 1,
                    }
                )
                self._reset_active_retry(state, "patch-writer")
                self._prepare_lean_writer_action(
                    slug,
                    state,
                    request=request,
                    chapter=chapter,
                    sequence_id=sequence_id,
                    must_findings=must,
                    parent_generation_id=str(state["generation_id"]),
                    reuse_preferred=True,
                )
                return WorkflowResult(
                    user_state="running",
                    message="发现问题，正在自动修订。",
                    sequence_id=sequence_id,
                )
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
            self._reset_active_retry(state, "patch-writer")
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
            int(
                (
                    state.get("technical_retry_counts")
                    if isinstance(
                        state.get("technical_retry_counts"),
                        dict,
                    )
                    else {}
                ).get("chapter-editor")
                or 0
            ),
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
        self._assert_fresh_session(slug, state, session)
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
