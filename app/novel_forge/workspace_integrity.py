"""Repository-wide write detection for untrusted creative role calls."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar


_IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
)
_T = TypeVar("_T")


@dataclass(frozen=True)
class WorkspaceDelta:
    """Paths changed by one creative role call."""

    created: tuple[str, ...]
    modified: tuple[str, ...]
    deleted: tuple[str, ...]

    @property
    def changed(self) -> tuple[str, ...]:
        return self.created + self.modified + self.deleted


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_workspace(root: Path) -> dict[str, str]:
    """Snapshot every project path creative roles are forbidden to mutate."""
    root = Path(root).resolve()
    if not root.is_dir():
        return {}
    snapshot: dict[str, str] = {}
    for current, directories, files in os.walk(root, topdown=True):
        directories[:] = sorted(
            name
            for name in directories
            if name not in _IGNORED_DIRECTORY_NAMES
        )
        current_path = Path(current)
        for name in directories:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[relative] = f"symlink:{os.readlink(path)}"
            else:
                snapshot[relative] = "directory"
        for name in sorted(files):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[relative] = f"symlink:{os.readlink(path)}"
            else:
                snapshot[relative] = f"file:{_file_sha256(path)}"
    return snapshot


def workspace_delta(
    before: dict[str, str],
    after: dict[str, str],
) -> WorkspaceDelta:
    """Return created, modified, and deleted project paths."""
    before_paths = set(before)
    after_paths = set(after)
    return WorkspaceDelta(
        created=tuple(sorted(after_paths - before_paths)),
        modified=tuple(
            sorted(
                path
                for path in before_paths & after_paths
                if before[path] != after[path]
            )
        ),
        deleted=tuple(sorted(before_paths - after_paths)),
    )


def remove_created_paths(root: Path, paths: tuple[str, ...]) -> None:
    """Remove only paths proven absent before the creative role call."""
    root = Path(root).resolve()
    for relative in sorted(
        paths,
        key=lambda value: (value.count("/"), len(value)),
        reverse=True,
    ):
        target = root / Path(relative)
        if not target.is_relative_to(root):
            continue
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target)


def guarded_role_call(
    root: Path,
    callback: Callable[[], _T],
    *,
    error_factory: Callable[[WorkspaceDelta], Exception],
) -> _T:
    """Run one role call and reject any project-tree mutation."""
    root = Path(root).resolve()
    before = snapshot_workspace(root)
    original_error: Exception | None = None
    result: _T | None = None
    try:
        result = callback()
    except Exception as exc:
        original_error = exc
    after = snapshot_workspace(root)
    delta = workspace_delta(before, after)
    if delta.changed:
        remove_created_paths(root, delta.created)
        error = error_factory(delta)
        if original_error is not None:
            raise error from original_error
        raise error
    if original_error is not None:
        raise original_error
    return result  # type: ignore[return-value]
