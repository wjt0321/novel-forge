"""Tests for the books/<slug>/ project operations (book_project + adapter ops)."""

import json
from pathlib import Path

import pytest

from app.novel_forge import book_project
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
        "## 2. 在场者状态\n| 人物 | 表面目标 |\n|---|---|\n| 甲 | 乙 |\n\n"
        "## 3. Beat 因果链\n| # | 触发 |\n|---|---|\n| 1 | a |\n| 2 | b |\n\n"
        "## 4. 信息账本\n| 信息 | 来源 |\n|---|---|\n| x | y |\n\n"
        "## 5. 信息预算\n- 主冲突：x\n",
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


def _review_file(tmp_path: Path, role: str, verdict: str, chapter: str = "ch01") -> Path:
    path = tmp_path / f"review-{role}.md"
    path.write_text(
        f"# Review — {chapter} / {role}\n\n"
        f"- chapter: {chapter}\n"
        f"- role: {role}\n"
        f"- verdict: {verdict}\n"
        "- date: 2026-07-16\n\n"
        "## Findings\n"
        "| # | 级别 (MUST/MAY) | 位置 | 原文证据 | 读者效果 | 修订意图 | 状态 (open/closed) |\n"
        "|---|---|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    return path


# --- business layer -----------------------------------------------------------


def test_project_status_reads_progress_and_states(tmp_path: Path):
    _make_book(tmp_path)
    data = book_project.project_status(tmp_path, "demo", None)
    assert data["slug"] == "demo"
    assert data["title"] == "演示书"
    assert data["genre"] == "都市神豪系统流"
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
    assert state["chapters"][0]["status"] == "blind_read"


def test_record_review_rejects_mismatched_role(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "line-editor", "pass")
    with pytest.raises(BookProjectError):
        book_project.record_review(tmp_path, "demo", 1, "causal-editor", review)


def test_record_review_rejects_editorial_verdict_for_line_roles(tmp_path: Path):
    _make_book(tmp_path)
    review = _review_file(tmp_path, "causal-editor", "ready_for_editor_decision")
    with pytest.raises(BookProjectError):
        book_project.record_review(tmp_path, "demo", 1, "causal-editor", review)


def test_advance_state_ready_requires_reviews(tmp_path: Path):
    _make_book(tmp_path)
    with pytest.raises(BookProjectError):
        book_project.advance_state(tmp_path, "demo", 1, "ready")
    book_project.record_review(
        tmp_path, "demo", 1, "blind-reader", _review_file(tmp_path, "blind-reader", "pass")
    )
    with pytest.raises(BookProjectError):
        book_project.advance_state(tmp_path, "demo", 1, "ready")
    book_project.record_review(
        tmp_path, "demo", 1, "texture-editor", _review_file(tmp_path, "texture-editor", "pass")
    )
    with pytest.raises(BookProjectError):
        book_project.advance_state(tmp_path, "demo", 1, "ready")
    book_project.record_review(
        tmp_path,
        "demo",
        1,
        "chapter-editor",
        _review_file(tmp_path, "chapter-editor", "ready_for_editor_decision"),
    )
    result = book_project.advance_state(tmp_path, "demo", 1, "ready")
    assert result["to"] == "ready"


def test_advance_state_rejects_unknown_state(tmp_path: Path):
    _make_book(tmp_path)
    with pytest.raises(BookProjectError):
        book_project.advance_state(tmp_path, "demo", 1, "published")


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
    assert "前置证据" in data["error"]["message"]


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
    target.write_text(
        "# Review\n\n- chapter: ch01\n- role: blind-reader\n- verdict: pass\n- date: 2026-07-17\n",
        encoding="utf-8",
    )
    result = book_project.record_review(tmp_path, "demo", 1, "blind-reader", target)
    assert result["verdict"] == "pass"
    assert target.exists()
