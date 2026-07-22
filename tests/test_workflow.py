"""Tests for the human-light three-role novel workflow."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from app.novel_forge import workflow as workflow_module
from app.novel_forge.book_evidence import evidence_status
from app.novel_forge.book_project import list_reviews, project_status
from app.novel_forge.chapter_sequence import chapter_sequence_status
from app.novel_forge.workflow import (
    NovelWorkflowOrchestrator,
    PlanningOutcome,
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
    completion_delay_seconds: float = 0.0


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
        self.review_instructions: list[tuple[str, str, str]] = []
        self.planning_calls: list[tuple[str, int]] = []
        self.planning_instructions: list[tuple[str, str]] = []
        self.writer_directives: list[tuple[str, tuple[str, ...]]] = []
        self.review_payloads: list[tuple[str, dict[str, str]]] = []
        self.background_threads: list[threading.Thread] = []
        self._role_counts: dict[str, int] = {}
        self._review_index = 0

    def create_session(self, role: str) -> SessionIdentity:
        count = self._role_counts.get(role, 0) + 1
        self._role_counts[role] = count
        session = SessionIdentity(
            session_id=f"native-{role}-{count:02d}",
            session_instance_id=f"instance-{role}-{count:02d}",
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
        self.writer_directives.append((session.session_id, must_findings))
        step = self.writer_steps.pop(0)
        if step.failure == "raise":
            raise RuntimeError("test harness failed before launch")

        def complete() -> None:
            if step.completion_delay_seconds:
                time.sleep(step.completion_delay_seconds)
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

        if step.completion_delay_seconds:
            thread = threading.Thread(target=complete, daemon=True)
            self.background_threads.append(thread)
            thread.start()
            return
        complete()

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
        self.planning_calls.append((session.session_id, chapter))
        self.planning_instructions.append((instructions, reasoning_effort))
        handoff = ""
        if chapter > 1:
            previous_quote = next(
                line.strip()[:48]
                for line in context["previous_chapter_ending"].splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
            handoff = (
                "## 0b. 章际交接\n"
                f"- 上一章正文路径：{context['previous_chapter_path']}\n"
                f"- 上一章正文 SHA-256：{context['previous_chapter_sha256']}\n"
                f"- 上一章结尾原文：{previous_quote}\n"
                "- 本章开头原文：deferred_until_drafted\n"
                "- 上一章结束时间：暴雨夜\n"
                "- 本章开始时间：同夜稍后\n"
                "- 上一章结束地点：旧楼走廊\n"
                "- 本章开始地点：地下室入口\n"
                "- 上一章结束动作：林舟打开门锁\n"
                "- 本章开始动作：林舟沿积水台阶下行\n"
                "- 转场类型：same_day_continuous\n"
                "- 上一章末明确决定：林舟选择开门并承担暴露风险\n"
                "- 本章是否推翻该决定：否\n"
                "- 若推翻，触发事件原文：无需：未推翻上一章决定\n\n"
            )
        scene = (
            f"# Scene Package - 第{chapter:02d}章\n\n"
            "## 0. 边界\n"
            "- 开始动作 / 停止动作：林舟开始处理门外逼近；"
            "门内的人叫出追兵姓名后停止。\n"
            f"- 承接压力 / 本章不解决：{request.conflict}\n\n"
            f"{handoff}"
            "## 1. 场景压力\n"
            f"- 视角角色要什么：{request.protagonist}要在追兵到达前作出选择。\n"
            "- 对手/世界独立要什么：追兵要找到门后藏匿者。\n"
            f"- 选择与即时成本：{request.conflict}\n"
            f"- 章末未解除压力：{request.ending_hook}\n\n"
            "## 1c. 决策问题\n"
            "- 不能同时得到的两样东西：赶在追兵前开门 / 不暴露藏匿者\n"
            "- 角色拒绝承认什么：不开门同样会把门内的人留给追兵\n"
            "- 角色误读了谁或什么：他以为门内的人不知道追兵身份\n"
            "- 哪句话不能说出口：门里到底是谁\n"
            "- 最终接受的具体代价：亲手让藏匿关系暴露\n\n"
            "## 1d. 认知与可证伪假设\n"
            "| 观察 | 当前假设 | 替代解释 | 置信度 | 可推翻证据 | 状态 |\n"
            "|---|---|---|---|---|---|\n"
            "| 脚步逼近 | 追兵尚未到门口 | 对方有人已在门内 | 中 | "
            "门内先叫出追兵姓名 | 未决 |\n\n"
            "## 1e. 规划反证与常识检查\n"
            "- 时间/日历算术：脚步距离与开锁动作按连续分钟核对。\n"
            "- 物理动作机制：门锁必须由林舟实际转动才会打开。\n"
            "- 人物知识来源：林舟只根据脚步、门锁和门内声音判断。\n"
            "- 不可逆性反证：开门后藏匿位置已经暴露。\n"
            "- 场景停止点：门内叫出追兵姓名后立即结束。\n\n"
            "## 2. 在场者状态\n"
            "| 人物 | 此刻目标 | 隐瞒/未知 | 本场变化 |\n"
            "|---|---|---|---|\n"
            "| 林舟 | 决定是否开门 | 不知门内人与追兵的关系 | 失去信息主动 |\n"
            "| 追兵 | 找到藏匿者 | 距离未知 | 持续逼近 |\n\n"
            "## 3. Beat 因果链\n"
            "| # | 触发 | 行动/决定 | 阻力/反应 | 结果与下一步 | 语域 |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | 脚步逼近 | 林舟检查并握住门锁 | 时间继续缩短 | "
            "拖延不再可行 | 贴身 |\n"
            "| 2 | 拖延失效 | 林舟转动门锁 | 门内的人先开口 | "
            "追兵身份被点破 | 贴身 |\n\n"
            "## 3c. 因果归属账本\n"
            "| 动作/条件 | 提出/执行者 | 知情者 | 后果承担者 |\n"
            "|---|---|---|---|\n"
            "| 转动门锁 | 林舟 | 林舟与门内人 | 林舟与藏匿者 |\n\n"
            "## 4. 信息账本\n"
            f"- 本章唯一新信息 / 来源 / 导致的选择：{request.ending_hook}\n\n"
            "## 5. 信息预算\n"
            "- 锚定物象（3-5）：门锁、积水、应急灯、鞋底水声\n"
            "- 关键对白意图：门内的点名夺走林舟的信息优势。\n"
            "- 新规则/伏笔/术语（各 0-1）：门内人与追兵认识。\n"
            "- 延后信息：双方具体关系延后揭示。\n\n"
            "## 5b. 专业判断审计\n"
            "- 无需：本章没有依赖专业判断推动的关键行动。\n\n"
            "## 7. 场景余波\n"
            f"- 身体 / 物件 / 关系 / 认知误信 / 未偿承诺："
            f"{request.ending_hook}\n"
        )
        return PlanningOutcome(
            files={
                "memory/worldbuilding.md": (
                    "# 世界设定\n\n"
                    f"## 物理规则\n- {request.world}\n\n"
                    "## 社会规则\n"
                    f"- {request.genre}中的人物受现实时间、空间和后果约束。\n\n"
                    "## 禁忌\n"
                    f"- 不得绕过本章核心冲突：{request.conflict}\n"
                ),
                "planning/research-boundaries.md": (
                    "# 研究边界\n\n"
                    "- 无需：测试正文只使用虚构地点和虚构事件。\n"
                ),
                "planning/story-engine.md": (
                    "# 故事发动机\n\n"
                    f"## 核心秘密\n- {request.ending_hook}\n\n"
                    f"## 欲望\n- {request.protagonist}必须处理：{request.conflict}\n\n"
                    "## 对抗中的独立意志\n"
                    "- 追兵按自己的目标逼近，不等待主角完成判断。\n\n"
                    "## 主角的错误模型\n"
                    "- 林舟以为门内的人不知道追兵身份。\n\n"
                    "## 替代行动与不兼容欲望\n"
                    "- 继续拖延会失去开门时机，立即开门会暴露藏匿者。\n\n"
                    f"## 不可逆选择\n- {request.conflict}\n\n"
                    "## 即时代价\n- 门一旦打开，藏匿关系立即暴露。\n\n"
                    f"## 未解承诺\n- {request.ending_hook}\n\n"
                    "## 主题压力\n- 选择是否仍成立，取决于人物承担的具体后果。\n"
                ),
                f"planning/scene-package-ch{chapter:02d}.md": scene,
            }
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
        self.review_contexts.append((role, set(context)))
        self.review_payloads.append((role, dict(context)))
        self.review_instructions.append(
            (role, instructions, reasoning_effort)
        )
        round_index = self._review_index // 2
        role_index = 0 if role == "blind-reader" else 1
        outcome = self.review_rounds[round_index][role_index]
        self._review_index += 1
        prose_quote = next(
            line.strip()[:48]
            for line in context["prose"].splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        updates = {"evidence_quote": prose_quote}
        if role == "chapter-editor" and "previous_chapter_ending" in context:
            updates["previous_chapter_quote"] = next(
                line.strip()[:48]
                for line in context["previous_chapter_ending"].splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        return replace(outcome, **updates)


def _pass_reviews() -> tuple[ReviewOutcome, ReviewOutcome]:
    return (
        ReviewOutcome(
            verdict="pass",
            human_likeness="convincing",
            reader_desire="continue",
            emotional_residue="主角已经作出选择，但门后的代价仍悬着。",
            next_chapter_pull="门后的人会要求主角付出什么？",
            evidence_quote="林舟握住门把",
            analysis={
                "reconstruction_space": "门外走廊通向一扇关闭的门，脚步从走廊尽头逼近。",
                "reconstruction_body": "林舟用掌心压住门把，身体动作始终贴着门。",
                "reconstruction_constraints": "追兵逼近，开门会暴露门内的人，拖延又会失去时机。",
                "reconstruction_emotion": "戒备随脚步逼近，最终被门内的点名推成失控。",
                "reconstruction_dialogue": "门内的人用点名夺走林舟的信息主动。",
                "memorable_image_1": "林舟把掌心压在门把上。",
                "memorable_image_2": "走廊尽头的脚步不断逼近。",
                "memorable_image_3": "门锁转动后，门内先叫出追兵的名字。",
            },
        ),
        ReviewOutcome(
            verdict="ready_for_editor_decision",
            evidence_quote="林舟握住门把",
            analysis={
                "editorial_causality": "脚步逼近迫使林舟开锁，开锁直接触发门内点名。",
                "editorial_agency": "林舟主动转动门锁并承担暴露藏匿者的后果。",
                "editorial_dialogue": "章末点名改变双方信息位置，没有承担设定讲解。",
                "editorial_texture": "动作与感官持续承载压力，没有抽象总结替代现场。",
                "editorial_continuity": "第一章无需上一章衔接，章内位置与动作连续。",
            },
        ),
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
            evidence_quote="林舟握住门把",
            analysis={
                "reconstruction_space": "能确认门与走廊，但追兵距离缺少变化。",
                "reconstruction_body": "林舟始终握住门把，身体反应较单一。",
                "reconstruction_constraints": "开门与暴露有关，但时间限制出现过晚。",
                "reconstruction_emotion": "紧张存在，尚未被具体选择推到转折。",
                "reconstruction_dialogue": "章末点名有效，前文缺少对话行动。",
                "memorable_image_1": "林舟握住门把。",
                "memorable_image_2": "走廊尽头传来脚步。",
                "memorable_image_3": "门内叫出追兵名字。",
            },
        ),
        ReviewOutcome(
            verdict="needs_revision",
            findings=(finding,),
            evidence_quote="林舟握住门把",
            analysis={
                "editorial_causality": "追兵压力进入过晚，开锁决定缺少充分触发。",
                "editorial_agency": "林舟作出选择，但此前替代行动没有落到动作。",
                "editorial_dialogue": "章末点名有效，前文信息交换不足。",
                "editorial_texture": "动作重复让压力没有继续升级。",
                "editorial_continuity": "第一章无需上一章衔接。",
            },
        ),
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
    completion_timeout_seconds: float = 0.5,
) -> NovelWorkflowOrchestrator:
    root = tmp_path / "repo"
    capsule_root = tmp_path / "capsules"
    return NovelWorkflowOrchestrator(
        root,
        backend,
        capsule_root=capsule_root,
        max_technical_retries=retries,
        writer_completion_timeout_seconds=completion_timeout_seconds,
        writer_completion_poll_seconds=0.005,
        writer_completion_stable_polls=2,
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
    assert backend.planning_calls == [("native-writer-01", 1)]
    assert backend.planning_instructions[0][1] == "high"
    assert backend.review_contexts[0] == ("blind-reader", {"prose"})
    assert backend.review_contexts[1][0] == "chapter-editor"
    assert backend.review_contexts[1][1] == {
        "prose",
        "scene_package",
        "story_contract",
        "canon",
        "blind_review",
        "machine_diagnostics",
    }
    assert backend.review_instructions[0][2] == "medium"
    assert backend.review_instructions[1][2] == "medium"
    assert "谜题成立不等于愿意追读" in backend.review_instructions[0][1]
    assert "每轮都完整执行五项审查" in backend.review_instructions[1][1]
    blind_review = (
        orchestrator.root / "books/demo/reviews/ch01-blind-reader.md"
    ).read_text(encoding="utf-8")
    assert (
        "- reconstruction_space: 门外走廊通向一扇关闭的门，脚步从走廊尽头逼近。"
        in blind_review
    )
    assert "- reviewer_id: native-blind-reader-01" in blind_review
    session_receipts = sorted(
        (
            orchestrator.root
            / ".local-guardian/demo/session-completions"
        ).glob("*.json")
    )
    assert len(session_receipts) == 3
    assert {
        json.loads(path.read_text(encoding="utf-8"))["role"]
        for path in session_receipts
    } == {"writer", "blind-reader", "chapter-editor"}
    assert not (
        orchestrator.root / "books/demo/.local-guardian"
    ).exists()


def test_same_backend_session_instance_cannot_impersonate_three_roles(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    original_create = backend.create_session

    def reused_instance(role: str) -> SessionIdentity:
        return replace(
            original_create(role),
            session_instance_id="one-native-context",
        )

    backend.create_session = reused_instance  # type: ignore[method-assign]
    orchestrator = _orchestrator(tmp_path, backend)

    with pytest.raises(
        workflow_module.WorkflowError,
        match="底层会话实例",
    ):
        orchestrator.start("demo", _request(), chapter=1)

    status = project_status(orchestrator.root, "demo", 1)
    assert not status["chapters"] or (
        status["chapters"][0].get("effective_status")
        not in {None, "ready"}
    )


def test_orchestrator_waits_for_async_writer_completion(tmp_path: Path):
    backend = ScriptedBackend(
        [
            WriterStep(
                _prose("异步完成"),
                completion_delay_seconds=0.03,
            )
        ],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(
        tmp_path,
        backend,
        retries=0,
        completion_timeout_seconds=0.5,
    )

    result = orchestrator.start("demo", _request(), chapter=1)
    for thread in backend.background_threads:
        thread.join(timeout=1)

    assert result.user_state == "chapter_complete"
    assert [
        item.session_id for item in backend.sessions if item.role == "writer"
    ] == ["native-writer-01"]
    receipts = list(
        (
            orchestrator.root
            / "books/demo/evidence/guardian-receipts"
        ).glob("*.json")
    )
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text(encoding="utf-8"))["status"] == "clean"


def test_timed_out_writer_is_retired_and_late_output_cannot_replace_retry(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [
            WriterStep(
                _prose("迟到旧稿"),
                completion_delay_seconds=0.15,
            ),
            WriterStep(_prose("新会话成功稿")),
        ],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(
        tmp_path,
        backend,
        retries=1,
        completion_timeout_seconds=0.03,
    )

    result = orchestrator.start("demo", _request(), chapter=1)
    for thread in backend.background_threads:
        thread.join(timeout=1)
    prose = (
        orchestrator.root / "books/demo/chapters/e01/ch-01/正文.md"
    ).read_text(encoding="utf-8")

    assert result.user_state == "chapter_complete"
    assert result.technical_retry_count == 1
    assert "新会话成功稿" in prose
    assert "迟到旧稿" not in prose
    assert [
        item.session_id for item in backend.sessions if item.role == "writer"
    ] == ["native-writer-01", "native-writer-02"]
    receipts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (
            orchestrator.root
            / "books/demo/evidence/guardian-receipts"
        ).glob("*.json")
    ]
    assert {item["status"] for item in receipts} == {
        "clean",
        "compromised",
    }
    compromised = next(
        item for item in receipts if item["status"] == "compromised"
    )
    assert "writer_completion_timeout" in compromised["reasons"]


def test_writer_launch_exception_skips_completion_wait_and_retries(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("未启动"), failure="raise"),
            WriterStep(_prose("异常后重试成功")),
        ],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend, retries=1)
    waited_capsules: list[Path] = []
    original_wait = orchestrator._wait_for_writer_completion

    def tracked_wait(capsule: Path, runtime_path: Path) -> bool:
        waited_capsules.append(capsule)
        return original_wait(capsule, runtime_path)

    orchestrator._wait_for_writer_completion = tracked_wait  # type: ignore[method-assign]

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "chapter_complete"
    assert result.technical_retry_count == 1
    assert len(waited_capsules) == 1
    assert [
        item.session_id for item in backend.sessions if item.role == "writer"
    ] == ["native-writer-01", "native-writer-02"]


def test_user_story_contract_is_injected_without_planner_reinterpretation(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [WriterStep(_prose("硬锚稿"))],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)
    request = WorkflowRequest(
        title="旧城屋脊",
        genre="民俗灾变",
        protagonist="裴照野，失业的古建修缮工",
        world="传统手艺消失会让天空开裂。",
        conflict="他必须在黎明前提前开脊救人，并承担违反行规的后果。",
        ending_hook="整条旧街的屋顶同时睁开，天空出现第一道裂缝。",
    )

    orchestrator.start("demo", request, chapter=1)

    book_dir = orchestrator.root / "books/demo"
    scene = (
        book_dir / "planning/scene-package-ch01.md"
    ).read_text(encoding="utf-8")
    handoff = (
        book_dir / "memory/context-cache/ch01-handoff.md"
    ).read_text(encoding="utf-8")
    editor_payload = next(
        payload
        for role, payload in backend.review_payloads
        if role == "chapter-editor"
    )

    assert "## 0a. 用户硬锚合同" in scene
    assert request.conflict in scene
    assert request.ending_hook in scene
    assert request.conflict in handoff
    assert request.ending_hook in handoff
    assert editor_payload["story_contract"] in scene
    assert request.conflict in editor_payload["story_contract"]
    assert request.ending_hook in editor_payload["story_contract"]


def test_orchestrator_does_not_invent_generic_story_decisions(tmp_path: Path):
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)

    orchestrator.start("demo", _request(), chapter=1)

    book_dir = orchestrator.root / "books/demo"
    generated_planning = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            book_dir / "planning/story-engine.md",
            book_dir / "planning/scene-package-ch01.md",
        )
    )
    assert "保住秘密 / 保住主动权" not in generated_planning
    assert "请你帮我" not in generated_planning
    assert "门把、雨水、脚步、失灵的灯" not in generated_planning


def test_review_outcome_accepts_role_authored_dimension_analysis():
    analysis = {
        "reconstruction_space": "门外走廊狭窄，人物隔门相对。",
        "reconstruction_body": "林舟的掌心持续压住门把。",
        "reconstruction_constraints": "追兵逼近，开门会暴露藏匿者。",
        "reconstruction_emotion": "戒备被门内的点名推成失控。",
        "reconstruction_dialogue": "门内的人用一句点名夺走信息主动。",
        "memorable_image_1": "掌心压紧门把。",
        "memorable_image_2": "走廊尽头的脚步逼近。",
        "memorable_image_3": "门锁转动后先传出追兵的名字。",
    }

    outcome = ReviewOutcome(
        verdict="pass",
        human_likeness="convincing",
        reader_desire="continue",
        emotional_residue="开门之后，藏匿关系已经无法恢复。",
        next_chapter_pull="门内的人为何认识追兵？",
        analysis=analysis,
        evidence_quote="林舟握住门把",
    )

    assert outcome.analysis == analysis
    assert outcome.evidence_quote == "林舟握住门把"


def test_writing_status_is_emitted_before_writer_planning(tmp_path: Path):
    messages: list[str] = []
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    original = backend.run_planning

    def guarded_planning(*args, **kwargs):
        assert messages == ["正在写作。"]
        return original(*args, **kwargs)

    backend.run_planning = guarded_planning  # type: ignore[method-assign]
    orchestrator = NovelWorkflowOrchestrator(
        tmp_path / "repo",
        backend,
        capsule_root=tmp_path / "capsules",
        on_status=messages.append,
    )

    orchestrator.start("demo", _request(), chapter=1)

    assert messages[0] == "正在写作。"


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
    assert backend.planning_calls == [("native-writer-01", 1)]
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
    assert backend.planning_calls == [("native-writer-01", 1)]
    patch_directive = backend.writer_directives[1][1]
    assert len(patch_directive) == 1
    assert "开场" in patch_directive[0]
    assert "林舟握住门把" in patch_directive[0]
    assert "阻力出现得太晚" in patch_directive[0]
    assert "把追兵的压力提前到第一段" in patch_directive[0]
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


def test_noop_patch_is_rejected_without_creating_a_generation(tmp_path: Path):
    prose = _prose("正文没有变化")
    backend = ScriptedBackend(
        [
            WriterStep(prose),
            WriterStep(prose),
        ],
        [_must_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend, retries=0)

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "decision_required"
    evidence = evidence_status(orchestrator.root, "demo", 1)
    assert evidence["generation_count"] == 1
    receipts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (
            orchestrator.root
            / "books/demo/evidence/guardian-receipts"
        ).glob("*.json")
    ]
    assert any(
        receipt["status"] == "compromised"
        and "no_content_change" in receipt["reasons"]
        for receipt in receipts
    )


def test_modified_generation_record_blocks_effective_ready(tmp_path: Path):
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)
    orchestrator.start("demo", _request(), chapter=1)
    generation_path = next(
        (
            orchestrator.root
            / "books/demo/evidence/generations"
        ).glob("*.md")
    )
    generation_path.write_text(
        generation_path.read_text(encoding="utf-8")
        + "\n<!-- rewritten in place -->\n",
        encoding="utf-8",
    )

    status = project_status(orchestrator.root, "demo", 1)

    assert status["workflow_integrity"]["status"] == "blocked"
    assert status["chapters"][0]["effective_status"] == "inconsistent"
    assert any(
        item["code"] == "generation_evidence_tampered"
        for item in status["workflow_integrity"]["blockers"]
    )
    user_status = orchestrator.status("demo")
    assert user_status.user_state != "chapter_complete"
    assert user_status.message != "第一章完成，是否继续第二章？"


@pytest.mark.parametrize(
    ("relative_path", "expected_code"),
    (
        (
            "reviews/ch01-blind-reader.md",
            "invalid_review_record",
        ),
        (
            "evidence/runtime-audits/native-writer-01.json",
            "runtime_audit_invalid",
        ),
    ),
)
def test_modified_review_or_runtime_blocks_effective_ready(
    tmp_path: Path,
    relative_path: str,
    expected_code: str,
):
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)
    orchestrator.start("demo", _request(), chapter=1)
    target = orchestrator.root / "books/demo" / relative_path
    target.write_text(
        target.read_text(encoding="utf-8") + "\n ",
        encoding="utf-8",
    )

    status = project_status(orchestrator.root, "demo", 1)

    assert status["workflow_integrity"]["status"] == "blocked"
    assert status["chapters"][0]["effective_status"] == "inconsistent"
    assert any(
        item["code"] == expected_code
        for item in status["workflow_integrity"]["blockers"]
    )


def test_modified_review_history_is_reported_as_immutable_tampering(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)
    orchestrator.start("demo", _request(), chapter=1)
    history = next(
        (
            orchestrator.root / "books/demo/reviews/history"
        ).glob("*.md")
    )
    history.write_text(
        history.read_text(encoding="utf-8")
        + "\n<!-- changed after creation -->\n",
        encoding="utf-8",
    )

    status = project_status(orchestrator.root, "demo", 1)

    assert status["chapters"][0]["effective_status"] == "inconsistent"
    assert any(
        item["code"] == "review_history_tampered"
        for item in status["workflow_integrity"]["blockers"]
    )


def test_sequence_finalization_failure_creates_no_ready_git_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    backend = ScriptedBackend(
        [WriterStep(_prose("初稿"))],
        [_pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)

    def fail_advance(*args, **kwargs):
        raise RuntimeError("sequence finalization failed")

    monkeypatch.setattr(
        workflow_module,
        "advance_chapter_sequence",
        fail_advance,
    )

    result = orchestrator.start("demo", _request(), chapter=1)

    assert result.user_state == "decision_required"
    status = project_status(orchestrator.root, "demo", 1)
    assert status["chapters"][0]["effective_status"] != "ready"
    log = subprocess.run(
        ["git", "-C", str(orchestrator.root / "books/demo"), "log", "--format=%s"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    assert "chapter: ch01 ready" not in log


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


def test_second_review_must_persists_decision_and_retires_patch_writer(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("初稿")),
            WriterStep(_prose("集中修订")),
        ],
        [_must_reviews(), _must_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)

    result = orchestrator.start("demo", _request(), chapter=1)
    status = orchestrator.status("demo")
    sequence = chapter_sequence_status(
        orchestrator.root,
        "demo",
        result.sequence_id,
    )

    assert result.user_state == "decision_required"
    assert status.user_state == "decision_required"
    assert status.message == "自动修订后仍有问题，请选择下一步。"
    assert sequence["effective_status"] == "awaiting_session"
    assert sequence["active_session_id"] is None
    sequence_file = next(
        (
            orchestrator.root
            / "books/demo/planning/chapter-sequences"
        ).glob("*.json")
    )
    sequence_record = json.loads(
        sequence_file.read_text(encoding="utf-8")
    )
    assert {
        item["session_id"]
        for item in sequence_record["retired_sessions"]
    } == {"native-writer-01", "native-writer-02"}


def test_user_retry_after_two_literary_versions_authorizes_fresh_third_writer(
    tmp_path: Path,
):
    backend = ScriptedBackend(
        [
            WriterStep(_prose("初稿")),
            WriterStep(_prose("集中修订")),
            WriterStep(_prose("人工选择后的回炉稿")),
        ],
        [_must_reviews(), _must_reviews(), _pass_reviews()],
    )
    orchestrator = _orchestrator(tmp_path, backend)
    failed = orchestrator.start("demo", _request(), chapter=1)

    result = orchestrator.retry("demo")

    assert failed.user_state == "decision_required"
    assert result.user_state == "chapter_complete"
    assert [
        item.session_id for item in backend.sessions if item.role == "writer"
    ] == [
        "native-writer-01",
        "native-writer-02",
        "native-writer-03",
    ]
    evidence = evidence_status(orchestrator.root, "demo", 1)
    assert evidence["generation_count"] == 3
    current_generation = next(
        item for item in evidence["records"] if item["stale"] is False
    )
    third = (
        orchestrator.root / "books/demo" / current_generation["path"]
    ).read_text(encoding="utf-8")
    assert '"authority": "human_delegate"' in third
    assert '"human_regeneration_authorized": true' in third
    assert (
        '"human_decision_reference": '
        '"automatic-workflow:user-selected-regenerate"'
        in third
    )
    current_reviews = list_reviews(
        orchestrator.root / "books/demo",
        "ch01",
    )
    assert {item["verdict"] for item in current_reviews} == {
        "pass",
        "ready_for_editor_decision",
    }


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
