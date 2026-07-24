"""Human-light orchestration for the three-role books workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from . import book_project
from .artifact_integrity import (
    _WORKFLOW_AUTHORITY_REGISTRY,
    record_session_completion,
)
from .book_evidence import (
    record_evidence,
    render_evidence_markdown,
)
from .book_git import book_git_status, checkpoint_book
from .chapter_sequence import (
    advance_chapter_sequence,
    attest_chapter_ready_candidate,
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
from .models import NovelForgeError
from .project_templates import init_book_project
from .review_prompt import (
    render_planning_instructions,
    render_review_instructions,
)
from .role_completion import (
    RoleCompletionError,
    SessionRunState,
    parse_role_run_state,
    require_role_result,
)
from .session_audit import (
    audit_session_log,
    evaluate_session_budget,
    record_runtime_audit,
)
from .workspace_integrity import (
    WorkspaceDelta,
    guarded_role_call,
    snapshot_workspace,
)


WORKFLOW_SCHEMA = "novel-forge-automatic-workflow/v1"
DEFAULT_WRITER_COMPLETION_TIMEOUT_SECONDS = 1800.0
USER_OPTIONS = (
    "A. 保留草稿",
    "B. 重新生成本章",
    "C. 停止任务",
)
REVIEW_ANALYSIS_FIELDS = {
    "blind-reader": (
        "reconstruction_space",
        "reconstruction_body",
        "reconstruction_constraints",
        "reconstruction_emotion",
        "reconstruction_dialogue",
        "memorable_image_1",
        "memorable_image_2",
        "memorable_image_3",
    ),
    "chapter-editor": (
        "editorial_causality",
        "editorial_agency",
        "editorial_dialogue",
        "editorial_texture",
        "editorial_continuity",
    ),
}
HARD_ANCHOR_FIELDS = (
    "protagonist",
    "world",
    "conflict",
    "ending_hook",
)
HARD_ANCHOR_STATUSES = {
    "covered",
    "implicit_but_unambiguous",
    "missing",
    "conflicted",
    "deferred_by_scene_boundary",
}


class WorkflowError(NovelForgeError):
    """Raised when automatic orchestration cannot continue."""


class BackendUnavailableError(WorkflowError):
    """Raised when no native-session backend is connected."""


class HarnessTrustError(BackendUnavailableError):
    """Raised when the configured Harness is not a trusted external entry."""


class ControlPlaneMutationError(WorkflowError):
    """Raised when a Harness call changes repository control-plane files."""


class ReviewSessionExhausted(WorkflowError):
    """Raised after one review role exhausts fresh-session retries."""

    def __init__(self, role: str, retry_count: int):
        super().__init__("独立审稿会话未能返回有效结果。")
        self.role = role
        self.retry_count = retry_count


@dataclass(frozen=True)
class WorkflowRequest:
    """The complete user-facing architecture input for one chapter."""

    title: str
    genre: str
    protagonist: str
    world: str
    conflict: str
    ending_hook: str

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, str) or not value.strip():
                raise WorkflowError(f"{name} 不能为空。")


@dataclass(frozen=True)
class RoleExecutionPreference:
    """Optional host-neutral model selection intent for one role."""

    preferred_model: str | None = None
    inherit_parent_model: bool = False

    def validate(self) -> None:
        if self.preferred_model is not None and not self.preferred_model.strip():
            raise WorkflowError("角色模型偏好不能为空字符串。")
        if self.preferred_model is not None and self.inherit_parent_model:
            raise WorkflowError("角色模型不能同时指定名称并继承父会话。")


@dataclass(frozen=True)
class SessionIdentity:
    """A native session created by the configured external Harness."""

    session_id: str
    session_instance_id: str
    provider: str
    model: str
    agent_harness: str
    role: str = field(default="", compare=False)
    requested_model: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class ReviewFinding:
    """One bounded review finding."""

    severity: str
    location: str
    evidence: str
    reader_effect: str
    revision_intent: str
    status: str = "open"


@dataclass(frozen=True)
class ReviewOutcome:
    """Structured output returned by a reviewer session."""

    verdict: str
    findings: tuple[ReviewFinding, ...] = ()
    human_likeness: str = "not_applicable"
    reader_desire: str = "not_applicable"
    emotional_residue: str = "not_applicable"
    next_chapter_pull: str = "not_applicable"
    analysis: dict[str, str] = field(default_factory=dict)
    hard_anchor_coverage: dict[str, dict[str, str]] = field(
        default_factory=dict
    )
    evidence_quote: str = ""
    previous_chapter_quote: str = "not_applicable"
    resolved_model: str | None = None
    terminal_role: str | None = None
    terminal_session_id: str | None = None
    terminal_session_instance_id: str | None = None
    operation_id: str | None = None
    operation_kind: str | None = None
    result_transport: str | None = None


@dataclass(frozen=True)
class PlanningOutcome:
    """Writer-authored mutable planning files for the current chapter."""

    files: dict[str, str]
    resolved_model: str | None = None
    terminal_role: str | None = None
    terminal_session_id: str | None = None
    terminal_session_instance_id: str | None = None
    operation_id: str | None = None
    operation_kind: str | None = None
    result_transport: str | None = None


@dataclass(frozen=True)
class WorkflowResult:
    """A user-safe workflow result."""

    user_state: str
    message: str
    sequence_id: str
    technical_retry_count: int = 0
    options: tuple[str, ...] = ()
    git_checkpoint_succeeded: bool = False


class SessionBackend(Protocol):
    """Vendor-neutral native session backend."""

    def create_session(
        self,
        role: str,
        *,
        preference: RoleExecutionPreference | None = None,
    ) -> SessionIdentity: ...

    def run_planning(
        self,
        session: SessionIdentity,
        *,
        request: WorkflowRequest,
        chapter: int,
        context: dict[str, str],
        instructions: str,
        reasoning_effort: str,
    ) -> PlanningOutcome: ...

    def run_writer(
        self,
        session: SessionIdentity,
        *,
        capsule_dir: Path,
        capsule_id: str,
        runtime_path: Path,
        must_findings: tuple[str, ...],
    ) -> SessionRunState: ...

    def wait_for_completion(
        self,
        session: SessionIdentity,
        *,
        run: SessionRunState,
        timeout_seconds: float,
    ) -> SessionRunState: ...

    def run_review(
        self,
        session: SessionIdentity,
        *,
        role: str,
        context: dict[str, str],
        instructions: str,
        reasoning_effort: str,
    ) -> ReviewOutcome: ...


class CommandSessionBackend:
    """Run a configured external Harness through a small JSON file protocol."""

    _SCRIPT_SUFFIXES = frozenset(
        {".bat", ".cmd", ".exe", ".js", ".mjs", ".ps1", ".py", ".sh"}
    )
    _INTERPRETER_NAMES = frozenset(
        {"bash", "cmd", "node", "perl", "powershell", "pwsh", "ruby", "sh"}
    )
    _INLINE_EXECUTION_FLAGS = frozenset(
        {"--command", "--eval", "-c", "-e", "-m", "/c", "/k"}
    )

    def __init__(self, command: str | list[str], *, root: Path):
        if isinstance(command, str):
            self.command = shlex.split(command, posix=True)
        else:
            self.command = list(command)
        if not self.command:
            raise WorkflowError("未配置自动写作引擎。")
        self.root = root.resolve()
        self._command_artifacts = self._resolve_command_artifacts()
        self._command_hashes = {
            path: self._file_sha256(path)
            for path in self._command_artifacts
        }

    @classmethod
    def from_environment(cls, root: Path) -> "CommandSessionBackend":
        command = os.environ.get("NOVEL_FORGE_HARNESS_COMMAND", "").strip()
        if not command:
            raise BackendUnavailableError("未配置自动写作引擎。")
        return cls(command, root=root)

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _resolve_command_artifacts(self) -> tuple[Path, ...]:
        executable = self.command[0]
        executable_path = Path(executable).expanduser()
        if executable_path.is_absolute():
            resolved_executable = executable_path.resolve()
        elif any(separator in executable for separator in ("/", "\\")):
            resolved_executable = (self.root / executable_path).resolve()
        else:
            located = shutil.which(executable)
            if not located:
                raise HarnessTrustError("自动写作引擎入口不存在。")
            resolved_executable = Path(located).resolve()
        artifacts = [resolved_executable]
        for argument in self.command[1:]:
            if argument.startswith("-"):
                continue
            candidate = Path(argument).expanduser()
            if not candidate.is_absolute():
                candidate = self.root / candidate
            if candidate.is_file():
                artifacts.append(candidate.resolve())
            elif (
                candidate.suffix.lower() in self._SCRIPT_SUFFIXES
                and ("/" in argument or "\\" in argument)
            ):
                raise HarnessTrustError("自动写作引擎入口不存在。")
        unique_artifacts = tuple(dict.fromkeys(artifacts))
        for path in unique_artifacts:
            if not path.is_file():
                raise HarnessTrustError("自动写作引擎入口不存在。")
            if path == self.root or self.root in path.parents:
                raise HarnessTrustError(
                    "正式 Harness 必须位于项目仓库外。"
                )
        executable_name = resolved_executable.stem.lower()
        is_interpreter = (
            executable_name in self._INTERPRETER_NAMES
            or re.fullmatch(
                r"(?:pythonw?|pypyw?)(?:\d+(?:\.\d+)*)?",
                executable_name,
            )
            is not None
        )
        flags = {argument.lower() for argument in self.command[1:]}
        if is_interpreter and (
            len(unique_artifacts) == 1
            or flags & self._INLINE_EXECUTION_FLAGS
        ):
            raise HarnessTrustError(
                "解释器命令必须引用可固定的仓库外入口脚本。"
            )
        return unique_artifacts

    def _verify_command_artifacts(self) -> None:
        for path, expected in self._command_hashes.items():
            if not path.is_file() or self._file_sha256(path) != expected:
                raise HarnessTrustError(
                    "自动写作引擎入口已发生变化。"
                )

    def _control_plane_snapshot(self) -> dict[str, str]:
        return snapshot_workspace(self.root)

    @staticmethod
    def _changed_snapshot_paths(
        before: dict[str, str],
        after: dict[str, str],
    ) -> list[str]:
        return sorted(
            path
            for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        )

    def _invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        self._verify_command_artifacts()
        control_before = self._control_plane_snapshot()
        with tempfile.TemporaryDirectory(prefix="novel-forge-harness-") as temp:
            directory = Path(temp)
            request_path = directory / "request.json"
            response_path = directory / "response.json"
            request_path.write_text(
                json.dumps(request, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    *self.command,
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                cwd=directory,
            )
            self._verify_command_artifacts()
            changed_paths = self._changed_snapshot_paths(
                control_before,
                self._control_plane_snapshot(),
            )
            if changed_paths:
                preview = ", ".join(changed_paths[:3])
                raise ControlPlaneMutationError(
                    "control_plane_mutation: "
                    f"外部 Harness 改动了仓库控制面：{preview}"
                )
            if proc.returncode != 0 or not response_path.is_file():
                raise WorkflowError("自动写作引擎未能完成本次操作。")
            try:
                payload = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise WorkflowError("自动写作引擎返回了无效结果。") from exc
            if not isinstance(payload, dict):
                raise WorkflowError("自动写作引擎返回了无效结果。")
            return payload

    @staticmethod
    def _run_state(payload: dict[str, Any]) -> SessionRunState:
        try:
            return parse_role_run_state(payload)
        except RoleCompletionError as exc:
            raise WorkflowError(str(exc)) from exc

    def _complete_role(
        self,
        session: SessionIdentity,
        *,
        run: SessionRunState,
        expected_role: str,
    ) -> tuple[SessionRunState, dict[str, Any]]:
        completion = run
        if run.status == "launched":
            completion = self.wait_for_completion(
                session,
                run=run,
                timeout_seconds=(
                    DEFAULT_WRITER_COMPLETION_TIMEOUT_SECONDS
                ),
            )
        if (
            completion.operation_id != run.operation_id
            or completion.operation_kind != run.operation_kind
        ):
            raise WorkflowError("自动写作引擎返回了错误的任务句柄。")
        try:
            result = require_role_result(
                completion,
                expected_role=expected_role,
                expected_session_id=session.session_id,
                expected_session_instance_id=session.session_instance_id,
            )
        except RoleCompletionError as exc:
            raise WorkflowError(str(exc)) from exc
        return completion, result

    def create_session(
        self,
        role: str,
        *,
        preference: RoleExecutionPreference | None = None,
    ) -> SessionIdentity:
        if preference is not None:
            preference.validate()
        payload = self._invoke(
            {
                "action": "create_session",
                "role": role,
                "requirements": {
                    "fresh_native_session": True,
                    "context_isolation": "required",
                },
                "model_preference": (
                    asdict(preference) if preference is not None else None
                ),
            }
        )
        try:
            return SessionIdentity(
                session_id=str(payload["session_id"]).strip(),
                session_instance_id=str(
                    payload["session_instance_id"]
                ).strip(),
                provider=str(payload["provider"]).strip(),
                model=str(payload["model"]).strip(),
                agent_harness=str(payload["agent_harness"]).strip(),
                role=role,
                requested_model=(
                    preference.preferred_model
                    if preference is not None
                    else None
                ),
            )
        except KeyError as exc:
            raise WorkflowError("自动写作引擎没有返回完整会话信息。") from exc

    def run_writer(
        self,
        session: SessionIdentity,
        *,
        capsule_dir: Path,
        capsule_id: str,
        runtime_path: Path,
        must_findings: tuple[str, ...],
    ) -> SessionRunState:
        payload = self._invoke(
            {
                "action": "run_session",
                "role": "writer",
                "session_id": session.session_id,
                "capsule_dir": str(capsule_dir),
                "capsule_id": capsule_id,
                "runtime_output": str(runtime_path),
                "must_findings": list(must_findings),
                "execution_profile": {
                    "reasoning_effort": "medium",
                    "response_count_limit": 1,
                },
                "completion_contract": {
                    "schema": "novel-forge-role-result/v1",
                    "role": "writer",
                    "artifact_relative_path": "draft/正文.md",
                    "host_absolute_path_forbidden": True,
                },
            }
        )
        return self._run_state(payload)

    def wait_for_completion(
        self,
        session: SessionIdentity,
        *,
        run: SessionRunState,
        timeout_seconds: float,
    ) -> SessionRunState:
        payload = self._invoke(
            {
                "action": "wait_session",
                "role": session.role or "writer",
                "session_id": session.session_id,
                "operation_handle": {
                    "kind": run.operation_kind,
                    "value": run.operation_id,
                },
                "timeout_seconds": timeout_seconds,
                "requirements": {
                    "official_terminal_state": True,
                    "file_stability_is_not_completion": True,
                    "bound_role_result_required": True,
                },
            }
        )
        result = self._run_state(payload)
        if (
            result.operation_id != run.operation_id
            or result.operation_kind != run.operation_kind
        ):
            raise WorkflowError("自动写作引擎返回了错误的任务句柄。")
        return result

    def run_planning(
        self,
        session: SessionIdentity,
        *,
        request: WorkflowRequest,
        chapter: int,
        context: dict[str, str],
        instructions: str,
        reasoning_effort: str,
    ) -> PlanningOutcome:
        payload = self._invoke(
            {
                "action": "run_session",
                "role": "writer",
                "phase": "planning",
                "session_id": session.session_id,
                "chapter": chapter,
                "request": asdict(request),
                "context": context,
                "instructions": instructions,
                "execution_profile": {
                    "reasoning_effort": reasoning_effort,
                    "response_count_limit": 1,
                },
                "completion_contract": {
                    "schema": "novel-forge-role-result/v1",
                    "role": "writer-planning",
                    "result_required": True,
                },
            }
        )
        run = self._run_state(payload)
        completion, result = self._complete_role(
            session,
            run=run,
            expected_role="writer-planning",
        )
        result_payload = result["payload"]
        files = result_payload.get("files")
        if not isinstance(files, dict) or not all(
            isinstance(path, str) and isinstance(text, str)
            for path, text in files.items()
        ):
            raise WorkflowError("Writer 会话没有返回有效的章节规划。")
        return PlanningOutcome(
            files=dict(files),
            resolved_model=completion.resolved_model,
            terminal_role=completion.role,
            terminal_session_id=completion.session_id,
            terminal_session_instance_id=completion.session_instance_id,
            operation_id=completion.operation_id,
            operation_kind=completion.operation_kind,
            result_transport=completion.result_transport,
        )

    def run_review(
        self,
        session: SessionIdentity,
        *,
        role: str,
        context: dict[str, str],
        instructions: str,
        reasoning_effort: str,
    ) -> ReviewOutcome:
        payload = self._invoke(
            {
                "action": "run_session",
                "role": role,
                "session_id": session.session_id,
                "context": context,
                "instructions": instructions,
                "execution_profile": {
                    "reasoning_effort": reasoning_effort,
                    "response_count_limit": 1,
                },
                "completion_contract": {
                    "schema": "novel-forge-role-result/v1",
                    "role": role,
                    "result_required": True,
                },
            }
        )
        run = self._run_state(payload)
        completion, result = self._complete_role(
            session,
            run=run,
            expected_role=role,
        )
        result_payload = result["payload"]
        findings = tuple(
            ReviewFinding(
                severity=str(item.get("severity") or ""),
                location=str(item.get("location") or ""),
                evidence=str(item.get("evidence") or ""),
                reader_effect=str(item.get("reader_effect") or ""),
                revision_intent=str(item.get("revision_intent") or ""),
                status=str(item.get("status") or "open"),
            )
            for item in result_payload.get("findings", [])
            if isinstance(item, dict)
        )
        return ReviewOutcome(
            verdict=str(result_payload.get("verdict") or ""),
            findings=findings,
            human_likeness=str(
                result_payload.get("human_likeness") or "not_applicable"
            ),
            reader_desire=str(
                result_payload.get("reader_desire") or "not_applicable"
            ),
            emotional_residue=str(
                result_payload.get("emotional_residue") or "not_applicable"
            ),
            next_chapter_pull=str(
                result_payload.get("next_chapter_pull") or "not_applicable"
            ),
            analysis={
                str(name): str(value)
                for name, value in (
                    result_payload.get("analysis") or {}
                ).items()
                if isinstance(name, str) and isinstance(value, str)
            }
            if isinstance(result_payload.get("analysis"), dict)
            else {},
            hard_anchor_coverage={
                str(name): {
                    str(field_name): str(field_value)
                    for field_name, field_value in item.items()
                    if isinstance(field_name, str)
                    and isinstance(field_value, str)
                }
                for name, item in (
                    result_payload.get("hard_anchor_coverage") or {}
                ).items()
                if isinstance(name, str) and isinstance(item, dict)
            }
            if isinstance(
                result_payload.get("hard_anchor_coverage"),
                dict,
            )
            else {},
            evidence_quote=str(
                result_payload.get("evidence_quote") or ""
            ),
            previous_chapter_quote=str(
                result_payload.get("previous_chapter_quote")
                or "not_applicable"
            ),
            resolved_model=completion.resolved_model,
            terminal_role=completion.role,
            terminal_session_id=completion.session_id,
            terminal_session_instance_id=completion.session_instance_id,
            operation_id=completion.operation_id,
            operation_kind=completion.operation_kind,
            result_transport=completion.result_transport,
        )


class _UnavailableBackend:
    """Placeholder used by read-only workflow commands."""

    def create_session(
        self,
        role: str,
        *,
        preference: RoleExecutionPreference | None = None,
    ) -> SessionIdentity:
        raise WorkflowError("未配置自动写作引擎。")

    def run_planning(self, *args: Any, **kwargs: Any) -> PlanningOutcome:
        raise WorkflowError("未配置自动写作引擎。")

    def run_writer(self, *args: Any, **kwargs: Any) -> SessionRunState:
        raise WorkflowError("未配置自动写作引擎。")

    def wait_for_completion(
        self, *args: Any, **kwargs: Any
    ) -> SessionRunState:
        raise WorkflowError("未配置自动写作引擎。")

    def run_review(self, *args: Any, **kwargs: Any) -> ReviewOutcome:
        raise WorkflowError("未配置自动写作引擎。")


def runtime_generation_metrics(report: dict[str, Any]) -> dict[str, Any]:
    """Map runtime observations without inventing values for unknown fields."""
    tokens = report.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    return {
        "elapsed_seconds": report.get("elapsed_seconds"),
        "request_count": report.get("request_count"),
        "input_tokens": tokens.get("input"),
        "output_tokens": tokens.get("output"),
        "cached_input_tokens": tokens.get("cached_input"),
        "total_tokens": tokens.get("total"),
    }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _user_result(
    state: str,
    message: str,
    sequence_id: str,
    *,
    retries: int = 0,
    options: tuple[str, ...] = (),
    git_ok: bool = False,
) -> WorkflowResult:
    return WorkflowResult(
        user_state=state,
        message=message,
        sequence_id=sequence_id,
        technical_retry_count=retries,
        options=options,
        git_checkpoint_succeeded=git_ok,
    )


def _chapter_label(number: int) -> str:
    labels = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
        10: "十",
    }
    return labels.get(number, str(number))


class NovelWorkflowOrchestrator:
    """Drive Writer, Blind Reader and Chapter Editor without user plumbing."""

    def __init__(
        self,
        root: Path,
        backend: SessionBackend,
        *,
        capsule_root: Path | None = None,
        max_technical_retries: int = 2,
        writer_completion_timeout_seconds: float = (
            DEFAULT_WRITER_COMPLETION_TIMEOUT_SECONDS
        ),
        role_preferences: dict[str, RoleExecutionPreference] | None = None,
        on_status: Callable[[str], None] | None = None,
    ):
        self.root = Path(root).resolve()
        self.backend = backend
        self.capsule_root = (
            Path(capsule_root).resolve()
            if capsule_root is not None
            else Path(tempfile.gettempdir()).resolve()
            / "novel-forge-capsules"
        )
        if (
            self.capsule_root == self.root
            or self.capsule_root.is_relative_to(self.root)
        ):
            raise WorkflowError("写作隔离目录必须位于项目仓库外。")
        if max_technical_retries < 0:
            raise WorkflowError("自动重试次数不能为负数。")
        if writer_completion_timeout_seconds <= 0:
            raise WorkflowError("Writer 完成等待时间必须大于零。")
        self.role_preferences = dict(role_preferences or {})
        for role, preference in self.role_preferences.items():
            if role not in {"writer", "blind-reader", "chapter-editor"}:
                raise WorkflowError(f"未知角色模型偏好：{role}")
            preference.validate()
        self.max_technical_retries = max_technical_retries
        self.writer_completion_timeout_seconds = (
            writer_completion_timeout_seconds
        )
        self.on_status = on_status or (lambda _: None)
        self._workflow_authority = (
            _WORKFLOW_AUTHORITY_REGISTRY.issue_for(self)
        )
        self._seen_sessions: set[str] = set()
        self._seen_session_instances: set[str] = set()

    @staticmethod
    def _workspace_error(delta: WorkspaceDelta) -> Exception:
        if delta.modified or delta.deleted:
            code = "control_plane_mutation"
        else:
            code = "unexpected_project_artifact"
        preview = ", ".join(delta.changed[:3])
        return ControlPlaneMutationError(
            f"{code}: 创作角色改动了项目工作区：{preview}"
        )

    def _role_call(self, callback: Callable[[], Any]) -> Any:
        return guarded_role_call(
            self.root,
            callback,
            error_factory=self._workspace_error,
        )

    def _control_path(self, slug: str) -> Path:
        return self.root / "books" / slug / "planning/workflow/active.json"

    def _save_control(
        self,
        slug: str,
        *,
        request: WorkflowRequest,
        chapter: int,
        sequence_id: str,
        phase: str,
        retries: int,
        decision_kind: str | None = None,
        decision_message: str | None = None,
        must_findings: tuple[str, ...] = (),
        parent_generation_id: str | None = None,
        resume_context: dict[str, Any] | None = None,
    ) -> None:
        _atomic_json(
            self._control_path(slug),
            {
                "schema": WORKFLOW_SCHEMA,
                "slug": slug,
                "chapter": chapter,
                "sequence_id": sequence_id,
                "phase": phase,
                "technical_retry_count": retries,
                "decision_kind": decision_kind,
                "decision_message": decision_message,
                "must_findings": list(must_findings),
                "parent_generation_id": parent_generation_id,
                "resume_context": resume_context,
                "request": asdict(request),
                "updated_at": _now(),
                "author_approval": False,
                "publication_eligibility": False,
            },
        )

    def _new_session(self, role: str) -> SessionIdentity:
        preference = self.role_preferences.get(role)
        session = self._role_call(
            lambda: self.backend.create_session(
                role,
                preference=preference,
            )
        )
        if not session.session_id.strip():
            raise WorkflowError("自动写作引擎没有创建有效会话。")
        if not session.session_instance_id.strip():
            raise WorkflowError("自动写作引擎没有返回底层会话实例。")
        if session.session_id in self._seen_sessions:
            raise WorkflowError("自动写作引擎重复使用了旧会话。")
        if session.session_instance_id in self._seen_session_instances:
            raise WorkflowError("自动写作引擎重复使用了同一底层会话实例。")
        self._seen_sessions.add(session.session_id)
        self._seen_session_instances.add(session.session_instance_id)
        return SessionIdentity(
            session_id=session.session_id,
            session_instance_id=session.session_instance_id,
            provider=session.provider,
            model=session.model,
            agent_harness=session.agent_harness,
            role=role,
            requested_model=(
                session.requested_model
                or (
                    preference.preferred_model
                    if preference is not None
                    else None
                )
            ),
        )

    def _prepare_project(
        self,
        slug: str,
        request: WorkflowRequest,
        chapter: int,
    ) -> Path:
        request.validate()
        book_dir = self.root / "books" / slug
        if not book_dir.is_dir():
            init_book_project(
                self.root,
                slug,
                request.title,
                request.genre,
            )
        if chapter > 1:
            self._seed_voice_exemplar(book_dir, chapter - 1)
        target = book_dir / f"chapters/e01/ch-{chapter:02d}/正文.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        return book_dir

    def _assert_project_is_managed(self, slug: str, chapter: int) -> None:
        book_dir = self.root / "books" / slug
        if not book_dir.is_dir() or self._control_path(slug).is_file():
            return
        unmanaged_paths = [
            book_dir / f"chapters/e01/ch-{chapter:02d}/正文.md",
            book_dir / f"planning/chapter-state/ch{chapter:02d}.md",
            book_dir / f"planning/chapter-state-ch{chapter:02d}.md",
        ]
        unmanaged_paths.extend(
            (book_dir / "reviews").glob(f"ch{chapter:02d}-*.md")
            if (book_dir / "reviews").is_dir()
            else ()
        )
        unmanaged_paths.extend(
            (book_dir / "evidence/generations").glob("*.md")
            if (book_dir / "evidence/generations").is_dir()
            else ()
        )
        if any(path.is_file() for path in unmanaged_paths):
            raise WorkflowError(
                "检测到未受自动流程管理的章节内容，拒绝继续。"
            )

    @staticmethod
    def _seed_voice_exemplar(book_dir: Path, previous_chapter: int) -> None:
        voice = book_dir / "memory/voice-bible.md"
        if not voice.is_file():
            return
        text = voice.read_text(encoding="utf-8-sig")
        marker = "## exemplar_notes"
        if marker not in text:
            return
        head, tail = text.split(marker, 1)
        if not re.search(r"(?m)^_+\s*$", tail):
            return
        previous = book_project.find_chapter_file(
            book_dir, previous_chapter
        ).read_text(encoding="utf-8-sig")
        quote = NovelWorkflowOrchestrator._quote(previous)
        replacement = (
            f"选自第 {previous_chapter:02d} 章：{quote}\n"
            "这段只作为叙事距离、即时动作压力和信息释放顺序的功能锚，"
            "不得复制具体名词、动作或句法。"
        )
        tail = re.sub(
            r"(?m)^_+\s*$",
            replacement,
            tail,
            count=1,
        )
        voice.write_text(head + marker + tail, encoding="utf-8")

    @staticmethod
    def _planning_context(book_dir: Path, chapter: int) -> dict[str, str]:
        """Build bounded context for the Writer's planning phase."""
        context: dict[str, str] = {}
        for name, relative in (
            ("story_engine", "planning/story-engine.md"),
            ("voice_bible", "memory/voice-bible.md"),
        ):
            path = book_dir / relative
            if path.is_file():
                context[name] = path.read_text(encoding="utf-8-sig")
        canon_dir = book_dir / "memory/canon"
        if canon_dir.is_dir():
            canon = "\n\n".join(
                path.read_text(encoding="utf-8-sig")
                for path in sorted(canon_dir.rglob("*.md"))
            )
            context["canon"] = canon[:12000]
        if chapter > 1:
            previous = book_project.find_chapter_file(book_dir, chapter - 1)
            previous_text = previous.read_text(encoding="utf-8-sig")
            context["previous_chapter_path"] = (
                previous.relative_to(book_dir).as_posix()
            )
            context["previous_chapter_sha256"] = hashlib.sha256(
                previous.read_bytes()
            ).hexdigest()
            context["previous_chapter_ending"] = previous_text[
                max(0, int(len(previous_text) * 0.8)) :
            ]
        return context

    @staticmethod
    def _story_contract(request: WorkflowRequest, chapter: int) -> str:
        """Render the user's immutable chapter architecture as a short contract."""
        return (
            "## 0a. 用户硬锚合同\n"
            f"- 章节：第 {chapter:02d} 章\n"
            f"- 书名：{request.title.strip()}\n"
            f"- 题材：{request.genre.strip()}\n"
            f"- 主角：{request.protagonist.strip()}\n"
            f"- 世界观：{request.world.strip()}\n"
            f"- 本章核心冲突：{request.conflict.strip()}\n"
            f"- 本章结尾钩子：{request.ending_hook.strip()}"
        )

    @classmethod
    def _inject_story_contract(
        cls,
        scene_text: str,
        request: WorkflowRequest,
        chapter: int,
    ) -> str:
        """Replace any planner-authored contract with the exact user input."""
        cleaned = re.sub(
            r"(?ms)^## 0a\. 用户硬锚合同\s*\n.*?(?=^## |\Z)",
            "",
            scene_text,
        ).strip()
        contract = cls._story_contract(request, chapter)
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("# "):
            return "\n".join(
                (lines[0], "", contract, "", *lines[1:])
            ).strip()
        return f"{contract}\n\n{cleaned}".strip()

    @classmethod
    def _prose_first_control_planning(
        cls,
        book_dir: Path,
        chapter: int,
        request: WorkflowRequest,
    ) -> PlanningOutcome:
        """Build minimal control materials without asking Writer to fill forms."""
        handoff = ""
        if chapter > 1:
            previous = book_project.find_chapter_file(book_dir, chapter - 1)
            previous_text = previous.read_text(encoding="utf-8-sig")
            previous_quote = cls._quote(
                previous_text[max(0, int(len(previous_text) * 0.8)) :]
            )
            previous_sha256 = hashlib.sha256(previous.read_bytes()).hexdigest()
            handoff = (
                "## 0b. 章际交接\n"
                f"- 上一章正文路径：{previous.relative_to(book_dir).as_posix()}\n"
                f"- 上一章正文 SHA-256：{previous_sha256}\n"
                f"- 上一章结尾原文：{previous_quote}\n"
                "- 本章开头原文：deferred_until_drafted\n"
                "- 上一章结束时间：上一章结尾时刻\n"
                "- 本章开始时间：紧接上一章之后\n"
                "- 上一章结束地点：上一章结尾场景\n"
                "- 本章开始地点：承接上一章场景或其直接后果\n"
                "- 上一章结束动作：见上一章结尾原文\n"
                "- 本章开始动作：从该动作造成的压力继续\n"
                "- 转场类型：same_day_continuous\n"
                "- 上一章末明确决定：延续上一章已经发生的选择\n"
                "- 本章是否推翻该决定：否\n"
                "- 若推翻，触发事件原文：无需：未推翻上一章决定\n\n"
            )
        scene = (
            f"# Scene Package - 第{chapter:02d}章\n\n"
            "## 0. 边界\n"
            f"- 开始动作 / 停止动作：从{request.conflict}进入现场；"
            f"在{request.ending_hook}出现后停止。\n"
            "- 承接压力 / 本章不解决：只完成本章冲突与钩子，"
            "不替作者预先解释后续答案。\n\n"
            f"{handoff}"
            "## 1. 场景压力\n"
            f"- 视角角色要什么：{request.protagonist}必须面对本章冲突。\n"
            f"- 对手/世界独立要什么：世界与其他人物按自身目标阻止"
            f"{request.protagonist}轻易达成目的。\n"
            f"- 选择与即时成本：{request.conflict}\n"
            f"- 章末未解除压力：{request.ending_hook}\n\n"
            "## 1c. 决策问题\n"
            "- 不能同时得到的两样东西：解决眼前冲突 / 不付出私人代价\n"
            "- 角色拒绝承认什么：拖延本身也会造成后果\n"
            "- 角色误读了谁或什么：对手或世界施压的真实方向\n"
            "- 哪句话不能说出口：会暴露人物软肋或关系债务的话\n"
            "- 最终接受的具体代价：为主动选择承担立刻可见的损失\n\n"
            "## 1d. 认知与可证伪假设\n"
            "| 观察 | 当前假设 | 替代解释 | 置信度 | 可推翻证据 | 状态 |\n"
            "|---|---|---|---|---|---|\n"
            "| 压力正在升级 | 主角必须立即行动 | 对手在诱导主角误判 | 中 | "
            "现场出现与当前判断矛盾的行动结果 | 未决 |\n\n"
            "## 1e. 规划反证与常识检查\n"
            "- 时间/日历算术：事件按正文现场的连续时间推进。\n"
            "- 物理动作机制：关键变化必须由人物、物件或环境中的实际动作造成。\n"
            "- 人物知识来源：人物只能依据亲历、已知事实和现场线索判断。\n"
            "- 不可逆性反证：若选择可无代价撤销，正文必须增加真实后果。\n"
            f"- 场景停止点：{request.ending_hook}\n\n"
            "## 2. 在场者状态\n"
            "| 人物 | 此刻目标 | 隐瞒/未知 | 本场变化 |\n"
            "|---|---|---|---|\n"
            f"| {request.protagonist} | 处理本章核心冲突 | 不掌握全部真相 | "
            "必须作出带代价的选择 |\n"
            "| 对手或世界压力 | 推进自身目标 | 不向主角完整解释 | "
            "迫使局面改变 |\n\n"
            "## 3. Beat 因果链\n"
            "| # | 触发 | 行动/决定 | 阻力/反应 | 结果与下一步 | 语域 |\n"
            "|---|---|---|---|---|---|\n"
            f"| 1 | {request.conflict} | 主角尝试处理眼前问题 | "
            "对手或环境拒绝配合 | 原方案失效，必须承担选择 | 贴身 |\n"
            f"| 2 | 原方案失效 | 主角作出不可轻易撤销的行动 | "
            f"行动产生即时后果 | {request.ending_hook} | 贴身 |\n\n"
            "## 3c. 因果归属账本\n"
            "| 动作/条件 | 提出/执行者 | 知情者 | 后果承担者 |\n"
            "|---|---|---|---|\n"
            f"| 面对并处理本章冲突 | {request.protagonist} | "
            f"{request.protagonist}与在场者 | {request.protagonist}及关系人 |\n\n"
            "## 4. 信息账本\n"
            f"- 本章唯一新信息 / 来源 / 导致的选择：{request.ending_hook}\n\n"
            "## 5. 信息预算\n"
            "- 锚定物象：由 Writer 从当前场景的身体、物件和位置中选择。\n"
            "- 关键对白意图：对白必须改变信息、关系或行动方向；无对白亦可。\n"
            "- 新规则/伏笔/术语：只保留会改变当前选择的一项以内。\n"
            "- 延后信息：钩子背后的完整答案留到后续章节。\n\n"
            "## 5b. 专业判断审计\n"
            "- 无需：控制面不预设专业结论，正文如使用专业行动由 Editor 核对。\n\n"
            "## 7. 场景余波\n"
            f"- 身体 / 物件 / 关系 / 认知误信 / 未偿承诺：{request.ending_hook}\n"
        )
        return PlanningOutcome(
            files={
                "memory/worldbuilding.md": (
                    "# 世界设定\n\n"
                    f"## 物理规则\n- {request.world}\n\n"
                    "## 社会规则\n"
                    f"- 故事采用{request.genre}的现实后果；人物与环境拥有独立意志。\n\n"
                    "## 禁忌\n"
                    f"- 不得绕过用户给定的核心冲突：{request.conflict}\n"
                ),
                "planning/research-boundaries.md": (
                    "# 研究边界\n\n"
                    "- 无需：默认不把未经验证的外部事实作为唯一关键情节支点；"
                    "需要专业事实时由正文审稿指出具体风险。\n"
                ),
                "planning/story-engine.md": (
                    "# 故事发动机\n\n"
                    f"## 核心秘密\n- {request.ending_hook}\n\n"
                    f"## 欲望\n- {request.protagonist}必须处理：{request.conflict}\n\n"
                    "## 对抗中的独立意志\n"
                    "- 对手、关系人和世界压力拥有自身目标，不等待主角完成解释。\n\n"
                    "## 主角的错误模型\n"
                    "- 主角对冲突的理解不完整，现场后果可以推翻其判断。\n\n"
                    "## 替代行动与不兼容欲望\n"
                    "- 逃避代价会放大冲突，立即行动又会失去另一项重要事物。\n\n"
                    f"## 不可逆选择\n- {request.conflict}\n\n"
                    "## 即时代价\n- 主角的行动必须造成身体、物件或关系上的即时变化。\n\n"
                    f"## 未解承诺\n- {request.ending_hook}\n\n"
                    "## 主题压力\n- 选择的意义由人物承担的具体后果呈现，不由旁白总结。\n"
                ),
                f"planning/scene-package-ch{chapter:02d}.md": scene,
            }
        )

    @classmethod
    def _write_writer_planning(
        cls,
        book_dir: Path,
        chapter: int,
        request: WorkflowRequest,
        outcome: PlanningOutcome,
    ) -> None:
        """Validate and persist planning authored by the current Writer."""
        required = {
            "memory/worldbuilding.md",
            "planning/research-boundaries.md",
            "planning/story-engine.md",
            f"planning/scene-package-ch{chapter:02d}.md",
        }
        allowed = {
            *required,
            "memory/voice-bible.md",
        }
        supplied = set(outcome.files)
        missing = sorted(required - supplied)
        unexpected = sorted(supplied - allowed)
        if missing:
            raise WorkflowError(
                "Writer 会话缺少章节规划文件：" + "、".join(missing)
            )
        if unexpected:
            raise WorkflowError(
                "Writer 会话返回了未授权的规划文件：" + "、".join(unexpected)
            )
        for relative, text in outcome.files.items():
            if not text.strip():
                raise WorkflowError(f"Writer 规划文件为空：{relative}")
            if relative == f"planning/scene-package-ch{chapter:02d}.md":
                text = cls._inject_story_contract(text, request, chapter)
            pure = Path(relative)
            if pure.is_absolute() or ".." in pure.parts:
                raise WorkflowError("Writer 规划文件路径越界。")
            target = (book_dir / pure).resolve()
            if not target.is_relative_to(book_dir.resolve()):
                raise WorkflowError("Writer 规划文件路径越界。")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text.rstrip() + "\n", encoding="utf-8")

    def _finalize_scene_handoff(self, slug: str, chapter: int) -> None:
        if chapter <= 1:
            return
        book_dir = self.root / "books" / slug
        scene = book_dir / "planning" / f"scene-package-ch{chapter:02d}.md"
        if not scene.is_file():
            return
        text = scene.read_text(encoding="utf-8-sig")
        if "deferred_until_drafted" not in text:
            return
        prose = book_project.find_chapter_file(
            book_dir, chapter
        ).read_text(encoding="utf-8-sig")
        scene.write_text(
            text.replace(
                "deferred_until_drafted",
                self._quote(prose),
                1,
            ),
            encoding="utf-8",
        )

    def start(
        self,
        slug: str,
        request: WorkflowRequest,
        *,
        chapter: int = 1,
    ) -> WorkflowResult:
        request.validate()
        self._assert_project_is_managed(slug, chapter)
        writer_session = self._new_session("writer")
        self.on_status("正在写作。")
        book_dir = self._prepare_project(slug, request, chapter)
        planning = self._role_call(
            lambda: self.backend.run_planning(
                writer_session,
                request=request,
                chapter=chapter,
                context=self._planning_context(book_dir, chapter),
                instructions=render_planning_instructions().text,
                reasoning_effort="high",
            )
        )
        if (
            planning.terminal_role != "writer-planning"
            or planning.terminal_session_id != writer_session.session_id
            or planning.terminal_session_instance_id
            != writer_session.session_instance_id
            or not planning.operation_id
            or not planning.operation_kind
            or not planning.result_transport
        ):
            raise WorkflowError(
                "规划结果没有绑定当前原生 Writer 会话终态。"
            )
        if planning.resolved_model:
            writer_session = replace(
                writer_session,
                model=planning.resolved_model,
            )
        self._write_writer_planning(book_dir, chapter, request, planning)
        sequence_id = f"auto-ch{chapter:02d}-{uuid.uuid4().hex[:10]}"
        begin_chapter_sequence(
            self.root,
            slug,
            chapter,
            1,
            sequence_id=sequence_id,
            orchestrator_run_id=f"workflow-{uuid.uuid4().hex[:12]}",
        )
        book_project.set_draft_mode(self.root, slug, chapter, "formal")
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
        self._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="writing",
            retries=0,
        )
        return self._run_sequence(
            slug,
            request,
            chapter,
            sequence_id,
            initial_writer_session=writer_session,
        )

    def _execute_generation(
        self,
        slug: str,
        chapter: int,
        sequence_id: str,
        *,
        must_findings: tuple[str, ...],
        parent_generation_id: str | None,
        initial_session: SessionIdentity | None = None,
        human_decision_reference: str | None = None,
    ) -> tuple[SessionIdentity, str, int] | None:
        target_path = f"chapters/e01/ch-{chapter:02d}/正文.md"
        for attempt in range(self.max_technical_retries + 1):
            session = (
                initial_session
                if attempt == 0 and initial_session is not None
                else self._new_session("writer")
            )
            claim_chapter_session(
                self.root,
                slug,
                sequence_id,
                session.session_id,
            )
            authorization_id = None
            if human_decision_reference is not None:
                authorization = authorize_regeneration(
                    self.root,
                    slug,
                    sequence_id,
                    session.session_id,
                    authority="human_delegate",
                    decision_reference=human_decision_reference,
                )
                authorization_id = authorization["authorization_id"]
            capsule = (
                self.capsule_root
                / slug
                / f"{session.session_id}-{uuid.uuid4().hex[:8]}"
            )
            runtime_path = (
                self.capsule_root
                / slug
                / "runtime"
                / f"{session.session_id}-{uuid.uuid4().hex[:8]}.json"
            )
            directive = "\n".join(f"- {item}" for item in must_findings)
            prepared = prepare_writer_capsule(
                self.root,
                slug,
                sequence_id,
                session.session_id,
                capsule,
                target_path,
                regeneration_authorization_id=authorization_id,
                patch_directive=directive or None,
            )

            def run_writer_role() -> tuple[
                SessionRunState,
                SessionRunState,
            ]:
                launched = self.backend.run_writer(
                    session,
                    capsule_dir=capsule,
                    capsule_id=prepared["capsule_id"],
                    runtime_path=runtime_path,
                    must_findings=must_findings,
                )
                terminal = launched
                if launched.status == "launched":
                    try:
                        terminal = self.backend.wait_for_completion(
                            session,
                            run=launched,
                            timeout_seconds=(
                                self.writer_completion_timeout_seconds
                            ),
                        )
                    except Exception:
                        terminal = SessionRunState(
                            operation_id=launched.operation_id,
                            operation_kind=launched.operation_kind,
                            status="failed",
                        )
                return launched, terminal

            try:
                run, completion = self._role_call(run_writer_role)
            except ControlPlaneMutationError as exc:
                reason = (
                    "control_plane_mutation"
                    if str(exc).startswith("control_plane_mutation:")
                    else "unexpected_project_artifact"
                )
                reject_writer_capsule(
                    self.root,
                    slug,
                    prepared["capsule_id"],
                    reason=reason,
                )
                if attempt < self.max_technical_retries:
                    self.on_status(
                        "写作会话异常，已自动换新会话重试。"
                    )
                    continue
                return None
            except Exception:
                reject_writer_capsule(
                    self.root,
                    slug,
                    prepared["capsule_id"],
                    reason="writer_launch_failed",
                )
                if attempt < self.max_technical_retries:
                    self.on_status(
                        "写作会话异常，已自动换新会话重试。"
                    )
                    continue
                return None
            if (
                completion.operation_id != run.operation_id
                or completion.operation_kind != run.operation_kind
            ):
                completion = SessionRunState(
                    operation_id=run.operation_id,
                    operation_kind=run.operation_kind,
                    status="failed",
                )
            if completion.status != "completed":
                reason = (
                    "writer_completion_timeout"
                    if completion.status == "timed_out"
                    else "writer_terminal_failure"
                )
                reject_writer_capsule(
                    self.root,
                    slug,
                    prepared["capsule_id"],
                    reason=reason,
                )
                if attempt < self.max_technical_retries:
                    self.on_status(
                        "写作会话异常，已自动换新会话重试。"
                    )
                    continue
                return None
            try:
                writer_result = require_role_result(
                    completion,
                    expected_role="writer",
                    expected_session_id=session.session_id,
                    expected_session_instance_id=session.session_instance_id,
                )
                artifact_relative_path = str(
                    writer_result["payload"].get(
                        "artifact_relative_path"
                    )
                    or ""
                ).strip()
                if artifact_relative_path != "draft/正文.md":
                    raise RoleCompletionError(
                        "Writer 返回了无效的 capsule 相对产物路径。"
                    )
            except RoleCompletionError:
                reject_writer_capsule(
                    self.root,
                    slug,
                    prepared["capsule_id"],
                    reason="writer_result_invalid",
                )
                if attempt < self.max_technical_retries:
                    self.on_status(
                        "写作会话异常，已自动换新会话重试。"
                    )
                    continue
                return None
            if completion.resolved_model:
                session = replace(
                    session,
                    model=completion.resolved_model,
                )
            if runtime_path.is_file():
                try:
                    record_capsule_runtime(
                        self.root,
                        slug,
                        prepared["capsule_id"],
                        runtime_path,
                    )
                except GuardianError:
                    pass
            try:
                imported = ingest_writer_capsule(
                    self.root,
                    slug,
                    prepared["capsule_id"],
                )
            except GuardianError:
                if attempt < self.max_technical_retries:
                    self.on_status(
                        "写作会话异常，已自动换新会话重试。"
                    )
                    continue
                return None
            report = audit_session_log(runtime_path)
            generation_id = (
                f"generation.ch{chapter:02d}."
                f"{uuid.uuid4().hex[:16]}"
            )
            self._record_generation(
                slug,
                chapter,
                session,
                prepared,
                imported,
                report,
                generation_id,
                parent_generation_id=parent_generation_id,
                is_patch=bool(must_findings),
            )
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
                operation_kind=completion.operation_kind,
                operation_id=completion.operation_id,
                result_transport=str(completion.result_transport),
                chapter=chapter,
                generation_id=generation_id,
                content_sha256=imported["body_sha256"],
                artifact=(
                    self.root
                    / "books"
                    / slug
                    / imported["target_path"]
                ),
                workflow_authority=self._workflow_authority,
            )
            return session, generation_id, attempt
        return None

    def _record_generation(
        self,
        slug: str,
        chapter: int,
        session: SessionIdentity,
        prepared: dict[str, Any],
        imported: dict[str, Any],
        report: dict[str, Any],
        generation_id: str,
        *,
        parent_generation_id: str | None,
        is_patch: bool,
        assurance_mode: str = "strict_audit",
    ) -> None:
        book_dir = self.root / "books" / slug
        chapter_path = book_dir / imported["target_path"]
        metrics = runtime_generation_metrics(report)
        lean_native = assurance_mode == "lean_native"
        record = {
            "schema_version": 1,
            "id": generation_id,
            "kind": "generation",
            "created_at": _now(),
            "authority": (
                "human_delegate"
                if prepared.get("human_regeneration_authorized") is True
                else "agent"
            ),
            "source_paths": [imported["target_path"]],
            "summary": "自动三角色工作流记录的当前章节正文。",
            "chapter": chapter,
            "draft_mode": "formal",
            "writer_type": "agent",
            "provider": report["provider"],
            "model": report["model"],
            "run_id": session.session_id,
            "agent_harness": report["agent_harness"],
            "reasoning_effort": report["reasoning_effort"],
            "content_path": imported["target_path"],
            "content_sha256": hashlib.sha256(
                chapter_path.read_bytes()
            ).hexdigest(),
            "prompt_template_id": prepared["prompt_template_id"],
            "prompt_sha256": prepared["prompt_sha256"],
            "metrics_source": (
                "unknown" if lean_native else "harness_reported"
            ),
            "generation_stage": "revised" if is_patch else "raw",
            "provenance_confidence": (
                "unknown" if lean_native else "harness_exposed"
            ),
            "sandbox_profile": (
                "unknown" if lean_native else "restricted"
            ),
            "assurance_mode": assurance_mode,
            "tool_capabilities": ["write_file"],
            "tool_failures": [],
            "draft_write_count": 0 if is_patch else 1,
            "draft_edit_count": 1 if is_patch else 0,
            "review_call_count": 0,
            "review_round": 1 if is_patch else 0,
            "parent_generation_id": parent_generation_id,
            **metrics,
        }
        if prepared.get("human_regeneration_authorized") is True:
            record["human_regeneration_authorized"] = True
            record["human_decision_reference"] = prepared[
                "human_decision_reference"
            ]
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".md",
            delete=False,
        ) as handle:
            handle.write(render_evidence_markdown(record))
            source = Path(handle.name)
        try:
            record_evidence(self.root, slug, source)
        finally:
            source.unlink(missing_ok=True)
        book_project.bind_generation(
            self.root,
            slug,
            chapter,
            generation_id,
        )
        report["budget"] = evaluate_session_budget(report, chapter_count=1)
        report["provenance_mismatches"] = []
        report["provenance_status"] = "verified"
        report["generation_record_ids"] = [generation_id]
        record_runtime_audit(book_dir, report)

    @staticmethod
    def _quote(prose: str) -> str:
        return next(
            line.strip()[:48]
            for line in prose.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

    def _render_review(
        self,
        slug: str,
        chapter: int,
        role: str,
        session: SessionIdentity,
        outcome: ReviewOutcome,
    ) -> str:
        book_dir = self.root / "books" / slug
        prose = book_project.find_chapter_file(
            book_dir, chapter
        ).read_text(encoding="utf-8-sig")
        quote = outcome.evidence_quote.strip()
        if not quote or quote not in prose:
            raise WorkflowError(f"{role} 没有返回当前正文中的有效审稿引文。")
        required_analysis = REVIEW_ANALYSIS_FIELDS[role]
        missing_analysis = [
            name
            for name in required_analysis
            if not outcome.analysis.get(name, "").strip()
        ]
        if missing_analysis:
            raise WorkflowError(
                f"{role} 缺少实质审稿字段："
                + "、".join(missing_analysis)
            )
        anchor_section = ""
        if role == "chapter-editor":
            coverage = outcome.hard_anchor_coverage
            missing_anchors = [
                name for name in HARD_ANCHOR_FIELDS if name not in coverage
            ]
            if missing_anchors:
                raise WorkflowError(
                    "chapter-editor 缺少用户硬锚核验："
                    + "、".join(missing_anchors)
                )
            anchor_lines: list[str] = []
            blocking_anchor_status = False
            for name in HARD_ANCHOR_FIELDS:
                item = coverage.get(name)
                if not isinstance(item, dict):
                    raise WorkflowError(
                        f"chapter-editor 硬锚 {name} 格式无效。"
                    )
                status = str(item.get("status") or "").strip()
                evidence = str(item.get("evidence") or "").strip()
                reconstruction = str(
                    item.get("reader_reconstruction") or ""
                ).strip()
                if status not in HARD_ANCHOR_STATUSES:
                    raise WorkflowError(
                        f"chapter-editor 硬锚 {name} 状态无效。"
                    )
                if (
                    status == "deferred_by_scene_boundary"
                    and name != "world"
                ):
                    raise WorkflowError(
                        f"chapter-editor 硬锚 {name} 不得延期。"
                    )
                if not reconstruction:
                    raise WorkflowError(
                        f"chapter-editor 硬锚 {name} 缺少读者重建。"
                    )
                if status in {
                    "covered",
                    "implicit_but_unambiguous",
                    "conflicted",
                } and (not evidence or evidence not in prose):
                    raise WorkflowError(
                        f"chapter-editor 硬锚 {name} 缺少当前正文证据。"
                    )
                if status in {"missing", "conflicted"}:
                    blocking_anchor_status = True
                anchor_lines.append(
                    f"- {name}: status={status}; "
                    f"evidence={evidence or 'not_found'}; "
                    f"reader_reconstruction={reconstruction}"
                )
            open_must = any(
                finding.severity.upper() == "MUST"
                and finding.status.lower() == "open"
                for finding in outcome.findings
            )
            if blocking_anchor_status and not open_must:
                raise WorkflowError(
                    "chapter-editor 发现用户硬锚缺失或冲突，"
                    "但没有返回开放 MUST。"
                )
            anchor_section = (
                "\n\n## Hard Anchor Coverage\n"
                + "\n".join(anchor_lines)
            )
        binding = book_project.review_binding(
            self.root,
            slug,
            chapter,
            role=role,
        )
        previous_quote = "not_applicable"
        if chapter > 1:
            previous_text = book_project.find_chapter_file(
                book_dir, chapter - 1
            ).read_text(encoding="utf-8-sig")
            previous_quote = outcome.previous_chapter_quote.strip()
            if role == "chapter-editor" and (
                not previous_quote or previous_quote not in previous_text
            ):
                raise WorkflowError(
                    "chapter-editor 没有返回上一章正文中的有效连续性引文。"
                )
        findings = [
            "| # | 级别 (MUST/MAY) | 位置 | 原文证据 | 读者效果 | 修订意图 | 状态 (open/closed) |",
            "|---|---|---|---|---|---|---|",
        ]
        for index, item in enumerate(outcome.findings, 1):
            findings.append(
                f"| {index} | {item.severity} | {item.location} | "
                f"{item.evidence} | {item.reader_effect} | "
                f"{item.revision_intent} | {item.status} |"
            )
        if role == "blind-reader":
            details = "\n".join(
                f"- {name}: {outcome.analysis[name].strip()}"
                for name in required_analysis
            )
            human_likeness = outcome.human_likeness
            reader_desire = outcome.reader_desire
            emotional_residue = outcome.emotional_residue
            next_pull = outcome.next_chapter_pull
            section = "## Prose-only Reconstruction\n" + details
            context_scope = "prose_only"
        else:
            details = "\n".join(
                f"- {name}: {outcome.analysis[name].strip()}"
                for name in required_analysis
            )
            human_likeness = "not_applicable"
            reader_desire = "not_applicable"
            emotional_residue = "not_applicable"
            next_pull = "not_applicable"
            section = (
                "## Editorial Dimensions\n"
                + details
                + anchor_section
            )
            context_scope = "full_review_context"
        return (
            f"# Review - ch{chapter:02d} / {role}\n\n"
            f"- chapter: ch{chapter:02d}\n"
            f"- role: {role}\n"
            f"- verdict: {outcome.verdict}\n"
            f"- date: {datetime.now(UTC).date().isoformat()}\n\n"
            f"- source_fingerprint: {binding['source_fingerprint']}\n"
            f"- chapter_sha256: {binding['chapter_sha256']}\n"
            f"- previous_chapter_sha256: {binding['previous_chapter_sha256']}\n"
            f"- planning_sha256: {binding['planning_sha256']}\n"
            f"- draft_mode: {binding['draft_mode']}\n"
            f"- generation_id: {binding['generation_id']}\n\n"
            f"- evidence_quote: {quote}\n"
            f"- previous_chapter_quote: {previous_quote}\n\n"
            "- reviewer_type: model\n"
            f"- reviewer_id: {session.session_id}\n"
            f"- review_session_id: {session.session_id}\n"
            f"- provider: {session.provider}\n"
            f"- model: {session.model}\n"
            f"- context_scope: {context_scope}\n"
            "- independence_note: 独立原生会话，按角色最小上下文执行。\n\n"
            f"- human_likeness: {human_likeness}\n"
            f"- reader_desire: {reader_desire}\n"
            f"- emotional_residue: {emotional_residue}\n"
            f"- next_chapter_pull: {next_pull}\n\n"
            "## Findings\n"
            + "\n".join(findings)
            + "\n\n"
            + section
            + "\n"
        )

    def _review_round(
        self,
        slug: str,
        chapter: int,
        writer_session: SessionIdentity,
        request: WorkflowRequest,
    ) -> tuple[tuple[str, ...], str, int]:
        book_dir = self.root / "books" / slug
        prose = book_project.find_chapter_file(
            book_dir, chapter
        ).read_text(encoding="utf-8-sig")
        blind_session, blind, blind_text, blind_retries = (
            self._run_review_role(
                slug,
                chapter,
                role="blind-reader",
                context={"prose": prose},
            )
        )
        blind_record = self._record_review_text(
            slug, chapter, "blind-reader", blind_text
        )
        blind_binding = book_project.review_binding(
            self.root,
            slug,
            chapter,
            role="blind-reader",
        )
        record_session_completion(
            self.root,
            slug,
            session_id=blind_session.session_id,
            session_instance_id=blind_session.session_instance_id,
            role="blind-reader",
            provider=blind_session.provider,
            model=blind_session.model,
            agent_harness=blind_session.agent_harness,
            context_scope="prose_only",
            operation_kind=str(blind.operation_kind),
            operation_id=str(blind.operation_id),
            result_transport=str(blind.result_transport),
            chapter=chapter,
            generation_id=blind_binding["generation_id"],
            content_sha256=blind_binding["chapter_sha256"],
            artifact=book_dir / blind_record["review_file"],
            workflow_authority=self._workflow_authority,
        )
        scene = (
            book_dir / f"planning/scene-package-ch{chapter:02d}.md"
        ).read_text(encoding="utf-8-sig")
        canon_parts = [
            path.read_text(encoding="utf-8-sig")
            for path in sorted((book_dir / "memory/canon").rglob("*.md"))
        ]
        editor_context = {
            "prose": prose,
            "scene_package": scene,
            "story_contract": self._story_contract(request, chapter),
            "canon": "\n".join(canon_parts)[:12000],
            "blind_review": blind_text,
            "machine_diagnostics": self._machine_diagnostics(
                book_project.run_gates(
                    self.root,
                    slug,
                    chapter,
                    expected_mode="formal",
                )
            ),
        }
        if chapter > 1:
            previous_text = book_project.find_chapter_file(
                book_dir, chapter - 1
            ).read_text(encoding="utf-8-sig")
            editor_context["previous_chapter_ending"] = previous_text[
                max(0, int(len(previous_text) * 0.8)) :
            ]
        editor_session, editor, editor_text, editor_retries = (
            self._run_review_role(
                slug,
                chapter,
                role="chapter-editor",
                context=editor_context,
            )
        )
        editor_record = self._record_review_text(
            slug, chapter, "chapter-editor", editor_text
        )
        editor_binding = book_project.review_binding(
            self.root,
            slug,
            chapter,
            role="chapter-editor",
        )
        record_session_completion(
            self.root,
            slug,
            session_id=editor_session.session_id,
            session_instance_id=editor_session.session_instance_id,
            role="chapter-editor",
            provider=editor_session.provider,
            model=editor_session.model,
            agent_harness=editor_session.agent_harness,
            context_scope="full_review_context",
            operation_kind=str(editor.operation_kind),
            operation_id=str(editor.operation_id),
            result_transport=str(editor.result_transport),
            chapter=chapter,
            generation_id=editor_binding["generation_id"],
            content_sha256=editor_binding["chapter_sha256"],
            artifact=book_dir / editor_record["review_file"],
            workflow_authority=self._workflow_authority,
        )
        must = tuple(
            dict.fromkeys(
                self._patch_directive(item)
                for outcome in (blind, editor)
                for item in outcome.findings
                if item.severity.upper() == "MUST"
                and item.status.lower() == "open"
            )
        )
        return must, editor_text, blind_retries + editor_retries

    def _run_review_role(
        self,
        slug: str,
        chapter: int,
        *,
        role: str,
        context: dict[str, str],
    ) -> tuple[SessionIdentity, ReviewOutcome, str, int]:
        """Run one reviewer in fresh sessions until a valid result arrives."""
        for attempt in range(self.max_technical_retries + 1):
            try:
                session = self._new_session(role)
                outcome = self._role_call(
                    lambda: self.backend.run_review(
                        session,
                        role=role,
                        context=context,
                        instructions=render_review_instructions(role).text,
                        reasoning_effort="medium",
                    )
                )
                if outcome.resolved_model:
                    session = replace(
                        session,
                        model=outcome.resolved_model,
                    )
                if (
                    outcome.terminal_role != role
                    or outcome.terminal_session_id != session.session_id
                    or outcome.terminal_session_instance_id
                    != session.session_instance_id
                    or not outcome.operation_id
                    or not outcome.operation_kind
                    or not outcome.result_transport
                ):
                    raise WorkflowError(
                        "审稿结果没有绑定当前原生角色会话终态。"
                    )
                text = self._render_review(
                    slug,
                    chapter,
                    role,
                    session,
                    outcome,
                )
                return session, outcome, text, attempt
            except WorkflowError:
                if attempt >= self.max_technical_retries:
                    raise ReviewSessionExhausted(role, attempt)
                self.on_status(
                    "审稿会话异常，已自动换新会话重试。"
                )
        raise ReviewSessionExhausted(
            role,
            self.max_technical_retries,
        )

    @staticmethod
    def _patch_directive(item: ReviewFinding) -> str:
        """Compile one evidence-aware, bounded Patch Writer obligation."""
        def clean(value: str, limit: int) -> str:
            return re.sub(r"\s+", " ", value).strip(" |｜")[:limit]

        return (
            f"{clean(item.location, 48)}｜"
            f"原文：{clean(item.evidence, 96)}｜"
            f"读者效果：{clean(item.reader_effect, 96)}｜"
            f"修订目标：{clean(item.revision_intent, 128)}"
        )

    @staticmethod
    def _machine_diagnostics(gates: dict[str, Any]) -> str:
        """Render a bounded editor-only summary without exposing it to Blind Reader."""
        lines = [
            "机器诊断只提供定位，不替代文学判断，也不得按数值机械改稿。"
        ]
        quality = gates.get("quality")
        if isinstance(quality, dict):
            for finding in quality.get("findings", [])[:12]:
                if not isinstance(finding, dict):
                    continue
                lines.append(
                    "- line "
                    f"{finding.get('line_number')}: "
                    f"{finding.get('rule_code')} / "
                    f"{finding.get('message')} / "
                    f"{finding.get('evidence')}"
                )
        literary = gates.get("literary")
        if isinstance(literary, dict):
            for finding in literary.get("findings", [])[:8]:
                if not isinstance(finding, dict):
                    continue
                lines.append(
                    f"- {finding.get('code')}: "
                    f"{finding.get('detail') or finding.get('message')}"
                )
        return "\n".join(lines)[:4000]

    def _record_review_text(
        self,
        slug: str,
        chapter: int,
        role: str,
        text: str,
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".md",
            delete=False,
        ) as handle:
            handle.write(text)
            source = Path(handle.name)
        try:
            return book_project.record_review(
                self.root,
                slug,
                chapter,
                role,
                source,
            )
        finally:
            source.unlink(missing_ok=True)

    def _decision_result(
        self,
        slug: str,
        request: WorkflowRequest,
        chapter: int,
        sequence_id: str,
        *,
        message: str,
        retries: int,
        decision_kind: str,
        must_findings: tuple[str, ...] = (),
        parent_generation_id: str | None = None,
        resume_context: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        self._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="decision_required",
            retries=retries,
            decision_kind=decision_kind,
            decision_message=message,
            must_findings=must_findings,
            parent_generation_id=parent_generation_id,
            resume_context=resume_context,
        )
        return _user_result(
            "decision_required",
            message,
            sequence_id,
            retries=retries,
            options=USER_OPTIONS,
        )

    def _finish_chapter(
        self,
        slug: str,
        request: WorkflowRequest,
        chapter: int,
        sequence_id: str,
        writer_session: SessionIdentity,
        retries: int,
    ) -> WorkflowResult:
        attest_chapter_ready_candidate(
            self.root,
            slug,
            sequence_id,
            writer_session.session_id,
            workflow_authority=self._workflow_authority,
        )
        book_project.advance_state(
            self.root,
            slug,
            chapter,
            "ready",
            evidence="automatic-workflow/current",
            create_git_checkpoint=False,
            workflow_authority=self._workflow_authority,
        )
        try:
            advance_chapter_sequence(
                self.root,
                slug,
                sequence_id,
                writer_session.session_id,
            )
        except Exception:
            book_project.advance_state(
                self.root,
                slug,
                chapter,
                "editorial_reviewed",
                evidence=f"reviews/ch{chapter:02d}-chapter-editor.md",
            )
            return self._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="本章尚未形成可恢复版本，请选择下一步。",
                retries=retries,
                decision_kind="sequence_finalization_failed",
            )
        sequence = chapter_sequence_status(
            self.root, slug, sequence_id
        )
        if sequence["effective_status"] != "complete":
            book_project.advance_state(
                self.root,
                slug,
                chapter,
                "editorial_reviewed",
                evidence=f"reviews/ch{chapter:02d}-chapter-editor.md",
            )
            return self._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="本章状态尚未一致，请选择下一步。",
                retries=retries,
                decision_kind="sequence_inconsistent",
            )
        self._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="complete",
            retries=retries,
        )
        checkpoint = checkpoint_book(
            self.root,
            slug,
            f"chapter: ch{chapter:02d} ready",
            tag=(
                f"checkpoint/ch{chapter - 4:02d}-ch{chapter:02d}"
                if chapter % 5 == 0
                else None
            ),
        )
        git_ok = (
            checkpoint.get("commit_hash") is not None
            and checkpoint.get("remote_count") == 0
            and book_git_status(self.root, slug).get("dirty") is False
        )
        if not git_ok:
            book_project.advance_state(
                self.root,
                slug,
                chapter,
                "editorial_reviewed",
                evidence=f"reviews/ch{chapter:02d}-chapter-editor.md",
            )
            return self._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="本章尚未形成可恢复版本，请选择下一步。",
                retries=retries,
                decision_kind="git_checkpoint_failed",
            )
        return _user_result(
            "chapter_complete",
            f"第{_chapter_label(chapter)}章完成，"
            f"是否继续第{_chapter_label(chapter + 1)}章？",
            sequence_id,
            retries=retries,
            git_ok=True,
        )

    def _run_sequence(
        self,
        slug: str,
        request: WorkflowRequest,
        chapter: int,
        sequence_id: str,
        *,
        initial_writer_session: SessionIdentity | None = None,
    ) -> WorkflowResult:
        initial = self._execute_generation(
            slug,
            chapter,
            sequence_id,
            must_findings=(),
            parent_generation_id=None,
            initial_session=initial_writer_session,
        )
        if initial is None:
            retries = self.max_technical_retries
            return self._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="自动重试仍未完成，请选择下一步。",
                retries=retries,
                decision_kind="initial_generation_failed",
            )
        writer_session, generation_id, retries = initial
        self._finalize_scene_handoff(slug, chapter)
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
        return self._review_after_generation(
            slug,
            request,
            chapter,
            sequence_id,
            writer_session,
            generation_id,
            retries,
            allow_patch=True,
        )

    def _review_after_generation(
        self,
        slug: str,
        request: WorkflowRequest,
        chapter: int,
        sequence_id: str,
        writer_session: SessionIdentity,
        generation_id: str,
        retries: int,
        *,
        allow_patch: bool,
    ) -> WorkflowResult:
        """Complete review, optional single patch, and ready finalization."""
        self.on_status("正在自动审稿。")
        try:
            must, _, review_retries = self._review_round(
                slug, chapter, writer_session, request
            )
        except ReviewSessionExhausted as exc:
            return self._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="自动重试仍未完成，请选择下一步。",
                retries=retries + exc.retry_count,
                decision_kind="review_session_failed",
                parent_generation_id=generation_id,
                resume_context={
                    "writer_session": asdict(writer_session),
                    "generation_id": generation_id,
                    "allow_patch": allow_patch,
                    "failed_role": exc.role,
                },
            )
        retries += review_retries
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
            if not allow_patch:
                rotate_chapter_session(
                    self.root,
                    slug,
                    sequence_id,
                    writer_session.session_id,
                    reason="additional_human_regeneration_required",
                )
                return self._decision_result(
                    slug,
                    request,
                    chapter,
                    sequence_id,
                    message="自动修订后仍有问题，请选择下一步。",
                    retries=retries,
                    decision_kind="literary_revision_required",
                    must_findings=must,
                    parent_generation_id=generation_id,
                )
            self.on_status("发现问题，正在自动修订。")
            rotate_chapter_session(
                self.root,
                slug,
                sequence_id,
                writer_session.session_id,
            )
            patched = self._execute_generation(
                slug,
                chapter,
                sequence_id,
                must_findings=must,
                parent_generation_id=generation_id,
            )
            if patched is None:
                total_retries = retries + self.max_technical_retries
                return self._decision_result(
                    slug,
                    request,
                    chapter,
                    sequence_id,
                    message="自动重试仍未完成，请选择下一步。",
                    retries=total_retries,
                    decision_kind="patch_generation_failed",
                    must_findings=must,
                    parent_generation_id=generation_id,
                )
            writer_session, generation_id, patch_retries = patched
            self._finalize_scene_handoff(slug, chapter)
            retries += patch_retries
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
            return self._review_after_generation(
                slug,
                request,
                chapter,
                sequence_id,
                writer_session,
                generation_id,
                retries,
                allow_patch=False,
            )
        return self._finish_chapter(
            slug,
            request,
            chapter,
            sequence_id,
            writer_session,
            retries,
        )

    def status(self, slug: str) -> WorkflowResult:
        path = self._control_path(slug)
        if not path.is_file():
            raise WorkflowError("还没有开始自动写作。")
        control = json.loads(path.read_text(encoding="utf-8"))
        phase = control.get("phase")
        sequence_id = str(control.get("sequence_id") or "")
        chapter = int(control.get("chapter") or 1)
        if phase == "complete":
            sequence = chapter_sequence_status(
                self.root, slug, sequence_id
            )
            project = book_project.project_status(
                self.root,
                slug,
                chapter,
            )
            chapter_state = next(
                (
                    item
                    for item in project.get("chapters", [])
                    if item.get("chapter") == f"ch{chapter:02d}"
                ),
                {},
            )
            if (
                sequence.get("effective_status") == "complete"
                and chapter_state.get("effective_status") == "ready"
                and project.get("workflow_integrity", {}).get("status")
                != "blocked"
            ):
                return _user_result(
                    "chapter_complete",
                    f"第{_chapter_label(chapter)}章完成，"
                    f"是否继续第{_chapter_label(chapter + 1)}章？",
                    sequence_id,
                    retries=int(
                        control.get("technical_retry_count") or 0
                    ),
                    git_ok=True,
                )
            return _user_result(
                "running",
                "本章状态尚未一致，系统正在重新核验。",
                sequence_id,
                retries=int(control.get("technical_retry_count") or 0),
            )
        if phase == "decision_required":
            return _user_result(
                "decision_required",
                str(
                    control.get("decision_message")
                    or "自动重试仍未完成，请选择下一步。"
                ),
                sequence_id,
                retries=int(control.get("technical_retry_count") or 0),
                options=USER_OPTIONS,
            )
        if phase == "stopped":
            return _user_result("stopped", "任务已停止。", sequence_id)
        return _user_result("running", "正在自动处理本章。", sequence_id)

    def retry(self, slug: str) -> WorkflowResult:
        """Resume a failed chapter with a new native writer session."""
        path = self._control_path(slug)
        if not path.is_file():
            raise WorkflowError("还没有开始自动写作。")
        control = json.loads(path.read_text(encoding="utf-8"))
        if control.get("phase") != "decision_required":
            return self.status(slug)
        request_data = control.get("request")
        if not isinstance(request_data, dict):
            raise WorkflowError("自动流程缺少章节架构。")
        request = WorkflowRequest(**request_data)
        chapter = int(control.get("chapter") or 1)
        sequence_id = str(control.get("sequence_id") or "")
        decision_kind = str(control.get("decision_kind") or "")
        previous_retries = int(
            control.get("technical_retry_count") or 0
        )
        if decision_kind == "review_session_failed":
            resume = control.get("resume_context")
            if not isinstance(resume, dict):
                raise WorkflowError("自动流程缺少审稿恢复信息。")
            writer_data = resume.get("writer_session")
            if not isinstance(writer_data, dict):
                raise WorkflowError("自动流程缺少 Writer 会话信息。")
            try:
                writer_session = SessionIdentity(**writer_data)
                generation_id = str(resume["generation_id"])
                allow_patch = bool(resume["allow_patch"])
            except (KeyError, TypeError) as exc:
                raise WorkflowError("自动流程缺少审稿恢复信息。") from exc
            self._save_control(
                slug,
                request=request,
                chapter=chapter,
                sequence_id=sequence_id,
                phase="reviewing",
                retries=previous_retries,
            )
            return self._review_after_generation(
                slug,
                request,
                chapter,
                sequence_id,
                writer_session,
                generation_id,
                previous_retries,
                allow_patch=allow_patch,
            )
        sequence = chapter_sequence_status(
            self.root, slug, sequence_id
        )
        if sequence.get("effective_status") != "awaiting_session":
            return _user_result(
                "decision_required",
                "当前草稿需要人工选择保留、重写或停止。",
                sequence_id,
                options=USER_OPTIONS,
            )
        must_findings = tuple(
            str(item)
            for item in control.get("must_findings", [])
            if str(item).strip()
        )
        parent_generation_id = (
            str(control["parent_generation_id"])
            if control.get("parent_generation_id")
            else None
        )
        self._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="writing",
            retries=previous_retries,
        )
        if decision_kind == "initial_generation_failed":
            return self._run_sequence(slug, request, chapter, sequence_id)
        if decision_kind not in {
            "patch_generation_failed",
            "literary_revision_required",
        }:
            return self._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="当前草稿需要人工选择保留、重写或停止。",
                retries=previous_retries,
                decision_kind=decision_kind or "manual_decision_required",
                must_findings=must_findings,
                parent_generation_id=parent_generation_id,
            )
        patched = self._execute_generation(
            slug,
            chapter,
            sequence_id,
            must_findings=must_findings,
            parent_generation_id=parent_generation_id,
            human_decision_reference=(
                "automatic-workflow:user-selected-regenerate"
                if decision_kind == "literary_revision_required"
                else None
            ),
        )
        if patched is None:
            return self._decision_result(
                slug,
                request,
                chapter,
                sequence_id,
                message="自动重试仍未完成，请选择下一步。",
                retries=previous_retries + self.max_technical_retries,
                decision_kind=decision_kind,
                must_findings=must_findings,
                parent_generation_id=parent_generation_id,
            )
        writer_session, generation_id, patch_retries = patched
        retries = previous_retries + patch_retries
        self._finalize_scene_handoff(slug, chapter)
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
        return self._review_after_generation(
            slug,
            request,
            chapter,
            sequence_id,
            writer_session,
            generation_id,
            retries,
            allow_patch=False,
        )

    def stop(self, slug: str) -> WorkflowResult:
        path = self._control_path(slug)
        if not path.is_file():
            raise WorkflowError("还没有开始自动写作。")
        control = json.loads(path.read_text(encoding="utf-8"))
        control["phase"] = "stopped"
        control["updated_at"] = _now()
        _atomic_json(path, control)
        return _user_result(
            "stopped",
            "任务已停止。",
            str(control.get("sequence_id") or ""),
        )


