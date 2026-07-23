"""Tests for the books/<slug>/ project operations (book_project + adapter ops)."""

import json
import hashlib
import os
from pathlib import Path
import shutil
import stat
import uuid

import pytest

from app.novel_forge import (
    artifact_integrity,
    book_project,
    guardian as guardian_module,
)
from app.novel_forge.artifact_integrity import (
    ArtifactIntegrityError,
    record_session_completion,
    seal_artifact,
)
from app.novel_forge.book_git import book_git_status
from app.novel_forge.chapter_sequence import (
    ChapterSequenceError,
    advance_chapter_sequence,
    attest_chapter_ready_candidate,
    begin_chapter_sequence,
    claim_chapter_session,
)
from app.novel_forge.book_evidence import record_evidence, render_evidence_markdown
from app.novel_forge.book_project import BookProjectError
from app.novel_forge.guardian import (
    CAPSULE_SCHEMA,
    GUARDIAN_RECEIPT_SCHEMA,
)
from app.novel_forge.project_templates import init_book_project
from app.novel_forge.session_audit import record_runtime_audit
from app.novel_forge.workflow import NovelWorkflowOrchestrator


_AUTHORITY_CONTROLLERS: list[NovelWorkflowOrchestrator] = []


def _workflow_authority(root: Path):
    controller = NovelWorkflowOrchestrator(
        root,
        object(),
        capsule_root=(
            root.parent
            / f"{root.name}-authority-capsules-{uuid.uuid4().hex[:8]}"
        ),
    )
    _AUTHORITY_CONTROLLERS.append(controller)
    return controller._workflow_authority
