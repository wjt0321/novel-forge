"""Local-only Git history for isolated `books/<slug>/` projects."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Any

from .models import NovelForgeError


LOCAL_BOOK_GIT_DIRECTORY = ".local-book-git"
_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_TAG_RE = re.compile(r"^checkpoint/ch\d{2,}-ch\d{2,}$")


class BookGitError(NovelForgeError):
    """Raised when a per-book local Git operation cannot be verified."""


def _remove_readonly_tree(path: Path) -> None:
    """Remove a Git directory whose object files may be read-only on Windows."""

    def make_writable_and_retry(
        function: Any,
        target: str,
        _: tuple[type[BaseException], BaseException, Any],
    ) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _paths(root: Path, slug: str) -> tuple[Path, Path, Path]:
    if not _SLUG_RE.fullmatch(slug):
        raise BookGitError(f"Invalid book slug: {slug!r}.")
    root = Path(root).resolve()
    book_dir = root / "books" / slug
    git_dir = root / LOCAL_BOOK_GIT_DIRECTORY / f"{slug}.git"
    pointer = book_dir / ".git"
    return book_dir, git_dir, pointer


def _run(
    args: list[str],
    *,
    cwd: Path,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise BookGitError("git executable not found.") from exc
    if proc.returncode not in allowed_returncodes:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown Git error"
        raise BookGitError(f"Git command failed: {' '.join(args)}: {detail}")
    return proc


def _read_pointer(pointer: Path) -> Path:
    if not pointer.is_file():
        raise BookGitError(f"book Git pointer is missing: {pointer}")
    text = pointer.read_text(encoding="utf-8-sig").strip()
    if not text.lower().startswith("gitdir:"):
        raise BookGitError(f"invalid book Git pointer: {pointer}")
    value = text.split(":", 1)[1].strip()
    target = Path(value)
    if not target.is_absolute():
        target = (pointer.parent / target).resolve()
    else:
        target = target.resolve()
    return target


def _head(book_dir: Path) -> str | None:
    proc = _run(
        ["rev-parse", "HEAD"],
        cwd=book_dir,
        allowed_returncodes=(0, 128),
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def book_git_status(root: Path, slug: str) -> dict[str, Any]:
    """Return metadata-only status for a book's isolated local repository."""
    book_dir, git_dir, pointer = _paths(root, slug)
    if not book_dir.is_dir():
        raise BookGitError(f"book directory not found: {book_dir}")
    actual_git_dir = _read_pointer(pointer)
    if actual_git_dir != git_dir.resolve():
        raise BookGitError(
            "book Git pointer references an unexpected git directory: "
            f"{actual_git_dir}"
        )
    if not git_dir.is_dir():
        raise BookGitError(f"book Git directory not found: {git_dir}")
    top = Path(
        _run(["rev-parse", "--show-toplevel"], cwd=book_dir).stdout.strip()
    ).resolve()
    if top != book_dir.resolve():
        raise BookGitError(f"unexpected book Git worktree root: {top}")
    remotes = [
        line
        for line in _run(["remote"], cwd=book_dir).stdout.splitlines()
        if line.strip()
    ]
    status_lines = [
        line
        for line in _run(["status", "--porcelain"], cwd=book_dir).stdout.splitlines()
        if line.strip()
    ]
    head = _head(book_dir)
    last_message = None
    if head:
        last_message = _run(
            ["log", "-1", "--pretty=%s"],
            cwd=book_dir,
        ).stdout.strip()
    return {
        "initialized": True,
        "book_dir": str(book_dir),
        "git_dir": str(git_dir),
        "head": head,
        "dirty": bool(status_lines),
        "changed_paths": len(status_lines),
        "remote_count": len(remotes),
        "last_message": last_message,
    }


