"""Vendor-neutral isolated writer capsules and import receipts."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .chapter_sequence import (
    chapter_sequence_status,
    invalidate_chapter_session,
)
from .guardian_contract import (
    GUARDIAN_CONTRACT_SCHEMA,
    guardian_contract,
)
from .models import NovelForgeError
from .session_audit import (
    audit_session_log,
    evaluate_session_budget,
)
from .writer_prompt import render_formal_writer_instructions


CAPSULE_SCHEMA = "novel-forge-writer-capsule/v1"
GUARDIAN_RECEIPT_SCHEMA = "novel-forge-guardian-receipt/v1"
REGENERATION_AUTHORIZATION_SCHEMA = (
    "novel-forge-regeneration-authorization/v1"
)
GUARDIAN_SESSION_DIRECTORY = Path("planning/guardian-sessions")
GUARDIAN_RECEIPT_DIRECTORY = Path("evidence/guardian-receipts")
LOCAL_GUARDIAN_DIRECTORY = Path(".local-guardian")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_TARGET_RE = re.compile(r"^chapters/e\d{2}/ch-(\d{2,})/正文\.md$")
_CAPSULE_ALLOWED_FILES = frozenset(
    {
        "capsule.json",
        "guardian-contract.json",
        "handoff.md",
        "instructions.md",
        "draft/正文.md",
    }
)
_CAPSULE_ALLOWED_DIRECTORIES = frozenset({"draft"})
_CAPSULE_PROTECTED_FILES = (
    "capsule.json",
    "guardian-contract.json",
    "handoff.md",
    "instructions.md",
)


class GuardianError(NovelForgeError):
    """Raised when an isolated writer capsule is invalid or compromised."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_text(
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise GuardianError(f"Guardian 回执已存在，不得覆盖：{path.name}")
    _atomic_json(path, payload)


