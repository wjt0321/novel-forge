"""Tests for vendor-neutral one-chapter-per-session orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.novel_forge import chapter_sequence as chapter_sequence_module
from app.novel_forge.chapter_sequence import (
    ChapterSequenceError,
    begin_chapter_sequence,
    chapter_sequence_status,
    claim_chapter_session,
    advance_chapter_sequence,
    invalidate_chapter_session,
)
from app.novel_forge.project_templates import init_book_project
from app.novel_forge.skill_adapter import main as adapter_main


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _sequence_book(tmp_path: Path) -> Path:
    init_book_project(tmp_path, "demo", "演示书", "现实悬疑")
    book_dir = tmp_path / "books" / "demo"
    (book_dir / "planning/scene-package-ch01.md").write_text(
        "# Scene Package\n\n"
        "## 1. 场景压力\n"
        "- 本章目标：主角必须决定是否开门。\n"
        "- 停止边界：门锁第一次转动后结束。\n",
        encoding="utf-8",
    )
    return book_dir


def test_begin_sequence_rejects_five_chapter_batch(tmp_path: Path):
    _sequence_book(tmp_path)

    with pytest.raises(ChapterSequenceError, match="最多 4 章"):
        begin_chapter_sequence(
            tmp_path,
            "demo",
            start_chapter=1,
            chapter_count=5,
            sequence_id="too-long",
        )


def test_begin_sequence_issues_one_chapter_launch_and_persists_state(
    tmp_path: Path,
):
    book_dir = _sequence_book(tmp_path)

    result = begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        chapter_count=3,
        sequence_id="seq-001",
        orchestrator_run_id="orchestrator-001",
    )
    status = chapter_sequence_status(tmp_path, "demo", "seq-001")

    assert result["status"] == "awaiting_session"
    assert result["chapter_count"] == 3
    assert result["launch"]["launch_next_session"] is True
    assert result["launch"]["chapter"] == 1
    assert result["launch"]["scope"]["chapter_count"] == 1
    assert result["launch"]["new_native_session_required"] is True
    assert result["launch"]["writer_session_must_end_after_ready"] is True
    assert result["launch"]["handoff_path"] == (
        "memory/context-cache/ch01-handoff.md"
    )
    assert len(result["launch"]["handoff_sha256"]) == 64
    assert status["sequence_id"] == "seq-001"
    assert status["current_chapter"] == 1
    assert status["used_session_ids"] == []
    assert (
        book_dir / "planning/chapter-sequences/seq-001.json"
    ).is_file()

    handoff = (
        book_dir / result["launch"]["handoff_path"]
    ).read_text(encoding="utf-8")
    assert "本次 writer scope 仅限第 01 章" in handoff
    assert "旧会话消息" in handoff
    assert "Scene Package" in handoff
    assert len(handoff) < 30_000


def test_handoff_hides_numeric_style_targets_and_warns_against_copying(
    tmp_path: Path,
):
    book_dir = _sequence_book(tmp_path)
    (book_dir / "memory/voice-bible.md").write_text(
        "# Voice Bible\n\n"
        "## exemplar_notes\n"
        "> 他把介绍信对折，再对折，塞进内袋，扣子摁了两下才摁住。\n"
        "- 句长均值：12.8\n"
        "- 对白占比：4.2%\n"
        "- 段内句数保持 1.3\n",
        encoding="utf-8",
    )

    result = begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        sequence_id="writer-safe-voice",
    )
    handoff = (
        book_dir / result["launch"]["handoff_path"]
    ).read_text(encoding="utf-8")

    assert "他把介绍信对折" in handoff
    assert "句长均值：12.8" not in handoff
    assert "对白占比：4.2%" not in handoff
    assert "段内句数保持 1.3" not in handoff
    assert "不得复用范文的具体名词、标志动作、章末物件或句法骨架" in handoff
    assert "正文默认 standard/medium" in handoff
    assert "Max/长思考" in handoff


def test_writer_handoff_hides_editor_only_scene_reasoning(tmp_path: Path):
    book_dir = _sequence_book(tmp_path)
    (book_dir / "planning/scene-package-ch01.md").write_text(
        "# Scene Package\n\n"
        "## 0. 边界\n"
        "- 开始动作：主角核对门锁。\n"
        "- 停止动作：门外的人叫出旧名。\n\n"
        "## 1. 场景压力\n"
        "- 目标：守住房间。\n"
        "- 阻力：持钥匙的人正在开门。\n\n"
        "## 1c. 决策问题\n"
        "- 角色拒绝承认什么：他害怕旧案重演。\n\n"
        "## 1d. 认知与可证伪假设\n"
        "| 观察 | 当前假设 | 替代解释 | 置信度 | 可推翻证据 | 状态 |\n"
        "|---|---|---|---|---|---|\n"
        "| 钥匙能转 | 对方是家属 | 钥匙被复制 | 中 | 核验身份 | 未决 |\n\n"
        "## 1e. 规划反证与常识检查\n"
        "- 人物知识来源：逐项核验全部可能来源。\n\n"
        "## 2. 在场者状态\n"
        "| 人物 | 此刻目标 | 隐瞒/未知 | 本场变化 |\n"
        "|---|---|---|---|\n"
        "| 主角 | 守门 | 不肯承认害怕 | 主动停工 |\n\n"
        "## 3. Beat 因果链\n"
        "| # | 触发 | 行动/决定 | 阻力/反应 | 结果与下一步 | 语域 |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 锁芯转动 | 主角抵门 | 门链松动 | 主角承担停工损失 | 贴身 |\n\n"
        "## 3c. 因果归属账本\n"
        "| 动作/条件 | 提出/执行者 | 知情者 | 后果承担者 |\n"
        "|---|---|---|---|\n"
        "| 停工 | 主角 | 委托人 | 主角 |\n\n"
        "## 4. 信息账本\n"
        "- 唯一新信息：门外人知道主角旧名。\n\n"
        "## 5. 信息预算\n"
        "- 关键对白意图：用旧名夺走主角的程序优势。\n\n"
        "## 5b. 专业判断审计\n"
        "- 门锁判断的执行条件与风险全部登记。\n\n"
        "## 6. 人物性呼吸段\n"
        "- 主角重新贴歪掉的标签，用拖延回避决定。\n\n"
        "## 7. 场景余波\n"
        "- 身体：掌心留下门链黑灰。\n",
        encoding="utf-8",
    )

    result = begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        sequence_id="writer-story-brief",
    )
    handoff = (
        book_dir / result["launch"]["handoff_path"]
    ).read_text(encoding="utf-8")

    assert "## 当前章 Writer Story Brief" in handoff
    assert "主角核对门锁" in handoff
    assert "持钥匙的人正在开门" in handoff
    assert "主角承担停工损失" in handoff
    assert "门外人知道主角旧名" in handoff
    assert "重新贴歪掉的标签" in handoff
    assert "认知与可证伪假设" not in handoff
    assert "规划反证与常识检查" not in handoff
    assert "因果归属账本" not in handoff
    assert "专业判断审计" not in handoff
    assert "钥匙被复制" not in handoff
    assert "逐项核验全部可能来源" not in handoff
    assert "后台故事义务" in handoff
    assert "不得在正文中逐条证明" in handoff
    assert "只完成本章正文" in handoff
    assert "当前章证据、当前章审稿与 ready 闭环" not in handoff
    assert "证据、审稿、状态与 ready 由编排器和独立角色处理" in handoff
    assert "主动选择不能用好奇、观察或事后补救冒充" in handoff
    assert "禁止把规划、因果链、替代解释或主题翻译成说明段" in handoff


def test_claim_requires_new_native_session_and_advance_requires_ready(
    tmp_path: Path,
):
    _sequence_book(tmp_path)
    begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        chapter_count=2,
        sequence_id="seq-claim",
    )

    claimed = claim_chapter_session(
        tmp_path,
        "demo",
        "seq-claim",
        "writer-native-001",
    )

    assert claimed["status"] == "running"
    assert claimed["active_session_id"] == "writer-native-001"
    assert claimed["current_chapter"] == 1
    with pytest.raises(ChapterSequenceError, match="尚未完整 ready"):
        advance_chapter_sequence(
            tmp_path,
            "demo",
            "seq-claim",
            "writer-native-001",
        )


def test_session_id_cannot_be_reused_by_another_sequence(tmp_path: Path):
    _sequence_book(tmp_path)
    begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        chapter_count=1,
        sequence_id="seq-a",
    )
    claim_chapter_session(
        tmp_path,
        "demo",
        "seq-a",
        "writer-native-shared",
    )

    # A completed/abandoned external run must not be silently relabelled as a
    # fresh chapter session. Use another project to avoid overlap semantics.
    init_book_project(tmp_path, "other", "另一书", "现实悬疑")
    other = tmp_path / "books" / "other"
    (other / "planning/scene-package-ch01.md").write_text(
        "# Scene Package\n\n## 1. 场景压力\n- 本章目标：离开。\n",
        encoding="utf-8",
    )
    begin_chapter_sequence(
        tmp_path,
        "other",
        start_chapter=1,
        chapter_count=1,
        sequence_id="seq-b",
    )

    with pytest.raises(ChapterSequenceError, match="已被使用"):
        claim_chapter_session(
            tmp_path,
            "other",
            "seq-b",
            "writer-native-shared",
        )


def test_adapter_sequence_operations_are_json_only_and_confirmed(
    tmp_path: Path,
    capsys,
):
    _sequence_book(tmp_path)

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "begin-chapter-sequence",
            "demo",
            "--start-chapter",
            "1",
            "--chapter-count",
            "1",
            "--sequence-id",
            "adapter-seq",
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
            "begin-chapter-sequence",
            "begin-chapter-sequence",
            "demo",
            "--start-chapter",
            "1",
            "--chapter-count",
            "1",
            "--sequence-id",
            "adapter-seq",
        ]
    )
    begun = _json_output(capsys)
    assert code == 0
    assert begun["ok"] is True
    assert begun["data"]["launch"]["launch_next_session"] is True
    assert "Scene Package" not in json.dumps(begun, ensure_ascii=False)

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "chapter-sequence-status",
            "demo",
            "adapter-seq",
        ]
    )
    status = _json_output(capsys)
    assert code == 0
    assert status["ok"] is True
    assert status["data"]["current_chapter"] == 1


def test_sequence_status_marks_forged_complete_record_inconsistent(
    tmp_path: Path,
):
    book_dir = _sequence_book(tmp_path)
    begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        chapter_count=1,
        sequence_id="forged-complete",
    )
    path = (
        book_dir
        / "planning/chapter-sequences/forged-complete.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(
        {
            "status": "complete",
            "current_index": 1,
            "active_session_id": None,
            "used_session_ids": ["writer-native-forged"],
            "completed_chapters": [1],
        }
    )
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    status = chapter_sequence_status(
        tmp_path,
        "demo",
        "forged-complete",
    )

    assert status["status"] == "complete"
    assert status["effective_status"] == "inconsistent"
    assert status["integrity"]["status"] == "blocked"
    assert status["integrity"]["findings"]


def test_complete_sequence_uses_successful_session_after_invalidation(
    tmp_path: Path,
    monkeypatch,
):
    book_dir = _sequence_book(tmp_path)
    begin_chapter_sequence(
        tmp_path,
        "demo",
        start_chapter=1,
        chapter_count=1,
        sequence_id="recovered-complete",
    )
    claim_chapter_session(
        tmp_path,
        "demo",
        "recovered-complete",
        "writer-native-compromised",
    )
    invalidate_chapter_session(
        tmp_path,
        "demo",
        "recovered-complete",
        "writer-native-compromised",
        reason="guardian_capsule_compromised",
    )
    claim_chapter_session(
        tmp_path,
        "demo",
        "recovered-complete",
        "writer-native-clean",
    )
    path = (
        book_dir
        / "planning/chapter-sequences/recovered-complete.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(
        {
            "status": "complete",
            "current_index": 1,
            "active_session_id": None,
            "completed_chapters": [1],
            "completed_sessions": {"1": "writer-native-clean"},
        }
    )
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        chapter_sequence_module,
        "_require_ready",
        lambda *_: (book_dir, {"generation_id": "generation.clean"}),
    )
    monkeypatch.setattr(
        chapter_sequence_module,
        "find_evidence_record",
        lambda *_: (
            SimpleNamespace(data={"run_id": "writer-native-clean"}),
            Path("generation.clean.md"),
        ),
    )

    status = chapter_sequence_status(
        tmp_path,
        "demo",
        "recovered-complete",
    )

    assert status["used_session_ids"] == [
        "writer-native-compromised",
        "writer-native-clean",
    ]
    assert status["invalidated_session_count"] == 1
    assert status["effective_status"] == "complete"
    assert status["integrity"] == {"status": "clean", "findings": []}
