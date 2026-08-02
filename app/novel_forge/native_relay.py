"""Persistent pull protocol for visible host-native creative sessions."""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import tempfile
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from . import book_project
from .artifact_integrity import record_session_completion
from .chapter_sequence import (
    begin_chapter_sequence,
    chapter_sequence_status,
    claim_chapter_session,
    rotate_chapter_session,
)
from .lint import lint_file
from .models import NovelForgeError
from .guardian import (
    GuardianError,
    authorize_regeneration,
    capsule_status,
    ingest_writer_capsule,
    prepare_writer_capsule,
    record_capsule_runtime,
    reject_writer_capsule,
)
from .review_prompt import (
    render_planning_instructions,
    render_review_instructions,
)
from .literary_texture import analyze_literary_texture
from .review_capsule import (
    ReviewCapsuleError,
    prepare_review_capsule,
    verify_review_capsule,
)
from .session_audit import audit_session_log
from .workspace_integrity import (
    create_workspace_backup,
    create_workspace_backup_from_snapshot,
    remove_created_paths,
    restore_workspace_paths,
    snapshot_workspace,
    snapshot_workspace_paths,
    workspace_delta,
)
from .workflow_observability import (
    record_call_observation,
    sanitize_call_telemetry,
)
from .workflow_iteration import (
    apply_local_replacements,
    evaluate_budget_breaker,
    evaluate_writer_model,
    plan_local_patch,
    require_high_risk_confirmation,
    display_workflow_state,
)
from .workflow import (
    NovelWorkflowOrchestrator,
    PlanningOutcome,
    REVISION_DECISION_KINDS,
    REVIEW_ANALYSIS_FIELDS,
    ReviewFinding,
    ReviewOutcome,
    SessionIdentity,
    WorkflowError,
    WorkflowRequest,
    WorkflowResult,
    _atomic_json,
    _decision_options,
    _quote_matches,
)


NATIVE_ACTION_SCHEMA = "novel-forge-native-action/v1"
NATIVE_COMPLETION_SCHEMA = "novel-forge-native-completion/v1"
NATIVE_RELAY_SCHEMA = "novel-forge-native-relay/v1"
MAX_LEAN_SURFACE_PATCH_ROUNDS = 3


def _chapter_target_path(chapter: int) -> str:
    """Return the canonical final-prose path for one chapter."""
    return f"chapters/e{chapter:02d}/ch-{chapter:02d}/正文.md"


LEAN_PROTECTED_CONTROL_PLANE_PATHS = (
    "app",
    "tools",
    "tests",
    ".agents/skills/novel-forge",
    ".claude/skills/novel-forge",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "requirements.txt",
    "run_novel_test.py",
)


