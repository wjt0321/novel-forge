"""Tests for vendor-neutral one-chapter-per-session orchestration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.novel_forge.chapter_sequence import (
    ChapterSequenceError,
    begin_chapter_sequence,
    chapter_sequence_status,
    claim_chapter_session,
    advance_chapter_sequence,
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
