"""Tests for the books/<slug>/ project operations (book_project + adapter ops)."""

import json
import hashlib
from pathlib import Path

import pytest

from app.novel_forge import book_project
from app.novel_forge.book_evidence import record_evidence, render_evidence_markdown
from app.novel_forge.book_project import BookProjectError
from app.novel_forge.project_templates import init_book_project
from app.novel_forge.skill_adapter import main as adapter_main


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


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
        "## 5. 信息预算\n- 主冲突：x\n\n"
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
) -> Path:
    number = int(chapter.removeprefix("ch"))
    binding = book_project.review_binding(tmp_path, "demo", number)
    path = tmp_path / f"review-{role}.md"
    path.write_text(
        f"# Review — {chapter} / {role}\n\n"
        f"- chapter: {chapter}\n"
        f"- role: {role}\n"
        f"- verdict: {verdict}\n"
        "- date: 2026-07-16\n\n"
        f"- source_fingerprint: {binding['source_fingerprint']}\n"
        f"- chapter_sha256: {binding['chapter_sha256']}\n"
        f"- planning_sha256: {binding['planning_sha256']}\n"
        f"- draft_mode: {binding['draft_mode']}\n"
        f"- generation_id: {binding['generation_id']}\n\n"
        "- reviewer_type: model\n"
        f"- reviewer_id: {role}-instance\n"
        f"- provider: {provider}\n"
        f"- model: {model}\n"
        f"- context_scope: {'prose_only' if role == 'blind-reader' else 'full_review_context'}\n"
        f"- independence_note: {independence_note}\n\n"
        "## Findings\n"
        "| # | 级别 (MUST/MAY) | 位置 | 原文证据 | 读者效果 | 修订意图 | 状态 (open/closed) |\n"
        "|---|---|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    return path


def _record_generation(
    tmp_path: Path,
    book_dir: Path,
    *,
    provider: str = "writer-provider",
    model: str = "writer-model",
    generation_id: str = "generation.ch01.current",
    **metrics,
) -> str:
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    source = tmp_path / f"{generation_id}.md"
    source.write_text(
        render_evidence_markdown(
            {
                "schema_version": 1,
                "id": generation_id,
                "kind": "generation",
                "created_at": "2026-07-17T12:00:00Z",
                "authority": "agent",
                "source_paths": ["chapters/e01/ch-01/正文.md"],
                "summary": "当前正式稿生成来源。",
                "chapter": 1,
                "draft_mode": "formal",
                "writer_type": "agent",
                "provider": provider,
                "model": model,
                "content_path": "chapters/e01/ch-01/正文.md",
                "content_sha256": hashlib.sha256(chapter.read_bytes()).hexdigest(),
                **metrics,
            }
        ),
        encoding="utf-8",
    )
    record_evidence(tmp_path, "demo", source)
    book_project.bind_generation(tmp_path, "demo", 1, generation_id)
    return generation_id


# --- business layer -----------------------------------------------------------


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
    for role in ("causal-editor", "line-editor", "texture-editor", "consistency-guard"):
        book_project.record_review(
            tmp_path, "demo", 1, role, _review_file(tmp_path, role, "pass")
        )
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
        "action_drafted",
        "dialogue_planned",
        "drafted",
        "surface_checked",
        "causal_reviewed",
        "line_reviewed",
        "texture_reviewed",
        "consistency_checked",
        "blind_read",
        "editorial_reviewed",
    ):
        book_project.advance_state(tmp_path, "demo", 1, state)
    result = book_project.advance_state(tmp_path, "demo", 1, "ready")
    assert result["to"] == "ready"


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
    for round_number, stage in ((1, "raw"), (2, "revised"), (3, "final")):
        _record_generation(
            tmp_path,
            book_dir,
            generation_id=f"generation.ch01.r{round_number}",
            review_round=round_number - 1,
            generation_stage=stage,
            metrics_source="user_observed",
        )

    status = book_project.project_status(tmp_path, "demo", 1)

    assert status["evidence"]["generation_count"] == 3
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


def test_sync_tools_refreshes_managed_and_preserves_handwritten(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    # Simulate an outdated managed file and a hand-filled voice bible.
    agent = book_dir / ".claude/agents/line-editor.md"
    agent.write_text("old version", encoding="utf-8")
    voice = book_dir / "memory/voice-bible.md"
    voice.write_text("# 手写声音圣经\n", encoding="utf-8")

    dry = book_project.sync_tools(tmp_path, "demo", dry_run=True)
    assert ".claude/agents/line-editor.md" in dry["updated"]
    assert agent.read_text(encoding="utf-8") == "old version"  # dry run did not write

    result = book_project.sync_tools(tmp_path, "demo")
    assert ".claude/agents/line-editor.md" in result["updated"]
    assert agent.read_text(encoding="utf-8") != "old version"
    assert voice.read_text(encoding="utf-8") == "# 手写声音圣经\n"


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
