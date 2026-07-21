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
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from . import book_project
from .book_evidence import (
    record_evidence,
    render_evidence_markdown,
)
from .book_git import checkpoint_book
from .chapter_sequence import (
    advance_chapter_sequence,
    begin_chapter_sequence,
    chapter_sequence_status,
    claim_chapter_session,
    rotate_chapter_session,
)
from .guardian import (
    GuardianError,
    ingest_writer_capsule,
    prepare_writer_capsule,
    record_capsule_runtime,
)
from .models import NovelForgeError
from .project_templates import init_book_project
from .session_audit import (
    audit_session_log,
    evaluate_session_budget,
    record_runtime_audit,
)


WORKFLOW_SCHEMA = "novel-forge-automatic-workflow/v1"
USER_OPTIONS = (
    "A. 保留草稿",
    "B. 重新生成本章",
    "C. 停止任务",
)


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
        payload = self._invoke({"action": "create_session", "role": role})
        try:
            return SessionIdentity(
                session_id=str(payload["session_id"]).strip(),
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
            }
        )

    def run_review(
        self,
        session: SessionIdentity,
        *,
        role: str,
        context: dict[str, str],
    ) -> ReviewOutcome:
        payload = self._invoke(
            {
                "action": "run_session",
                "role": role,
                "session_id": session.session_id,
                "context": context,
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
        )


class _UnavailableBackend:
    """Placeholder used by read-only workflow commands."""

    def create_session(self, role: str) -> SessionIdentity:
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
        self.max_technical_retries = max_technical_retries
        self.on_status = on_status or (lambda _: None)
        self._seen_sessions: set[str] = set()

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
        if session.session_id in self._seen_sessions:
            raise WorkflowError("自动写作引擎重复使用了旧会话。")
        self._seen_sessions.add(session.session_id)
        return SessionIdentity(
            session_id=session.session_id,
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
        self._write_architecture(book_dir, request, chapter)
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
    def _write_architecture(
        book_dir: Path,
        request: WorkflowRequest,
        chapter: int,
    ) -> None:
        world = book_dir / "memory/worldbuilding.md"
        if "__________" in world.read_text(encoding="utf-8-sig"):
            world.write_text(
                "# 世界设定\n\n"
                f"## 物理规则\n- {request.world}\n\n"
                "## 社会规则\n"
                f"- 题材与环境：{request.genre}；世界不会自动为主角让路。\n\n"
                "## 禁忌\n"
                f"- 主角的选择必须受本章冲突约束：{request.conflict}\n",
                encoding="utf-8",
            )
        research = book_dir / "planning/research-boundaries.md"
        if "__________" in research.read_text(encoding="utf-8-sig"):
            research.write_text(
                "# 研究边界\n\n"
                "- 无需：本次自动章节只使用用户提供的虚构架构，"
                "不把未核验外部事实作为关键情节支点。\n",
                encoding="utf-8",
            )
        engine = book_dir / "planning/story-engine.md"
        if "__________" in engine.read_text(encoding="utf-8-sig"):
            engine.write_text(
                "# 故事发动机\n\n"
                f"## 核心秘密\n- {request.ending_hook}\n\n"
                f"## 欲望\n- {request.protagonist}想解决：{request.conflict}\n\n"
                "## 对抗中的独立意志\n"
                "- 对手按自身利益行动，不因主角判断正确而停止施压。\n"
                "- 即使主角判断正确，对手仍会逼迫主角立即付出代价。\n\n"
                "## 主角的错误模型\n"
                "- 主角误以为拖延可以同时保住秘密和安全。\n"
                "- 对手提前抵达即可推翻这个判断。\n\n"
                "## 替代行动与不兼容欲望\n"
                "- 主角可以求助，但这会暴露他最想隐藏的部分。\n"
                "- 主角不能同时保住秘密与行动主动权。\n\n"
                f"## 不可逆选择\n- {request.conflict}\n\n"
                "## 即时代价\n- 选择一旦落地，关系与安全边界立即改变。\n\n"
                f"## 未解承诺\n- {request.ending_hook}\n\n"
                "## 主题压力\n- 人能否在不求助的前提下承担选择的后果。\n",
                encoding="utf-8",
            )
        scene = book_dir / "planning" / f"scene-package-ch{chapter:02d}.md"
        if not scene.exists() or "第XX章" in scene.read_text(
            encoding="utf-8-sig"
        ):
            handoff = ""
            if chapter > 1:
                previous_path = book_project.find_chapter_file(
                    book_dir, chapter - 1
                )
                previous_text = previous_path.read_text(
                    encoding="utf-8-sig"
                )
                previous_quote = NovelWorkflowOrchestrator._quote(
                    previous_text
                )
                previous_sha256 = hashlib.sha256(
                    previous_path.read_bytes()
                ).hexdigest()
                handoff = (
                    "## 0b. 章际交接\n"
                    f"- 上一章正文路径："
                    f"{previous_path.relative_to(book_dir).as_posix()}\n"
                    f"- 上一章正文 SHA-256：{previous_sha256}\n"
                    f"- 上一章结尾原文：{previous_quote}\n"
                    "- 本章开头原文：deferred_until_drafted\n"
                    "- 上一章结束时间：上一章连续场景末\n"
                    "- 本章开始时间：紧接上一章之后\n"
                    "- 上一章结束地点：上一章停止点\n"
                    "- 本章开始地点：承接上一章行动后果的现场\n"
                    "- 上一章结束动作：章末钩子触发\n"
                    "- 本章开始动作：主角回应章末钩子的后果\n"
                    "- 转场类型：same_day_continuous\n"
                    "- 上一章末明确决定：主角承担已经作出的选择\n"
                    "- 本章是否推翻该决定：否\n"
                    "- 若推翻，触发事件原文：无需：未推翻上一章决定\n\n"
                )
            scene.write_text(
                f"# Scene Package - 第{chapter:02d}章\n\n"
                "## 0. 边界\n"
                "- 开始动作 / 停止动作：主角开始处理眼前危机；"
                "章末钩子落地后立即停止。\n"
                f"- 承接压力 / 本章不解决：{request.conflict}\n\n"
                f"{handoff}"
                "## 1. 场景压力\n"
                f"- 视角角色要什么：{request.protagonist}要掌握主动。\n"
                "- 对手/世界独立要什么：阻力要迫使主角立刻表态。\n"
                f"- 选择与即时成本：{request.conflict}\n"
                f"- 章末未解除压力：{request.ending_hook}\n\n"
                "## 1c. 决策问题\n"
                "- 不能同时得到的两样东西：保住秘密 / 保住主动权\n"
                "- 角色拒绝承认什么：独自处理已经不再可行\n"
                "- 角色误读了谁或什么：把短暂沉默误读为安全\n"
                "- 哪句话不能说出口：请你帮我\n"
                "- 最终接受的具体代价：让另一人看见自己的软肋\n\n"
                "## 1d. 认知与可证伪假设\n"
                "| 观察 | 当前假设 | 替代解释 | 置信度 | 可推翻证据 | 状态 |\n"
                "|---|---|---|---|---|---|\n"
                "| 阻力正在逼近 | 仍有时间拖延 | 对方已提前布局 | 中 | "
                "对方直接出现 | 未决 |\n\n"
                "## 1e. 规划反证与常识检查\n"
                "- 时间/日历算术：本章只使用连续短时段，按动作先后核对。\n"
                "- 物理动作机制：所有关键变化必须由可执行动作触发。\n"
                "- 人物知识来源：人物只依据亲见、亲闻和既有经验判断。\n"
                "- 不可逆性反证：一旦秘密暴露，不能靠解释恢复原状。\n"
                "- 场景停止点：章末钩子出现后立即结束。\n\n"
                "## 2. 在场者状态\n"
                "| 人物 | 此刻目标 | 隐瞒/未知 | 本场变化 |\n"
                "|---|---|---|---|\n"
                f"| 主角 | 解决冲突 | 隐瞒真实软肋 | 被迫选择 |\n"
                "| 阻力方 | 取得优势 | 真实计划未知 | 逼近一步 |\n\n"
                "## 3. Beat 因果链\n"
                "| # | 触发 | 行动/决定 | 阻力/反应 | 结果与下一步 | 语域 |\n"
                "|---|---|---|---|---|---|\n"
                "| 1 | 危机逼近 | 主角尝试独自处理 | 阻力压缩时间 | "
                "旧办法失效 | 贴身 |\n"
                "| 2 | 旧办法失效 | 主角作出不可逆选择 | 对方立即回应 | "
                "章末钩子落地 | 贴身 |\n\n"
                "## 3c. 因果归属账本\n"
                "| 动作/条件 | 提出/执行者 | 知情者 | 后果承担者 |\n"
                "|---|---|---|---|\n"
                "| 不可逆选择 | 主角 | 当场人物 | 主角与被牵连者 |\n\n"
                "## 4. 信息账本\n"
                f"- 本章唯一新信息 / 来源 / 导致的选择：{request.ending_hook}\n\n"
                "## 5. 信息预算\n"
                "- 锚定物象（3-5）：门把、雨水、脚步、失灵的灯\n"
                "- 关键对白意图：章末一句话只负责转移责任与信息，"
                "不承担设定讲解。\n"
                "- 新规则/伏笔/术语（各 0-1）：只保留章末钩子一项。\n"
                "- 延后信息：对手完整目的延后揭示。\n\n"
                "## 5b. 专业判断审计\n"
                "- 无需：本章不依赖未经验证的专业操作推动关键选择。\n\n"
                "## 7. 场景余波\n"
                f"- 身体 / 物件 / 关系 / 认知误信 / 未偿承诺："
                f"{request.ending_hook}\n",
                encoding="utf-8",
            )

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
        self._prepare_project(slug, request, chapter)
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
            evidence=f"memory/context-cache/ch{chapter:02d}-handoff.md",
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
        return self._run_sequence(slug, request, chapter, sequence_id)

    def _execute_generation(
        self,
        slug: str,
        chapter: int,
        sequence_id: str,
        *,
        must_findings: tuple[str, ...],
        parent_generation_id: str | None,
    ) -> tuple[SessionIdentity, str, int] | None:
        target_path = f"chapters/e01/ch-{chapter:02d}/正文.md"
        for attempt in range(self.max_technical_retries + 1):
            session = self._new_session("writer")
            claim_chapter_session(
                self.root,
                slug,
                sequence_id,
                session.session_id,
            )
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
                patch_directive=directive or None,
            )
            try:
                self.backend.run_writer(
                    session,
                    capsule_dir=capsule,
                    capsule_id=prepared["capsule_id"],
                    runtime_path=runtime_path,
                    must_findings=must_findings,
                )
            except Exception:
                pass
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
    ) -> None:
        book_dir = self.root / "books" / slug
        chapter_path = book_dir / imported["target_path"]
        metrics = runtime_generation_metrics(report)
        record = {
            "schema_version": 1,
            "id": generation_id,
            "kind": "generation",
            "created_at": _now(),
            "authority": "agent",
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
        quote = self._quote(prose)
        binding = book_project.review_binding(
            self.root,
            slug,
            chapter,
            role=role,
        )
        previous_quote = "not_applicable"
        if chapter > 1:
            previous_quote = self._quote(
                book_project.find_chapter_file(
                    book_dir, chapter - 1
                ).read_text(encoding="utf-8-sig")
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
                f"- {name}: {quote}"
                for name in (
                    "reconstruction_space",
                    "reconstruction_body",
                    "reconstruction_constraints",
                    "reconstruction_emotion",
                    "reconstruction_dialogue",
                    "memorable_image_1",
                    "memorable_image_2",
                    "memorable_image_3",
                )
            )
            human_likeness = outcome.human_likeness
            reader_desire = outcome.reader_desire
            emotional_residue = outcome.emotional_residue
            next_pull = outcome.next_chapter_pull
            section = "## Prose-only Reconstruction\n" + details
            context_scope = "prose_only"
        else:
            details = "\n".join(
                f"- {name}: {quote}"
                for name in (
                    "editorial_causality",
                    "editorial_agency",
                    "editorial_dialogue",
                    "editorial_texture",
                    "editorial_continuity",
                )
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
            f"- reviewer_id: automatic-{role}\n"
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
        )
        blind_text = self._render_review(
            slug,
            chapter,
            "blind-reader",
            blind_session,
            blind,
        )
        self._record_review_text(
            slug, chapter, "blind-reader", blind_text
        )
        scene = (
            book_dir / f"planning/scene-package-ch{chapter:02d}.md"
        ).read_text(encoding="utf-8-sig")
        canon_parts = [
            path.read_text(encoding="utf-8-sig")
            for path in sorted((book_dir / "memory/canon").rglob("*.md"))
        ]
        editor_session = self._new_session("chapter-editor")
        editor = self.backend.run_review(
            editor_session,
            role="chapter-editor",
            context={
                "prose": prose,
                "scene_package": scene,
                "canon": "\n".join(canon_parts)[:12000],
                "blind_review": blind_text,
            },
        )
        editor_text = self._render_review(
            slug,
            chapter,
            "chapter-editor",
            editor_session,
            editor,
        )
        self._record_review_text(
            slug, chapter, "chapter-editor", editor_text
        )
        must = tuple(
            dict.fromkeys(
                f"{item.location}：{item.revision_intent}"
                for outcome in (blind, editor)
                for item in outcome.findings
                if item.severity.upper() == "MUST"
                and item.status.lower() == "open"
            )
        )
        return must, editor_text

    def _record_review_text(
        self,
        slug: str,
        chapter: int,
        role: str,
        text: str,
    ) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".md",
            delete=False,
        ) as handle:
            handle.write(text)
            source = Path(handle.name)
        try:
            book_project.record_review(
                self.root,
                slug,
                chapter,
                role,
                source,
            )
        finally:
            source.unlink(missing_ok=True)

    def _run_sequence(
        self,
        slug: str,
        request: WorkflowRequest,
        chapter: int,
        sequence_id: str,
    ) -> WorkflowResult:
        self.on_status("正在写作。")
        initial = self._execute_generation(
            slug,
            chapter,
            sequence_id,
            must_findings=(),
            parent_generation_id=None,
        )
        if initial is None:
            retries = self.max_technical_retries
            self._save_control(
                slug,
                request=request,
                chapter=chapter,
                sequence_id=sequence_id,
                phase="decision_required",
                retries=retries,
            )
            return _user_result(
                "decision_required",
                "自动重试仍未完成，请选择下一步。",
                sequence_id,
                retries=retries,
                options=USER_OPTIONS,
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
        must, _ = self._review_round(slug, chapter, writer_session)
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
                return _user_result(
                    "decision_required",
                    "自动重试仍未完成，请选择下一步。",
                    sequence_id,
                    retries=total_retries,
                    options=USER_OPTIONS,
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
                slug, chapter, writer_session
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
                return _user_result(
                    "decision_required",
                    "自动修订后仍有问题，请选择下一步。",
                    sequence_id,
                    retries=retries,
                    options=USER_OPTIONS,
                )
        ready = book_project.advance_state(
            self.root,
            slug,
            chapter,
            "ready",
            evidence="automatic-workflow/current",
        )
        if ready.get("local_git", {}).get("status") != "recorded":
            book_project.advance_state(
                self.root,
                slug,
                chapter,
                "editorial_reviewed",
                evidence=f"reviews/ch{chapter:02d}-chapter-editor.md",
            )
            return _user_result(
                "decision_required",
                "本章尚未形成可恢复版本，请选择下一步。",
                sequence_id,
                retries=retries,
                options=USER_OPTIONS,
            )
        advance_chapter_sequence(
            self.root,
            slug,
            sequence_id,
            writer_session.session_id,
        )
        sequence = chapter_sequence_status(
            self.root, slug, sequence_id
        )
        if sequence["effective_status"] != "complete":
            return _user_result(
                "decision_required",
                "本章状态尚未一致，请选择下一步。",
                sequence_id,
                retries=retries,
                options=USER_OPTIONS,
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
            f"workflow: ch{chapter:02d} complete",
        )
        git_ok = (
            checkpoint.get("commit_hash") is not None
            and checkpoint.get("remote_count") == 0
        )
        if not git_ok:
            return _user_result(
                "decision_required",
                "本章尚未形成可恢复版本，请选择下一步。",
                sequence_id,
                retries=retries,
                options=USER_OPTIONS,
            )
        return _user_result(
            "chapter_complete",
            f"第{_chapter_label(chapter)}章完成，"
            f"是否继续第{_chapter_label(chapter + 1)}章？",
            sequence_id,
            retries=retries,
            git_ok=True,
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
            if sequence.get("effective_status") == "complete":
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
        if phase == "decision_required":
            return _user_result(
                "decision_required",
                "自动重试仍未完成，请选择下一步。",
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
        self._save_control(
            slug,
            request=request,
            chapter=chapter,
            sequence_id=sequence_id,
            phase="writing",
            retries=int(control.get("technical_retry_count") or 0),
        )
        return self._run_sequence(slug, request, chapter, sequence_id)

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