class NativeWorkspaceMutationError(WorkflowError):
    """Raised after restoring one creative role's project mutation."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        message = "创作角色修改了项目控制面。"
        if detail:
            message += detail
        super().__init__(message)


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

    @staticmethod
    def _lean_protected_control_plane_paths(slug: str) -> tuple[str, ...]:
        return LEAN_PROTECTED_CONTROL_PLANE_PATHS + (
            f".local-guardian/{slug}",
            f".local-book-git/{slug}.git",
        )

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
    def _cjk_char_count(text: str) -> int:
        """Count CJK code points for a prose observation summary."""
        return sum(
            1
            for char in text
            if "\u3400" <= char <= "\u4dbf"
            or "\u4e00" <= char <= "\u9fff"
            or "\uf900" <= char <= "\ufaff"
        )

    def _body_observation_summary(
        self,
        slug: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Return a content-free digest summary of the current staged prose."""
        candidates: list[Path] = []
        prepared = state.get("capsule")
        if isinstance(prepared, Mapping):
            capsule_dir = str(prepared.get("capsule_dir") or "").strip()
            if capsule_dir:
                candidates.append(
                    Path(capsule_dir)
                    / str(prepared.get("draft_output") or "draft/正文.md")
                )
        chapter = state.get("chapter")
        if isinstance(chapter, int) and not isinstance(chapter, bool):
            candidates.append(
                self.root / "books" / slug / _chapter_target_path(chapter)
            )
        for candidate in candidates:
            try:
                content = candidate.read_bytes()
                text = content.decode("utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            texture = analyze_literary_texture(text)
            return {
                "sha256": hashlib.sha256(content).hexdigest(),
                "cjk_chars": self._cjk_char_count(text),
                "literary_texture_risk": str(
                    texture.get("risk_level") or "unknown"
                ),
            }
        return None

    def _call_observation_context(
        self,
        slug: str,
        state: Mapping[str, Any],
        action: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Capture pre-call facts before a native role can mutate prose."""
        role = self._phase_role(dict(state))
        purpose = (
            "planning"
            if role == "writer-planning"
            else "session_setup"
            if role == "writer-session"
            else str(action.get("stage") or "draft")
            if role == "writer"
            else "review"
            if role in {"blind-reader", "chapter-editor"}
            else "other"
        )
        counts = state.get("technical_retry_counts")
        counts = counts if isinstance(counts, Mapping) else {}
        retry_bucket = self._retry_bucket(dict(state))
        return {
            "action_id": str(action["action_id"]),
            "chapter": int(state["chapter"]),
            "role": role,
            "purpose": purpose,
            "action_kind": str(action.get("kind") or "run_role"),
            "started_at": datetime.now(UTC).isoformat(),
            "technical_retry_index": int(counts.get(retry_bucket) or 0),
            "revision_round": int(state.get("patch_round") or 0),
            "body_before": self._body_observation_summary(slug, state),
        }

    @staticmethod
    def _completion_telemetry(
        completion: Mapping[str, Any],
        started_at: str,
    ) -> dict[str, Any]:
        """Read optional host telemetry and fall back to Relay wall time."""
        raw = completion.get("telemetry")
        if not isinstance(raw, Mapping):
            runtime = completion.get("runtime_snapshot")
            if isinstance(runtime, Mapping):
                usage = runtime.get("usage")
                timing = runtime.get("timing")
                usage = usage if isinstance(usage, Mapping) else {}
                timing = timing if isinstance(timing, Mapping) else {}
                raw = {
                    **{
                        field: usage.get(field)
                        for field in (
                            "input_tokens",
                            "output_tokens",
                            "cached_input_tokens",
                            "total_tokens",
                            "request_count",
                        )
                    },
                    "elapsed_seconds": timing.get("elapsed_seconds"),
                }
            else:
                raw = {}
        telemetry = sanitize_call_telemetry(raw)
        if telemetry["elapsed_seconds"] is None:
            try:
                started = datetime.fromisoformat(started_at)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                elapsed = max(
                    0.0,
                    (datetime.now(UTC) - started).total_seconds(),
                )
            except (TypeError, ValueError):
                elapsed = 0.0
            telemetry["elapsed_seconds"] = round(elapsed, 3)
            telemetry["elapsed_source"] = "relay_wall_clock"
        return telemetry

    @staticmethod
    def _completion_scope_counts(
        completion: Mapping[str, Any],
    ) -> dict[str, int]:
        """Sample review scope labels without using them for routing."""
        counts = {
            "local": 0,
            "structural": 0,
            "blocking": 0,
            "unclassified": 0,
        }
        role_result = completion.get("role_result")
        payload = (
            role_result.get("payload")
            if isinstance(role_result, Mapping)
            else None
        )
        if not isinstance(payload, dict):
            return counts
        for finding in NativeWorkflowRelay._normalized_findings(payload):
            if finding.severity.upper() != "MUST" or finding.status.lower() != "open":
                continue
            scope = (
                finding.scope
                if finding.scope in counts
                else "unclassified"
            )
            counts[scope] += 1
        return counts

    def _observe_call(
        self,
        slug: str,
        context: Mapping[str, Any] | None,
        completion: Mapping[str, Any],
        result: WorkflowResult,
        *,
        outcome: str,
        failure_reason: str | None = None,
        body_after: dict[str, Any] | None = None,
    ) -> None:
        """Persist best-effort local metrics without affecting creative work."""
        if not isinstance(context, Mapping):
            return
        try:
            fresh_state = self._load_state(slug)
            after = (
                body_after
                if body_after is not None
                else self._body_observation_summary(slug, fresh_state)
            )
            before = context.get("body_before")
            if before is None and after is None:
                changed: bool | None = None
            elif isinstance(before, Mapping) and isinstance(after, Mapping):
                changed = before.get("sha256") != after.get("sha256")
            else:
                changed = True
            effect = "none"
            if result.user_state == "chapter_complete":
                effect = "promotion"
            elif result.user_state == "decision_required":
                effect = "author_decision"
            elif (
                outcome == "completed"
                and fresh_state.get("phase") == "awaiting_writer"
                and fresh_state.get("must_findings")
            ):
                effect = "revision_requested"
            session = completion.get("session")
            session = session if isinstance(session, Mapping) else {}
            completed_at = datetime.now(UTC).isoformat()
            observation_path = (
                self.root
                / ".local-guardian"
                / slug
                / "workflow-observations"
                / f"ch{int(context['chapter']):02d}"
                / f"{context['action_id']}.json"
            )
            observation_existed = observation_path.is_file()
            record_call_observation(
                self.root,
                slug,
                {
                    **dict(context),
                    "outcome": outcome,
                    "completed_at": completed_at,
                    "provider": str(session.get("provider") or "unknown"),
                    "model": str(session.get("model") or "unknown"),
                    "telemetry": self._completion_telemetry(
                        completion,
                        str(context.get("started_at") or completed_at),
                    ),
                    "body_after": after,
                    "body_changed": changed,
                    "must_scope_counts": self._completion_scope_counts(
                        completion
                    ),
                    "workflow_effect": effect,
                    "failure_reason": failure_reason,
                },
            )
            try:
                self._refresh_active_action_integrity(slug)
            except (NovelForgeError, OSError, TypeError, ValueError):
                if not observation_existed:
                    observation_path.unlink(missing_ok=True)
                    for directory in (
                        observation_path.parent,
                        observation_path.parent.parent,
                    ):
                        try:
                            directory.rmdir()
                        except OSError:
                            pass
                raise
        except (NovelForgeError, OSError, TypeError, ValueError):
            return

    def _refresh_active_action_integrity(self, slug: str) -> None:
        """Rebase the pending action after a control-plane observation write."""
        state = self._load_state(slug)
        action_id = str(state.get("action_id") or "").strip()
        if not action_id or not self._action_path(slug).is_file():
            return
        integrity_root = self._integrity_root(slug)
        _atomic_json(
            self._snapshot_path(slug, action_id),
            snapshot_workspace(integrity_root),
        )
        create_workspace_backup(
            integrity_root,
            self._backup_path(slug, action_id),
        )
        if not self.strict_audit:
            self._write_lean_control_snapshot(slug, action_id)

    def _review_result_path(
        self,
        slug: str,
        chapter: int,
        role: str,
    ) -> Path:
        return self._diff_dir(slug, chapter) / f"{role}.json"

    def _staged_body_matches_state(self, state: dict[str, Any]) -> bool:
        if self.strict_audit or not isinstance(state.get("capsule"), dict):
            return False
        expected = str(state.get("body_sha256") or "").strip()
        if not expected:
            return False
        try:
            candidates = [self._staged_body_path(state)]
            candidates.append(
                self.root
                / "books"
                / str(state["slug"])
                / _chapter_target_path(int(state["chapter"]))
            )
            return any(
                body.is_file()
                and hashlib.sha256(body.read_bytes()).hexdigest() == expected
                for body in candidates
            )
        except (OSError, KeyError, TypeError, ValueError):
            return False

    @staticmethod
    def _reset_transient_dir(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)

    @staticmethod
    def _reset_writer_capsule_dir(path: Path) -> None:
        """Remove regenerable capsule files but never the staged prose.

        The staged draft survives every technical retry or regenerate until
        promotion: only auxiliary files (instructions, handoff, context,
        manifests) are cleared so the guardian can rebuild the capsule.
        """
        if not path.exists():
            return
        preserved = path / "draft" / "正文.md"
        for child in path.iterdir():
            if child.name == "draft":
                if not child.is_dir():
                    child.unlink()
                    continue
                for leaf in child.iterdir():
                    if leaf != preserved:
                        if leaf.is_dir():
                            shutil.rmtree(leaf)
                        else:
                            leaf.unlink()
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    FROZEN_DRAFT_FILENAME = "控制面冻结稿.md"

    def _freeze_initial_draft(self, state: dict[str, Any]) -> None:
        source = self._staged_body_path(state)
        initial = self._diff_dir(
            str(state["slug"]), int(state["chapter"])
        ) / self.FROZEN_DRAFT_FILENAME
        if not initial.exists():
            initial.write_bytes(source.read_bytes())

    def _write_staged_diff(self, state: dict[str, Any]) -> None:
        diff_dir = self._diff_dir(
            str(state["slug"]), int(state["chapter"])
        )
        initial = diff_dir / self.FROZEN_DRAFT_FILENAME
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
                fromfile=self.FROZEN_DRAFT_FILENAME,
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
        if phase == "awaiting_double_review":
            for role in state.get("pending_review_roles", []):
                if role not in state.get("completed_review_roles", []):
                    return role
            return "blind-reader"
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
        role: str | None = None,
        telemetry: Any = None,
    ) -> WorkflowResult:
        """Complete the current Lean action without a technical envelope."""
        state = self._load_state(slug)
        if self.strict_audit:
            raise WorkflowError("严格审计模式必须提交完整角色终态。")
        if state.get("phase") == "decision_required":
            raise WorkflowError(
                "当前没有可完成的角色动作；请按 status 或 next-action "
                "列出的可达命令处理（authorize-revision / continue-budget / "
                "approve-high-risk / retry / stop）。"
            )
        parallel = state.get("phase") == "awaiting_double_review"
        if parallel:
            control_ids = state.get("control_run_ids")
            resolved_role = str(role or "").strip()
            if not resolved_role and isinstance(control_ids, dict):
                for candidate_role, candidate_id in control_ids.items():
                    if str(candidate_id or "") == str(session_id or ""):
                        resolved_role = str(candidate_role)
                        break
            if not resolved_role:
                # 兼容路径：最后领取（issued 末尾）的未完成角色，其次
                # 队列头部——按领取顺序完成与任意顺序完成都能正确解析。
                completed = set(state.get("completed_review_roles", []))
                for candidate in reversed(
                    list(state.get("issued_review_roles", []))
                ):
                    if candidate not in completed:
                        resolved_role = str(candidate)
                        break
            if not resolved_role:
                for candidate in state.get("pending_review_roles", []):
                    if candidate not in state.get(
                        "completed_review_roles", []
                    ):
                        resolved_role = str(candidate)
                        break
            if not resolved_role:
                raise WorkflowError(
                    "并行双审下无法确定完成角色；请传入该角色的宿主会话 ID "
                    "或 --role blind-reader|chapter-editor。"
                )
            role = resolved_role
        else:
            role = self._phase_role(state)
        if parallel:
            # 角色卡是权威（重签/刷新都写角色卡）；主卡只用于 repair 标记。
            action = self._role_action(slug, role)
        else:
            action = self.next_action(slug)
        expected = action.get("session")
        control_run_id = str(state.get("control_run_id") or "").strip()
        if control_run_id:
            if parallel:
                role_control_id = str(
                    state.get("control_run_ids", {}).get(role) or ""
                ).strip()
                if role_control_id:
                    session_id = role_control_id
                    session_instance_id = role_control_id
            else:
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
        try:
            payload = self._result_payload(
                result_file,
                repair_common_quotes=True,
            )
        except WorkflowError:
            if not parallel:
                raise
            # 并行队列不可逆：结果缺失时重签该角色，避免卡死在
            # awaiting_double_review。
            state["failed_review_role"] = role
            _atomic_json(self._state_path(slug), state)
            return self._recover_technical_failure(
                slug,
                state,
                failure_reason="missing_or_invalid_result_file",
            )
        if role == "writer" and state.get("phase") != "awaiting_local_patch":
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
        if telemetry is not None:
            completion["telemetry"] = telemetry
        return self.complete_role(slug, completion)

    def _relay_dir(self, slug: str) -> Path:
        return self.root / ".local-guardian" / slug / "native-relay"

    def _state_path(self, slug: str) -> Path:
        return self._relay_dir(slug) / "state.json"

    def _action_path(self, slug: str) -> Path:
        return self._relay_dir(slug) / "next-action.json"

    def _role_action_path(self, slug: str, role: str) -> Path:
        return self._relay_dir(slug) / f"next-action.{role}.json"

    def _role_action(self, slug: str, role: str) -> dict[str, Any]:
        payload = json.loads(
            self._role_action_path(slug, role).read_text(encoding="utf-8")
        )
        if payload.get("schema") != NATIVE_ACTION_SCHEMA:
            raise WorkflowError("原生角色动作格式无效。")
        return payload

    def _relay_snapshot_dir(self, slug: str) -> Path:
        root_namespace = hashlib.sha256(
            str(self.root).casefold().encode("utf-8")
        ).hexdigest()[:16]
        return (
            self.orchestrator.capsule_root
            / "native-relay-snapshots"
            / root_namespace
            / slug
        )

    def _snapshot_path(self, slug: str, action_id: str) -> Path:
        return self._relay_snapshot_dir(slug) / f"{action_id}.json"

    def _backup_path(self, slug: str, action_id: str) -> Path:
        return self._relay_snapshot_dir(slug) / f"{action_id}.zip"

    def _control_snapshot_path(self, slug: str, action_id: str) -> Path:
        return self._snapshot_path(slug, action_id).with_suffix(
            ".control.json"
        )

    def _control_backup_path(self, slug: str, action_id: str) -> Path:
        return self._backup_path(slug, action_id).with_suffix(
            ".control.zip"
        )

    def _write_lean_control_snapshot(
        self,
        slug: str,
        action_id: str,
    ) -> None:
        protected_paths = self._lean_protected_control_plane_paths(slug)
        control_snapshot = snapshot_workspace_paths(
            self.root,
            protected_paths,
        )
        _atomic_json(
            self._control_snapshot_path(slug, action_id),
            control_snapshot,
        )
        create_workspace_backup_from_snapshot(
            self.root,
            self._control_backup_path(slug, action_id),
            control_snapshot,
        )

    def _result_path(self, slug: str, action_id: str) -> Path:
        root_namespace = hashlib.sha256(
            str(self.root).casefold().encode("utf-8")
        ).hexdigest()[:16]
        return (
            self.orchestrator.capsule_root
            / "native-role-results"
            / root_namespace
            / slug
            / f"{action_id}.json"
        )

    def _active_snapshot_action_id(
        self,
        slug: str,
        role: str | None = None,
    ) -> str | None:
        if role is not None:
            try:
                action = self._role_action(slug, role)
            except (OSError, ValueError, json.JSONDecodeError):
                return None
            return str(action.get("action_id") or "")
        try:
            payload = json.loads(
                self._action_path(slug).read_text(encoding="utf-8")
            )
            if payload.get("schema") == NATIVE_ACTION_SCHEMA:
                return str(payload.get("action_id") or "")
        except (OSError, json.JSONDecodeError):
            pass
        return None

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
        expected_action_id = state.get("action_id")
        if str(state.get("phase") or "") == "awaiting_double_review":
            try:
                expected_action_id = self._role_action(
                    str(state["slug"]),
                    role,
                ).get("action_id")
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        if completion.get("action_id") != expected_action_id:
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
        if str(state.get("phase") or "") == "awaiting_double_review":
            action = self._role_action(str(state["slug"]), role)
        else:
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
        *,
        write_primary: bool = True,
    ) -> None:
        action["assurance_mode"] = self.assurance_mode
        if self.strict_audit:
            action["completion_template"] = _completion_template(action)
        else:
            action.pop("completion_template", None)
            role = str(
                action.get("role") or self._phase_role(state)
            )
            action["result"] = _lean_result_contract(role)
            if state.get("phase") == "awaiting_local_patch":
                action["result"] = {
                    "schema": "novel-forge-local-patch-result/v1",
                    "required": ["replacements"],
                    "replacement_item": ["target", "replacement"],
                }
                action["delivery"] = (
                    "只委派原 Writer 输出 replacement fragments；"
                    "Lead 不改正文。完成后执行 complete-role。"
                )
            elif role in {
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
                    "Lead 禁止亲自写 result_file；必须委派独立角色。"
                    "Lead 等待角色完成后执行 complete-role；无需填写技术表单。"
                )
            else:
                action.pop("result_file", None)
                action["delivery"] = (
                    "Lead 禁止亲自写正文；必须委派 Writer 角色。"
                    "Lead 等待正文落盘后执行 complete-role；无需填写技术表单。"
                )
        active_observation = state.get("active_call_observation")
        if (
            not isinstance(active_observation, dict)
            or active_observation.get("action_id") != action["action_id"]
        ):
            state["active_call_observation"] = self._call_observation_context(
                slug,
                state,
                action,
            )
        action["display_state"] = display_workflow_state(
            str(state.get("phase") or ""),
            patch_round=int(state.get("patch_round") or 0),
        )
        if write_primary:
            state["action_id"] = action["action_id"]
        state["assurance_mode"] = self.assurance_mode
        action["issued_retry_count"] = int(
            state.get("technical_retry_count") or 0
        )
        _atomic_json(self._state_path(slug), state)
        if write_primary:
            _atomic_json(self._action_path(slug), action)
        if action.get("role") in {"blind-reader", "chapter-editor"}:
            role = str(action.get("role"))
            role_path = self._role_action_path(slug, role)
            _atomic_json(role_path, action)
            state.setdefault("role_card_sha256", {})[role] = hashlib.sha256(
                role_path.read_bytes()
            ).hexdigest()
            _atomic_json(self._state_path(slug), state)
        integrity_root = self._integrity_root(slug)
        _atomic_json(
            self._snapshot_path(slug, action["action_id"]),
            snapshot_workspace(integrity_root),
        )
        create_workspace_backup(
            integrity_root,
            self._backup_path(slug, action["action_id"]),
        )
        if not self.strict_audit:
            self._write_lean_control_snapshot(
                slug,
                str(action["action_id"]),
            )

    def _is_control_plane_self_path(self, slug: str, path: str) -> bool:
        """Paths the control plane itself rewrites while a role runs.

        The whole native-relay directory is excluded because every
        completion, decision, and card issue rewrites files inside it;
        per-role cards are instead protected by the recorded
        ``role_card_sha256`` digests checked during workspace verification,
        so tampering with an issued card is still detected.
        """
        guard_prefix = f".local-guardian/{slug}/"
        own_dirs = (
            f"{guard_prefix}authorizations",
            f"{guard_prefix}session-completions",
            f"{guard_prefix}workflow-observations",
        )
        primary_card = f"{guard_prefix}native-relay/next-action.json"
        return (
            path
            in {
                f"{guard_prefix}integrity.key",
                f"{guard_prefix}native-relay",
                *own_dirs,
            }
            or (
                path.startswith(f"{guard_prefix}native-relay/")
                and path != primary_card
            )
            or any(path.startswith(directory + "/") for directory in own_dirs)
        )

    def _verify_lean_control_plane(
        self,
        slug: str,
        action_id: str,
    ) -> bool:
        snapshot_path = self._control_snapshot_path(slug, action_id)
        backup_path = self._control_backup_path(slug, action_id)
        if not snapshot_path.is_file():
            return False
        try:
            before = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowError("原生角色控制面快照损坏。") from exc
        if not isinstance(before, dict):
            raise WorkflowError("原生角色控制面快照格式无效。")
        before = {
            path: digest
            for path, digest in before.items()
            if not self._is_control_plane_self_path(slug, path)
        }
        protected_paths = self._lean_protected_control_plane_paths(slug)
        after = {
            path: digest
            for path, digest in snapshot_workspace_paths(
                self.root,
                protected_paths,
            ).items()
            if not self._is_control_plane_self_path(slug, path)
        }
        delta = workspace_delta(before, after)
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
                {
                    path: digest
                    for path, digest in snapshot_workspace_paths(
                        self.root,
                        protected_paths,
                    ).items()
                    if not self._is_control_plane_self_path(slug, path)
                },
            )
            snapshot_path.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)
            if restored.changed:
                raise WorkflowError("项目控制面自动恢复失败。")
            return True
        snapshot_path.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)
        return False

    def _verify_workspace(
        self,
        slug: str,
        action_id: str,
        role: str | None = None,
    ) -> None:
        control_plane_mutated = False
        if not self.strict_audit:
            control_plane_mutated = self._verify_lean_control_plane(
                slug,
                action_id,
            )
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
            action_path = (
                self._role_action_path(slug, role)
                if role is not None
                else self._action_path(slug)
            )
            action = json.loads(action_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowError("原生角色动作记录损坏。") from exc
        if role is not None:
            recorded = self._load_state(slug).get("role_card_sha256", {})
            expected = recorded.get(role)
            if expected:
                try:
                    current = hashlib.sha256(
                        action_path.read_bytes()
                    ).hexdigest()
                except OSError:
                    current = ""
                if current != expected:
                    raise NativeWorkspaceMutationError(
                        "control_plane_mutation",
                        detail=" 角色动作卡已被篡改；请重签该角色。",
                    )
        current_state = self._load_state(slug)
        forged_action_id = str(current_state.get("action_id") or "")
        if role is None and forged_action_id and forged_action_id != action.get(
            "action_id"
        ):
            # 串行流程中 state 的 action_id 必须等于当前主卡；不一致视为
            # 状态篡改，恢复动作 ID 与签发时的重试计数。并行双审下
            # state["action_id"] 记录主卡而校验按角色卡进行，跳过。
            current_state["action_id"] = action.get("action_id")
            issued_retries = action.get("issued_retry_count")
            if isinstance(issued_retries, int):
                current_state["technical_retry_count"] = issued_retries
            _atomic_json(self._state_path(slug), current_state)
            raise NativeWorkspaceMutationError(
                "control_plane_mutation",
                detail=" 状态中的动作 ID 被篡改，已恢复为签发值。",
            )
        allowed = {
            str(path)
            for path in action.get("allowed_project_writes", [])
            if isinstance(path, str)
        }
        control_plane_managed = {
            str(path)
            for path in action.get("control_plane_managed_paths", [])
            if isinstance(path, str)
        }
        permitted_delta = allowed | control_plane_managed
        if role is not None:
            # 并行双审：其他审稿角色的 result 文件与其 review capsule
            # 管理路径（可能因该角色技术重签而被控制面重建）都是合法变化。
            for other_role in ("blind-reader", "chapter-editor"):
                if other_role == role:
                    continue
                try:
                    other = self._role_action(slug, other_role)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                permitted_delta |= {
                    str(path)
                    for path in other.get("allowed_project_writes", [])
                    if isinstance(path, str)
                }
                permitted_delta |= {
                    str(path)
                    for path in other.get(
                        "control_plane_managed_paths", []
                    )
                    if isinstance(path, str)
                }
        unexpected_created = tuple(
            path for path in delta.created if path not in permitted_delta
        )
        unexpected_modified = tuple(
            path for path in delta.modified if path not in permitted_delta
        )
        unexpected_deleted = tuple(
            path for path in delta.deleted if path not in permitted_delta
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
                tuple(
                    path
                    for path in restored.created
                    if path not in permitted_delta
                )
                + tuple(
                    path
                    for path in restored.modified
                    if path not in permitted_delta
                )
                + tuple(
                    path
                    for path in restored.deleted
                    if path not in permitted_delta
                )
            )
            if restored_unexpected:
                raise WorkflowError("项目控制面自动恢复失败。")
            snapshot_path.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)
            reason = "control_plane_mutation" if (
                control_plane_mutated
                or unexpected_modified
                or unexpected_deleted
            ) else "unexpected_project_artifact"
            raise NativeWorkspaceMutationError(
                reason,
                detail=self._workspace_mutation_detail(allowed, action),
            )
        snapshot_path.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)
        if control_plane_mutated:
            raise NativeWorkspaceMutationError(
                "control_plane_mutation",
                detail=self._workspace_mutation_detail(allowed, action),
            )

    @staticmethod
    def _workspace_mutation_detail(
        allowed: set[str],
        action: dict[str, Any],
    ) -> str:
        """Return the allowed-write hint for a control-plane mutation failure."""
        permitted = "，".join(sorted(allowed)) if allowed else "无"
        capsule = action.get("capsule")
        target = "writer/draft/正文.md"
        if isinstance(capsule, dict):
            target = str(
                capsule.get("output") or target
            )
        return (
            f" 唯一允许写入：{permitted}；"
            f"请只写动作卡指定的 {target}。"
        )

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
        self._reset_writer_capsule_dir(capsule_dir)
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
                require_body_history=self.strict_audit,
            )
            authorization_id = authorization["authorization_id"]
        prepared = prepare_writer_capsule(
            self.root,
            slug,
            sequence_id,
            session.session_id,
            capsule_dir,
            _chapter_target_path(chapter),
            regeneration_authorization_id=authorization_id,
            patch_directive=(
                "\n".join(f"- {item}" for item in must_findings)
                if must_findings
                else None
            ),
            writer_context_mode=request.writer_context_mode,
            volume=request.volume,
        )
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
            "kind": "run_role",
            "role": "writer",
            "stage": "patch" if must_findings else "draft",
            "session": {
                "mode": (
                    "reuse_preferred" if reuse_preferred else "new"
                ),
                "must_be_independent": (
                    request.host_capability != "exploration"
                ),
                "requested_model": (
                    request.writer_model
                    if request.writer_model != "unknown"
                    else None
                ),
            },
            "host_capability": request.host_capability,
            "formal_ready_allowed": (
                request.host_capability != "exploration"
            ),
            "dispatcher": "python_or_host_adapter",
            "lead_involved": False,
            "lead_must_delegate": True,
            "lead_may_write_role_output": False,
            "reasoning_effort": "medium",
            "capsule": {
                "id": prepared["capsule_id"],
                "path": prepared["capsule_dir"],
                "operation": prepared["operation"],
                "instructions": "instructions.md",
                "handoff": "handoff.md",
                "context": "writer-context.md",
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
            "read_only_project_files": [
                (
                    self._diff_dir(slug, chapter)
                    / self.FROZEN_DRAFT_FILENAME
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
                "control_run_id": session.session_id,
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
        model_policy = evaluate_writer_model(
            self.root,
            slug,
            volume=request.volume,
            model=request.writer_model,
        )
        if model_policy["status"] == "calibration_required":
            state = {
                "schema": NATIVE_RELAY_SCHEMA,
                "slug": slug,
                "chapter": chapter,
                "request": asdict(request),
                "phase": "decision_required",
                "decision_kind": "writer_model_calibration_required",
                "writer_model_policy": model_policy,
                "author_approval": False,
                "publication_eligibility": False,
            }
            _atomic_json(self._state_path(slug), state)
            self._action_path(slug).unlink(missing_ok=True)
            return WorkflowResult(
                user_state="decision_required",
                message="Writer 模型发生变化，请先完成作者小样校准。",
                sequence_id="",
                options=("批准校准后重新 start", "保持原 Writer 模型", "停止"),
            )
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
                (
                    "exploration"
                    if request.host_capability == "exploration"
                    else "formal"
                ),
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
                "host_capability": request.host_capability,
                "formal_ready_allowed": (
                    request.host_capability != "exploration"
                ),
                "chapter_risk": request.chapter_risk,
                "known_total_tokens": 0,
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
        """Return the current bounded host action or the next chapter handoff."""
        path = self._action_path(slug)
        state = self._load_state(slug)
        if state.get("phase") == "awaiting_double_review":
            repair_role = self._phase_role(state)
            for card_path in (
                path,
                self._role_action_path(slug, repair_role),
            ):
                try:
                    card = json.loads(card_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if (
                    isinstance(card, dict)
                    and card.get("completion_repair")
                ):
                    return card
            pending = list(state.get("pending_review_roles", []))
            completed = set(state.get("completed_review_roles", []))
            issued = list(state.get("issued_review_roles", []))
            for role in pending:
                if role not in completed and role not in issued:
                    action = self._role_action(slug, role)
                    state["issued_review_roles"] = issued + [role]
                    _atomic_json(self._state_path(slug), state)
                    return action
            raise WorkflowError(
                "双审角色卡均已签发，等待角色完成后执行 complete-role。"
            )
        if not path.is_file():
            if state.get("phase") == "complete":
                next_chapter = int(state.get("chapter") or 0) + 1
                return {
                    "schema": NATIVE_ACTION_SCHEMA,
                    "kind": "start_next_chapter",
                    "chapter": next_chapter,
                    "task": (
                        f"第{next_chapter - 1:02d}章已完成。"
                        f"执行 start {slug} --chapter {next_chapter} 开始下一章。"
                    ),
                }
            if state.get("phase") == "decision_required":
                decision_kind = str(state.get("decision_kind") or "")
                return {
                    "schema": NATIVE_ACTION_SCHEMA,
                    "kind": "user_decision",
                    "decision_kind": decision_kind,
                    "message": self._decision_message(state),
                    "options": _decision_options(decision_kind),
                    "must_findings": list(state.get("must_findings", [])),
                }
            raise WorkflowError("当前没有等待执行的原生角色动作。")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != NATIVE_ACTION_SCHEMA:
            raise WorkflowError("原生角色动作格式无效。")
        return payload

    @staticmethod
    def _decision_message(state: dict[str, Any]) -> str:
        """Render the decision message with the revision-round hint."""
        decision_kind = str(state.get("decision_kind") or "")
        message = str(
            state.get("decision_message")
            or "自动修订后仍有问题，请选择下一步。"
        )
        if decision_kind in REVISION_DECISION_KINDS:
            patch_round = int(state.get("patch_round") or 0)
            message += (
                f"\n第 {patch_round} 轮集中修订后仍有 MUST；"
                "授权续修将再跑一轮 Writer 与完整双审，"
                "不会自动继续。"
            )
        return message

    def status(self, slug: str) -> WorkflowResult:
        """Return the native relay phase in user language, not stale DB state."""
        state = self._load_state(slug)
        phase = str(state.get("phase") or "")
        sequence_id = str(state.get("sequence_id") or "")
        retries = int(state.get("technical_retry_count") or 0)
        messages = {
            "awaiting_writer": (
                "等待 Writer 完成当前章节。执行 next-action 获取角色任务。"
            ),
            "awaiting_writer_planning": (
                "等待 Writer 准备当前章节。执行 next-action 获取角色任务。"
            ),
            "awaiting_writer_session": "正在创建 Writer 会话。",
            "awaiting_patch_writer_session": "正在创建修订 Writer 会话。",
            "awaiting_blind_reader": (
                "等待 Blind Reader 审稿。执行 next-action 获取角色任务。"
            ),
            "awaiting_chapter_editor": (
                "等待 Chapter Editor 审稿。执行 next-action 获取角色任务。"
            ),
            "awaiting_double_review": (
                "等待 Blind Reader 与 Chapter Editor 双审（可并行委派）。"
                "执行 next-action 领取两张角色卡。"
            ),
            "complete": (
                f"第{int(state.get('chapter') or 0):02d}章完成。"
                f"执行 next-action 开始第{int(state.get('chapter') or 0) + 1:02d}章。"
            ),
            "stopped": "任务已停止。",
        }
        if phase == "decision_required":
            decision_kind = str(state.get("decision_kind") or "")
            return WorkflowResult(
                user_state="decision_required",
                message=self._decision_message(state),
                sequence_id=sequence_id,
                technical_retry_count=retries,
                options=_decision_options(decision_kind),
            )
        return WorkflowResult(
            user_state=(
                "chapter_complete"
                if phase == "complete"
                else "stopped" if phase == "stopped" else "running"
            ),
            message=messages.get(phase, "正在自动处理本章。"),
            sequence_id=sequence_id,
            technical_retry_count=retries,
            git_checkpoint_succeeded=phase == "complete",
        )

    def stop(self, slug: str) -> WorkflowResult:
        """Stop the workflow and retire any pending native action."""
        action_id = ""
        if self._state_path(slug).is_file():
            action_id = str(
                self._load_state(slug).get("action_id") or ""
            )
        result = self.orchestrator.stop(slug)
        if self._state_path(slug).is_file():
            state = self._load_state(slug)
            state["phase"] = "stopped"
            _atomic_json(self._state_path(slug), state)
        self._action_path(slug).unlink(missing_ok=True)
        if self._state_path(slug).is_file():
            state = self._load_state(slug)
            for role in state.get("pending_review_roles", []):
                self._role_action_path(slug, role).unlink(missing_ok=True)
        if action_id:
            self._snapshot_path(slug, action_id).unlink(missing_ok=True)
            self._backup_path(slug, action_id).unlink(missing_ok=True)
            self._control_snapshot_path(slug, action_id).unlink(
                missing_ok=True
            )
            self._control_backup_path(slug, action_id).unlink(
                missing_ok=True
            )
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
        failed_phase = str(state.get("failed_phase") or "")
        review_body_available = bool(
            state.get("generation_id") and state.get("body_sha256")
        ) or self._staged_body_matches_state(state)
        if (
            sequence_id
            and review_body_available
            and not state.get("must_findings")
            and decision_kind in {"", "native_role_failed"}
            and failed_phase
            in {
                "awaiting_blind_reader",
                "awaiting_chapter_editor",
                "awaiting_double_review",
            }
        ):
            role = "blind-reader"
            blind_payload = state.get("blind_outcome")
            if isinstance(blind_payload, dict):
                try:
                    self._assert_review_evidence_quote(
                        slug,
                        state,
                        "blind-reader",
                        self._stored_outcome(blind_payload),
                    )
                except WorkflowError:
                    state.pop("blind_outcome", None)
                    state.pop("blind_session", None)
                else:
                    role = "chapter-editor"
            bucket = role
            counts = state.get("technical_retry_counts")
            if not isinstance(counts, dict):
                counts = {}
                state["technical_retry_counts"] = counts
            counts[bucket] = 0
            state["technical_retry_count"] = 0
            was_parallel = failed_phase == "awaiting_double_review"
            if was_parallel:
                state["phase"] = "awaiting_double_review"
                issued = [
                    item for item in state.get("issued_review_roles", [])
                    if item != role
                ]
                state["issued_review_roles"] = issued
            else:
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
            self._write_action(
                slug,
                state,
                action,
                write_primary=not was_parallel,
            )
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
            # 重新生成是全新草稿：陈旧 MUST 与修订轮次不得被技术恢复
            # 当作 patch 指令重新路由。
            state.pop("must_findings", None)
            state.pop("patch_round", None)
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
        telemetry = sanitize_call_telemetry(completion.get("telemetry"))
        current_tokens = telemetry.get("total_tokens")
        observation = state.get("active_call_observation")
        try:
            completion_role = str(
                (completion.get("role_result") or {}).get("role") or ""
            )
            current_role = (
                completion_role
                if str(state.get("phase") or "")
                == "awaiting_double_review"
                and completion_role in {"blind-reader", "chapter-editor"}
                else None
            )
            action_id = self._active_snapshot_action_id(
                slug,
                current_role,
            ) or str(state.get("action_id") or "")
            self._verify_workspace(
                slug,
                action_id,
                role=current_role,
            )
            state = self._load_state(slug)
            if isinstance(current_tokens, int):
                state["known_total_tokens"] = (
                    int(state.get("known_total_tokens") or 0) + current_tokens
                )
                _atomic_json(self._state_path(slug), state)
            phase = state.get("phase")
            if phase == "awaiting_local_patch":
                result = self._complete_local_patch(slug, state, completion)
            elif phase == "awaiting_writer":
                result = self._complete_writer(slug, state, completion)
            elif phase in {
                "awaiting_patch_writer_session",
                "awaiting_writer_session",
            }:
                result = self._complete_patch_writer_session(
                    slug,
                    state,
                    completion,
                )
            elif phase in {
                "awaiting_blind_reader",
                "awaiting_chapter_editor",
                "awaiting_double_review",
            }:
                result = self._complete_review(slug, state, completion)
            elif phase == "awaiting_writer_planning":
                result = self._complete_planning(slug, state, completion)
            else:
                raise WorkflowError("当前没有等待中的可回传角色。")
        except NativeCompletionRepairError as exc:
            state = self._load_state(slug)
            return self._request_completion_repair(
                slug,
                state,
                reason=exc.reason,
            )
        except NativeWorkspaceMutationError as exc:
            state = self._load_state(slug)
            failed_body = self._body_observation_summary(slug, state)
            self._remember_failed_completion_session(state, completion)
            result = self._recover_technical_failure(
                slug,
                state,
                failure_reason=exc.reason,
                failure_detail=exc.detail,
            )
            self._observe_call(
                slug,
                observation,
                completion,
                result,
                outcome="failed",
                failure_reason=exc.reason,
                body_after=failed_body,
            )
            return result
        except (GuardianError, WorkflowError, OSError, ValueError) as exc:
            state = self._load_state(slug)
            failed_body = self._body_observation_summary(slug, state)
            self._remember_failed_completion_session(state, completion)
            failed_review_role = str(
                (completion.get("role_result") or {}).get("role") or ""
            )
            if failed_review_role in {"blind-reader", "chapter-editor"}:
                state["failed_review_role"] = failed_review_role
                _atomic_json(self._state_path(slug), state)
            reason = f"{type(exc).__name__}: {exc}"
            result = self._recover_technical_failure(
                slug,
                state,
                failure_reason=reason,
            )
            self._observe_call(
                slug,
                observation,
                completion,
                result,
                outcome="failed",
                failure_reason=reason,
                body_after=failed_body,
            )
            return result
        self._observe_call(
            slug,
            observation,
            completion,
            result,
            outcome="completed",
        )
        return result

    @staticmethod
    def _review_retry_message(failure_reason: str) -> str:
        """Return a compact, actionable review delivery retry message."""
        detail = str(failure_reason or "").strip()
        if not detail:
            return "审稿会话异常，已自动换新会话重试。"
        return "审稿结果未被接受，已自动换新会话重试：" + detail[:360]

    @staticmethod
    def _retry_bucket(state: dict[str, Any]) -> str:
        phase = str(state.get("phase") or "")
        if phase == "awaiting_writer_planning":
            return "writer-planning"
        if phase == "awaiting_blind_reader":
            return "blind-reader"
        if phase == "awaiting_chapter_editor":
            return "chapter-editor"
        if phase in {"awaiting_patch_writer_session", "awaiting_local_patch"}:
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
        counts[bucket] = 0
        state["technical_retry_count"] = 0

    def _request_completion_repair(
        self,
        slug: str,
        state: dict[str, Any],
        *,
        reason: str,
    ) -> WorkflowResult:
        phase = str(state.get("phase") or "")
        if phase == "awaiting_double_review":
            try:
                repair_role = self._phase_role(state)
                action_id = str(
                    self._role_action(slug, repair_role).get("action_id")
                    or ""
                )
            except (OSError, ValueError, json.JSONDecodeError):
                action_id = str(state.get("action_id") or "")
        else:
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
        phase = str(state.get("phase") or "")
        if phase == "awaiting_double_review":
            role = self._phase_role(state)
            try:
                action = self._role_action(slug, role)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise WorkflowError("原生角色动作记录损坏。") from exc
        else:
            action = self.next_action(slug)
        action["completion_repair"] = {
            "attempt": attempt,
            "reason": reason,
            "instruction": (
                "Do not rerun the role. Resubmit the same official terminal "
                "using completion_template."
            ),
        }
        self._write_action(
            slug,
            state,
            action,
            write_primary=phase != "awaiting_double_review",
        )
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
        if not self.strict_audit:
            self._refresh_blind_outcome_if_changed(slug, state)
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
            # 并行双审时 Editor 独立审稿，不依赖 Blind 结论。
            blind_review = None
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
        }
        if blind_review is not None:
            inputs["blind_review"] = blind_review
        texture_hint = str(analyze_literary_texture(prose).get("hint") or "")
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
        elif texture_hint:
            inputs["machine_diagnostics"] = texture_hint[:160]
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
        state.setdefault("review_capsules", {})[role] = descriptor
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
            "lead_must_delegate": True,
            "lead_may_write_role_output": False,
            "reasoning_effort": "medium",
            "parallel_review": (
                not self.strict_audit
                and str(state.get("phase") or "")
                == "awaiting_double_review"
            ),
            "review_capsule": descriptor,
            "task": (
                "Read only the sealed review capsule and write the compact "
                "JSON judgment to result_file. Do not create any form, "
                "envelope, evidence, or control-plane record."
                if not self.strict_audit
                else (
                    "Read only the sealed review capsule and return the "
                    "structured role result through the official terminal."
                )
            ),
            "result": {
                **_result_contract(role),
                "review_capsule_id_required": True,
            },
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [],
        }
        if not self.strict_audit:
            control_session = self._control_session(
                role,
                int(state["chapter"]),
            )
            state["control_run_id"] = control_session.session_id
            state.setdefault("control_run_ids", {})[
                role
            ] = control_session.session_id
            integrity_root = self._integrity_root(slug)
            review_prefix = review_dir.relative_to(integrity_root).as_posix()
            action["control_plane_managed_paths"] = [
                f"{review_prefix}/{path}"
                for path in snapshot_workspace(review_dir)
            ]
        return action

    def _start_double_review(
        self,
        slug: str,
        state: dict[str, Any],
    ) -> WorkflowResult:
        """Dispatch both reviewers, in parallel in Lean and serially in strict.

        Lean writes two role cards up front (blind-reader as the primary
        card); the host may delegate them concurrently and complete them in
        either order. Strict audit keeps the serial blind-then-editor flow.
        """
        request = self._request_from_state(state)
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"] or "")
        if self.strict_audit:
            state["phase"] = "awaiting_blind_reader"
            action = self._review_action(slug, state, "blind-reader")
            self._write_action(slug, state, action)
            return WorkflowResult(
                user_state="running",
                message="正在自动审稿。",
                sequence_id=sequence_id,
            )
        state.update(
            {
                "phase": "awaiting_double_review",
                "pending_review_roles": ["blind-reader", "chapter-editor"],
                "completed_review_roles": [],
                "issued_review_roles": [],
            }
        )
        self._reset_active_retry(state, "blind-reader")
        blind = self._review_action(slug, state, "blind-reader")
        self._reset_active_retry(state, "chapter-editor")
        editor = self._review_action(slug, state, "chapter-editor")
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="reviewing",
            retries=0,
        )
        self._write_action(slug, state, blind)
        self._write_action(slug, state, editor, write_primary=False)
        return WorkflowResult(
            user_state="running",
            message="正在自动审稿。",
            sequence_id=sequence_id,
        )

    def _verify_current_review_capsule(
        self,
        state: dict[str, Any],
        completion: dict[str, Any],
        role: str,
    ) -> None:
        try:
            primary = json.loads(
                self._action_path(str(state["slug"])).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError):
            primary = None
        candidates: list[dict[str, Any]] = []
        if isinstance(primary, dict) and primary.get("role") == role:
            primary_capsule = primary.get("review_capsule")
            if isinstance(primary_capsule, dict):
                candidates.append(primary_capsule)
        capsule_by_role = state.get("review_capsules", {}).get(role)
        if isinstance(capsule_by_role, dict):
            candidates.append(capsule_by_role)
        legacy_capsule = state.get("review_capsule")
        if isinstance(legacy_capsule, dict):
            candidates.append(legacy_capsule)
        require_blind_review = not (
            not self.strict_audit
            and str(state.get("phase") or "")
            == "awaiting_double_review"
        )
        descriptor = None
        for candidate in candidates:
            if completion.get("review_capsule_id") != candidate.get("id"):
                continue
            try:
                verify_review_capsule(
                    candidate,
                    expected_role=role,
                    expected_body_sha256=str(state["body_sha256"]),
                    require_machine_diagnostics=self.strict_audit,
                    require_blind_review=require_blind_review,
                )
            except ReviewCapsuleError:
                continue
            descriptor = candidate
            break
        if descriptor is None:
            raise NativeWorkspaceMutationError(
                "review_capsule_mutation"
            )

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
            _chapter_target_path(chapter),
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
        failure_detail: str = "",
    ) -> WorkflowResult:
        phase = str(state.get("phase") or "")
        if phase == "awaiting_blind_reader":
            state.pop("blind_outcome", None)
            state.pop("blind_outcome_source", None)
            state.pop("blind_session", None)
        if phase == "awaiting_chapter_editor":
            blind_payload = state.get("blind_outcome")
            if isinstance(blind_payload, dict):
                try:
                    self._assert_review_evidence_quote(
                        slug,
                        state,
                        "blind-reader",
                        self._stored_outcome(blind_payload),
                    )
                except WorkflowError:
                    state.pop("blind_outcome", None)
                    state.pop("blind_session", None)
                    state["phase"] = "awaiting_blind_reader"
                    phase = "awaiting_blind_reader"
        _, retries = self._next_retry_count(state)
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
            state["decision_message"] = "自动重试仍未完成，请选择下一步。"
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
                message=(
                    "写作会话异常，已自动换新会话重试。"
                    f"{failure_detail}"
                ),
                sequence_id=sequence_id,
                technical_retry_count=retries,
            )
        if phase in {
            "awaiting_blind_reader",
            "awaiting_chapter_editor",
            "awaiting_double_review",
        }:
            role = (
                "blind-reader"
                if phase == "awaiting_blind_reader"
                else "chapter-editor"
                if phase == "awaiting_chapter_editor"
                else self._phase_role(state)
            )
            if phase == "awaiting_double_review":
                failed_role = str(
                    state.get("failed_review_role") or ""
                )
                pending = list(state.get("pending_review_roles", []))
                if failed_role in pending:
                    role = failed_role
                state.pop("failed_review_role", None)
                completed = set(state.get("completed_review_roles", []))
                issued = [
                    item for item in state.get("issued_review_roles", [])
                    if item != role
                ]
                completed.discard(role)
                state["issued_review_roles"] = issued
                state["completed_review_roles"] = sorted(completed)
            action = self._review_action(slug, state, role)
            self._write_action(
                slug,
                state,
                action,
                write_primary=phase != "awaiting_double_review",
            )
            return WorkflowResult(
                user_state="running",
                message=self._review_retry_message(failure_reason),
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
                message=(
                    "写作会话异常，已自动换新会话重试。"
                    f"{failure_detail}"
                ),
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
                    "decision_message": "表面规则修订后仍有问题，请选择下一步。",
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
                    "must_be_independent": True,
                },
                "lead_must_delegate": True,
                "lead_may_write_role_output": False,
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
            if state.get("patch_round"):
                self._write_staged_diff(state)
                state.pop("must_findings", None)
            staged_body = self._staged_body_path(state)
            body_sha256 = hashlib.sha256(staged_body.read_bytes()).hexdigest()
            if not isinstance(runtime_snapshot, dict):
                runtime_snapshot = self._lean_runtime_snapshot(
                    session,
                    str(prepared.get("capsule_id") or ""),
                )
            state.update(
                {
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
            state.pop("blind_outcome", None)
            state.pop("blind_outcome_source", None)
            state.pop("blind_session", None)
            state.pop("editor_outcome", None)
            state.pop("editor_session", None)
            state.pop("surface_findings", None)
            return self._start_double_review(slug, state)
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
        state.pop("blind_outcome", None)
        return self._start_double_review(slug, state)

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
        if capsule_status(self.root, slug, capsule_id) == "imported":
            return session
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
                        scope=(
                            str(item.get("scope") or "unclassified").lower()
                            if str(item.get("scope") or "").lower()
                            in {"local", "structural", "blocking"}
                            else "unclassified"
                        ),
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
                            scope="unclassified",
                        )
                    )
        return tuple(findings)

    @staticmethod
    def _canonical_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Map older compact review keys into the one canonical Lean schema."""
        canonical = dict(payload)
        aliases = {
            "must_issues": "must",
            "quote": "evidence_quote",
            "emotional_aftertaste": "emotional_residue",
        }
        for legacy, current in aliases.items():
            if current not in canonical and legacy in canonical:
                canonical[current] = canonical[legacy]
        return canonical

    @staticmethod
    def _review_enum_value(
        value: Any,
        *,
        field: str,
        allowed: tuple[str, ...],
    ) -> str:
        """Normalize natural 0--10 review scores without preserving ambiguity."""
        if value is None or str(value).strip() == "":
            return "not_applicable"
        text = str(value).strip().lower()
        if text in allowed or text == "not_applicable":
            return text
        try:
            if isinstance(value, bool):
                raise ValueError
            score = float(text)
        except (TypeError, ValueError):
            raise WorkflowError(
                f"Blind Reader {field} 无效：当前值={value!r}；"
                f"期望值={' / '.join(allowed)}，或 0-10 数字分数。"
            ) from None
        if not 0 <= score <= 10:
            raise WorkflowError(
                f"Blind Reader {field} 无效：当前值={value!r}；"
                f"数字分数必须位于 0-10，或使用 {' / '.join(allowed)}。"
            )
        if field == "human_likeness":
            return "convincing" if score >= 7 else "uncertain" if score >= 4 else "synthetic"
        return "continue" if score >= 7 else "conditional" if score >= 4 else "stop"

    @staticmethod
    def _review_outcome(
        payload: dict[str, Any],
        *,
        role: str,
        session: SessionIdentity,
        terminal: dict[str, str],
        strict_audit: bool = False,
    ) -> ReviewOutcome:
        payload = NativeWorkflowRelay._canonical_review_payload(payload)
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
        human_likeness = (
            NativeWorkflowRelay._review_enum_value(
                payload.get("human_likeness"),
                field="human_likeness",
                allowed=("convincing", "uncertain", "synthetic"),
            )
            if role == "blind-reader"
            else "not_applicable"
        )
        reader_desire = (
            NativeWorkflowRelay._review_enum_value(
                payload.get("reader_desire"),
                field="reader_desire",
                allowed=("continue", "conditional", "stop"),
            )
            if role == "blind-reader"
            else "not_applicable"
        )
        if role == "blind-reader" and human_likeness == "synthetic":
            open_must = tuple(
                item
                for item in findings
                if item.severity.upper() == "MUST"
                and item.status.lower() == "open"
            )
            if (
                verdict != "needs_revision"
                or len(open_must) != 1
                or open_must[0].scope != "structural"
            ):
                raise WorkflowError(
                    "Blind Reader synthetic 必须返回 needs_revision 和恰好一条 structural MUST。"
                )
        return ReviewOutcome(
            verdict=verdict,
            findings=findings,
            human_likeness=human_likeness,
            reader_desire=reader_desire,
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

    def _review_outcome_source(
        self,
        slug: str,
        state: dict[str, Any],
        role: str,
    ) -> dict[str, Any] | None:
        path = self._review_result_path(slug, int(state["chapter"]), role)
        try:
            payload = path.read_bytes()
            stat = path.stat()
        except OSError:
            return None
        return {
            "path": path.relative_to(self.root / "books" / slug).as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "mtime_ns": stat.st_mtime_ns,
        }

    def _refresh_blind_outcome_if_changed(
        self,
        slug: str,
        state: dict[str, Any],
    ) -> None:
        """Use a corrected Blind Reader result file instead of a stale state copy."""
        source = self._review_outcome_source(slug, state, "blind-reader")
        stored_source = state.get("blind_outcome_source")
        if (
            source is None
            or not isinstance(stored_source, dict)
            or source["sha256"] == stored_source.get("sha256")
        ):
            return
        session_payload = state.get("blind_session")
        existing = state.get("blind_outcome")
        if not isinstance(session_payload, dict) or not isinstance(existing, dict):
            raise WorkflowError("Blind Reader 缓存缺少会话绑定，不能刷新结果。")
        session = SessionIdentity(**session_payload)
        existing_outcome = self._stored_outcome(existing)
        payload = self._result_payload(
            self._review_result_path(slug, int(state["chapter"]), "blind-reader"),
            repair_common_quotes=True,
        )
        refreshed = self._review_outcome(
            payload,
            role="blind-reader",
            session=session,
            terminal={
                "kind": str(existing_outcome.operation_kind),
                "value": str(existing_outcome.operation_id),
                "result_transport": str(existing_outcome.result_transport),
            },
            strict_audit=False,
        )
        self._assert_review_evidence_quote(
            slug, state, "blind-reader", refreshed
        )
        state["blind_outcome"] = asdict(refreshed)
        state["blind_outcome_source"] = source

    def _assert_review_evidence_quote(
        self,
        slug: str,
        state: dict[str, Any],
        role: str,
        outcome: ReviewOutcome,
    ) -> None:
        """Require every review's evidence quote to match the reviewed prose."""
        quote = outcome.evidence_quote.strip()
        if not self.strict_audit:
            prose = self._staged_body_path(state).read_text(
                encoding="utf-8-sig"
            )
        else:
            prose = book_project.find_chapter_file(
                self.root / "books" / slug,
                int(state["chapter"]),
            ).read_text(encoding="utf-8-sig")
        matched, detail = _quote_matches(quote, prose)
        if not matched:
            raise WorkflowError(
                f"{role} 没有返回当前正文中的有效审稿引文。{detail}"
            )

    def _record_staged_review_completion(
        self,
        slug: str,
        state: dict[str, Any],
        role: str,
        session: SessionIdentity,
        outcome: ReviewOutcome,
    ) -> None:
        result_path = self._review_result_path(
            slug, int(state["chapter"]), role
        )
        if not result_path.is_file():
            return
        record_session_completion(
            self.root,
            slug,
            session_id=session.session_id,
            session_instance_id=session.session_instance_id,
            role=role,
            provider=session.provider,
            model=session.model,
            agent_harness=session.agent_harness,
            context_scope=(
                "prose_only"
                if role == "blind-reader"
                else "full_review_context"
            ),
            operation_kind=str(outcome.operation_kind),
            operation_id=str(outcome.operation_id),
            result_transport=str(outcome.result_transport),
            chapter=int(state["chapter"]),
            generation_id=(
                f"staged-review.ch{int(state['chapter']):02d}."
                f"{str(state.get('body_sha256') or '')[:16]}"
            ),
            content_sha256=str(state["body_sha256"]),
            artifact=result_path,
            provisional=True,
            workflow_authority=self.orchestrator._workflow_authority,
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
            provisional=False,
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

    @staticmethod
    def _combined_open_must_findings(
        blind: ReviewOutcome,
        editor: ReviewOutcome,
    ) -> tuple[ReviewFinding, ...]:
        unique: list[ReviewFinding] = []
        seen: set[tuple[str, str, str]] = set()
        for item in (*blind.findings, *editor.findings):
            if (
                item.severity.upper() != "MUST"
                or item.status.lower() != "open"
            ):
                continue
            key = (item.location, item.evidence, item.revision_intent)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return tuple(unique)

    def _request_local_patch(
        self,
        slug: str,
        state: dict[str, Any],
        findings: tuple[ReviewFinding, ...],
        plan: list[dict[str, str]],
    ) -> WorkflowResult:
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        request = self._request_from_state(state)
        patch_dir = self._diff_dir(slug, chapter) / "local-patch"
        self._reset_transient_dir(patch_dir)
        input_path = patch_dir / "input.json"
        result_path = patch_dir / "replacements.json"
        body_path = self._staged_body_path(state)
        body_sha256 = hashlib.sha256(body_path.read_bytes()).hexdigest()
        _atomic_json(
            input_path,
            {
                "schema": "novel-forge-local-patch-input/v1",
                "chapter": chapter,
                "immutable_anchors": {
                    "core_event": request.conflict,
                    "chapter_end_goal": request.ending_hook,
                    "body_sha256": body_sha256,
                },
                "instruction": (
                    "只替换给定连续段落；不得改变核心事件、硬锚点或章末目标。"
                    "每项返回原 target 与 replacement，不输出完整正文。"
                ),
                "targets": plan,
            },
        )
        action = {
            "schema": NATIVE_ACTION_SCHEMA,
            "action_id": f"native-action-{uuid.uuid4().hex[:16]}",
            "kind": "run_role",
            "role": "writer",
            "stage": "local-patch",
            "session": {
                "mode": "reuse_preferred",
                "must_be_independent": True,
            },
            "lead_must_delegate": True,
            "lead_may_write_role_output": False,
            "reasoning_effort": "medium",
            "input_file": str(input_path),
            "result_file": str(result_path),
            "repository_exploration_forbidden": True,
            "allowed_project_writes": [
                result_path.relative_to(self._integrity_root(slug)).as_posix()
            ],
        }
        state.update(
            {
                "phase": "awaiting_local_patch",
                "patch_round": int(state.get("patch_round") or 0) + 1,
                "must_findings": [
                    self.orchestrator._patch_directive(item)
                    for item in findings
                ],
                "local_patch_plan": plan,
                "local_patch_body_sha256": body_sha256,
            }
        )
        writer = state.get("writer_session")
        if isinstance(writer, dict):
            state["control_run_id"] = str(writer.get("session_id") or "")
        self._reset_active_retry(state, "patch-writer")
        self.orchestrator._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="patching",
            retries=0,
            must_findings=tuple(state["must_findings"]),
        )
        self._write_action(slug, state, action)
        return WorkflowResult(
            user_state="running",
            message="发现局部问题，正在精确修订。",
            sequence_id=sequence_id,
        )

    def _complete_local_patch(
        self,
        slug: str,
        state: dict[str, Any],
        completion: dict[str, Any],
    ) -> WorkflowResult:
        session, role_result, _ = self._validate_completion(
            state, completion, role="writer"
        )
        payload = role_result.get("payload")
        replacements = payload.get("replacements") if isinstance(payload, dict) else None
        if not isinstance(replacements, list) or not replacements:
            raise WorkflowError("局部 Patch 必须返回 replacements 列表。")
        body_path = self._staged_body_path(state)
        before = body_path.read_text(encoding="utf-8-sig")
        expected = str(state.get("local_patch_body_sha256") or "")
        actual = hashlib.sha256(body_path.read_bytes()).hexdigest()
        if not expected or actual != expected:
            raise WorkflowError("局部 Patch 的正文基线已变化，不能替换。")
        allowed_targets = {
            str(item.get("target") or "")
            for item in state.get("local_patch_plan", [])
            if isinstance(item, dict)
        }
        supplied_targets = {
            str(item.get("target") or "")
            for item in replacements
            if isinstance(item, dict)
        }
        if supplied_targets != allowed_targets:
            raise WorkflowError("局部 Patch 返回的 target 与签发范围不一致。")
        after = apply_local_replacements(before, replacements)
        body_path.write_text(after, encoding="utf-8")
        prepared = state.get("capsule")
        if not isinstance(prepared, dict):
            raise WorkflowError("局部 Patch 缺少 Writer Capsule 绑定。")
        surface_findings = self._capsule_surface_findings(prepared)
        if surface_findings:
            request = self._request_from_state(state)
            result = self.orchestrator._decision_result(
                slug, request, int(state["chapter"]), str(state["sequence_id"]),
                message="局部修订后硬检查仍有问题，请选择下一步。",
                retries=int(state.get("technical_retry_count") or 0),
                decision_kind="local_patch_hard_gate_failed",
                must_findings=tuple(surface_findings),
                parent_generation_id=None,
            )
            state["phase"] = "decision_required"
            state["decision_kind"] = "local_patch_hard_gate_failed"
            state["must_findings"] = list(surface_findings)
            state["decision_message"] = "局部修订后硬检查仍有问题，请选择下一步。"
            _atomic_json(self._state_path(slug), state)
            self._action_path(slug).unlink(missing_ok=True)
            return result
        self._write_staged_diff(state)
        body_sha256 = hashlib.sha256(body_path.read_bytes()).hexdigest()
        state.update(
            {
                "body_sha256": body_sha256,
                "review_session_ids": [],
                "review_session_instance_ids": [],
            }
        )
        for key in (
            "blind_outcome", "blind_outcome_source", "blind_session",
            "editor_outcome", "editor_session", "local_patch_plan",
            "local_patch_body_sha256",
        ):
            state.pop(key, None)
        self._remember_session(state, session, role="writer", status="completed")
        return self._start_double_review(slug, state)

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
            "session": {
                "mode": "reuse_preferred",
                "must_be_independent": True,
            },
            "lead_must_delegate": True,
            "lead_may_write_role_output": False,
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
            "read_only_project_files": [
                (
                    self._diff_dir(slug, chapter)
                    / self.FROZEN_DRAFT_FILENAME
                )
                .relative_to(self._integrity_root(slug))
                .as_posix()
            ],
        }
        state.update(
            {
                "phase": "awaiting_writer",
                "must_findings": list(must),
                "patch_round": int(state.get("patch_round") or 0) + 1,
                "control_run_id": str(writer["session_id"]),
            }
        )
        state.pop("blind_outcome", None)
        state.pop("blind_outcome_source", None)
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

    def _finalize_staged_chapter(
        self,
        slug: str,
        state: dict[str, Any],
        editor_session: SessionIdentity,
        editor_outcome: ReviewOutcome,
    ) -> WorkflowResult:
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        request = self._request_from_state(state)
        blind_payload = state.get("blind_outcome")
        blind_session_payload = state.get("blind_session")
        if not isinstance(blind_payload, dict) or not isinstance(
            blind_session_payload, dict
        ):
            raise WorkflowError("正式晋升前缺少 Blind Reader 结果。")
        blind = self._stored_outcome(blind_payload)
        self._promote_staged_writer(slug, state)
        self._record_native_review(
            slug, state, "blind-reader",
            SessionIdentity(**blind_session_payload), blind,
        )
        self._record_native_review(
            slug, state, "chapter-editor", editor_session, editor_outcome
        )
        book_project.advance_state(
            self.root, slug, chapter, "blind_read",
            evidence=f"reviews/ch{chapter:02d}-blind-reader.md",
        )
        book_project.advance_state(
            self.root, slug, chapter, "editorial_reviewed",
            evidence=f"reviews/ch{chapter:02d}-chapter-editor.md",
        )
        writer_payload = state.get("writer_session")
        if not isinstance(writer_payload, dict):
            raise WorkflowError("当前章节缺少 Writer 会话绑定。")
        result = self.orchestrator._finish_chapter(
            slug, request, chapter, sequence_id,
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

    def approve_high_risk(
        self, slug: str, *, decision_reference: str
    ) -> WorkflowResult:
        state = self._load_state(slug)
        if (
            state.get("phase") != "decision_required"
            or state.get("decision_kind") != "high_risk_author_confirmation"
        ):
            raise WorkflowError("当前没有待确认的高风险章节。")
        if not str(decision_reference or "").strip():
            raise WorkflowError("高风险确认必须提供作者决定依据。")
        session_payload = state.get("pending_editor_session")
        outcome_payload = state.get("pending_editor_outcome")
        if not isinstance(session_payload, dict) or not isinstance(
            outcome_payload, dict
        ):
            raise WorkflowError("高风险确认缺少已完成双审绑定。")
        state["high_risk_approved"] = True
        state["high_risk_decision_reference"] = str(decision_reference)
        state.pop("decision_kind", None)
        return self._finalize_staged_chapter(
            slug, state, SessionIdentity(**session_payload),
            self._stored_outcome(outcome_payload),
        )

    def continue_after_budget(
        self, slug: str, *, decision_reference: str
    ) -> WorkflowResult:
        state = self._load_state(slug)
        if (
            state.get("phase") != "decision_required"
            or state.get("decision_kind") != "hard_budget_reached"
        ):
            raise WorkflowError("当前没有待继续的硬预算断路。")
        if not str(decision_reference or "").strip():
            raise WorkflowError("继续调用必须提供作者决定依据。")
        state["budget_override"] = True
        state["budget_decision_reference"] = str(decision_reference)
        findings_payload = state.get("pending_open_must")
        findings = tuple(
            ReviewFinding(**item) for item in findings_payload or []
            if isinstance(item, dict)
        )
        must = tuple(str(item) for item in state.get("must_findings", []))
        plan = plan_local_patch(
            self._staged_body_path(state).read_text(encoding="utf-8-sig"),
            findings,
        )
        state.pop("decision_kind", None)
        if plan is not None:
            return self._request_local_patch(slug, state, findings, plan)
        return self._request_staged_literary_patch(slug, state, must)

    def authorize_revision(
        self, slug: str, *, decision_reference: str
    ) -> WorkflowResult:
        """Authorize one bounded literary revision after the second review round.

        Official replacement for the python -c recovery call: records the
        author's decision, then resumes the staged revision so the revised
        body is re-reviewed before ready. It is not an unlimited retry loop.
        """
        if self.strict_audit:
            return self.orchestrator.authorize_revision(
                slug,
                decision_reference=decision_reference,
            )
        state = self._load_state(slug)
        decision_kind = str(state.get("decision_kind") or "")
        if (
            state.get("phase") != "decision_required"
            or decision_kind not in REVISION_DECISION_KINDS
        ):
            raise WorkflowError("当前没有等待作者授权的续修决策。")
        reference = str(decision_reference or "").strip()
        if not reference:
            raise WorkflowError("续修授权必须提供作者决定依据。")
        must = tuple(
            str(item)
            for item in state.get("must_findings", [])
            if str(item).strip()
        )
        if not must:
            raise WorkflowError("续修授权缺少待处理的 MUST。")
        state["author_revision_authorized"] = True
        state["author_revision_reference"] = reference
        state["human_decision_reference"] = (
            f"author-revision:ch{int(state['chapter']):02d}"
        )
        _atomic_json(self._state_path(slug), state)
        self._record_author_revision(state, reference, decision_kind, must)
        return self._request_staged_literary_patch(slug, state, must)

    def _record_author_revision(
        self,
        state: dict[str, Any],
        decision_reference: str,
        decision_kind: str,
        must: tuple[str, ...],
    ) -> None:
        """Persist one author revision decision as a lightweight evidence file."""
        slug = str(state["slug"])
        directory = self._relay_dir(slug) / "author-revisions"
        directory.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": "novel-forge-author-revision/v1",
            "id": f"author-rev-{uuid.uuid4().hex[:12]}",
            "slug": slug,
            "chapter": int(state["chapter"]),
            "sequence_id": str(state.get("sequence_id") or ""),
            "decision_kind": decision_kind,
            "decision_reference": decision_reference,
            "must_findings": list(must),
            "created_at": datetime.now(UTC).isoformat(),
            "author_approval": False,
            "publication_eligibility": False,
        }
        path = directory / f"{record['id']}.json"
        _atomic_json(path, record)

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
        self._record_staged_review_completion(
            slug, state, role, session, outcome
        )
        if role == "blind-reader":
            state.update(
                {
                    "blind_outcome": asdict(outcome),
                    "blind_outcome_source": self._review_outcome_source(
                        slug, state, "blind-reader"
                    ),
                    "blind_session": asdict(session),
                }
            )
            completed = set(state.get("completed_review_roles", []))
            completed.add("blind-reader")
            state["completed_review_roles"] = sorted(completed)
            _atomic_json(self._state_path(slug), state)
            if "chapter-editor" not in completed:
                # 并行双审：等 Chapter Editor 完成；其卡由 next-action
                # 按队列签出，主卡不做额外切换。
                return WorkflowResult(
                    user_state="running",
                    message="正在自动审稿。",
                    sequence_id=sequence_id,
                )
            editor_payload = state.get("editor_outcome")
            editor_session_payload = state.get("editor_session")
            if not isinstance(editor_payload, dict) or not isinstance(
                editor_session_payload, dict
            ):
                raise WorkflowError("并行双审合流前缺少 Chapter Editor 结果。")
            return self._finalize_double_review(
                slug,
                state,
                SessionIdentity(**editor_session_payload),
                self._stored_outcome(editor_payload),
            )

        completed = set(state.get("completed_review_roles", []))
        completed.add("chapter-editor")
        state["completed_review_roles"] = sorted(completed)
        state["editor_outcome"] = asdict(outcome)
        state["editor_session"] = asdict(session)
        _atomic_json(self._state_path(slug), state)
        if "blind-reader" not in completed:
            return WorkflowResult(
                user_state="running",
                message="正在自动审稿。",
                sequence_id=sequence_id,
            )
        return self._finalize_double_review(slug, state, session, outcome)

    def _finalize_double_review(
        self,
        slug: str,
        state: dict[str, Any],
        editor_session: SessionIdentity,
        editor_outcome: ReviewOutcome,
    ) -> WorkflowResult:
        """Merge both parallel review results after both roles completed."""
        request = self._request_from_state(state)
        chapter = int(state["chapter"])
        sequence_id = str(state["sequence_id"])
        outcome = editor_outcome
        session = editor_session
        self._refresh_blind_outcome_if_changed(slug, state)
        blind_payload = state.get("blind_outcome")
        blind_session_payload = state.get("blind_session")
        if not isinstance(blind_payload, dict) or not isinstance(
            blind_session_payload, dict
        ):
            raise WorkflowError("Chapter Editor 前缺少 Blind Reader 结果。")
        blind = self._stored_outcome(blind_payload)
        self._assert_review_evidence_quote(
            slug,
            state,
            "blind-reader",
            blind,
        )
        open_must = self._combined_open_must_findings(blind, outcome)
        must = self._combined_must_findings(blind, outcome)
        if must:
            if int(state.get("patch_round") or 0) >= 1:
                patch_round = int(state.get("patch_round") or 0)
                result = self.orchestrator._decision_result(
                    slug,
                    request,
                    chapter,
                    sequence_id,
                    message=(
                        f"第 {patch_round} 轮集中修订后仍有 MUST；"
                        "authorize-revision 将再跑一轮 Writer 与完整双审，"
                        "已进入作者决定，不会自动继续。"
                    ),
                    retries=int(state.get("technical_retry_count") or 0),
                    decision_kind="literary_revision_required",
                    must_findings=must,
                    parent_generation_id=None,
                )
                state["phase"] = "decision_required"
                state["decision_kind"] = "literary_revision_required"
                state["must_findings"] = list(must)
                state["decision_message"] = "自动修订后仍有问题，请选择下一步。"
                _atomic_json(self._state_path(slug), state)
                self._action_path(slug).unlink(missing_ok=True)
                return result
            budget_status = evaluate_budget_breaker(
                int(state.get("known_total_tokens") or 0),
                soft_limit=request.soft_token_budget,
                hard_limit=request.hard_token_budget,
            )
            if budget_status == "soft":
                state["optional_depth_checks_disabled"] = True
            if budget_status == "hard" and not state.get("budget_override"):
                state.update(
                    {
                        "phase": "decision_required",
                        "decision_kind": "hard_budget_reached",
                        "must_findings": list(must),
                        "decision_message": (
                            "已达到硬预算，正文与双审结果已保留，"
                            "请由作者决定是否继续修订。"
                        ),
                        "pending_open_must": [asdict(item) for item in open_must],
                        "pending_editor_outcome": asdict(outcome),
                        "pending_editor_session": asdict(session),
                    }
                )
                _atomic_json(self._state_path(slug), state)
                self._action_path(slug).unlink(missing_ok=True)
                return self.orchestrator._decision_result(
                    slug, request, chapter, sequence_id,
                    message="已达到硬预算，正文与双审结果已保留，请由作者决定是否继续修订。",
                    retries=int(state.get("technical_retry_count") or 0),
                    decision_kind="hard_budget_reached",
                    must_findings=must,
                    parent_generation_id=None,
                )
            local_plan = plan_local_patch(
                self._staged_body_path(state).read_text(encoding="utf-8-sig"),
                open_must,
            )
            if local_plan is not None:
                return self._request_local_patch(
                    slug, state, open_must, local_plan
                )
            return self._request_staged_literary_patch(slug, state, must)

        if state.get("formal_ready_allowed") is False:
            state.update(
                {
                    "phase": "decision_required",
                    "decision_kind": "exploration_only",
                    "decision_message": (
                        "当前宿主能力仅允许探索，草稿与双审结果已保留"
                        "但不能进入 ready。"
                    ),
                    "pending_editor_outcome": asdict(outcome),
                    "pending_editor_session": asdict(session),
                }
            )
            _atomic_json(self._state_path(slug), state)
            self._action_path(slug).unlink(missing_ok=True)
            return self.orchestrator._decision_result(
                slug, request, chapter, sequence_id,
                message="当前宿主能力仅允许探索，草稿与双审结果已保留但不能进入 ready。",
                retries=int(state.get("technical_retry_count") or 0),
                decision_kind="exploration_only",
                parent_generation_id=None,
            )
        if (
            require_high_risk_confirmation(request.chapter_risk)
            and not state.get("high_risk_approved")
        ):
            state.update(
                {
                    "phase": "decision_required",
                    "decision_kind": "high_risk_author_confirmation",
                    "decision_message": (
                        "本章属于高风险节点，双审已通过，"
                        "请作者确认后再晋升。"
                    ),
                    "pending_editor_outcome": asdict(outcome),
                    "pending_editor_session": asdict(session),
                }
            )
            _atomic_json(self._state_path(slug), state)
            self._action_path(slug).unlink(missing_ok=True)
            return self.orchestrator._decision_result(
                slug, request, chapter, sequence_id,
                message="本章属于高风险节点，双审已通过，请作者确认后再晋升。",
                retries=int(state.get("technical_retry_count") or 0),
                decision_kind="high_risk_author_confirmation",
                parent_generation_id=None,
            )
        return self._finalize_staged_chapter(
            slug, state, session, outcome
        )

    def _complete_review(
        self,
        slug: str,
        state: dict[str, Any],
        completion: dict[str, Any],
    ) -> WorkflowResult:
        phase = str(state["phase"])
        completion_role = str(
            (completion.get("role_result") or {}).get("role") or ""
        )
        if phase == "awaiting_double_review":
            role = (
                completion_role
                if completion_role in {"blind-reader", "chapter-editor"}
                else self._phase_role(state)
            )
        else:
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
        self._assert_review_evidence_quote(slug, state, role, outcome)
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
            _chapter_target_path(chapter),
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
