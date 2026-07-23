"""Repository-wide write detection for untrusted creative role calls."""

from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
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


def create_workspace_backup(root: Path, archive_path: Path) -> None:
    """Store restorable project bytes outside the protected workspace."""
    root = Path(root).resolve()
    archive_path = Path(archive_path).resolve()
    if archive_path == root or archive_path.is_relative_to(root):
        raise ValueError("workspace backup 必须位于项目仓库外。")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_name(
        f".{archive_path.name}.{os.getpid()}.tmp"
    )
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for current, directories, files in os.walk(
                root,
                topdown=True,
            ):
                directories[:] = sorted(
                    name
                    for name in directories
                    if name not in _IGNORED_DIRECTORY_NAMES
                )
                current_path = Path(current)
                for name in directories:
                    path = current_path / name
                    if path.is_symlink():
                        continue
                    relative = path.relative_to(root).as_posix()
                    archive.writestr(f"{relative}/", b"")
                for name in sorted(files):
                    path = current_path / name
                    if path.is_symlink():
                        continue
                    archive.write(
                        path,
                        arcname=path.relative_to(root).as_posix(),
                    )
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_existing_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def restore_workspace_paths(
    root: Path,
    archive_path: Path,
    before: dict[str, str],
    paths: tuple[str, ...],
) -> None:
    """Restore modified or deleted paths to their action-start bytes."""
    root = Path(root).resolve()
    archive_path = Path(archive_path).resolve()
    if not archive_path.is_file():
        raise FileNotFoundError("workspace backup 不存在。")
    with zipfile.ZipFile(archive_path, mode="r") as archive:
        members = set(archive.namelist())
        for relative in sorted(
            set(paths),
            key=lambda value: (value.count("/"), value),
        ):
            marker = before.get(relative)
            if marker is None:
                continue
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError("workspace restore 路径越界。")
            target = root.joinpath(*relative_path.parts)
            if marker == "directory":
                if target.exists() and not target.is_dir():
                    _remove_existing_path(target)
                target.mkdir(parents=True, exist_ok=True)
                continue
            if marker.startswith("symlink:"):
                _remove_existing_path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(marker.removeprefix("symlink:"), target)
                continue
            if not marker.startswith("file:") or relative not in members:
                raise ValueError(
                    f"workspace backup 缺少受保护路径：{relative}"
                )
            if target.exists() or target.is_symlink():
                _remove_existing_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(relative))


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
