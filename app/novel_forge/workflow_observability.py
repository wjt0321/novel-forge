"""Local, read-only workflow cost observations for Lean Native production."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .models import NovelForgeError


CALL_OBSERVATION_SCHEMA = "novel-forge-call-observation/v1"
COST_SUMMARY_SCHEMA = "novel-forge-workflow-cost-summary/v1"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "total_tokens",
    "request_count",
)
_SCOPE_NAMES = ("local", "structural", "blocking", "unclassified")
_PHASE_NAMES = (
    "planning",
    "writer_draft",
    "initial_review",
    "patch",
    "re_review",
    "control_plane",
    "other",
)
_EFFECT_NAMES = (
    "none",
    "revision_requested",
    "promotion",
    "author_decision",
)


class WorkflowObservabilityError(NovelForgeError):
    """Raised when a local workflow observation is invalid or conflicting."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nonnegative_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value >= 0 else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def sanitize_call_telemetry(payload: Any) -> dict[str, Any]:
    """Normalize optional host metrics without making telemetry a workflow gate."""
    source = payload if isinstance(payload, Mapping) else {}
    existing_warnings = source.get("warnings")
    warnings = (
        [str(item) for item in existing_warnings if str(item).strip()]
        if isinstance(existing_warnings, list)
        else []
    )
    result: dict[str, Any] = {}
    for field in _TOKEN_FIELDS:
        raw = source.get(field)
        value = _nonnegative_int(raw) if raw is not None else None
        if raw is not None and value is None:
            warnings.append(f"{field}_invalid")
        result[field] = value
    if (
        result["total_tokens"] is None
        and result["input_tokens"] is not None
        and result["output_tokens"] is not None
    ):
        result["total_tokens"] = (
            result["input_tokens"] + result["output_tokens"]
        )
    elapsed_raw = source.get("elapsed_seconds")
    elapsed = (
        _nonnegative_number(elapsed_raw)
        if elapsed_raw is not None
        else None
    )
    if elapsed_raw is not None and elapsed is None:
        warnings.append("elapsed_seconds_invalid")
    result["elapsed_seconds"] = elapsed
    requested_source = str(source.get("elapsed_source") or "").strip()
    result["elapsed_source"] = (
        requested_source
        if elapsed is not None
        and requested_source in {"host_telemetry", "relay_wall_clock"}
        else "host_telemetry"
        if elapsed is not None
        else "unknown"
    )
    result["warnings"] = warnings
    return result


def _validate_slug(slug: str) -> str:
    value = str(slug or "").strip()
    if not value or not value.replace("-", "").replace("_", "").isalnum():
        raise WorkflowObservabilityError(
            f"Invalid book slug: {slug!r}. Use alphanumeric, dash, or underscore."
        )
    return value


def _observation_root(root: Path, slug: str) -> Path:
    safe_slug = _validate_slug(slug)
    return (
        Path(root).resolve()
        / ".local-guardian"
        / safe_slug
        / "workflow-observations"
    )


