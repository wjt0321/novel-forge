"""Content-addressed, read-only input capsules for native review roles."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from .models import NovelForgeError


REVIEW_CAPSULE_SCHEMA = "novel-forge-review-capsule/v1"
_FILE_NAMES = {
    "instructions": "instructions.md",
    "prose": "prose.md",
    "scene_package": "scene-package.md",
    "story_contract": "story-contract.md",
    "canon": "canon.md",
    "blind_review": "blind-review.md",
    "machine_diagnostics": "machine-diagnostics.md",
    "previous_chapter_ending": "previous-chapter-ending.md",
}


class ReviewCapsuleError(NovelForgeError):
    """Raised when a sealed review input capsule is invalid or changed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise ReviewCapsuleError(
                f"review capsule 文件已存在：{path.name}"
            )
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_review_capsule(
    capsule_root: Path,
    slug: str,
    role: str,
    *,
    instructions: str,
    inputs: dict[str, str],
    body_sha256: str,
) -> dict[str, Any]:
    """Seal the exact inputs one independent reviewer may read."""
    allowed = (
        {"prose"}
        if role == "blind-reader"
        else {
            "prose",
            "scene_package",
            "story_contract",
            "canon",
            "blind_review",
            "machine_diagnostics",
            "previous_chapter_ending",
        }
    )
    if role not in {"blind-reader", "chapter-editor"}:
        raise ReviewCapsuleError(f"未知审稿角色：{role}")
    if set(inputs) - allowed or "prose" not in inputs:
        raise ReviewCapsuleError("review capsule 输入超出角色边界。")
    capsule_id = f"review-{role}-{uuid.uuid4().hex[:16]}"
    capsule_dir = (
        Path(capsule_root).resolve()
        / "review-capsules"
        / slug
        / capsule_id
    )
    capsule_dir.mkdir(parents=True, exist_ok=False)
    material = {"instructions": instructions, **inputs}
    files: list[dict[str, Any]] = []
    for logical_name, text in material.items():
        filename = _FILE_NAMES[logical_name]
        path = capsule_dir / filename
        payload = text.encode("utf-8")
        _write_new(path, payload)
        files.append(
            {
                "logical_name": logical_name,
                "path": filename,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    manifest = {
        "schema": REVIEW_CAPSULE_SCHEMA,
        "capsule_id": capsule_id,
        "slug": slug,
        "role": role,
        "body_sha256": body_sha256,
        "files": files,
    }
    manifest_path = capsule_dir / "manifest.json"
    _write_new(
        manifest_path,
        (
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )
    return {
        "schema": REVIEW_CAPSULE_SCHEMA,
        "id": capsule_id,
        "path": str(capsule_dir),
        "role": role,
        "manifest": "manifest.json",
        "manifest_sha256": _sha256(manifest_path),
        "body_sha256": body_sha256,
    }


def verify_review_capsule(
    descriptor: dict[str, Any],
    *,
    expected_role: str,
    expected_body_sha256: str,
) -> dict[str, str]:
    """Verify every sealed input and return its logical text mapping."""
    if descriptor.get("schema") != REVIEW_CAPSULE_SCHEMA:
        raise ReviewCapsuleError("review capsule 描述格式无效。")
    capsule_dir = Path(str(descriptor.get("path") or "")).resolve()
    manifest_name = str(descriptor.get("manifest") or "")
    manifest_parts = PurePosixPath(manifest_name).parts
    if (
        not manifest_name
        or PurePosixPath(manifest_name).is_absolute()
        or ".." in manifest_parts
    ):
        raise ReviewCapsuleError("review capsule manifest 路径无效。")
    manifest_path = capsule_dir.joinpath(*manifest_parts)
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or _sha256(manifest_path)
        != descriptor.get("manifest_sha256")
    ):
        raise ReviewCapsuleError("review capsule manifest 已改变。")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewCapsuleError("review capsule manifest 无法读取。") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != REVIEW_CAPSULE_SCHEMA
        or manifest.get("capsule_id") != descriptor.get("id")
        or manifest.get("role") != expected_role
        or manifest.get("body_sha256") != expected_body_sha256
        or descriptor.get("body_sha256") != expected_body_sha256
    ):
        raise ReviewCapsuleError("review capsule 与当前正文或角色不匹配。")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ReviewCapsuleError("review capsule 文件清单无效。")
    result: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict):
            raise ReviewCapsuleError("review capsule 文件项无效。")
        logical_name = str(item.get("logical_name") or "")
        relative = str(item.get("path") or "")
        parts = PurePosixPath(relative).parts
        if (
            logical_name not in _FILE_NAMES
            or not relative
            or PurePosixPath(relative).is_absolute()
            or ".." in parts
        ):
            raise ReviewCapsuleError("review capsule 文件路径无效。")
        path = capsule_dir.joinpath(*parts)
        if (
            not path.is_file()
            or path.is_symlink()
            or _sha256(path) != item.get("sha256")
            or path.stat().st_size != item.get("bytes")
        ):
            raise ReviewCapsuleError(
                f"review capsule 文件已改变：{logical_name}"
            )
        result[logical_name] = path.read_text(encoding="utf-8")
    expected = {"instructions", "prose"}
    if expected_role == "chapter-editor":
        expected.update(
            {
                "scene_package",
                "story_contract",
                "canon",
                "blind_review",
                "machine_diagnostics",
            }
        )
    if not expected.issubset(result):
        raise ReviewCapsuleError("review capsule 缺少角色必要输入。")
    return result