def initialize_book_git(
    root: Path,
    slug: str,
    title: str,
) -> dict[str, Any]:
    """Initialize a local-only repository and create the book-init commit."""
    book_dir, git_dir, pointer = _paths(root, slug)
    if not book_dir.is_dir():
        raise BookGitError(f"book directory not found: {book_dir}")
    if pointer.exists():
        status = book_git_status(root, slug)
        return {**status, "initialized": False, "commit_created": False}
    if git_dir.exists():
        raise BookGitError(
            "external book Git history already exists but the worktree pointer "
            f"is missing: {git_dir}; use restore-book-git"
        )
    git_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(
            [
                "init",
                "--initial-branch=main",
                f"--separate-git-dir={git_dir}",
                str(book_dir),
            ],
            cwd=book_dir.parent,
        )
        _run(["config", "user.name", "Novel Forge"], cwd=book_dir)
        _run(
            ["config", "user.email", "novel-forge@local.invalid"],
            cwd=book_dir,
        )
        _run(["add", "-A"], cwd=book_dir)
        _run(
            ["commit", "-m", f"book-init: initialize {title.strip()}"],
            cwd=book_dir,
        )
    except Exception:
        if pointer.exists():
            pointer.unlink()
        if git_dir.exists():
            _remove_readonly_tree(git_dir)
        raise
    status = book_git_status(root, slug)
    return {**status, "initialized": True, "commit_created": True}


def checkpoint_book(
    root: Path,
    slug: str,
    message: str,
    *,
    tag: str | None = None,
) -> dict[str, Any]:
    """Commit the current book worktree and optionally add an immutable tag."""
    if not message or not message.strip():
        raise BookGitError("checkpoint message cannot be empty.")
    if re.search(r"[\x00-\x1f]", message):
        raise BookGitError("checkpoint message contains control characters.")
    if tag is not None and not _TAG_RE.fullmatch(tag):
        raise BookGitError(f"invalid checkpoint tag: {tag!r}")
    book_dir, _, _ = _paths(root, slug)
    before = book_git_status(root, slug)
    if before["remote_count"]:
        raise BookGitError("book Git repositories must not configure remotes.")
    _run(["add", "-A"], cwd=book_dir)
    diff = _run(
        ["diff", "--cached", "--quiet"],
        cwd=book_dir,
        allowed_returncodes=(0, 1),
    )
    committed = diff.returncode == 1
    if committed:
        _run(["commit", "-m", message.strip()], cwd=book_dir)
    head = _head(book_dir)
    tag_result = None
    if tag is not None:
        existing = _run(
            ["tag", "--list", tag],
            cwd=book_dir,
        ).stdout.strip()
        if existing:
            tag_result = tag
        else:
            _run(["tag", "-a", tag, "-m", message.strip()], cwd=book_dir)
            tag_result = tag
    return {
        "committed": committed,
        "commit_hash": head,
        "message": message.strip() if committed else "No changes to commit.",
        "tag": tag_result,
        "remote_count": 0,
    }


def restore_book_worktree(root: Path, slug: str) -> dict[str, Any]:
    """Restore a missing book worktree from its external local Git history."""
    book_dir, git_dir, pointer = _paths(root, slug)
    if not git_dir.is_dir():
        raise BookGitError(f"external book Git history not found: {git_dir}")
    if book_dir.exists() and any(book_dir.iterdir()):
        raise BookGitError(
            f"refusing to restore over a non-empty book directory: {book_dir}"
        )
    book_dir.mkdir(parents=True, exist_ok=True)
    pointer.write_text(
        f"gitdir: {git_dir.resolve().as_posix()}\n",
        encoding="utf-8",
    )
    try:
        _run(["config", "core.worktree", str(book_dir.resolve())], cwd=book_dir)
        _run(["checkout", "-f", "HEAD", "--", "."], cwd=book_dir)
    except Exception:
        if pointer.exists():
            pointer.unlink()
        raise
    status = book_git_status(root, slug)
    return {
        "restored": True,
        "book_dir": str(book_dir),
        "git_dir": str(git_dir),
        "commit_hash": status["head"],
        "dirty": status["dirty"],
    }
