"""External integrity seals for immutable artifacts and role sessions."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .models import NovelForgeError


ARTIFACT_SEAL_SCHEMA = "novel-forge-artifact-seal/v1"
SESSION_COMPLETION_SCHEMA = "novel-forge-session-completion/v2"
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_WORKFLOW_AUTHORITIES: set[str] = set()
_IMMUTABLE_ARTIFACT_KINDS = frozenset(
    {
        "generation",
        "runtime-audit",
        "review-history",
    }
)


class ArtifactIntegrityError(NovelForgeError):
    """Raised when an external integrity record is invalid."""


class WorkflowAuthority:
    """Opaque in-process authority held only by the active orchestrator."""

    __slots__ = ("_nonce",)

    def __init__(self, nonce: str):
        self._nonce = nonce


def _issue_workflow_authority() -> WorkflowAuthority:
    """Issue a non-serializable capability for one orchestrator process."""
    nonce = secrets.token_hex(32)
    _WORKFLOW_AUTHORITIES.add(nonce)
    return WorkflowAuthority(nonce)


def require_workflow_authority(
    authority: WorkflowAuthority | None,
) -> None:
    """Reject control-plane mutations outside an active orchestrator."""
    if (
        not isinstance(authority, WorkflowAuthority)
        or authority._nonce not in _WORKFLOW_AUTHORITIES
    ):
        raise ArtifactIntegrityError(
            "正式自动流程缺少编排器权限，不能伪造会话完成或 ready。"
        )


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _canonical(data: Mapping[str, Any]) -> bytes:
    payload = {key: value for key, value in data.items() if key != "signature"}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _ledger_dir(root: Path, slug: str) -> Path:
    return Path(root).resolve() / ".local-guardian" / slug


def _key(root: Path, slug: str) -> bytes:
    path = _ledger_dir(root, slug) / "integrity.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        value = path.read_bytes()
        if len(value) < 32:
            raise ArtifactIntegrityError("外置完整性密钥损坏。")
        return value
    value = os.urandom(32)
    try:
        with path.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        value = path.read_bytes()
    return value


def _sign(root: Path, slug: str, data: Mapping[str, Any]) -> str:
    return hmac.new(
        _key(root, slug),
        _canonical(data),
        hashlib.sha256,
    ).hexdigest()


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        dict(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8-sig") == text:
            return
        raise ArtifactIntegrityError(f"完整性记录已存在，不得覆盖：{path.name}")
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise ArtifactIntegrityError(
                f"完整性记录已存在，不得覆盖：{path.name}"
            )
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _artifact_identity(
    root: Path,
    slug: str,
    artifact: Path,
) -> tuple[Path, str, str, str]:
    root = Path(root).resolve()
    book_dir = (root / "books" / slug).resolve()
    source = Path(artifact).resolve()
    if not source.is_file() or not source.is_relative_to(book_dir):
        raise ArtifactIntegrityError("只能封印当前书目录中的现有文件。")
    relative = source.relative_to(book_dir).as_posix()
    path_hash = hashlib.sha256(relative.encode("utf-8")).hexdigest()
    content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    return source, relative, path_hash, content_hash


def seal_artifact(
    root: Path,
    slug: str,
    artifact: Path,
    *,
    kind: str,
) -> dict[str, Any]:
    """Seal the exact bytes of one book artifact in the external ledger."""
    _, relative, path_hash, content_hash = _artifact_identity(
        root, slug, artifact
    )
    payload = {
        "schema": ARTIFACT_SEAL_SCHEMA,
        "slug": slug,
        "kind": kind,
        "artifact_path": relative,
        "artifact_sha256": content_hash,
        "recorded_at": _now(),
    }
    payload["signature"] = _sign(root, slug, payload)
    target = (
        _ledger_dir(root, slug)
        / "artifact-seals"
        / f"{path_hash}-{content_hash}.json"
    )
    if kind in _IMMUTABLE_ARTIFACT_KINDS:
        prior = list(target.parent.glob(f"{path_hash}-*.json"))
        if prior and target not in prior:
            raise ArtifactIntegrityError(
                f"不可变产物已封印，不得重新封印不同内容：{relative}"
            )
    _write_immutable_json(target, payload)
    return {
        "artifact_path": relative,
        "artifact_sha256": content_hash,
        "seal_path": str(target),
    }


def artifact_integrity_errors(
    root: Path,
    slug: str,
    artifact: Path,
    *,
    expected_kind: str | None = None,
) -> list[str]:
    """Verify that current artifact bytes match an immutable external seal."""
    try:
        _, relative, path_hash, content_hash = _artifact_identity(
            root, slug, artifact
        )
    except ArtifactIntegrityError as exc:
        return [str(exc)]
    directory = _ledger_dir(root, slug) / "artifact-seals"
    target = directory / f"{path_hash}-{content_hash}.json"
    if not target.is_file():
        prior = list(directory.glob(f"{path_hash}-*.json"))
        return [
            (
                "artifact_tampered"
                if prior
                else "artifact_seal_missing"
            )
            + f":{relative}"
        ]
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return [f"artifact_seal_invalid:{relative}"]
    if not isinstance(payload, dict):
        return [f"artifact_seal_invalid:{relative}"]
    signature = str(payload.get("signature") or "")
    expected_signature = _sign(root, slug, payload)
    errors: list[str] = []
    if (
        payload.get("schema") != ARTIFACT_SEAL_SCHEMA
        or payload.get("slug") != slug
        or payload.get("artifact_path") != relative
        or payload.get("artifact_sha256") != content_hash
        or not hmac.compare_digest(signature, expected_signature)
    ):
        errors.append(f"artifact_seal_invalid:{relative}")
    if expected_kind is not None and payload.get("kind") != expected_kind:
        errors.append(f"artifact_kind_mismatch:{relative}")
    return errors


def _safe_id(value: str) -> str:
    safe = _SAFE_ID_RE.sub("-", value).strip("-._")
    if not safe:
        raise ArtifactIntegrityError("会话实例 ID 无法转换为安全文件名。")
    return safe[:120]


def record_session_completion(
    root: Path,
    slug: str,
    *,
    session_id: str,
    session_instance_id: str,
    role: str,
    provider: str,
    model: str,
    agent_harness: str,
    context_scope: str,
    chapter: int,
    generation_id: str,
    content_sha256: str,
    artifact: Path,
    workflow_authority: WorkflowAuthority | None = None,
) -> dict[str, Any]:
    """Record one completed native role session bound to exact artifacts."""
    require_workflow_authority(workflow_authority)
    if not isinstance(chapter, int) or isinstance(chapter, bool) or chapter < 1:
        raise ArtifactIntegrityError("会话完成凭证 chapter 必须是正整数。")
    if not generation_id.strip():
        raise ArtifactIntegrityError("会话完成凭证缺少 generation_id。")
    if not _SHA256_RE.fullmatch(content_sha256):
        raise ArtifactIntegrityError(
            "会话完成凭证 content_sha256 必须是 SHA-256。"
        )
    _, artifact_path, _, artifact_sha256 = _artifact_identity(
        root,
        slug,
        artifact,
    )
    values = {
        "session_id": session_id,
        "session_instance_id": session_instance_id,
        "role": role,
        "provider": provider,
        "model": model,
        "agent_harness": agent_harness,
        "context_scope": context_scope,
        "chapter": chapter,
        "generation_id": generation_id,
        "content_sha256": content_sha256,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
    }
    if any(not str(value).strip() for value in values.values()):
        raise ArtifactIntegrityError("会话完成凭证缺少必要字段。")
    directory = _ledger_dir(root, slug) / "session-completions"
    if directory.is_dir():
        for path in directory.glob("*.json"):
            try:
                existing = json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                continue
            if not isinstance(existing, dict):
                continue
            if existing.get("session_id") == session_id:
                if (
                    all(existing.get(key) == value for key, value in values.items())
                ):
                    return existing
                raise ArtifactIntegrityError("原生 session_id 已被其他角色使用。")
            if existing.get("session_instance_id") == session_instance_id:
                raise ArtifactIntegrityError("底层会话实例已被其他角色使用。")
    payload = {
        "schema": SESSION_COMPLETION_SCHEMA,
        "slug": slug,
        **values,
        "completed_at": _now(),
    }
    payload["signature"] = _sign(root, slug, payload)
    target = directory / f"{_safe_id(session_instance_id)}.json"
    _write_immutable_json(target, payload)
    return payload


def session_completion_errors(
    root: Path,
    slug: str,
    *,
    session_id: str,
    expected_role: str,
    expected_context_scope: str,
    expected_provider: str | None = None,
    expected_model: str | None = None,
    expected_chapter: int | None = None,
    expected_generation_id: str | None = None,
    expected_content_sha256: str | None = None,
    expected_artifact: Path | None = None,
) -> list[str]:
    """Validate a role session against the external completion ledger."""
    directory = _ledger_dir(root, slug) / "session-completions"
    if not directory.is_dir():
        return [f"session_completion_missing:{expected_role}"]
    matching: dict[str, Any] | None = None
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("session_id") == session_id:
            matching = payload
            break
    if matching is None:
        return [f"session_completion_missing:{expected_role}"]
    errors: list[str] = []
    signature = str(matching.get("signature") or "")
    if (
        matching.get("schema") != SESSION_COMPLETION_SCHEMA
        or matching.get("slug") != slug
        or not hmac.compare_digest(signature, _sign(root, slug, matching))
    ):
        errors.append(f"session_completion_invalid:{expected_role}")
    if matching.get("role") != expected_role:
        errors.append(f"session_role_mismatch:{expected_role}")
    if matching.get("context_scope") != expected_context_scope:
        errors.append(f"session_context_mismatch:{expected_role}")
    if (
        expected_provider is not None
        and matching.get("provider") != expected_provider
    ):
        errors.append(f"session_provider_mismatch:{expected_role}")
    if expected_model is not None and matching.get("model") != expected_model:
        errors.append(f"session_model_mismatch:{expected_role}")
    if (
        expected_chapter is not None
        and matching.get("chapter") != expected_chapter
    ):
        errors.append(f"session_chapter_mismatch:{expected_role}")
    if (
        expected_generation_id is not None
        and matching.get("generation_id") != expected_generation_id
    ):
        errors.append(f"session_generation_mismatch:{expected_role}")
    if (
        expected_content_sha256 is not None
        and matching.get("content_sha256") != expected_content_sha256
    ):
        errors.append(f"session_content_mismatch:{expected_role}")
    if expected_artifact is not None:
        try:
            _, relative, _, digest = _artifact_identity(
                root,
                slug,
                expected_artifact,
            )
        except ArtifactIntegrityError:
            errors.append(f"session_artifact_missing:{expected_role}")
        else:
            if matching.get("artifact_path") != relative:
                errors.append(f"session_artifact_mismatch:{expected_role}")
            if matching.get("artifact_sha256") != digest:
                errors.append(f"session_artifact_hash_mismatch:{expected_role}")
    return errors
