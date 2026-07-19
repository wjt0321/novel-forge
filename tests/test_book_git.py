"""Tests for isolated local Git histories under books/<slug>/."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.novel_forge.book_git import (
    BookGitError,
    book_git_status,
    checkpoint_book,
    initialize_book_git,
    restore_book_worktree,
)
from app.novel_forge.skill_adapter import main as adapter_main


def _book(tmp_path: Path, slug: str = "demo") -> Path:
    book_dir = tmp_path / "books" / slug
    book_dir.mkdir(parents=True)
    (book_dir / ".gitignore").write_text(
        ".novel-forge/\nmemory/context-cache/\n",
        encoding="utf-8",
    )
    (book_dir / "README.md").write_text("# 演示书\n", encoding="utf-8")
    return book_dir


def _git(book_dir: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=book_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_initialize_book_git_uses_external_metadata_and_no_remote(
    tmp_path: Path,
):
    book_dir = _book(tmp_path)

    result = initialize_book_git(tmp_path, "demo", "演示书")

    git_pointer = book_dir / ".git"
    assert git_pointer.is_file()
    assert Path(result["git_dir"]) == tmp_path / ".local-book-git" / "demo.git"
    assert Path(result["git_dir"]).is_dir()
    assert result["initialized"] is True
    assert result["commit_created"] is True
    assert result["remote_count"] == 0
    assert _git(book_dir, "branch", "--show-current") == "main"
    assert _git(book_dir, "log", "-1", "--pretty=%s") == (
        "book-init: initialize 演示书"
    )
    assert _git(book_dir, "config", "user.name") == "Novel Forge"
    assert _git(book_dir, "config", "user.email") == (
        "novel-forge@local.invalid"
    )
    assert _git(book_dir, "status", "--porcelain") == ""


def test_checkpoint_book_commits_all_tracked_changes_and_can_tag(
    tmp_path: Path,
):
    book_dir = _book(tmp_path)
    initialize_book_git(tmp_path, "demo", "演示书")
    chapter = book_dir / "chapters" / "e01" / "ch-01" / "正文.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# 第一章\n\n正文。\n", encoding="utf-8")

    result = checkpoint_book(
        tmp_path,
        "demo",
        "chapter: ch01 ready",
        tag="checkpoint/ch01-ch05",
    )

    assert result["committed"] is True
    assert result["message"] == "chapter: ch01 ready"
    assert result["tag"] == "checkpoint/ch01-ch05"
    assert _git(book_dir, "status", "--porcelain") == ""
    assert _git(book_dir, "tag", "--list") == "checkpoint/ch01-ch05"
    assert _git(
        book_dir,
        "for-each-ref",
        "refs/tags/checkpoint/ch01-ch05",
        "--format=%(objecttype)",
    ) == "tag"


def test_checkpoint_book_is_noop_when_nothing_changed(tmp_path: Path):
    _book(tmp_path)
    initialize_book_git(tmp_path, "demo", "演示书")

    result = checkpoint_book(tmp_path, "demo", "chapter: ch01 draft")

    assert result["committed"] is False
    assert result["message"] == "No changes to commit."
    assert result["commit_hash"]


def test_restore_book_worktree_recovers_tracked_files(tmp_path: Path):
    book_dir = _book(tmp_path)
    initialize_book_git(tmp_path, "demo", "演示书")
    chapter = book_dir / "chapters" / "e01" / "ch-01" / "正文.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# 第一章\n\n不能丢失的正文。\n", encoding="utf-8")
    checkpoint = checkpoint_book(
        tmp_path,
        "demo",
        "chapter: ch01 draft",
    )
    expected = chapter.read_bytes()

    shutil.rmtree(book_dir)
    result = restore_book_worktree(tmp_path, "demo")

    assert result["restored"] is True
    assert result["commit_hash"] == checkpoint["commit_hash"]
    assert chapter.read_bytes() == expected
    assert (book_dir / ".git").is_file()
    assert _git(book_dir, "status", "--porcelain") == ""


def test_book_git_status_rejects_unexpected_gitdir_pointer(tmp_path: Path):
    book_dir = _book(tmp_path)
    initialize_book_git(tmp_path, "demo", "演示书")
    book_dir.rename(tmp_path / "books" / "renamed")

    with pytest.raises(BookGitError, match="unexpected git directory"):
        book_git_status(tmp_path, "renamed")


def _adapter_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_adapter_can_initialize_status_and_checkpoint_local_book_git(
    tmp_path: Path,
    capsys,
):
    book_dir = _book(tmp_path)

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-book-git",
            "init-book-git",
            "demo",
            "--title",
            "演示书",
        ]
    )
    assert code == 0
    initialized = _adapter_json(capsys)
    assert initialized["ok"] is True
    assert initialized["data"]["local_git"]["remote_count"] == 0

    (book_dir / "README.md").write_text("# 演示书\n\n新说明。\n", encoding="utf-8")
    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "book-git-checkpoint",
            "book-git-checkpoint",
            "demo",
            "--message",
            "manual: update readme",
            "--tag",
            "checkpoint/ch01-ch05",
        ]
    )
    assert code == 0
    checkpoint = _adapter_json(capsys)
    assert checkpoint["data"]["local_git"]["committed"] is True
    assert checkpoint["data"]["local_git"]["tag"] == "checkpoint/ch01-ch05"

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "book-git-status",
            "demo",
        ]
    )
    assert code == 0
    status = _adapter_json(capsys)
    assert status["data"]["local_git"]["last_message"] == (
        "manual: update readme"
    )


def test_adapter_can_restore_missing_book_worktree(tmp_path: Path, capsys):
    book_dir = _book(tmp_path)
    initialize_book_git(tmp_path, "demo", "演示书")
    shutil.rmtree(book_dir)

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "restore-book-git",
            "restore-book-git",
            "demo",
        ]
    )

    assert code == 0
    data = _adapter_json(capsys)
    assert data["ok"] is True
    assert data["data"]["local_git"]["restored"] is True
    assert (book_dir / "README.md").exists()