def _write_immutable_bytes(path: Path, payload: bytes) -> None:
    if path.exists():
        raise GuardianError(f"Guardian 外置记录已存在，不得覆盖：{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _guardian_store(root: Path, slug: str) -> Path:
    return Path(root).resolve() / LOCAL_GUARDIAN_DIRECTORY / slug


def _guardian_key(root: Path, slug: str, *, create: bool) -> bytes:
    path = _guardian_store(root, slug) / "guardian.key"
    if not path.exists():
        if not create:
            raise GuardianError("Guardian 外置签名密钥不存在。")
        _write_immutable_bytes(path, secrets.token_bytes(32))
    key = path.read_bytes()
    if len(key) != 32:
        raise GuardianError("Guardian 外置签名密钥损坏。")
    return key


def _signed_receipt(
    root: Path,
    slug: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    unsigned = dict(payload)
    unsigned.pop("guardian_auth", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    key = _guardian_key(root, slug, create=True)
    return {
        **unsigned,
        "guardian_auth": {
            "algorithm": "hmac-sha256",
            "key_id": hashlib.sha256(key).hexdigest()[:16],
            "signature": hmac.new(
                key,
                canonical,
                hashlib.sha256,
            ).hexdigest(),
        },
    }


def _receipt_auth_valid(
    root: Path,
    slug: str,
    receipt: Mapping[str, Any],
) -> bool:
    auth = receipt.get("guardian_auth")
    if not isinstance(auth, dict):
        return False
    if auth.get("algorithm") != "hmac-sha256":
        return False
    try:
        key = _guardian_key(root, slug, create=False)
    except GuardianError:
        return False
    if auth.get("key_id") != hashlib.sha256(key).hexdigest()[:16]:
        return False
    unsigned = dict(receipt)
    unsigned.pop("guardian_auth", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    expected = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(
        str(auth.get("signature") or ""),
        expected,
    )


def _external_receipt_path(
    root: Path,
    slug: str,
    capsule_id: str,
) -> Path:
    return (
        _guardian_store(root, slug)
        / "receipts"
        / f"{capsule_id}.json"
    )


def _runtime_sidecar_path(
    root: Path,
    slug: str,
    capsule_id: str,
) -> Path:
    return (
        _guardian_store(root, slug)
        / "runtime"
        / f"{capsule_id}.json"
    )


def _authorization_path(
    root: Path,
    slug: str,
    authorization_id: str,
) -> Path:
    return (
        _guardian_store(root, slug)
        / "authorizations"
        / f"{authorization_id}.json"
    )


def _write_signed_receipt(
    root: Path,
    slug: str,
    book_dir: Path,
    capsule_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    signed = _signed_receipt(root, slug, payload)
    external = _external_receipt_path(root, slug, capsule_id)
    public = _receipt_path(book_dir, capsule_id)
    if external.exists() or public.exists():
        raise GuardianError(f"Guardian 回执已存在，不得覆盖：{capsule_id}")
    _write_immutable_json(external, signed)
    try:
        _write_immutable_json(public, signed)
    except Exception:
        external.unlink(missing_ok=True)
        raise
    return signed


def _safe_id(value: str, field: str) -> str:
    text = value.strip()
    if not _SAFE_ID_RE.fullmatch(text):
        raise GuardianError(
            f"{field} 只能包含字母、数字、点、下划线和连字符。"
        )
    return text


def _book_dir(root: Path, slug: str) -> Path:
    path = Path(root).resolve() / "books" / slug
    if not path.is_dir():
        raise GuardianError(f"books/ 项目不存在：{path}")
    return path


def _outside_repository(root: Path, capsule_dir: Path) -> Path:
    root_resolved = Path(root).resolve()
    capsule = Path(capsule_dir)
    if not capsule.is_absolute():
        raise GuardianError("capsule_dir 必须是绝对路径。")
    resolved = capsule.resolve()
    if (
        resolved == root_resolved
        or resolved.is_relative_to(root_resolved)
        or root_resolved.is_relative_to(resolved)
    ):
        raise GuardianError(
            "writer capsule 必须位于仓库外，且不能是仓库的父目录。"
        )
    return resolved


def _target_path(value: str, chapter: int) -> str:
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise GuardianError("target_path 必须是 books 项目内的相对路径。")
    normalized = pure.as_posix()
    match = _TARGET_RE.fullmatch(normalized)
    if match is None or int(match.group(1)) != chapter:
        raise GuardianError(
            "target_path 必须匹配 chapters/eXX/ch-NN/正文.md，"
            "且章节编号与当前序列一致。"
        )
    return normalized


def _sequence_record(
    book_dir: Path,
    sequence_id: str,
) -> dict[str, Any]:
    sequence_id = _safe_id(sequence_id, "sequence_id")
    path = (
        book_dir
        / "planning/chapter-sequences"
        / f"{sequence_id}.json"
    )
    if not path.is_file():
        raise GuardianError(f"章节序列不存在：{sequence_id}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GuardianError(f"章节序列 JSON 损坏：{sequence_id}") from exc
    if not isinstance(payload, dict):
        raise GuardianError(f"章节序列 JSON 顶层不是对象：{sequence_id}")
    return payload


def prepare_writer_capsule(
    root: Path,
    slug: str,
    sequence_id: str,
    session_id: str,
    capsule_dir: Path,
    target_path: str,
    *,
    regeneration_authorization_id: str | None = None,
) -> dict[str, Any]:
    """Create a repository-external capsule for one claimed writer session."""
    root = Path(root).resolve()
    book_dir = _book_dir(root, slug)
    _guardian_key(root, slug, create=True)
    status = chapter_sequence_status(root, slug, sequence_id)
    if (
        status.get("status") != "running"
        or status.get("active_session_id") != session_id
        or not isinstance(status.get("current_chapter"), int)
    ):
        raise GuardianError(
            "writer capsule 必须绑定当前序列已 claim 的原生 session。"
        )
    chapter = status["current_chapter"]
    target = _target_path(target_path, chapter)
    target_file = book_dir / Path(*PurePosixPath(target).parts)
    if target_file.exists() and not target_file.is_file():
        raise GuardianError(f"正文目标不是普通文件：{target}")
    operation = "patch" if target_file.is_file() else "draft"
    input_body_sha256 = _sha256(target_file) if target_file.is_file() else None
    clean_hashes = _clean_body_hashes(root, slug, chapter)
    authorization: dict[str, Any] | None = None
    authorization_sha256: str | None = None
    authorization_id = str(regeneration_authorization_id or "").strip()
    if authorization_id:
        authorization, authorization_sha256 = (
            _load_regeneration_authorization(
                root,
                slug,
                authorization_id,
                sequence_id=sequence_id,
                session_id=session_id,
                chapter=chapter,
                prior_body_sha256=clean_hashes,
            )
        )
        if _authorization_already_used(book_dir, authorization_id):
            raise GuardianError(
                "regeneration authorization 已被其他 capsule 使用。"
            )
    if len(clean_hashes) >= 2 and authorization is None:
        raise GuardianError(
            "human_decision_required: 第三个不同正文版本必须在创建 capsule "
            "前获得 author/human_delegate 明确授权。"
        )
    human_regeneration_authorized = authorization is not None
    decision_reference = (
        str(authorization["decision_reference"])
        if authorization is not None
        else ""
    )
    capsule = _outside_repository(root, Path(capsule_dir))
    if capsule.exists():
        if not capsule.is_dir():
            raise GuardianError(f"capsule_dir 不是目录：{capsule}")
        if any(capsule.iterdir()):
            raise GuardianError(f"capsule_dir 必须为空：{capsule}")
    capsule.mkdir(parents=True, exist_ok=True)
    sequence = _sequence_record(book_dir, sequence_id)
    handoff = sequence.get("handoffs", {}).get(str(chapter))
    if not isinstance(handoff, dict):
        raise GuardianError("当前章节缺少有界 handoff 记录。")
    handoff_path = book_dir / str(handoff.get("handoff_path") or "")
    if not handoff_path.is_file():
        raise GuardianError("当前章节 handoff 文件不存在。")
    handoff_sha256 = _sha256(handoff_path)
    if handoff_sha256 != handoff.get("handoff_sha256"):
        raise GuardianError("当前章节 handoff 已被修改，不能创建 writer capsule。")

    capsule_id = f"cap-ch{chapter:02d}-{uuid.uuid4().hex[:12]}"
    prompt = render_formal_writer_instructions(
        chapter,
        operation=operation,
    )
    (capsule / "instructions.md").write_text(
        prompt.text,
        encoding="utf-8",
    )
    prompt_sha256 = _sha256(capsule / "instructions.md")
    manifest = {
        "schema": CAPSULE_SCHEMA,
        "capsule_id": capsule_id,
        "slug": slug,
        "chapter": chapter,
        "sequence_id": sequence_id,
        "session_id": session_id,
        "handoff_sha256": handoff_sha256,
        "prompt_template_id": prompt.template_id,
        "prompt_sha256": prompt_sha256,
        "target_path": target,
        "operation": operation,
        "input_body_sha256": input_body_sha256,
        "human_regeneration_authorized": human_regeneration_authorized,
        "human_decision_reference": decision_reference or None,
        "regeneration_authorization_id": authorization_id or None,
        "regeneration_authorization_sha256": authorization_sha256,
        "allowed_outputs": [
            "draft/正文.md",
        ],
        "created_at": _now(),
        "author_approval": False,
        "publication_eligibility": False,
    }
    (capsule / "draft").mkdir(exist_ok=True)
    if target_file.is_file():
        (capsule / "draft/正文.md").write_bytes(target_file.read_bytes())
    (capsule / "handoff.md").write_bytes(handoff_path.read_bytes())
    (capsule / "guardian-contract.json").write_text(
        json.dumps(
            guardian_contract(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (capsule / "capsule.json").write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    protected_hashes = {
        name: _sha256(capsule / name)
        for name in _CAPSULE_PROTECTED_FILES
    }
    control = {
        **manifest,
        "capsule_dir": str(capsule),
        "status": "prepared",
        "protected_hashes": protected_hashes,
        "updated_at": manifest["created_at"],
    }
    _supersede_prepared_capsules(
        book_dir,
        sequence_id=sequence_id,
        chapter=chapter,
        session_id=session_id,
    )
    _atomic_json(
        book_dir / GUARDIAN_SESSION_DIRECTORY / f"{capsule_id}.json",
        control,
    )
    return {
        "capsule_id": capsule_id,
        "capsule_dir": str(capsule),
        "chapter": chapter,
        "sequence_id": sequence_id,
        "session_id": session_id,
        "handoff_sha256": handoff_sha256,
        "prompt_template_id": prompt.template_id,
        "prompt_sha256": prompt_sha256,
        "target_path": target,
        "operation": operation,
        "input_body_sha256": input_body_sha256,
        "human_regeneration_authorized": human_regeneration_authorized,
        "human_decision_reference": decision_reference or None,
        "regeneration_authorization_id": authorization_id or None,
        "draft_output": "draft/正文.md",
        "runtime_record_operation": "record-capsule-runtime",
        "isolation_attested": False,
        "requires_external_sandbox": True,
        "control_plane_exposed": False,
        "author_approval": False,
        "publication_eligibility": False,
    }


def _load_control(
    book_dir: Path,
    capsule_id: str,
) -> tuple[Path, dict[str, Any]]:
    capsule_id = _safe_id(capsule_id, "capsule_id")
    path = (
        book_dir
        / GUARDIAN_SESSION_DIRECTORY
        / f"{capsule_id}.json"
    )
    if not path.is_file():
        raise GuardianError(f"Guardian capsule 记录不存在：{capsule_id}")
    try:
        control = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GuardianError(f"Guardian capsule 记录损坏：{capsule_id}") from exc
    if (
        not isinstance(control, dict)
        or control.get("schema") != CAPSULE_SCHEMA
        or control.get("capsule_id") != capsule_id
    ):
        raise GuardianError(f"Guardian capsule 身份不合法：{capsule_id}")
    return path, control


def _supersede_prepared_capsules(
    book_dir: Path,
    *,
    sequence_id: str,
    chapter: int,
    session_id: str,
) -> None:
    directory = book_dir / GUARDIAN_SESSION_DIRECTORY
    if not directory.is_dir():
        return
    for path in directory.glob("*.json"):
        try:
            control = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(control, dict)
            and control.get("status") == "prepared"
            and control.get("sequence_id") == sequence_id
            and control.get("chapter") == chapter
            and control.get("session_id") == session_id
        ):
            control["status"] = "superseded"
            control["superseded_reason"] = "newer_capsule_prepared"
            control["updated_at"] = _now()
            _atomic_json(path, control)


def _capsule_inventory(capsule: Path) -> tuple[list[str], list[str]]:
    unexpected: list[str] = []
    unsafe: list[str] = []
    capsule_resolved = capsule.resolve()
    for path in capsule.rglob("*"):
        relative = path.relative_to(capsule).as_posix()
        if path.is_symlink():
            unsafe.append(relative)
            continue
        try:
            resolved = path.resolve()
        except OSError:
            unsafe.append(relative)
            continue
        if not resolved.is_relative_to(capsule_resolved):
            unsafe.append(relative)
            continue
        if path.is_dir():
            if relative not in _CAPSULE_ALLOWED_DIRECTORIES:
                unexpected.append(relative)
        elif relative not in _CAPSULE_ALLOWED_FILES:
            unexpected.append(relative)
    return sorted(unexpected), sorted(unsafe)


def _receipt_path(book_dir: Path, capsule_id: str) -> Path:
    return (
        book_dir
        / GUARDIAN_RECEIPT_DIRECTORY
        / f"{capsule_id}.json"
    )


def _clean_body_hashes(
    root: Path,
    slug: str,
    chapter: int,
) -> set[str]:
    hashes: set[str] = set()
    directory = _guardian_store(root, slug) / "receipts"
    if not directory.is_dir():
        return hashes
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        body_sha256 = payload.get("body_sha256")
        if (
            payload.get("schema") == GUARDIAN_RECEIPT_SCHEMA
            and payload.get("status") == "clean"
            and payload.get("chapter") == chapter
            and _receipt_auth_valid(root, slug, payload)
            and isinstance(body_sha256, str)
            and len(body_sha256) == 64
        ):
            hashes.add(body_sha256)
    return hashes


def _authorization_already_used(
    book_dir: Path,
    authorization_id: str,
) -> bool:
    directory = book_dir / GUARDIAN_SESSION_DIRECTORY
    if not directory.is_dir():
        return False
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("regeneration_authorization_id")
            == authorization_id
        ):
            return True
    return False


def _load_regeneration_authorization(
    root: Path,
    slug: str,
    authorization_id: str,
    *,
    sequence_id: str,
    session_id: str,
    chapter: int,
    prior_body_sha256: set[str],
) -> tuple[dict[str, Any], str]:
    authorization_id = _safe_id(
        authorization_id,
        "regeneration_authorization_id",
    )
    path = _authorization_path(root, slug, authorization_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardianError(
            "regeneration authorization 不存在或损坏。"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != REGENERATION_AUTHORIZATION_SCHEMA
        or payload.get("authorization_id") != authorization_id
        or payload.get("slug") != slug
        or payload.get("chapter") != chapter
        or payload.get("sequence_id") != sequence_id
        or payload.get("session_id") != session_id
        or payload.get("authority") not in {"author", "human_delegate"}
        or payload.get("authorized") is not True
        or not str(payload.get("decision_reference") or "").strip()
        or payload.get("prior_body_sha256")
        != sorted(prior_body_sha256)
        or not _receipt_auth_valid(root, slug, payload)
    ):
        raise GuardianError(
            "regeneration authorization 与当前章节控制面不匹配。"
        )
    return payload, _sha256(path)


def authorize_regeneration(
    root: Path,
    slug: str,
    sequence_id: str,
    session_id: str,
    *,
    authority: str,
    decision_reference: str,
) -> dict[str, Any]:
    """Record one signed, chapter-bound human regeneration authorization."""
    root = Path(root).resolve()
    book_dir = _book_dir(root, slug)
    authority = authority.strip()
    if authority not in {"author", "human_delegate"}:
        raise GuardianError(
            "regeneration authority 必须是 author 或 human_delegate。"
        )
    decision_reference = decision_reference.strip()
    if not decision_reference:
        raise GuardianError("regeneration decision_reference 不能为空。")
    status = chapter_sequence_status(root, slug, sequence_id)
    if (
        status.get("status") != "running"
        or status.get("active_session_id") != session_id
        or not isinstance(status.get("current_chapter"), int)
    ):
        raise GuardianError(
            "regeneration authorization 必须绑定当前已 claim 的章节 session。"
        )
    chapter = status["current_chapter"]
    prior_body_sha256 = _clean_body_hashes(root, slug, chapter)
    if len(prior_body_sha256) < 2:
        raise GuardianError(
            "regeneration authorization 只用于第三个不同正文版本。"
        )
    authorization_id = (
        f"regen-ch{chapter:02d}-{uuid.uuid4().hex[:12]}"
    )
    payload = _signed_receipt(
        root,
        slug,
        {
            "schema": REGENERATION_AUTHORIZATION_SCHEMA,
            "authorization_id": authorization_id,
            "slug": slug,
            "chapter": chapter,
            "sequence_id": sequence_id,
            "session_id": session_id,
            "authority": authority,
            "decision_reference": decision_reference,
            "prior_body_sha256": sorted(prior_body_sha256),
            "authorized": True,
            "created_at": _now(),
            "author_approval": False,
            "publication_eligibility": False,
        },
    )
    path = _authorization_path(root, slug, authorization_id)
    _write_immutable_json(path, payload)
    return {
        "authorization_id": authorization_id,
        "chapter": chapter,
        "sequence_id": sequence_id,
        "session_id": session_id,
        "authority": authority,
        "decision_reference": decision_reference,
        "prior_body_sha256": sorted(prior_body_sha256),
        "authorization_sha256": _sha256(path),
        "author_approval": False,
        "publication_eligibility": False,
    }


def _has_valid_isolation_attestation(
    runtime_path: Path,
    capsule_id: str,
) -> bool:
    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    attestation = payload.get("guardian")
    required = {
        "capsule_id": capsule_id,
        "workspace_mode": "isolated_writer_capsule",
        "filesystem_scope": "capsule_only",
        "book_control_plane_visible": False,
        "validator_source_visible": False,
        "reported_by": "external_harness",
    }
    return isinstance(attestation, dict) and all(
        attestation.get(key) == value
        for key, value in required.items()
    )


def _record_compromised(
    root: Path,
    slug: str,
    book_dir: Path,
    control_path: Path,
    control: dict[str, Any],
    unexpected: list[str],
    reasons: list[str],
) -> None:
    capsule_id = control["capsule_id"]
    receipt = {
        "schema": GUARDIAN_RECEIPT_SCHEMA,
        "capsule_id": capsule_id,
        "slug": slug,
        "chapter": control["chapter"],
        "sequence_id": control["sequence_id"],
        "session_id": control["session_id"],
        "target_path": control["target_path"],
        "handoff_sha256": control["handoff_sha256"],
        "operation": control.get("operation", "draft"),
        "input_body_sha256": control.get("input_body_sha256"),
        "human_regeneration_authorized": control.get(
            "human_regeneration_authorized",
            False,
        ),
        "human_decision_reference": control.get("human_decision_reference"),
        "prompt_template_id": control.get("prompt_template_id"),
        "prompt_sha256": control.get("prompt_sha256"),
        "regeneration_authorization_id": control.get(
            "regeneration_authorization_id"
        ),
        "regeneration_authorization_sha256": control.get(
            "regeneration_authorization_sha256"
        ),
        "status": "compromised",
        "isolation_attested": False,
        "control_plane_exposed": None,
        "unexpected_files": unexpected,
        "reasons": reasons,
        "body_sha256": None,
        "runtime_snapshot_sha256": None,
        "recorded_at": _now(),
        "author_approval": False,
        "publication_eligibility": False,
    }
    _write_signed_receipt(
        root,
        slug,
        book_dir,
        capsule_id,
        receipt,
    )
    sequence_status = chapter_sequence_status(
        root,
        slug,
        control["sequence_id"],
    )
    if sequence_status.get("active_session_id") == control["session_id"]:
        invalidate_chapter_session(
            root,
            slug,
            control["sequence_id"],
            control["session_id"],
            reason="guardian_capsule_compromised",
        )
    control["status"] = "compromised"
    control["updated_at"] = _now()
    control["receipt_path"] = (
        _receipt_path(book_dir, capsule_id)
        .relative_to(book_dir)
        .as_posix()
    )
    _atomic_json(control_path, control)


def record_capsule_runtime(
    root: Path,
    slug: str,
    capsule_id: str,
    runtime_file: Path,
) -> dict[str, Any]:
    """Store a Harness-owned runtime sidecar outside the book workspace."""
    root = Path(root).resolve()
    book_dir = _book_dir(root, slug)
    control_path, control = _load_control(book_dir, capsule_id)
    if control.get("status") != "prepared":
        raise GuardianError(
            f"writer capsule 状态 {control.get('status')} 不能记录 runtime。"
        )
    source = _outside_repository(root, Path(runtime_file))
    if not source.is_file():
        raise GuardianError(f"runtime_file 不存在：{source}")
    if not _has_valid_isolation_attestation(source, capsule_id):
        raise GuardianError("runtime 缺少匹配的外部 Harness 隔离证明。")
    report = audit_session_log(source)
    if report.get("source_format") != "novel-forge-runtime-v1":
        raise GuardianError("runtime 必须是 novel-forge-runtime/v1。")
    if report.get("session_id") != control["session_id"]:
        raise GuardianError("runtime session_id 与 capsule 不一致。")
    if report.get("scope_chapter_count") != 1:
        raise GuardianError("runtime scope 必须严格绑定一章。")
    budget = evaluate_session_budget(report, chapter_count=1)
    if budget.get("status") != "within_budget":
        raise GuardianError("runtime 预算观测不完整或已经超限。")
    sidecar = _runtime_sidecar_path(root, slug, capsule_id)
    payload = source.read_bytes()
    _write_immutable_bytes(sidecar, payload)
    control["runtime_sidecar_path"] = str(sidecar)
    control["runtime_snapshot_sha256"] = hashlib.sha256(payload).hexdigest()
    control["runtime_source_log_sha256"] = report["source_log_sha256"]
    control["updated_at"] = _now()
    _atomic_json(control_path, control)
    return {
        "capsule_id": capsule_id,
        "session_id": control["session_id"],
        "runtime_snapshot_sha256": control["runtime_snapshot_sha256"],
        "runtime_source_log_sha256": report["source_log_sha256"],
        "budget": budget,
        "isolation_attested": True,
        "author_approval": False,
        "publication_eligibility": False,
    }


def ingest_writer_capsule(
    root: Path,
    slug: str,
    capsule_id: str,
) -> dict[str, Any]:
    """Import one isolated draft and record an immutable Guardian receipt."""
    root = Path(root).resolve()
    book_dir = _book_dir(root, slug)
    control_path, control = _load_control(book_dir, capsule_id)
    if control.get("status") != "prepared":
        raise GuardianError(
            f"writer capsule 状态 {control.get('status')} 不能再次导入。"
        )
    capsule = _outside_repository(root, Path(control["capsule_dir"]))
    if not capsule.is_dir():
        raise GuardianError(f"writer capsule 不存在：{capsule}")

    unexpected, unsafe = _capsule_inventory(capsule)
    reasons: list[str] = []
    sequence_status = chapter_sequence_status(
        root,
        slug,
        control["sequence_id"],
    )
    if (
        sequence_status.get("status") != "running"
        or sequence_status.get("current_chapter") != control["chapter"]
        or sequence_status.get("active_session_id") != control["session_id"]
    ):
        reasons.append("sequence_session_not_active")
    if unexpected:
        reasons.append("unexpected_files")
    if unsafe:
        reasons.append("path_escape_or_symlink")
        unexpected = sorted(set(unexpected + unsafe))
    for name, expected in control.get("protected_hashes", {}).items():
        path = capsule / name
        if not path.is_file() or _sha256(path) != expected:
            reasons.append(f"protected_input_changed:{name}")

    draft = capsule / "draft/正文.md"
    target = book_dir / Path(
        *PurePosixPath(control["target_path"]).parts
    )
    if not draft.is_file():
        reasons.append("missing_draft")
    if control.get("operation") == "draft":
        if target.exists():
            reasons.append("target_changed_since_prepare")
    elif control.get("operation") == "patch":
        if (
            not target.is_file()
            or _sha256(target) != control.get("input_body_sha256")
        ):
            reasons.append("target_changed_since_prepare")
    else:
        reasons.append("invalid_capsule_operation")

    runtime_value = control.get("runtime_sidecar_path")
    runtime = Path(runtime_value) if isinstance(runtime_value, str) else None
    if runtime is None or not runtime.is_file():
        reasons.append("missing_runtime_sidecar")
    elif _sha256(runtime) != control.get("runtime_snapshot_sha256"):
        reasons.append("runtime_sidecar_changed")
    elif not _has_valid_isolation_attestation(
        runtime,
        control["capsule_id"],
    ):
        reasons.append("missing_or_invalid_isolation_attestation")

    report: dict[str, Any] | None = None
    if not reasons:
        try:
            draft.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            reasons.append("draft_not_utf8")
        try:
            report = audit_session_log(runtime)
        except NovelForgeError:
            reasons.append("invalid_runtime_snapshot")
        if report is not None:
            if report.get("source_format") != "novel-forge-runtime-v1":
                reasons.append("runtime_snapshot_not_canonical")
            if report.get("session_id") != control["session_id"]:
                reasons.append("runtime_session_mismatch")
            if report.get("scope_chapter_count") != 1:
                reasons.append("runtime_scope_mismatch")
            budget = evaluate_session_budget(report, chapter_count=1)
            if budget.get("status") != "within_budget":
                reasons.append("runtime_budget_incomplete_or_exceeded")
    if draft.is_file():
        candidate_sha256 = _sha256(draft)
        clean_hashes = _clean_body_hashes(
            root,
            slug,
            control["chapter"],
        )
        authorization_valid = False
        authorization_id = str(
            control.get("regeneration_authorization_id") or ""
        ).strip()
        if authorization_id:
            try:
                authorization, authorization_sha256 = (
                    _load_regeneration_authorization(
                        root,
                        slug,
                        authorization_id,
                        sequence_id=control["sequence_id"],
                        session_id=control["session_id"],
                        chapter=control["chapter"],
                        prior_body_sha256=clean_hashes,
                    )
                )
                authorization_valid = (
                    control.get("human_regeneration_authorized") is True
                    and control.get("regeneration_authorization_sha256")
                    == authorization_sha256
                    and control.get("human_decision_reference")
                    == authorization.get("decision_reference")
                )
            except GuardianError:
                authorization_valid = False
        if (
            candidate_sha256 not in clean_hashes
            and len(clean_hashes) >= 2
            and not authorization_valid
        ):
            reasons.append("human_regeneration_authorization_missing")

    if reasons:
        _record_compromised(
            root,
            slug,
            book_dir,
            control_path,
            control,
            unexpected,
            sorted(set(reasons)),
        )
        raise GuardianError(
            "writer capsule compromised: " + ", ".join(sorted(set(reasons)))
        )

    target_changed = False
    if control.get("operation") == "draft":
        target_changed = target.exists()
    elif (
        not target.is_file()
        or _sha256(target) != control.get("input_body_sha256")
    ):
        target_changed = True
    if target_changed:
        _record_compromised(
            root,
            slug,
            book_dir,
            control_path,
            control,
            [],
            ["target_changed_since_prepare"],
        )
        raise GuardianError(
            "writer capsule compromised: target_changed_since_prepare"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = draft.read_bytes()
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    body_sha256 = hashlib.sha256(payload).hexdigest()
    receipt = {
        "schema": GUARDIAN_RECEIPT_SCHEMA,
        "capsule_id": control["capsule_id"],
        "slug": slug,
        "chapter": control["chapter"],
        "sequence_id": control["sequence_id"],
        "session_id": control["session_id"],
        "target_path": control["target_path"],
        "handoff_sha256": control["handoff_sha256"],
        "operation": control.get("operation", "draft"),
        "input_body_sha256": control.get("input_body_sha256"),
        "human_regeneration_authorized": control.get(
            "human_regeneration_authorized",
            False,
        ),
        "human_decision_reference": control.get("human_decision_reference"),
        "prompt_template_id": control.get("prompt_template_id"),
        "prompt_sha256": control.get("prompt_sha256"),
        "regeneration_authorization_id": control.get(
            "regeneration_authorization_id"
        ),
        "regeneration_authorization_sha256": control.get(
            "regeneration_authorization_sha256"
        ),
        "status": "clean",
        "isolation_attested": True,
        "control_plane_exposed": False,
        "unexpected_files": [],
        "reasons": [],
        "body_sha256": body_sha256,
        "runtime_snapshot_sha256": control["runtime_snapshot_sha256"],
        "runtime_source_log_sha256": report["source_log_sha256"],
        "recorded_at": _now(),
        "author_approval": False,
        "publication_eligibility": False,
    }
    receipt_path = _receipt_path(book_dir, control["capsule_id"])
    _write_signed_receipt(
        root,
        slug,
        book_dir,
        control["capsule_id"],
        receipt,
    )
    control["status"] = "imported"
    control["updated_at"] = _now()
    control["receipt_path"] = receipt_path.relative_to(book_dir).as_posix()
    control["body_sha256"] = body_sha256
    _atomic_json(control_path, control)
    return {
        "capsule_id": control["capsule_id"],
        "chapter": control["chapter"],
        "session_id": control["session_id"],
        "status": "clean",
        "operation": control.get("operation", "draft"),
        "input_body_sha256": control.get("input_body_sha256"),
        "human_regeneration_authorized": control.get(
            "human_regeneration_authorized",
            False,
        ),
        "human_decision_reference": control.get("human_decision_reference"),
        "prompt_template_id": control.get("prompt_template_id"),
        "prompt_sha256": control.get("prompt_sha256"),
        "regeneration_authorization_id": control.get(
            "regeneration_authorization_id"
        ),
        "body_sha256": body_sha256,
        "target_path": control["target_path"],
        "receipt_path": receipt_path.relative_to(book_dir).as_posix(),
        "control_plane_exposed": False,
        "author_approval": False,
        "publication_eligibility": False,
    }


def guardian_receipt_errors(
    book_dir: Path,
    chapter: int,
    generation: Mapping[str, Any],
) -> list[str]:
    """Validate a clean capsule receipt against the current agent generation."""
    if generation.get("writer_type") == "human":
        if generation.get("authority") in {"author", "human_delegate"}:
            return []
        return ["human writer generation 缺少 author/human_delegate authority。"]
    book_dir = Path(book_dir)
    root = book_dir.parents[1]
    slug = book_dir.name
    run_id = str(generation.get("run_id") or "").strip()
    content_path = str(generation.get("content_path") or "").strip()
    content_sha256 = str(generation.get("content_sha256") or "").strip()
    prompt_template_id = str(
        generation.get("prompt_template_id") or ""
    ).strip()
    prompt_sha256 = str(generation.get("prompt_sha256") or "").strip()
    if not prompt_template_id:
        return [
            "formal agent generation 缺少 Guardian prompt_template_id。"
        ]
    if not prompt_sha256:
        return ["formal agent generation 缺少 Guardian prompt_sha256。"]
    directory = Path(book_dir) / GUARDIAN_RECEIPT_DIRECTORY
    receipts: list[dict[str, Any]] = []
    if directory.is_dir():
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("schema") == GUARDIAN_RECEIPT_SCHEMA
                and payload.get("status") == "clean"
                and payload.get("chapter") == chapter
                and payload.get("session_id") == run_id
            ):
                receipts.append(payload)
    if not receipts:
        return ["formal agent generation 缺少干净 Guardian 导入回执。"]
    matching_receipts = [
        receipt
        for receipt in receipts
        if receipt.get("target_path") == content_path
        and receipt.get("body_sha256") == content_sha256
    ]
    receipt = (
        matching_receipts[-1]
        if matching_receipts
        else receipts[-1]
    )
    capsule_id = str(receipt.get("capsule_id") or "")
    external_path = _external_receipt_path(root, slug, capsule_id)
    try:
        external = json.loads(external_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["Guardian 回执缺少外置权威账本副本。"]
    if external != receipt or not _receipt_auth_valid(
        root,
        slug,
        receipt,
    ):
        return ["Guardian 回执签名或外置账本绑定无效。"]
    control_path = (
        book_dir
        / GUARDIAN_SESSION_DIRECTORY
        / f"{capsule_id}.json"
    )
    try:
        control = json.loads(control_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["Guardian 回执缺少对应 capsule 控制记录。"]
    if (
        not isinstance(control, dict)
        or control.get("status") != "imported"
        or control.get("receipt_path")
        != _receipt_path(book_dir, capsule_id)
        .relative_to(book_dir)
        .as_posix()
        or control.get("body_sha256") != receipt.get("body_sha256")
        or control.get("runtime_snapshot_sha256")
        != receipt.get("runtime_snapshot_sha256")
        or control.get("prompt_template_id")
        != receipt.get("prompt_template_id")
        or control.get("prompt_sha256") != receipt.get("prompt_sha256")
    ):
        return ["Guardian 回执与 imported capsule 控制记录不一致。"]
    if receipt.get("control_plane_exposed") is not False:
        return ["Guardian 回执未证明 writer 与控制面隔离。"]
    if receipt.get("isolation_attested") is not True:
        return ["Guardian 回执缺少外部 Harness 隔离证明。"]
    if receipt.get("unexpected_files") != []:
        return ["Guardian 回执包含未声明输出文件。"]
    if receipt.get("target_path") != content_path:
        return ["Guardian 回执 target_path 与 generation 不一致。"]
    if receipt.get("prompt_template_id") != prompt_template_id:
        return [
            "Guardian 回执 prompt_template_id 与 generation 不一致。"
        ]
    if receipt.get("prompt_sha256") != prompt_sha256:
        return ["Guardian 回执 prompt_sha256 与 generation 不一致。"]
    pure = PurePosixPath(content_path)
    target = Path(book_dir) / Path(*pure.parts)
    if not target.is_file():
        return ["Guardian 回执绑定的当前正文不存在。"]
    current_sha256 = _sha256(target)
    if current_sha256 != receipt.get("body_sha256"):
        return ["Guardian 回执与当前正文 SHA-256 不一致。"]
    if current_sha256 != content_sha256:
        return ["Guardian 回执与 generation 正文 SHA-256 不一致。"]
    return []
