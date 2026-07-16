"""Tests for the new books/<slug>/ project layout."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.novel_forge.project_templates import init_book_project
from app.novel_forge.service import NovelForgeService
from app.novel_forge.skill_adapter import main


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def test_init_book_project_creates_expected_structure(tmp_path: Path):
    result = init_book_project(tmp_path, "test-book", "Test Book", "现实悬疑")

    book_dir = Path(result["book_dir"])
    assert book_dir == tmp_path / "books" / "test-book"
    assert (book_dir / ".gitignore").exists()
    assert (book_dir / "CLAUDE.md").exists()
    assert (book_dir / "README.md").exists()
    assert (book_dir / "chapters").is_dir()
    assert (book_dir / "memory" / "entities").is_dir()
    assert (book_dir / "memory" / "future").is_dir()
    assert (book_dir / "memory" / "context-cache").is_dir()
    assert (book_dir / "planning" / "events").is_dir()
    assert (book_dir / "reviews" / "archive").is_dir()
    assert (book_dir / "patches").is_dir()
    assert (book_dir / ".snapshots").is_dir()
    assert (book_dir / "tools" / "quality_check.py").exists()
    assert (book_dir / "tools" / "narrative_gate.py").exists()
    assert (book_dir / "planning" / "chapter-state").is_dir()
    assert (book_dir / "planning" / "scene-package-template.md").exists()
    assert (book_dir / "planning" / "action-draft-template.md").exists()
    assert (book_dir / "planning" / "dialogue-ledger-template.md").exists()
    assert (book_dir / "planning" / "chapter-state-template.md").exists()
    assert (book_dir / ".claude" / "agents" / "context-collector.md").exists()
    assert (book_dir / ".claude" / "agents" / "consistency-guard.md").exists()
    assert (book_dir / ".claude" / "agents" / "chapter-editor.md").exists()
    assert (book_dir / ".claude" / "agents" / "causal-editor.md").exists()
    assert (book_dir / ".claude" / "agents" / "line-editor.md").exists()
    assert (book_dir / ".claude" / "agents" / "orchestrator.md").exists()

    claude_md = (book_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Test Book" in claude_md
    assert "test-book" in claude_md
    assert "chapters/eXX/ch-XX/正文.md" in claude_md
    assert "工作流版本" in claude_md
    assert "v3" in claude_md
    assert "严禁复制其他书的正文" in claude_md

    readme = (book_dir / "README.md").read_text(encoding="utf-8")
    assert "Test Book" in readme
    assert "默认工作流: v3" in readme
    assert "不得复制其他书的正文" in readme



def test_generated_narrative_gate_rejects_unfilled_scene_package(tmp_path: Path):
    result = init_book_project(tmp_path, "gate-book", "Gate Book", "悬疑")
    book_dir = Path(result["book_dir"])
    chapter = book_dir / "chapter.md"
    chapter.write_text("# 第一章\n\n甲走进门。\n\n乙没有起身。\n\n雨停了。\n", encoding="utf-8")
    package = book_dir / "planning" / "scene-package-ch01.md"
    package.write_text(
        (book_dir / "planning" / "scene-package-template.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    script = book_dir / "tools" / "narrative_gate.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(chapter), str(package)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 1
    assert "scene-package 缺少或未填写章节" in proc.stdout


def test_init_book_project_does_not_overwrite_existing_files(tmp_path: Path):
    book_dir = tmp_path / "books" / "preserve"
    (book_dir / ".claude" / "agents").mkdir(parents=True)
    (book_dir / "CLAUDE.md").write_text("existing", encoding="utf-8")
    (book_dir / ".claude" / "agents" / "context-collector.md").write_text(
        "custom agent", encoding="utf-8"
    )

    result = init_book_project(tmp_path, "preserve", "Preserve", "科幻")

    assert "CLAUDE.md" in result["skipped_files"]
    assert ".claude/agents/context-collector.md" in result["skipped_files"]
    assert (book_dir / "README.md").exists()
    assert (book_dir / "CLAUDE.md").read_text(encoding="utf-8") == "existing"
    assert (
        book_dir / ".claude" / "agents" / "context-collector.md"
    ).read_text(encoding="utf-8") == "custom agent"


def test_init_book_project_rejects_bad_slug():
    with pytest.raises(Exception):
        init_book_project(Path("/tmp"), "bad slug!", "Title", "Genre")


def test_adapter_init_novel_project_requires_confirm(tmp_path: Path, capsys):
    code = main(
        [
            "--root",
            str(tmp_path),
            "init-novel-project",
            "new-book",
            "--title",
            "New Book",
            "--genre",
            "悬疑",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"
    assert not (tmp_path / "books" / "new-book").exists()


def test_adapter_init_novel_project_success(tmp_path: Path, capsys):
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-novel-project",
            "init-novel-project",
            "new-book",
            "--title",
            "New Book",
            "--genre",
            "悬疑",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["operation"] == "init-novel-project"
    assert data["state_changed"] is True
    assert "created_files" in data["data"]
    assert (tmp_path / "books" / "new-book" / "CLAUDE.md").exists()
    # Adapter must not leak file contents.
    assert "小说宪法" not in json.dumps(data)


def test_service_init_novel_project_does_not_require_database(tmp_path: Path):
    # The new project layout is filesystem-only; service can still be used
    # without an existing library/ data/ setup.
    svc = NovelForgeService(tmp_path)
    result = svc.init_novel_project("fs-only", "FS Only", "短篇")
    assert (tmp_path / "books" / "fs-only" / "tools" / "quality_check.py").exists()


def test_quality_check_script_detects_issues(tmp_path: Path):
    init_book_project(tmp_path, "qc", "QC", "测试")
    script = tmp_path / "books" / "qc" / "tools" / "quality_check.py"
    sample = tmp_path / "sample.md"
    sample.write_text(
        '她说""你好""。\n'
        "你好吗。\n"
        "为人民服务五个字。\n"
        "不是A而是B。\n"
        "他有——把枪。\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(script), str(sample)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    output = proc.stdout
    assert output is not None
    assert "quote-duplication" in output
    assert "question-mark-mismatch" in output
    assert "word-count-tic" in output
    assert "negation-flip" in output
    assert "em-dash" in output


def test_quality_check_script_clean_file(tmp_path: Path):
    init_book_project(tmp_path, "qc2", "QC2", "测试")
    script = tmp_path / "books" / "qc2" / "tools" / "quality_check.py"
    sample = tmp_path / "clean.md"
    sample.write_text('她说："你好。"\n天黑了。\n', encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script), str(sample)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "No findings" in proc.stdout