def _print_result(result: WorkflowResult) -> None:
    print(result.message)
    for option in result.options:
        print(option)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Novel Forge 原生会话接力工作流；无命令桥时由 Skill 驱动宿主 "
            "Roles，可选命令 Backend 仅用于 headless"
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Novel Forge 项目根目录。",
    )
    parser.add_argument(
        "--strict-audit",
        action="store_true",
        help="启用完整运行遥测与仓库级审计；日常创作默认关闭。",
    )
    sub = parser.add_subparsers(dest="operation", required=True)
    start = sub.add_parser("start")
    start.add_argument("slug")
    start.add_argument("--chapter", type=int, default=1)
    start.add_argument("--title", required=True)
    start.add_argument("--genre", required=True)
    start.add_argument("--protagonist", required=True)
    start.add_argument("--world", required=True)
    start.add_argument("--conflict", required=True)
    start.add_argument("--hook", required=True)
    for name in ("status", "retry", "stop", "next-action"):
        command = sub.add_parser(name)
        command.add_argument("slug")
    complete = sub.add_parser("complete-role")
    complete.add_argument("slug")
    complete.add_argument("--from-file", type=Path)
    complete.add_argument("--session-id")
    complete.add_argument("--session-instance-id")
    complete.add_argument("--provider", default="unknown")
    complete.add_argument("--model", default="unknown")
    complete.add_argument("--agent-harness", default="native-host")
    args = parser.parse_args(argv)
    try:
        from .native_relay import NativeWorkflowRelay

        relay = NativeWorkflowRelay(
            args.root,
            strict_audit=args.strict_audit,
        )
        if args.operation == "next-action":
            action = relay.next_action(args.slug)
            print(json.dumps(action, ensure_ascii=False, sort_keys=True))
            return 0
        if args.operation == "complete-role":
            if not args.strict_audit:
                result = relay.complete_minimal(
                    args.slug,
                    session_id=args.session_id,
                    session_instance_id=args.session_instance_id,
                    provider=args.provider,
                    model=args.model,
                    agent_harness=args.agent_harness,
                    result_file=args.from_file,
                )
            else:
                if args.from_file is None:
                    raise WorkflowError(
                        "严格审计 complete-role 必须提供 --from-file。"
                    )
                completion = json.loads(
                    args.from_file.read_text(encoding="utf-8")
                )
                if not isinstance(completion, dict):
                    raise WorkflowError("原生角色终态必须是 JSON 对象。")
                result = relay.complete_role(
                    args.slug,
                    completion,
                )
            _print_result(result)
            return 0 if result.user_state != "decision_required" else 2
        command_backend = bool(
            os.environ.get("NOVEL_FORGE_HARNESS_COMMAND", "").strip()
        )
        if args.operation == "start" and not command_backend:
            result = relay.start(
                args.slug,
                WorkflowRequest(
                    title=args.title,
                    genre=args.genre,
                    protagonist=args.protagonist,
                    world=args.world,
                    conflict=args.conflict,
                    ending_hook=args.hook,
                ),
                chapter=args.chapter,
            )
            _print_result(result)
            return 0
        if args.operation == "retry" and not command_backend:
            result = relay.retry(args.slug)
            _print_result(result)
            return 0 if result.user_state != "decision_required" else 2
        if args.operation == "stop":
            result = relay.stop(args.slug)
            _print_result(result)
            return 0
        backend: SessionBackend
        if args.operation in {"start", "retry"}:
            backend = CommandSessionBackend.from_environment(args.root)
        else:
            backend = _UnavailableBackend()
        orchestrator = NovelWorkflowOrchestrator(
            args.root,
            backend,
            on_status=print,
        )
        if args.operation == "start":
            result = orchestrator.start(
                args.slug,
                WorkflowRequest(
                    title=args.title,
                    genre=args.genre,
                    protagonist=args.protagonist,
                    world=args.world,
                    conflict=args.conflict,
                    ending_hook=args.hook,
                ),
                chapter=args.chapter,
            )
        elif args.operation == "status":
            result = orchestrator.status(args.slug)
        elif args.operation == "stop":
            result = orchestrator.stop(args.slug)
        else:
            result = orchestrator.retry(args.slug)
        _print_result(result)
        return 0 if result.user_state != "decision_required" else 2
    except BackendUnavailableError:
        print("自动写作环境尚未就绪，本章没有开始。")
        return 2
    except (NovelForgeError, OSError, ValueError):
        print("自动流程暂时无法继续，请稍后重试。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
