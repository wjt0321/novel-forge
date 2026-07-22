"""Human-light orchestration for the three-role books workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from . import book_project
from .artifact_integrity import (
    _issue_workflow_authority,
    record_session_completion,
)
from .book_evidence import (
    record_evidence,
    render_evidence_markdown,
)
from .book_git import checkpoint_book
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
from .session_audit import (
    audit_session_log,
    evaluate_session_budget,
    record_runtime_audit,
)


WORKFLOW_SCHEMA = "novel-forge-automatic-workflow/v1"
DEFAULT_WRITER_COMPLETION_TIMEOUT_SECONDS = 1800.0
DEFAULT_WRITER_COMPLETION_POLL_SECONDS = 0.25
DEFAULT_WRITER_COMPLETION_STABLE_POLLS = 3
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


class WorkflowError(NovelForgeError):
    """Raised when automatic orchestration cannot continue."""


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
class SessionIdentity:
    """A native session created by the configured external Harness."""

    session_id: str
    session_instance_id: str
    provider: str
    model: str
    agent_harness: str
    role: str = field(default="", compare=False)


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
    evidence_quote: str = ""
    previous_chapter_quote: str = "not_applicable"


@dataclass(frozen=True)
class PlanningOutcome:
    """Writer-authored mutable planning files for the current chapter."""

    files: dict[str, str]


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

    def create_session(self, role: str) -> SessionIdentity: ...

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
    ) -> None: ...

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

    def __init__(self, command: str | list[str]):
        if isinstance(command, str):
            self.command = shlex.split(command, posix=os.name != "nt")
        else:
            self.command = list(command)
        if not self.command:
            raise WorkflowError("未配置自动写作引擎。")

    @classmethod
    def from_environment(cls) -> "CommandSessionBackend":
        command = os.environ.get("NOVEL_FORGE_HARNESS_COMMAND", "").strip()
        if not command:
            raise WorkflowError("未配置自动写作引擎。")
        return cls(command)

    def _invoke(self, request: dict[str, Any]) -> dict[str, Any]:
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

    def create_session(self, role: str) -> SessionIdentity:
        payload = self._invoke(
            {
                "action": "create_session",
                "role": role,
                "requirements": {
                    "fresh_native_session": True,
                    "context_isolation": "required",
                },
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
    ) -> None:
        self._invoke(
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
            }
        )

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
            }
        )
        files = payload.get("files")
        if not isinstance(files, dict) or not all(
            isinstance(path, str) and isinstance(text, str)
            for path, text in files.items()
        ):
            raise WorkflowError("Writer 会话没有返回有效的章节规划。")
        return PlanningOutcome(files=dict(files))

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
            }
        )
        findings = tuple(
            ReviewFinding(
                severity=str(item.get("severity") or ""),
                location=str(item.get("location") or ""),
                evidence=str(item.get("evidence") or ""),
                reader_effect=str(item.get("reader_effect") or ""),
                revision_intent=str(item.get("revision_intent") or ""),
                status=str(item.get("status") or "open"),
            )
            for item in payload.get("findings", [])
            if isinstance(item, dict)
        )
        return ReviewOutcome(
            verdict=str(payload.get("verdict") or ""),
            findings=findings,
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
            analysis={
                str(name): str(value)
                for name, value in (payload.get("analysis") or {}).items()
                if isinstance(name, str) and isinstance(value, str)
            }
            if isinstance(payload.get("analysis"), dict)
            else {},
            evidence_quote=str(payload.get("evidence_quote") or ""),
            previous_chapter_quote=str(
                payload.get("previous_chapter_quote") or "not_applicable"
            ),
        )


class _UnavailableBackend:
    """Placeholder used by read-only workflow commands."""

    def create_session(self, role: str) -> SessionIdentity:
        raise WorkflowError("未配置自动写作引擎。")

    def run_planning(self, *args: Any, **kwargs: Any) -> PlanningOutcome:
        raise WorkflowError("未配置自动写作引擎。")

    def run_writer(self, *args: Any, **kwargs: Any) -> None:
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
        writer_completion_poll_seconds: float = (
            DEFAULT_WRITER_COMPLETION_POLL_SECONDS
        ),
        writer_completion_stable_polls: int = (
            DEFAULT_WRITER_COMPLETION_STABLE_POLLS
        ),
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
        if writer_completion_poll_seconds <= 0:
            raise WorkflowError("Writer 完成轮询间隔必须大于零。")
        if writer_completion_stable_polls < 1:
            raise WorkflowError("Writer 稳定输出采样次数必须至少为 1。")
        self.max_technical_retries = max_technical_retries
        self.writer_completion_timeout_seconds = (
            writer_completion_timeout_seconds
        )
        self.writer_completion_poll_seconds = writer_completion_poll_seconds
        self.writer_completion_stable_polls = writer_completion_stable_polls
        self.on_status = on_status or (lambda _: None)
        self._workflow_authority = _issue_workflow_authority()
        self._seen_sessions: set[str] = set()
        self._seen_session_instances: set[str] = set()

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
                "request": asdict(request),
                "updated_at": _now(),
                "author_approval": False,
                "publication_eligibility": False,
            },
        )

    def _new_session(self, role: str) -> SessionIdentity:
        session = self.backend.create_session(role)
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
        self.on_status("正在写作。")
        request.validate()
        writer_session = self._new_session("writer")
        book_dir = self._prepare_project(slug, request, chapter)
        planning = self.backend.run_planning(
            writer_session,
            request=request,
            chapter=chapter,
            context=self._planning_context(book_dir, chapter),
            instructions=render_planning_instructions().text,
            reasoning_effort="high",
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
            writer_launched = False
            try:
                self.backend.run_writer(
                    session,
                    capsule_dir=capsule,
                    capsule_id=prepared["capsule_id"],
                    runtime_path=runtime_path,
                    must_findings=must_findings,
                )
                writer_launched = True
            except Exception:
                pass
            writer_completed = False
            if writer_launched:
                writer_completed = self._wait_for_writer_completion(
                    capsule,
                    runtime_path,
                )
            if writer_launched and not writer_completed:
                reject_writer_capsule(
                    self.root,
                    slug,
                    prepared["capsule_id"],
                    reason="writer_completion_timeout",
                )
                if attempt < self.max_technical_retries:
                    self.on_status(
                        "写作会话异常，已自动换新会话重试。"
                    )
                    continue
                return None
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

    @staticmethod
    def _writer_output_snapshot(
        capsule: Path,
        runtime_path: Path,
    ) -> tuple[int, int, int, int] | None:
        draft = capsule / "draft/正文.md"
        if not draft.is_file() or not runtime_path.is_file():
            return None
        try:
            draft_stat = draft.stat()
            runtime_stat = runtime_path.stat()
        except OSError:
            return None
        if draft_stat.st_size <= 0 or runtime_stat.st_size <= 0:
            return None
        return (
            draft_stat.st_size,
            draft_stat.st_mtime_ns,
            runtime_stat.st_size,
            runtime_stat.st_mtime_ns,
        )

    def _wait_for_writer_completion(
        self,
        capsule: Path,
        runtime_path: Path,
    ) -> bool:
        """Wait until asynchronous Harness outputs exist and stop changing."""
        deadline = (
            time.monotonic() + self.writer_completion_timeout_seconds
        )
        previous: tuple[int, int, int, int] | None = None
        stable_polls = 0
        while True:
            snapshot = self._writer_output_snapshot(capsule, runtime_path)
            if snapshot is None:
                previous = None
                stable_polls = 0
            elif snapshot == previous:
                stable_polls += 1
            else:
                previous = snapshot
                stable_polls = 1
            if stable_polls >= self.writer_completion_stable_polls:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(
                min(self.writer_completion_poll_seconds, remaining)
            )

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
    ) -> None:
        book_dir = self.root / "books" / slug
        chapter_path = book_dir / imported["target_path"]
        metrics = runtime_generation_metrics(report)
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
            "metrics_source": "harness_reported",
            "generation_stage": "revised" if is_patch else "raw",
            "provenance_confidence": "harness_exposed",
            "sandbox_profile": "restricted",
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
            section = "## Editorial Dimensions\n" + details
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
    ) -> tuple[tuple[str, ...], str]:
        book_dir = self.root / "books" / slug
        prose = book_project.find_chapter_file(
            book_dir, chapter
        ).read_text(encoding="utf-8-sig")
        blind_session = self._new_session("blind-reader")
        blind = self.backend.run_review(
            blind_session,
            role="blind-reader",
            context={"prose": prose},
            instructions=render_review_instructions("blind-reader").text,
            reasoning_effort="medium",
        )
        blind_text = self._render_review(
            slug,
            chapter,
            "blind-reader",
            blind_session,
            blind,
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
        editor_session = self._new_session("chapter-editor")
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
        editor = self.backend.run_review(
            editor_session,
            role="chapter-editor",
            context=editor_context,
            instructions=render_review_instructions("chapter-editor").text,
            reasoning_effort="medium",
        )
        editor_text = self._render_review(
            slug,
            chapter,
            "chapter-editor",
            editor_session,
            editor,
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
        return must, editor_text

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
        self._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="complete",
            retries=retries,
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
        self.on_status("正在自动审稿。")
        must, _ = self._review_round(
            slug, chapter, writer_session, request
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
            self.on_status("正在自动审稿。")
            must, _ = self._review_round(
                slug, chapter, writer_session, request
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
        decision_kind = str(control.get("decision_kind") or "")
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
        previous_retries = int(
            control.get("technical_retry_count") or 0
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
        self.on_status("正在自动审稿。")
        must, _ = self._review_round(
            slug, chapter, writer_session, request
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
                message="重新生成后仍有问题，请选择下一步。",
                retries=retries,
                decision_kind="literary_revision_required",
                must_findings=must,
                parent_generation_id=generation_id,
            )
        return self._finish_chapter(
            slug,
            request,
            chapter,
            sequence_id,
            writer_session,
            retries,
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
        description="Novel Forge 自动三角色小说工作流"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Novel Forge 项目根目录。",
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
    for name in ("status", "retry", "stop"):
        command = sub.add_parser(name)
        command.add_argument("slug")
    args = parser.parse_args(argv)
    try:
        backend: SessionBackend
        if args.operation in {"start", "retry"}:
            backend = CommandSessionBackend.from_environment()
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
    except (NovelForgeError, OSError, ValueError):
        print("自动流程暂时无法继续，请稍后重试。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