from app.novel_forge.skill_adapter import main as adapter_main
from app.novel_forge.writer_prompt import FORMAL_WRITER_PROMPT_ID


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def _remove_readonly_tree(path: Path) -> None:
    def make_writable_and_retry(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _make_book(tmp_path: Path, slug: str = "demo") -> Path:
    init_book_project(tmp_path, slug, "演示书", "都市神豪系统流")
    book_dir = tmp_path / "books" / slug
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text(
        "# 第一章 押金\n\n"
        + "他沿着街慢慢走，天色一点点暗下来，路灯次第亮起，像被人逐一点燃的引线。"
        * 60,
        encoding="utf-8",
    )
    (book_dir / "planning/scene-package-ch01.md").write_text(
        "# Scene Package\n\n"
        "## 1. 场景压力\n- 目标：x\n\n"
        "## 1c. 决策问题\n"
        "- 不能同时得到的两样东西：保住钱 / 保住脸\n"
        "- 拒绝承认：已经害怕\n"
        "- 误读：把沉默当作同意\n"
        "- 不能说出口的话：请留下\n"
        "- 接受的代价：失去主动权\n\n"
        "## 1d. 认知与可证伪假设\n"
        "| 观察事实 | 人物当前假设 | 替代解释 | 置信度 | 可推翻证据 | 本章状态 |\n"
        "|---|---|---|---|---|---|\n"
        "| 对方沉默 | 对方准备拒绝 | 对方没有听清 | 中 | 对方稍后主动答应 | 未决 |\n\n"
        "## 1e. 规划反证与常识检查\n"
        "- 时间/日历算术：无具体日期；只核对先后顺序。\n"
        "- 物理动作机制：先开门，再把钥匙交给对方。\n"
        "- 人物知识来源：对方当面说明钥匙用途。\n"
        "- 不可逆性反证：交钥匙后门锁立即更换，无法撤回。\n"
        "- 场景停止点：钥匙交出且门锁响起时停止。\n\n"
        "## 2. 在场者状态\n| 人物 | 表面目标 |\n|---|---|\n| 甲 | 乙 |\n\n"
        "## 3. Beat 因果链\n| # | 触发 |\n|---|---|\n| 1 | a |\n| 2 | b |\n\n"
        "## 3c. 因果归属账本\n"
        "| 动作/条件 | 提出或执行者 | 对象 | 当场知情者 | 来源 beat | 后果承担者 |\n"
        "|---|---|---|---|---|---|\n"
        "| 三日期限 | 甲 | 乙 | 甲、乙 | 2 | 乙 |\n\n"
        "## 4. 信息账本\n| 信息 | 来源 |\n|---|---|\n| x | y |\n\n"
        "## 5. 信息预算\n"
        "- 主冲突：x\n"
        "- 关键对白意图：无需：本章关键冲突不依赖对白转移事实或责任\n\n"
        "## 5b. 专业判断审计\n"
        "- 无需：本章没有依赖专业判断推动的关键行动。\n\n"
        "## 7. 场景余波\n"
        "- 身体：手指发冷\n"
        "- 物件：门锁留下新划痕\n"
        "- 关系：甲欠乙一次解释\n"
        "- 认知/误信：甲仍误以为乙会让步\n"
        "- 未偿债务/承诺：下一章必须回应敲门者\n",
        encoding="utf-8",
    )
    return book_dir


def _waive_materials(book_dir: Path) -> None:
    (book_dir / "memory/worldbuilding.md").write_text(
        "# 世界设定\n\n- 无需：纯现实题材。\n", encoding="utf-8"
    )
    (book_dir / "planning/research-boundaries.md").write_text(
        "# 研究边界\n\n- 无需：无外部事实依赖。\n", encoding="utf-8"
    )
    (book_dir / "planning/story-engine.md").write_text(
        "# 故事发动机\n\n"
        "## 欲望\n- 主角想保住家人。\n\n"
        "## 阻力\n- 他必须暴露自己的秘密。\n\n"
        "## 不可逆选择\n- 他决定留下。\n\n"
        "## 即时代价\n- 他失去逃走的机会。\n\n"
        "## 未解承诺\n- 门外的人是谁。\n",
        encoding="utf-8",
    )


def _review_file(
    tmp_path: Path,
    role: str,
    verdict: str,
    chapter: str = "ch01",
    *,
    provider: str = "review-provider",
    model: str = "review-model",
    independence_note: str = "",
    human_likeness: str = "convincing",
    reader_desire: str = "continue",
    emotional_residue: str = "人物的选择留下了尚未化解的关系压力。",
    next_chapter_pull: str = "读者想知道门内的人会不会回应。",
    review_session_id: str | None = None,
    context_scope: str | None = None,
    substantive: bool = True,
    record_completion: bool = True,
) -> Path:
    number = int(chapter.removeprefix("ch"))
    binding = book_project.review_binding(
        tmp_path, "demo", number, role=role
    )
    book_dir = tmp_path / "books/demo"
    chapter_path = book_project.find_chapter_file(book_dir, number)
    chapter_text = chapter_path.read_text(encoding="utf-8-sig")
    evidence_quote = next(
        line.strip()[:24]
        for line in chapter_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    previous_quote = "not_applicable"
    if number > 1:
        previous_text = book_project.find_chapter_file(
            book_dir, number - 1
        ).read_text(encoding="utf-8-sig")
        previous_quote = next(
            line.strip()[-24:]
            for line in previous_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    path = book_dir / "reviews" / f"{chapter}-{role}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    review_session_id = review_session_id or (
        f"review-session-{role}-{uuid.uuid4().hex[:8]}"
    )
    context_scope = context_scope or (
        "prose_only" if role == "blind-reader" else "full_review_context"
    )
    substantive_text = ""
    if substantive and role == "blind-reader":
        substantive_text = (
            "\n## Prose-only Reconstruction\n"
            f"- reconstruction_space: {evidence_quote}\n"
            f"- reconstruction_body: {evidence_quote}\n"
            f"- reconstruction_constraints: {evidence_quote}\n"
            f"- reconstruction_emotion: {evidence_quote}\n"
            f"- reconstruction_dialogue: {evidence_quote}\n"
            f"- memorable_image_1: {evidence_quote}\n"
            f"- memorable_image_2: {evidence_quote}\n"
            f"- memorable_image_3: {evidence_quote}\n"
        )
    elif substantive and role == "chapter-editor":
        substantive_text = (
            "\n## Editorial Dimensions\n"
            f"- editorial_causality: {evidence_quote}\n"
            f"- editorial_agency: {evidence_quote}\n"
            f"- editorial_dialogue: {evidence_quote}\n"
            f"- editorial_texture: {evidence_quote}\n"
            f"- editorial_continuity: {evidence_quote}\n"
        )
    path.write_text(
        f"# Review — {chapter} / {role}\n\n"
        f"- chapter: {chapter}\n"
        f"- role: {role}\n"
        f"- verdict: {verdict}\n"
        "- date: 2026-07-16\n\n"
        f"- source_fingerprint: {binding['source_fingerprint']}\n"
        f"- chapter_sha256: {binding['chapter_sha256']}\n"
        f"- previous_chapter_sha256: {binding['previous_chapter_sha256']}\n"
        f"- planning_sha256: {binding['planning_sha256']}\n"
        f"- draft_mode: {binding['draft_mode']}\n"
        f"- generation_id: {binding['generation_id']}\n\n"
        f"- evidence_quote: {evidence_quote}\n"
        f"- previous_chapter_quote: {previous_quote}\n\n"
        "- reviewer_type: model\n"
        f"- reviewer_id: {role}-instance\n"
        f"- review_session_id: {review_session_id}\n"
        f"- provider: {provider}\n"
        f"- model: {model}\n"
        f"- context_scope: {context_scope}\n"
        f"- independence_note: {independence_note}\n\n"
        f"- human_likeness: {human_likeness if role == 'blind-reader' else 'not_applicable'}\n\n"
        f"- reader_desire: {reader_desire if role == 'blind-reader' else 'not_applicable'}\n"
        f"- emotional_residue: {emotional_residue if role == 'blind-reader' else 'not_applicable'}\n"
        f"- next_chapter_pull: {next_chapter_pull if role == 'blind-reader' else 'not_applicable'}\n\n"
        "## Findings\n"
        "| # | 级别 (MUST/MAY) | 位置 | 原文证据 | 读者效果 | 修订意图 | 状态 (open/closed) |\n"
        "|---|---|---|---|---|---|---|\n"
        + substantive_text,
        encoding="utf-8",
    )
    if record_completion:
        record_session_completion(
            tmp_path,
            "demo",
            session_id=review_session_id,
            session_instance_id=f"instance-{review_session_id}",
            role=role,
            provider=provider,
            model=model,
            agent_harness="test-harness",
            context_scope=context_scope,
            operation_kind="test-review-operation",
            operation_id=f"operation-{review_session_id}",
            result_transport="inline",
            chapter=number,
            generation_id=binding["generation_id"],
            content_sha256=binding["chapter_sha256"],
            artifact=path,
            workflow_authority=_workflow_authority(tmp_path),
        )
    return path


def _record_generation(
    tmp_path: Path,
    book_dir: Path,
    *,
    provider: str = "writer-provider",
    model: str = "writer-model",
    generation_id: str = "generation.ch01.current",
    chapter_number: int = 1,
    run_id: str = "writer-session-001",
    record_audit: bool = True,
    record_guardian: bool = True,
    audit_generation_ids: list[str] | None = None,
    **metrics,
) -> str:
    chapter = book_project.find_chapter_file(book_dir, chapter_number)
    content_path = chapter.relative_to(book_dir).as_posix()
    state = next(
        item
        for item in book_project.project_status(
            tmp_path, "demo", chapter_number
        )["chapters"]
        if item["chapter"] == f"ch{chapter_number:02d}"
    )
    observed_metrics = {
        "draft_write_count": 1,
        "draft_edit_count": 0,
        "review_call_count": 2,
    }
    observed_metrics.update(metrics)
    prompt_sha256 = hashlib.sha256(
        b"test formal writer prompt"
    ).hexdigest()
    source = tmp_path / f"{generation_id}.md"
    generation_data = {
        "schema_version": 1,
        "id": generation_id,
        "kind": "generation",
        "created_at": "2026-07-17T12:00:00Z",
        "authority": "agent",
        "source_paths": [content_path],
        "summary": "当前正式稿生成来源。",
        "chapter": chapter_number,
        "draft_mode": state["draft_mode"],
        "writer_type": "agent",
        "provider": provider,
        "model": model,
        "run_id": run_id,
        "agent_harness": "test-harness",
        "reasoning_effort": "standard",
        "tool_failures": [],
        "content_path": content_path,
        "content_sha256": hashlib.sha256(chapter.read_bytes()).hexdigest(),
        "prompt_template_id": FORMAL_WRITER_PROMPT_ID,
        "prompt_sha256": prompt_sha256,
        **observed_metrics,
    }
    source.write_text(
        render_evidence_markdown(generation_data),
        encoding="utf-8",
    )
    record_evidence(tmp_path, "demo", source)
    book_project.bind_generation(
        tmp_path, "demo", chapter_number, generation_id
    )
    if record_guardian:
        capsule_id = (
            "test-"
            + hashlib.sha256(generation_id.encode("utf-8")).hexdigest()[:16]
        )
        receipt_relative = (
            Path("evidence/guardian-receipts")
            / f"{capsule_id}.json"
        )
        runtime_sha256 = "0" * 64
        receipt = {
            "schema": GUARDIAN_RECEIPT_SCHEMA,
            "capsule_id": capsule_id,
            "slug": "demo",
            "chapter": chapter_number,
            "sequence_id": "synthetic-test-sequence",
            "session_id": run_id,
            "target_path": content_path,
            "handoff_sha256": "0" * 64,
            "prompt_template_id": FORMAL_WRITER_PROMPT_ID,
            "prompt_sha256": prompt_sha256,
            "status": "clean",
            "isolation_attested": True,
            "control_plane_exposed": False,
            "unexpected_files": [],
            "reasons": [],
            "body_sha256": generation_data["content_sha256"],
            "runtime_snapshot_sha256": runtime_sha256,
            "recorded_at": "2026-07-17T12:00:00Z",
            "author_approval": False,
            "publication_eligibility": False,
        }
        guardian_module._atomic_json(
            (
                book_dir
                / "planning/guardian-sessions"
                / f"{capsule_id}.json"
            ),
            {
                "schema": CAPSULE_SCHEMA,
                "capsule_id": capsule_id,
                "status": "imported",
                "receipt_path": receipt_relative.as_posix(),
                "body_sha256": generation_data["content_sha256"],
                "runtime_snapshot_sha256": runtime_sha256,
                "prompt_template_id": FORMAL_WRITER_PROMPT_ID,
                "prompt_sha256": prompt_sha256,
            },
        )
        guardian_module._write_signed_receipt(
            tmp_path,
            "demo",
            book_dir,
            capsule_id,
            receipt,
        )
    if record_audit:
        source_hash = hashlib.sha256(
            f"{run_id}:{provider}:{model}".encode("utf-8")
        ).hexdigest()
        record_runtime_audit(
            book_dir,
            {
                "schema_version": 1,
                "source_format": "synthetic-test",
                "source_log_sha256": source_hash,
                "session_id": run_id,
                "agent_harness": "test-harness",
                "provider": provider,
                "model": model,
                "reasoning_effort": "standard",
                "elapsed_seconds": 1.0,
                "request_count": 1,
                "tokens": {
                    "input": 10,
                    "output": 10,
                    "cached_input": 10,
                    "total": 30,
                },
                "max_context_tokens": 30,
                "context_reset_count": 0,
                "tool_calls": {
                    "total": 1,
                    "failed": 0,
                    "by_name": {"write": 1},
                },
                "budget": {
                    "status": "within_budget",
                    "continue_allowed": True,
                    "chapter_count": 1,
                    "findings": [],
                    "limits": {},
                },
                "provenance_mismatches": [],
                "scope_chapter_count": 1,
                "generation_record_ids": (
                    audit_generation_ids or [generation_id]
                ),
            },
        )
    record_session_completion(
        tmp_path,
        "demo",
        session_id=run_id,
        session_instance_id=f"instance-{run_id}",
        role="writer",
        provider=provider,
        model=model,
        agent_harness="test-harness",
        context_scope="writer_capsule_only",
        operation_kind="test-writer-operation",
        operation_id=f"operation-{run_id}",
        result_transport="artifact",
        chapter=chapter_number,
        generation_id=generation_id,
        content_sha256=generation_data["content_sha256"],
        artifact=chapter,
        workflow_authority=_workflow_authority(tmp_path),
    )
    return generation_id


def test_bind_generation_creates_local_draft_checkpoint(tmp_path: Path):
    book_dir = _make_book(tmp_path)

    _record_generation(tmp_path, book_dir)

    status = book_git_status(tmp_path, "demo")
    assert status["last_message"] == "chapter: ch01 draft"
    assert status["dirty"] is True  # runtime audit is recorded after the draft commit


# --- business layer -----------------------------------------------------------


def test_formal_runtime_audit_requires_complete_budget_observation(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    run_id = "partial-runtime-session"
    record_runtime_audit(
        book_dir,
        {
            "schema_version": 1,
            "source_format": "novel-forge-runtime-v1",
            "source_log_sha256": hashlib.sha256(run_id.encode()).hexdigest(),
            "session_id": run_id,
            "agent_harness": "generic-harness/1",
            "provider": "generic-provider",
            "model": "generic-model",
            "reasoning_effort": "standard",
            "elapsed_seconds": 1.0,
            "request_count": 1,
            "tokens": {
                "input": 1,
                "output": 1,
                "cached_input": None,
                "total": None,
            },
            "max_context_tokens": None,
            "context_reset_count": None,
            "tool_calls": {
                "total": 0,
                "failed": 0,
                "by_name": {},
            },
            "budget": {
                "status": "partial",
                "continue_allowed": True,
                "chapter_count": 1,
                "findings": [],
                "limits": {},
            },
            "provenance_mismatches": [],
        },
    )

    errors = book_project._runtime_audit_errors(
        book_dir,
        {
            "writer_type": "agent",
            "run_id": run_id,
            "agent_harness": "generic-harness/1",
            "provider": "generic-provider",
            "model": "generic-model",
            "reasoning_effort": "standard",
            "tool_failures": [],
        },
    )

    assert any("完整观测" in error for error in errors)


def test_project_status_reads_progress_and_states(tmp_path: Path):
    _make_book(tmp_path)
    data = book_project.project_status(tmp_path, "demo", None)
    assert data["slug"] == "demo"
    assert data["title"] == "演示书"
    assert data["genre"] == "都市神豪系统流"
    assert data["chapters"][0]["chapter"] == "ch01"
    assert data["chapters"][0]["missing_chapter_state"] is True
    assert any(
        item["code"] == "content_present_while_planned"
        for item in data["workflow_integrity"]["blockers"]
    )
    detail = book_project.project_status(tmp_path, "demo", 1)
    assert detail["cjk"] and detail["cjk"] > 1000
    assert detail["chapter_file"] == "chapters/e01/ch-01/正文.md"


def test_run_gates_reports_quality_and_narrative(tmp_path: Path):
    _make_book(tmp_path)
    data = book_project.run_gates(tmp_path, "demo", 1)
    assert data["cjk"] and data["cjk"] > 1000
    assert "blocking" in data["quality"]
    # Materials are unfilled templates → narrative gate must block.
    assert any("worldbuilding" in b for b in data["narrative"]["blocking"])
    # Findings never contain the prose body itself.
    assert "正文.md" not in json.dumps(data["quality"]["findings"])


def test_run_gates_missing_chapter(tmp_path: Path):
    _make_book(tmp_path)
    with pytest.raises(BookProjectError):
        book_project.run_gates(tmp_path, "demo", 9)


def test_record_review_validates_and_stores(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    result = book_project.record_review(tmp_path, "demo", 1, "blind-reader", review)
    assert result["verdict"] == "pass"
    assert (book_dir / "reviews/ch01-blind-reader.md").exists()
    state = book_project.project_status(tmp_path, "demo", 1)
    assert state["chapters"][0]["status"] == "planned"


def test_record_review_rejects_mismatched_role(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "line-editor", "pass")
    with pytest.raises(BookProjectError):
        book_project.record_review(tmp_path, "demo", 1, "causal-editor", review)


def test_default_workflow_requires_only_two_high_value_reviews():
    from app.novel_forge.planning_spec import (
        CHAPTER_STATES,
        DEFAULT_REVIEW_ROLES,
        READY_REQUIRED_REVIEWS,
    )

    assert CHAPTER_STATES == (
        "planned",
        "context_collected",
        "scene_packaged",
        "drafted",
        "surface_checked",
        "blind_read",
        "editorial_reviewed",
        "ready",
    )
    assert DEFAULT_REVIEW_ROLES == ("blind-reader", "chapter-editor")
    assert READY_REQUIRED_REVIEWS == (
        ("blind-reader", "pass"),
        ("chapter-editor", "ready_for_editor_decision"),
    )


def test_record_review_rejects_stale_source_fingerprint(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text(chapter.read_text(encoding="utf-8") + "\n正文变化。\n", encoding="utf-8")

    with pytest.raises(BookProjectError, match="正文或规划材料已经变化"):
        book_project.record_review(tmp_path, "demo", 1, "blind-reader", review)


def test_saved_review_becomes_stale_after_chapter_change(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    book_project.record_review(tmp_path, "demo", 1, "blind-reader", review)

    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text(chapter.read_text(encoding="utf-8") + "\n正文变化。\n", encoding="utf-8")

    status = book_project.project_status(tmp_path, "demo", 1)
    saved = next(r for r in status["reviews"] if r["role"] == "blind-reader")
    assert saved["stale"] is True


def test_directly_written_invalid_review_cannot_enter_benchmark(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    _record_generation(tmp_path, book_dir)
    reviews_dir = book_dir / "reviews"
    for role, verdict in (
        ("blind-reader", "pass"),
        ("chapter-editor", "ready_for_editor_decision"),
    ):
        source = _review_file(
            tmp_path,
            role,
            verdict,
            provider="independent-provider",
            model=f"{role}-model",
        )
        text = source.read_text(encoding="utf-8")
        if role == "blind-reader":
            text = text.replace(
                "- evidence_quote: 他沿着街慢慢走",
                "- evidence_quote: 正文不存在的伪造引文",
            )
        (reviews_dir / f"ch01-{role}.md").write_text(
            text,
            encoding="utf-8",
        )

    status = book_project.project_status(tmp_path, "demo", 1)
    blind = next(
        review
        for review in status["reviews"]
        if review["role"] == "blind-reader"
    )

    assert blind["validation_valid"] is False
    assert status["benchmark_eligible"] is False
    assert any(
        item["code"] == "invalid_review_record"
        for item in status["workflow_integrity"]["blockers"]
    )


def test_stale_generation_cannot_be_reused_for_new_review(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _record_generation(tmp_path, book_dir)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text(
        chapter.read_text(encoding="utf-8") + "\n门外的人又敲了一次。\n",
        encoding="utf-8",
    )

    review = _review_file(tmp_path, "causal-editor", "pass")
    with pytest.raises(BookProjectError, match="generation.*正文"):
        book_project.record_review(
            tmp_path, "demo", 1, "causal-editor", review
        )


def test_record_review_rejects_editorial_verdict_for_line_roles(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "causal-editor", "ready_for_editor_decision")
    with pytest.raises(BookProjectError):
        book_project.record_review(tmp_path, "demo", 1, "causal-editor", review)


def test_advance_state_ready_requires_reviews(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    paragraph = "他敲门，她没有开。" * 900
    chapter.write_text(
        f"# 第一章\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n",
        encoding="utf-8",
    )
    _waive_materials(book_dir)
    _record_generation(tmp_path, book_dir)
    with pytest.raises(BookProjectError):
        book_project.advance_state(tmp_path, "demo", 1, "ready")
    book_project.record_review(
        tmp_path, "demo", 1, "blind-reader", _review_file(tmp_path, "blind-reader", "pass")
    )
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "chapter-editor",
        _review_file(tmp_path, "chapter-editor", "ready_for_editor_decision"),
    )
    for state in (
        "context_collected",
        "scene_packaged",
        "drafted",
        "surface_checked",
        "blind_read",
        "editorial_reviewed",
    ):
        book_project.advance_state(
            tmp_path,
            "demo",
            1,
            state,
            evidence=(
                None
                if state in {"blind_read", "editorial_reviewed"}
                else f"planning/{state}.md"
            ),
        )
    with pytest.raises(BookProjectError, match="章节序列"):
        book_project.advance_state(
            tmp_path,
            "demo",
            1,
            "ready",
            evidence="project-status/current",
        )


def test_immutable_review_history_cannot_be_resealed_after_mutation(
    tmp_path: Path,
):
    _make_book(tmp_path)
    source = _review_file(
        tmp_path,
        "blind-reader",
        "needs_revision",
        record_completion=False,
    )
    recorded = book_project.record_review(
        tmp_path,
        "demo",
        1,
        "blind-reader",
        source,
    )
    history = tmp_path / "books/demo" / recorded["review_record"]
    history.write_text(
        history.read_text(encoding="utf-8") + "\n被原地修改。\n",
        encoding="utf-8",
    )

    with pytest.raises(ArtifactIntegrityError, match="不得重新封印"):
        seal_artifact(
            tmp_path,
            "demo",
            history,
            kind="review-history",
        )


def test_session_completion_requires_orchestrator_authority(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_project.find_chapter_file(book_dir, 1)

    with pytest.raises(
        ArtifactIntegrityError,
        match="编排器权限",
    ):
        record_session_completion(
            tmp_path,
            "demo",
            session_id="fabricated-session",
            session_instance_id="fabricated-instance",
            role="writer",
            provider="fabricated-provider",
            model="fabricated-model",
            agent_harness="fabricated-harness",
            context_scope="writer_capsule_only",
            operation_kind="fabricated-operation",
            operation_id="fabricated-operation-id",
            result_transport="artifact",
            chapter=1,
            generation_id="generation.ch01.fabricated",
            content_sha256=hashlib.sha256(chapter.read_bytes()).hexdigest(),
            artifact=chapter,
        )


def test_workflow_authority_has_no_standalone_issuer():
    assert not hasattr(
        artifact_integrity,
        "_issue_workflow_authority",
    )


def test_session_completion_seals_native_operation_and_result_channel(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter = book_project.find_chapter_file(book_dir, 1)
    digest = hashlib.sha256(chapter.read_bytes()).hexdigest()

    payload = record_session_completion(
        tmp_path,
        "demo",
        session_id="native-writer-001",
        session_instance_id="instance-native-writer-001",
        role="writer",
        provider="test-provider",
        model="test-model",
        agent_harness="test-harness",
        context_scope="writer_capsule_only",
        operation_kind="host_background_task",
        operation_id="opaque-operation-001",
        result_transport="artifact",
        chapter=1,
        generation_id="generation.ch01.current",
        content_sha256=digest,
        artifact=chapter,
        workflow_authority=_workflow_authority(tmp_path),
    )

    assert payload["schema"] == "novel-forge-session-completion/v3"
    assert payload["operation_kind"] == "host_background_task"
    assert payload["operation_id"] == "opaque-operation-001"
    assert payload["result_transport"] == "artifact"


def test_ready_chapter_launches_next_fresh_session_with_bounded_handoff(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    sequence = begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        chapter_count=2,
        sequence_id="two-chapters",
    )
    assert sequence["launch"]["chapter"] == 1
    claim_chapter_session(
        tmp_path,
        "demo",
        "two-chapters",
        "writer-session-001",
    )

    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    paragraph = "他敲门，她没有开。" * 900
    chapter.write_text(
        f"# 第一章\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n",
        encoding="utf-8",
    )
    _waive_materials(book_dir)
    _record_generation(
        tmp_path,
        book_dir,
        run_id="writer-session-001",
    )
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "blind-reader",
        _review_file(
            tmp_path,
            "blind-reader",
            "pass",
            review_session_id="blind-session-001",
        ),
    )
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "chapter-editor",
        _review_file(
            tmp_path,
            "chapter-editor",
            "ready_for_editor_decision",
            review_session_id="editor-session-001",
        ),
    )
    for state in (
        "context_collected",
        "scene_packaged",
        "drafted",
        "surface_checked",
        "blind_read",
        "editorial_reviewed",
    ):
        book_project.advance_state(
            tmp_path,
            "demo",
            1,
            state,
            evidence=(
                None
                if state in {"blind_read", "editorial_reviewed"}
                else f"planning/{state}.md"
            ),
        )
    authority = _workflow_authority(tmp_path)
    attest_chapter_ready_candidate(
        tmp_path,
        "demo",
        "two-chapters",
        "writer-session-001",
        workflow_authority=authority,
    )
    book_project.advance_state(
        tmp_path,
        "demo",
        1,
        "ready",
        evidence="project-status/current",
        workflow_authority=authority,
    )

    voice = book_dir / "memory/voice-bible.md"
    voice.write_text(
        voice.read_text(encoding="utf-8").replace(
            "________________",
            "选自第一章：他敲门，她没有开。门锁里有一声很轻的回响。"
            "这段以动作承受关系压力，不解释情绪。",
        ),
        encoding="utf-8",
    )
    (book_dir / "planning/scene-package-ch02.md").write_text(
        "# Scene Package\n\n"
        "## 0b. 章际交接\n"
        "- 上一章结束动作：敲门。\n"
        "- 本章开始动作：门内的人靠近。\n\n"
        "## 1. 场景压力\n"
        "- 本章目标：决定是否回应。\n"
        "- 停止边界：门内第一次出声后结束。\n",
        encoding="utf-8",
    )

    advanced = advance_chapter_sequence(
        tmp_path,
        "demo",
        "two-chapters",
        "writer-session-001",
    )

    assert advanced["status"] == "awaiting_session"
    assert advanced["completed_chapters"] == [1]
    assert advanced["launch"]["chapter"] == 2
    assert advanced["launch"]["new_native_session_required"] is True
    assert "writer-session-001" in advanced["launch"]["forbidden_session_ids"]
    handoff_path = book_dir / advanced["launch"]["handoff_path"]
    handoff = handoff_path.read_text(encoding="utf-8")
    assert "上一章正文 SHA-256" in handoff
    assert "他敲门，她没有开" in handoff
    assert "这段以动作承受关系压力" in handoff
    assert "门内的人靠近" in handoff
    assert "review-session" not in handoff
    assert len(handoff) < 30_000

    with pytest.raises(ChapterSequenceError, match="已被使用"):
        claim_chapter_session(
            tmp_path,
            "demo",
            "two-chapters",
            "writer-session-001",
        )
    claimed = claim_chapter_session(
        tmp_path,
        "demo",
        "two-chapters",
        "writer-session-002",
    )
    assert claimed["current_chapter"] == 2


def test_surface_checked_rejects_blocking_source_hygiene(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text(
        "# 第一章\n\n他母亲走回去的时候没有说话。她走得比他**慢**。\n",
        encoding="utf-8",
    )
    for state in (
        "context_collected",
        "scene_packaged",
        "drafted",
    ):
        book_project.advance_state(tmp_path, "demo", 1, state)

    with pytest.raises(BookProjectError, match="surface gate"):
        book_project.advance_state(tmp_path, "demo", 1, "surface_checked")


def test_blind_reader_requires_explicit_human_likeness_verdict(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(
        tmp_path,
        "blind-reader",
        "pass",
        human_likeness="uncertain",
    )

    with pytest.raises(BookProjectError, match="human_likeness"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


def test_blind_reader_pass_requires_reader_desire_to_continue(
    tmp_path: Path,
):
    _make_book(tmp_path)
    review = _review_file(
        tmp_path,
        "blind-reader",
        "pass",
        reader_desire="conditional",
    )

    with pytest.raises(BookProjectError, match="reader_desire"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


@pytest.mark.parametrize("field", ["emotional_residue", "next_chapter_pull"])
def test_blind_reader_pass_requires_substantive_reader_pull_evidence(
    tmp_path: Path,
    field: str,
):
    _make_book(tmp_path)
    kwargs = {field: "-"}
    review = _review_file(
        tmp_path,
        "blind-reader",
        "pass",
        **kwargs,
    )

    with pytest.raises(BookProjectError, match=field):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


def test_runtime_audit_must_bind_exactly_one_generation(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    generation_id = _record_generation(
        tmp_path,
        book_dir,
        audit_generation_ids=[
            "generation.ch01.current",
            "generation.ch02.invalid",
        ],
    )
    generation, _ = book_project.find_evidence_record(
        tmp_path, "demo", generation_id
    )

    errors = book_project._runtime_audit_errors(
        book_dir, generation.data
    )

    assert any("只能绑定当前 generation" in error for error in errors)


def test_second_chapter_cannot_record_reused_writer_session(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter_two = book_dir / "chapters/e01/ch-02/正文.md"
    chapter_two.parent.mkdir(parents=True, exist_ok=True)
    chapter_two.write_text(
        "# 第二章\n\n" + "她终于开门，但没有让他进去。" * 240,
        encoding="utf-8",
    )
    shutil.copyfile(
        book_dir / "planning/scene-package-ch01.md",
        book_dir / "planning/scene-package-ch02.md",
    )
    _record_generation(
        tmp_path,
        book_dir,
        run_id="reused-writer-session",
    )
    with pytest.raises(
        ArtifactIntegrityError,
        match="session_id 已被其他角色使用",
    ):
        _record_generation(
            tmp_path,
            book_dir,
            generation_id="generation.ch02.current",
            chapter_number=2,
            run_id="reused-writer-session",
            record_audit=False,
        )


def test_ready_rejects_exceeded_draft_mutation_budget(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    paragraph = "他敲门，她没有开。" * 900
    chapter.write_text(
        f"# 第一章\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n",
        encoding="utf-8",
    )
    _waive_materials(book_dir)
    _record_generation(
        tmp_path,
        book_dir,
        draft_write_count=1,
        draft_edit_count=10,
    )
    for role, verdict in (
        ("blind-reader", "pass"),
        ("chapter-editor", "ready_for_editor_decision"),
    ):
        book_project.record_review(
            tmp_path,
            "demo",
            1,
            role,
            _review_file(tmp_path, role, verdict),
        )
    for state in (
        "context_collected",
        "scene_packaged",
        "drafted",
        "surface_checked",
        "blind_read",
        "editorial_reviewed",
    ):
        book_project.advance_state(
            tmp_path,
            "demo",
            1,
            state,
            evidence=(
                None
                if state in {"blind_read", "editorial_reviewed"}
                else f"planning/{state}.md"
            ),
        )

    with pytest.raises(BookProjectError, match="draft-mutation-budget"):
        book_project.advance_state(
            tmp_path,
            "demo",
            1,
            "ready",
            evidence="project-status/current",
        )


@pytest.mark.parametrize(
    ("role", "verdict"),
    [
        ("blind-reader", "pass"),
        ("chapter-editor", "ready_for_editor_decision"),
    ],
)
def test_default_review_requires_substantive_dimensions(
    tmp_path: Path,
    role: str,
    verdict: str,
):
    _make_book(tmp_path)
    review = _review_file(
        tmp_path,
        role,
        verdict,
        substantive=False,
    )

    with pytest.raises(BookProjectError, match="实质审稿字段"):
        book_project.record_review(tmp_path, "demo", 1, role, review)


def test_blind_reader_rejects_future_chapter_knowledge(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    review.write_text(
        review.read_text(encoding="utf-8")
        + "\n## 盲读结论\n这个物件会在 ch05 被找回。\n",
        encoding="utf-8",
    )

    with pytest.raises(BookProjectError, match="未来章节"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


def test_blind_reader_rejects_chapter_id_touching_chinese_text(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    review.write_text(
        review.read_text(encoding="utf-8")
        + "\n## 盲读结论\n这个物件会在ch05被找回。\n",
        encoding="utf-8",
    )

    with pytest.raises(BookProjectError, match="未来章节"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


def test_record_review_can_replace_existing_future_leaking_review(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    leaking = _review_file(tmp_path, "blind-reader", "pass")
    leaking.write_text(
        leaking.read_text(encoding="utf-8")
        + "\n## 盲读结论\n这个物件会在 ch05 被找回。\n",
        encoding="utf-8",
    )
    canonical = book_dir / "reviews/ch01-blind-reader.md"
    canonical.write_text(
        leaking.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    replacement = tmp_path / "clean-blind-review.md"
    clean = _review_file(tmp_path, "blind-reader", "pass")
    replacement.write_text(
        clean.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = book_project.record_review(
        tmp_path, "demo", 1, "blind-reader", replacement
    )

    assert result["verdict"] == "pass"
    assert "ch05" not in canonical.read_text(encoding="utf-8")


def test_review_rejects_future_date(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    review.write_text(
        review.read_text(encoding="utf-8").replace(
            "- date: 2026-07-16",
            "- date: 2029-07-19",
        ),
        encoding="utf-8",
    )

    with pytest.raises(BookProjectError, match="未来"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


def test_advance_state_rejects_unknown_state(tmp_path: Path):
    _make_book(tmp_path)
    with pytest.raises(BookProjectError):
        book_project.advance_state(tmp_path, "demo", 1, "published")


def test_project_status_never_claims_author_or_publication_approval(tmp_path: Path):
    _make_book(tmp_path)

    status = book_project.project_status(tmp_path, "demo", 1)

    assert status["author_approval"] is False
    assert status["publication_eligibility"] is False
    assert "evidence" in status


def test_chapter_project_status_reports_serial_style_through_current_chapter(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    for number in range(1, 4):
        chapter = book_dir / f"chapters/e01/ch-{number:02d}/正文.md"
        chapter.parent.mkdir(parents=True, exist_ok=True)
        chapter.write_text(
            f"# 第{number}章\n\n"
            + "客厅里很安静。" * 8
            + "他绕过桌子，推开窗，确认楼下没有人。" * 8,
            encoding="utf-8",
        )

    status = book_project.project_status(tmp_path, "demo", 3)

    assert any(
        finding["code"] == "cross-chapter-repetition"
        for finding in status["literary_profile"]["findings"]
    )


def test_project_status_flags_ready_chapter_with_current_blocking_gate(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text(
        "# 第一章\n\n他母亲走回去的时候没有说话。她走得比他**慢**。\n",
        encoding="utf-8",
    )
    book_project.advance_state(tmp_path, "demo", 1, "context_collected")
    state_path = book_dir / "planning/chapter-state/ch01.md"
    state_text = state_path.read_text(encoding="utf-8")
    state_path.write_text(
        state_text.replace("- status: context_collected", "- status: ready"),
        encoding="utf-8",
    )

    status = book_project.project_status(tmp_path, "demo", 1)

    codes = {issue["code"] for issue in status["workflow_integrity"]["blockers"]}
    assert "ready_with_blocking_gates" in codes


def test_ready_formal_placeholder_state_evidence_is_blocking(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    book_project.advance_state(tmp_path, "demo", 1, "context_collected")
    state_path = book_dir / "planning/chapter-state/ch01.md"
    state_text = state_path.read_text(encoding="utf-8")
    state_path.write_text(
        state_text.replace("- status: context_collected", "- status: ready"),
        encoding="utf-8",
    )

    status = book_project.project_status(tmp_path, "demo", 1)

    assert any(
        issue["code"] == "placeholder_state_evidence"
        for issue in status["workflow_integrity"]["blockers"]
    )


def test_run_gates_uses_persisted_exploration_and_formal_modes(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text("# 1\n\n" + "人" * 4999 + "\n", encoding="utf-8")

    book_project.set_draft_mode(tmp_path, "demo", 1, "exploration")
    exploration = book_project.run_gates(tmp_path, "demo", 1)
    assert exploration["mode"] == "exploration"
    assert exploration["ready_eligible"] is False
    assert not any(
        "5000" in item for item in exploration["narrative"]["blocking"]
    )

    book_project.set_draft_mode(tmp_path, "demo", 1, "formal")
    formal = book_project.run_gates(tmp_path, "demo", 1)
    assert formal["mode"] == "formal"
    assert formal["ready_eligible"] is False
    assert any("5000" in item for item in formal["narrative"]["blocking"])

    chapter.write_text("# 1\n\n" + "人" * 5000 + "\n", encoding="utf-8")
    boundary = book_project.run_gates(tmp_path, "demo", 1)
    assert not any("5000" in item for item in boundary["narrative"]["blocking"])


def test_run_gates_mode_argument_is_assertion_not_override(tmp_path: Path):
    _make_book(tmp_path)
    book_project.set_draft_mode(tmp_path, "demo", 1, "exploration")

    with pytest.raises(BookProjectError, match="稿件模式"):
        book_project.run_gates(tmp_path, "demo", 1, expected_mode="formal")

    status = book_project.project_status(tmp_path, "demo", 1)
    assert status["chapters"][0]["draft_mode"] == "exploration"


def test_exploration_chapter_cannot_enter_ready(tmp_path: Path):
    _make_book(tmp_path)
    book_project.set_draft_mode(tmp_path, "demo", 1, "exploration")

    with pytest.raises(BookProjectError, match="exploration"):
        book_project.advance_state(tmp_path, "demo", 1, "ready")


def test_degraded_exploration_reports_tool_limit_and_cannot_enter_ready(
    tmp_path: Path,
):
    _make_book(tmp_path)
    book_project.set_draft_mode(
        tmp_path, "demo", 1, "degraded_exploration"
    )

    gates = book_project.run_gates(tmp_path, "demo", 1)

    assert gates["mode"] == "degraded_exploration"
    assert gates["ready_eligible"] is False
    assert not gates["narrative"]["blocking"]
    assert any("降级运行" in item for item in gates["narrative"]["advisory"])
    status = book_project.project_status(tmp_path, "demo", 1)
    assert "degraded_exploration" in status["benchmark_missing"]
    with pytest.raises(BookProjectError, match="formal"):
        book_project.advance_state(tmp_path, "demo", 1, "ready")


def test_critical_review_rejects_quote_not_found_in_prose(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    text = review.read_text(encoding="utf-8")
    review.write_text(
        text.replace(
            "- evidence_quote: 他沿着街慢慢走",
            "- evidence_quote: 正文里从未出现的句子",
        ),
        encoding="utf-8",
    )

    with pytest.raises(BookProjectError, match="evidence_quote"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


def test_previous_chapter_change_stales_next_chapter_consistency_review(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter2 = book_dir / "chapters/e01/ch-02/正文.md"
    chapter2.parent.mkdir(parents=True)
    chapter2.write_text(
        "# 第二章\n\n"
        + "次日下午，他仍记得昨夜关门的声音。"
        * 80,
        encoding="utf-8",
    )
    source_package = book_dir / "planning/scene-package-ch01.md"
    (book_dir / "planning/scene-package-ch02.md").write_text(
        source_package.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    review = _review_file(
        tmp_path, "consistency-guard", "pass", chapter="ch02"
    )
    book_project.record_review(
        tmp_path, "demo", 2, "consistency-guard", review
    )

    chapter1 = book_dir / "chapters/e01/ch-01/正文.md"
    chapter1.write_text(
        chapter1.read_text(encoding="utf-8") + "\n上一章结尾改变。\n",
        encoding="utf-8",
    )
    status = book_project.project_status(tmp_path, "demo", 2)
    saved = next(
        item
        for item in status["reviews"]
        if item["role"] == "consistency-guard"
    )

    assert saved["stale"] is True


def test_previous_chapter_change_does_not_stale_local_only_review(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter2 = book_dir / "chapters/e01/ch-02/正文.md"
    chapter2.parent.mkdir(parents=True)
    chapter2.write_text(
        "# 第二章\n\n" + "次日，他继续向前走。" * 80,
        encoding="utf-8",
    )
    (book_dir / "planning/scene-package-ch02.md").write_text(
        (book_dir / "planning/scene-package-ch01.md").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    review = _review_file(tmp_path, "line-editor", "pass", chapter="ch02")
    book_project.record_review(
        tmp_path, "demo", 2, "line-editor", review
    )

    chapter1 = book_dir / "chapters/e01/ch-01/正文.md"
    chapter1.write_text(
        chapter1.read_text(encoding="utf-8") + "\n前章变化。\n",
        encoding="utf-8",
    )
    status = book_project.project_status(tmp_path, "demo", 2)
    saved = next(
        item for item in status["reviews"] if item["role"] == "line-editor"
    )

    assert saved["stale"] is False


def test_project_status_flags_nested_duplicate_review_artifact(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    duplicate = book_dir / "reviews/ch01/blind-reader.md"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text("# duplicate review\n", encoding="utf-8")

    status = book_project.project_status(tmp_path, "demo", 1)

    assert status["benchmark_eligible"] is False
    assert any(
        item["code"] == "duplicate_review_artifact"
        for item in status["workflow_integrity"]["warnings"]
    )


def test_checkpoint_chapter_requires_arc_audit_before_other_ready_evidence(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter5 = book_dir / "chapters/e01/ch-05/正文.md"
    chapter5.parent.mkdir(parents=True, exist_ok=True)
    chapter5.write_text("# 第五章\n\n正文。\n", encoding="utf-8")

    with pytest.raises(BookProjectError, match="arc audit"):
        book_project.advance_state(tmp_path, "demo", 5, "ready")


def test_same_origin_blind_review_requires_note_and_stays_visible(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _record_generation(
        tmp_path,
        book_dir,
        provider="same-provider",
        model="same-model",
    )
    no_note = _review_file(
        tmp_path,
        "blind-reader",
        "pass",
        provider="same-provider",
        model="same-model",
    )
    with pytest.raises(BookProjectError, match="independence_note"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", no_note
        )

    with_note = _review_file(
        tmp_path,
        "blind-reader",
        "pass",
        provider="same-provider",
        model="same-model",
        independence_note="使用独立会话，且只加载匿名正文。",
    )
    book_project.record_review(
        tmp_path, "demo", 1, "blind-reader", with_note
    )
    status = book_project.project_status(tmp_path, "demo", 1)
    review = next(r for r in status["reviews"] if r["role"] == "blind-reader")
    assert review["same_provider_model_as_generation"] is True
    assert review["independent"] is False
    assert review["session_isolated"] is True


def test_blind_reader_pass_rejects_same_writer_session(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _record_generation(tmp_path, book_dir, run_id="shared-session")
    review = _review_file(
        tmp_path,
        "blind-reader",
        "pass",
        review_session_id="shared-session",
        record_completion=False,
    )

    with pytest.raises(BookProjectError, match="独立会话"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", review
        )


def test_simulated_blind_may_report_failure_but_cannot_pass(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _record_generation(tmp_path, book_dir, run_id="writer-session")
    diagnostic = _review_file(
        tmp_path,
        "blind-reader",
        "needs_revision",
        review_session_id="writer-session",
        context_scope="simulated_blind",
        human_likeness="synthetic",
        record_completion=False,
    )

    recorded = book_project.record_review(
        tmp_path, "demo", 1, "blind-reader", diagnostic
    )
    assert recorded["verdict"] == "needs_revision"

    passing = _review_file(
        tmp_path,
        "blind-reader",
        "pass",
        review_session_id="writer-session",
        record_completion=False,
        context_scope="simulated_blind",
    )
    with pytest.raises(BookProjectError, match="simulated_blind"):
        book_project.record_review(
            tmp_path, "demo", 1, "blind-reader", passing
        )


def test_run_gates_blocks_malformed_dialogue_and_ready_eligibility(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text(
        "# 第一章\n\n"
        + ('周蓉说："周蓉说：你别再查了。"\n\n' * 200)
        + ("罗闻沿着墙摸到总阀，记录红针的位置。" * 400),
        encoding="utf-8",
    )
    _waive_materials(book_dir)

    gates = book_project.run_gates(tmp_path, "demo", 1)

    assert gates["ready_eligible"] is False
    assert any(
        item["code"] == "malformed-dialogue-structure"
        for item in gates["literary"]["blocking"]
    )


def test_review_parser_normalizes_markdown_wrapped_verdicts():
    parsed = book_project.parse_review(
        "- verdict: **needs_revision**（一处问题）\n"
        "- context_scope: **prose_only**（仅正文）\n"
    )

    assert parsed["verdict"] == "needs_revision"
    assert parsed["context_scope"] == "prose_only"


def test_project_status_separates_ready_evidence_from_benchmark_independence(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    _record_generation(tmp_path, book_dir)
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "blind-reader",
        _review_file(
            tmp_path,
            "blind-reader",
            "pass",
            provider="independent-provider",
            model="reader-model",
        ),
    )
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "chapter-editor",
        _review_file(
            tmp_path,
            "chapter-editor",
            "ready_for_editor_decision",
            provider="independent-provider",
            model="editor-model",
        ),
    )

    status = book_project.project_status(tmp_path, "demo", 1)

    assert status["review_confidence"] == "independent"
    assert status["benchmark_eligible"] is True
    assert status["author_approval"] is False


def test_project_status_reports_generation_budget_exhaustion(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    for round_number, stage in ((1, "raw"), (2, "final")):
        chapter = book_dir / "chapters/e01/ch-01/正文.md"
        chapter.write_text(
            chapter.read_text(encoding="utf-8")
            + f"\n第 {round_number} 轮修订。\n",
            encoding="utf-8",
        )
        _record_generation(
            tmp_path,
            book_dir,
            generation_id=f"generation.ch01.r{round_number}",
            run_id=f"writer-session-{round_number:03d}",
            review_round=round_number - 1,
            generation_stage=stage,
            metrics_source="user_observed",
        )

    status = book_project.project_status(tmp_path, "demo", 1)

    assert status["evidence"]["generation_count"] == 2
    assert status["evidence"]["review_cycle_status"] == "budget_exhausted"
    assert status["evidence"]["another_generation_requires_human"] is True


def test_advance_state_rejects_non_adjacent_forward_jump(tmp_path: Path):
    _make_book(tmp_path)

    with pytest.raises(BookProjectError, match="非法状态迁移"):
        book_project.advance_state(tmp_path, "demo", 1, "drafted")


def test_advance_state_allows_adjacent_forward_and_explicit_rollback(tmp_path: Path):
    _make_book(tmp_path)

    first = book_project.advance_state(tmp_path, "demo", 1, "context_collected")
    second = book_project.advance_state(tmp_path, "demo", 1, "scene_packaged")
    rollback = book_project.advance_state(tmp_path, "demo", 1, "planned")

    assert first["from"] == "planned"
    assert first["to"] == "context_collected"
    assert second["from"] == "context_collected"
    assert second["to"] == "scene_packaged"
    assert rollback["from"] == "scene_packaged"
    assert rollback["to"] == "planned"


def test_ready_rejects_placeholder_evidence_before_writing_state(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    paragraph = "他敲门，她没有开。" * 900
    chapter.write_text(
        f"# 第一章\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n",
        encoding="utf-8",
    )
    _waive_materials(book_dir)
    _record_generation(tmp_path, book_dir)
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "blind-reader",
        _review_file(tmp_path, "blind-reader", "pass"),
    )
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "chapter-editor",
        _review_file(
            tmp_path,
            "chapter-editor",
            "ready_for_editor_decision",
        ),
    )
    for state in (
        "context_collected",
        "scene_packaged",
        "drafted",
        "surface_checked",
        "blind_read",
        "editorial_reviewed",
    ):
        book_project.advance_state(tmp_path, "demo", 1, state)

    with pytest.raises(BookProjectError, match="占位证据"):
        book_project.advance_state(tmp_path, "demo", 1, "ready")

    status = book_project.project_status(tmp_path, "demo", 1)
    assert status["chapters"][0]["status"] == "editorial_reviewed"


def test_sync_tools_refreshes_managed_and_preserves_handwritten(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    # Simulate an outdated managed file and a hand-filled voice bible.
    managed = book_dir / "tools/narrative_gate.py"
    managed.write_text("old version", encoding="utf-8")
    voice = book_dir / "memory/voice-bible.md"
    voice.write_text("# 手写声音圣经\n", encoding="utf-8")

    dry = book_project.sync_tools(tmp_path, "demo", dry_run=True)
    assert "tools/narrative_gate.py" in dry["updated"]
    assert managed.read_text(encoding="utf-8") == "old version"

    result = book_project.sync_tools(tmp_path, "demo")
    assert "tools/narrative_gate.py" in result["updated"]
    assert managed.read_text(encoding="utf-8") != "old version"
    assert voice.read_text(encoding="utf-8") == "# 手写声音圣经\n"


def test_sync_tools_migrates_generated_v44_constitution_only(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    (book_dir / ".git").unlink()
    _remove_readonly_tree(tmp_path / ".local-book-git" / "demo.git")
    claude = book_dir / "CLAUDE.md"
    claude.write_text(
        claude.read_text(encoding="utf-8").replace(
            "- 工作流版本: v5.3（正文优先 Lean 原生工作流）",
            "- 工作流版本: v4.4（隔离 Writer Capsule 与外置控制面）",
        ),
        encoding="utf-8",
    )
    readme = book_dir / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "- 默认工作流: v5.3",
            "- 默认工作流: v4.4",
        ),
        encoding="utf-8",
    )

    result = book_project.sync_tools(tmp_path, "demo")

    assert "CLAUDE.md" in result["updated"]
    assert "README.md" in result["updated"]
    assert "v5.3" in claude.read_text(encoding="utf-8")
    assert "v5.3" in readme.read_text(encoding="utf-8")
    assert result["local_git"]["initialized"] is True
    assert result["local_git"]["commit_created"] is True
    assert result["local_git"]["remote_count"] == 0


def test_sync_tools_preserves_handwritten_constitution_without_version_marker(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    claude = book_dir / "CLAUDE.md"
    claude.write_text(
        "# 手写项目宪法\n\n- 标题: 《演示书》\n- 类型: 都市神豪系统流\n",
        encoding="utf-8",
    )

    result = book_project.sync_tools(tmp_path, "demo")

    assert "CLAUDE.md" in result["preserved"]
    assert claude.read_text(encoding="utf-8").startswith("# 手写项目宪法")


def test_sync_tools_preserves_handwritten_constitution_with_incidental_v37(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    claude = book_dir / "CLAUDE.md"
    claude.write_text(
        "# 手写项目宪法\n\n"
        "- 标题: 《演示书》\n"
        "- 类型: 都市神豪系统流\n\n"
        "本项目吸收了 v3.7 的实验经验，但以下红线由作者手工维护。\n",
        encoding="utf-8",
    )

    result = book_project.sync_tools(tmp_path, "demo")

    assert "CLAUDE.md" in result["preserved"]
    assert "作者手工维护" in claude.read_text(encoding="utf-8")


def test_sync_tools_maps_legacy_chapter_state_to_v38_chain(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    state_path = book_dir / "planning/chapter-state/ch01.md"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        book_project._new_chapter_state(1).replace(
            "- status: planned",
            "- status: causal_reviewed",
        ),
        encoding="utf-8",
    )

    result = book_project.sync_tools(tmp_path, "demo")

    assert "planning/chapter-state/ch01.md" in result["migrated_states"]
    migrated = book_project.parse_chapter_state(
        state_path.read_text(encoding="utf-8")
    )
    assert migrated["status"] == "surface_checked"


def test_sync_tools_adds_memory_kernel_assets_without_touching_canon(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    memory_guide = book_dir / "memory/MEMORY.md"
    record_template = book_dir / "memory/memory-record-template.md"
    memory_guide.unlink()
    record_template.unlink()
    canon = book_dir / "memory/canon/facts/handwritten.md"
    canon.parent.mkdir(parents=True, exist_ok=True)
    canon.write_text("handwritten canon", encoding="utf-8")

    result = book_project.sync_tools(tmp_path, "demo")

    assert "memory/MEMORY.md" in result["created"]
    assert "memory/memory-record-template.md" in result["created"]
    assert memory_guide.exists()
    assert record_template.exists()
    assert canon.read_text(encoding="utf-8") == "handwritten canon"


def test_sync_tools_creates_evaluation_assets_without_overwriting_constitution(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    constitution = book_dir / "evaluation/constitution.md"
    constitution.write_text("# 作者手工修订的评测宪法\n", encoding="utf-8")
    generation_template = book_dir / "evaluation/generation-template.md"
    generation_template.unlink()

    result = book_project.sync_tools(tmp_path, "demo")

    assert "evaluation/generation-template.md" in result["created"]
    assert generation_template.exists()
    assert (
        constitution.read_text(encoding="utf-8")
        == "# 作者手工修订的评测宪法\n"
    )


# --- adapter surface ------------------------------------------------------------


def test_adapter_project_status(tmp_path: Path, capsys):
    _make_book(tmp_path)
    code = adapter_main(["--root", str(tmp_path), "project-status", "demo"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["slug"] == "demo"
    assert "正文" not in json.dumps(data["data"].get("chapters", []))


def test_adapter_run_gates(tmp_path: Path, capsys):
    _make_book(tmp_path)
    code = adapter_main(["--root", str(tmp_path), "run-gates", "demo", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert "quality" in data["data"]
    assert "narrative" in data["data"]


def test_adapter_set_draft_mode_requires_confirm_and_run_gate_asserts_mode(
    tmp_path: Path, capsys
):
    _make_book(tmp_path)
    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "set-draft-mode",
            "demo",
            "1",
            "--mode",
            "exploration",
        ]
    )
    denied = _json_output(capsys)
    assert code == 0
    assert denied["ok"] is False
    assert denied["error"]["code"] == "confirmation_required"

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "set-draft-mode",
            "set-draft-mode",
            "demo",
            "1",
            "--mode",
            "exploration",
        ]
    )
    changed = _json_output(capsys)
    assert code == 0
    assert changed["ok"] is True
    assert changed["data"]["to"] == "exploration"

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "run-gates",
            "demo",
            "1",
            "--mode",
            "formal",
        ]
    )
    mismatch = _json_output(capsys)
    assert code == 0
    assert mismatch["ok"] is False
    assert "稿件模式" in mismatch["error"]["message"]


def test_adapter_record_review_requires_confirm(tmp_path: Path, capsys):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "record-review",
            "demo",
            "1",
            "--role",
            "blind-reader",
            "--file",
            str(review),
        ]
    )
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"


def test_adapter_record_review_success(tmp_path: Path, capsys):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "blind-reader", "pass")
    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "record-review",
            "record-review",
            "demo",
            "1",
            "--role",
            "blind-reader",
            "--file",
            str(review),
        ]
    )
    data = _json_output(capsys)
    assert code == 0
    assert data["ok"] is True
    assert data["state_changed"] is True


def test_adapter_advance_state_ready_gating(tmp_path: Path, capsys):
    _make_book(tmp_path)
    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "advance-state",
            "advance-state",
            "demo",
            "1",
            "--to",
            "ready",
        ]
    )
    data = _json_output(capsys)
    assert data["ok"] is False
    assert (
        "前置证据" in data["error"]["message"]
        or "generation evidence" in data["error"]["message"]
    )


def test_adapter_sync_tools_dry_run_needs_no_confirm(tmp_path: Path, capsys):
    _make_book(tmp_path)
    code = adapter_main(["--root", str(tmp_path), "sync-tools", "demo", "--dry-run"])
    data = _json_output(capsys)
    assert code == 0
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["state_changed"] is False


def test_adapter_sync_tools_requires_confirm_when_writing(tmp_path: Path, capsys):
    _make_book(tmp_path)
    code = adapter_main(["--root", str(tmp_path), "sync-tools", "demo"])
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"


def test_record_review_accepts_file_already_in_place(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    target = book_dir / "reviews/ch01-blind-reader.md"
    source = _review_file(tmp_path, "blind-reader", "pass")
    target.write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = book_project.record_review(tmp_path, "demo", 1, "blind-reader", target)
    assert result["verdict"] == "pass"
    assert target.exists()