def _atomic_write_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        dict(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if path.is_file():
        if path.read_text(encoding="utf-8-sig") == text:
            return
        raise WorkflowObservabilityError(
            f"工作流调用观测已存在，不得覆盖：{path.name}"
        )
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
            raise WorkflowObservabilityError(
                f"工作流调用观测已存在，不得覆盖：{path.name}"
            )
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _required_text(data: Mapping[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise WorkflowObservabilityError(f"工作流调用观测缺少 {field}。")
    return value


def _body_summary(value: Any, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise WorkflowObservabilityError(f"{field} 必须是正文摘要或 null。")
    digest = str(value.get("sha256") or "").strip()
    cjk_chars = _nonnegative_int(value.get("cjk_chars"))
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or cjk_chars is None:
        raise WorkflowObservabilityError(f"{field} 正文摘要无效。")
    return {"sha256": digest, "cjk_chars": cjk_chars}


def _scope_counts(value: Any) -> dict[str, int]:
    source = value if isinstance(value, Mapping) else {}
    result: dict[str, int] = {}
    for name in _SCOPE_NAMES:
        count = _nonnegative_int(source.get(name))
        result[name] = count if count is not None else 0
    return result


def _normalized_observation(
    slug: str,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    action_id = _required_text(observation, "action_id")
    if not _SAFE_ID_RE.fullmatch(action_id):
        raise WorkflowObservabilityError("工作流调用 action_id 无效。")
    chapter = _nonnegative_int(observation.get("chapter"))
    if chapter is None or chapter < 1:
        raise WorkflowObservabilityError("工作流调用 chapter 必须是正整数。")
    retry_index = _nonnegative_int(observation.get("technical_retry_index"))
    revision_round = _nonnegative_int(observation.get("revision_round"))
    if retry_index is None or revision_round is None:
        raise WorkflowObservabilityError("工作流调用轮次必须是非负整数。")
    before = _body_summary(observation.get("body_before"), "body_before")
    after = _body_summary(observation.get("body_after"), "body_after")
    changed = observation.get("body_changed")
    if changed is not None and not isinstance(changed, bool):
        raise WorkflowObservabilityError("body_changed 必须是布尔值或 null。")
    effect = str(observation.get("workflow_effect") or "none").strip()
    if effect not in _EFFECT_NAMES:
        effect = "none"
    payload = {
        "schema": CALL_OBSERVATION_SCHEMA,
        "slug": slug,
        "action_id": action_id,
        "chapter": chapter,
        "role": _required_text(observation, "role"),
        "purpose": _required_text(observation, "purpose"),
        "action_kind": _required_text(observation, "action_kind"),
        "outcome": _required_text(observation, "outcome"),
        "started_at": _required_text(observation, "started_at"),
        "completed_at": _required_text(observation, "completed_at"),
        "provider": _required_text(observation, "provider"),
        "model": _required_text(observation, "model"),
        "technical_retry_index": retry_index,
        "revision_round": revision_round,
        "telemetry": sanitize_call_telemetry(observation.get("telemetry")),
        "body_before": before,
        "body_after": after,
        "body_changed": changed,
        "must_scope_counts": _scope_counts(
            observation.get("must_scope_counts")
        ),
        "workflow_effect": effect,
        "failure_reason": str(
            observation.get("failure_reason") or ""
        ).strip()
        or None,
        "recorded_at": str(
            observation.get("recorded_at")
            or observation.get("completed_at")
            or _now()
        ),
    }
    return payload


def record_call_observation(
    root: Path,
    slug: str,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Write one immutable local observation keyed by native action id."""
    payload = _normalized_observation(slug, observation)
    target = (
        _observation_root(root, slug)
        / f"ch{payload['chapter']:02d}"
        / f"{payload['action_id']}.json"
    )
    _atomic_write_once(target, payload)
    return payload


def _load_observations(root: Path, slug: str) -> list[dict[str, Any]]:
    directory = _observation_root(root, slug)
    if not directory.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("ch*/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("schema") == CALL_OBSERVATION_SCHEMA
            and payload.get("slug") == slug
        ):
            records.append(payload)
    return records


def _phase(record: Mapping[str, Any]) -> str:
    purpose = str(record.get("purpose") or "")
    role = str(record.get("role") or "")
    revision_round = int(record.get("revision_round") or 0)
    if purpose == "planning":
        return "planning"
    if role == "writer" and purpose == "draft":
        return "writer_draft"
    if role == "writer" and purpose == "patch":
        return "patch"
    if role in {"blind-reader", "chapter-editor"} and purpose == "review":
        return "re_review" if revision_round > 0 else "initial_review"
    if purpose == "session_setup":
        return "control_plane"
    return "other"


def _empty_metrics() -> dict[str, Any]:
    return {
        "call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "total_tokens": 0,
        "elapsed_seconds": 0.0,
        "unknown_token_calls": 0,
        "unknown_elapsed_calls": 0,
        "body_change_count": 0,
        "known_token_share": None,
    }


def _add_record(metrics: dict[str, Any], record: Mapping[str, Any]) -> None:
    metrics["call_count"] += 1
    telemetry = record.get("telemetry")
    telemetry = telemetry if isinstance(telemetry, Mapping) else {}
    for field in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "total_tokens",
    ):
        value = _nonnegative_int(telemetry.get(field))
        if value is not None:
            metrics[field] += value
    if _nonnegative_int(telemetry.get("total_tokens")) is None:
        metrics["unknown_token_calls"] += 1
    elapsed = _nonnegative_number(telemetry.get("elapsed_seconds"))
    if elapsed is None:
        metrics["unknown_elapsed_calls"] += 1
    else:
        metrics["elapsed_seconds"] = round(
            metrics["elapsed_seconds"] + float(elapsed), 3
        )
    if record.get("body_changed") is True:
        metrics["body_change_count"] += 1


def _chapter_summary(chapter: int, records: list[dict[str, Any]]) -> dict[str, Any]:
    phases = {name: _empty_metrics() for name in _PHASE_NAMES}
    totals = _empty_metrics()
    retry_overlay = _empty_metrics()
    scopes = {name: 0 for name in _SCOPE_NAMES}
    effects = {name: 0 for name in _EFFECT_NAMES}
    for record in records:
        _add_record(phases[_phase(record)], record)
        _add_record(totals, record)
        if int(record.get("technical_retry_index") or 0) > 0 or record.get(
            "outcome"
        ) != "completed":
            _add_record(retry_overlay, record)
        source_scopes = record.get("must_scope_counts")
        if isinstance(source_scopes, Mapping):
            for name in _SCOPE_NAMES:
                scopes[name] += _nonnegative_int(source_scopes.get(name)) or 0
        effect = str(record.get("workflow_effect") or "none")
        effects[effect if effect in effects else "none"] += 1
    known_total = int(totals["total_tokens"] or 0)
    if known_total > 0:
        totals["known_token_share"] = 1.0
        retry_overlay["known_token_share"] = round(
            int(retry_overlay["total_tokens"] or 0) / known_total,
            4,
        )
        for metrics in phases.values():
            metrics["known_token_share"] = round(
                int(metrics["total_tokens"] or 0) / known_total,
                4,
            )
    return {
        "chapter": chapter,
        "call_count": len(records),
        "phases": phases,
        "totals": totals,
        "retry_overlay": retry_overlay,
        "must_scope_counts": scopes,
        "workflow_effect_counts": effects,
    }


def workflow_cost_summary(
    root: Path,
    slug: str,
    *,
    chapter: int | None = None,
    recent_chapters: int = 5,
) -> dict[str, Any]:
    """Aggregate local observations without feeding them back into routing."""
    records = _load_observations(root, slug)
    available = sorted(
        {
            int(record["chapter"])
            for record in records
            if isinstance(record.get("chapter"), int)
        }
    )
    if chapter is not None:
        selected = [chapter] if chapter in available else []
    else:
        count = recent_chapters if recent_chapters > 0 else 5
        selected = available[-count:]
    chapters = [
        _chapter_summary(
            number,
            [record for record in records if record.get("chapter") == number],
        )
        for number in selected
    ]
    aggregate_records = [
        record for record in records if record.get("chapter") in selected
    ]
    totals = (
        _chapter_summary(0, aggregate_records)
        if aggregate_records
        else _chapter_summary(0, [])
    )
    totals.pop("chapter", None)
    return {
        "schema": COST_SUMMARY_SCHEMA,
        "slug": slug,
        "selected_chapters": selected,
        "chapters": chapters,
        "totals": totals,
        "routing_affected": False,
        "author_approval": False,
        "publication_eligibility": False,
    }
