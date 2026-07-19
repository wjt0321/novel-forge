"""Sanitized external harness session auditing for books projects."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .models import NovelForgeError
from .planning_spec import (
    DEFAULT_CHAPTERS_PER_SEQUENCE,
    MAX_CACHED_INPUT_TOKENS_PER_CHAPTER,
    MAX_CHAPTERS_PER_SEQUENCE,
    MAX_REQUEST_CONTEXT_TOKENS,
    MAX_REQUESTS_PER_CHAPTER,
)


RUNTIME_AUDIT_SCHEMA_VERSION = 1
RUNTIME_AUDIT_DIRECTORY = Path("evidence/runtime-audits")
HARNESS_CONTRACT_SCHEMA = "novel-forge-harness-contract/v1"
RUNTIME_REPORT_SCHEMA = "novel-forge-runtime/v1"
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")


class SessionAuditError(NovelForgeError):
    """Raised when a session export or sanitized audit record is invalid."""


def harness_contract() -> dict[str, Any]:
    """Return the vendor-neutral runtime contract for any writing harness."""
    return {
        "schema": HARNESS_CONTRACT_SCHEMA,
        "purpose": (
            "Define the minimum observable runtime behavior required for "
            "formal novel production."
        ),
        "runtime_report_schema": {
            "const": RUNTIME_REPORT_SCHEMA,
            "report_mode": "cumulative_session_snapshot",
            "required": [
                "schema",
                "session_id",
                "scope",
                "harness",
                "model",
                "timing",
                "usage",
                "tools",
            ],
            "scope": {
                "chapter_count": {"const": 1},
            },
            "harness": {
                "name": "non_empty_string",
                "version": "non_empty_string_or_unknown",
            },
            "model": {
                "provider": "non_empty_string_or_unknown",
                "name": "non_empty_string_or_unknown",
                "reasoning_effort": [
                    "standard",
                    "high",
                    "max",
                    "unknown",
                ],
            },
            "timing": {
                "elapsed_seconds": "non_negative_number_or_null",
            },
            "usage": {
                "request_count": "non_negative_integer_or_null",
                "input_tokens": "non_negative_integer_or_null",
                "output_tokens": "non_negative_integer_or_null",
                "cached_input_tokens": "non_negative_integer_or_null",
                "total_tokens": "non_negative_integer_or_null",
                "max_request_context_tokens": (
                    "non_negative_integer_or_null"
                ),
                "context_reset_count": "non_negative_integer_or_null",
            },
            "tools": {
                "call_count": "non_negative_integer_or_null",
                "failure_count": "non_negative_integer_or_null",
                "by_name": "object_of_non_negative_integer_counts",
            },
        },
        "lifecycle": {
            "load_contract_before_formal_writing": True,
            "one_writer_session_per_chapter": True,
            "observe_after_each_model_response": True,
            "emit_cumulative_snapshot": True,
            "audit_snapshot_before_next_request": True,
            "stop_before_next_request_when_denied": True,
            "record_final_audit_before_ready": True,
            "blind_review_uses_separate_session": True,
            "next_chapter_requires_new_session": True,
            "writer_session_ends_after_chapter_ready": True,
            "orchestrator_may_auto_launch_next_session": True,
        },
        "adapter_operations": {
            "get_contract": "harness-contract",
            "begin_sequence": (
                "begin-chapter-sequence <slug> --start-chapter <n> "
                "--chapter-count <1..4>"
            ),
            "claim_writer_session": (
                "claim-chapter-session <slug> <sequence-id> "
                "--session-id <native-session-id>"
            ),
            "advance_sequence": (
                "advance-chapter-sequence <slug> <sequence-id> "
                "--session-id <native-session-id>"
            ),
            "sequence_status": (
                "chapter-sequence-status <slug> <sequence-id>"
            ),
            "audit_snapshot": (
                "session-audit <slug> --file <absolute-runtime-json>"
            ),
            "record_final_audit": (
                "--confirm record-session-audit record-session-audit "
                "<slug> --file <absolute-runtime-json>"
            ),
        },
        "limits_per_chapter": {
            "request_count": MAX_REQUESTS_PER_CHAPTER,
            "cached_input_tokens": MAX_CACHED_INPUT_TOKENS_PER_CHAPTER,
            "cached_input_tokens_interpretation": "hard_ceiling_not_target",
            "max_request_context_tokens": MAX_REQUEST_CONTEXT_TOKENS,
        },
        "reasoning_policy": {
            "planning_and_causal_checks": "high",
            "prose_draft_default": "standard_or_medium",
            "review_default": "standard_or_medium",
            "max_reasoning": "named_exception_only",
            "numeric_style_targets_visible_to_writer": False,
        },
        "chapter_sequence": {
            "default_chapter_count": DEFAULT_CHAPTERS_PER_SEQUENCE,
            "maximum_chapter_count": MAX_CHAPTERS_PER_SEQUENCE,
            "five_or_more_must_be_split": True,
            "previous_chapter_must_be_ready": True,
            "one_launch_directive_at_a_time": True,
            "native_session_id_must_not_be_reused": True,
            "generation_run_id_must_equal_claimed_session_id": True,
            "continuity_source": "bounded_external_handoff",
            "forbidden_context": [
                "old_session_messages",
                "old_tool_output",
                "old_review_bodies",
                "other_book_assets",
            ],
        },
        "decision_protocol": {
            "continue_field": "budget.continue_allowed",
            "continue_value": True,
            "stop_value": False,
            "stop_is_not_overridable_by_writer_or_editor": True,
            "unknown_metrics_require_non_formal_mode": True,
        },
        "provenance_protocol": {
            "generation_run_id_equals_runtime_session_id": True,
            "generation_metadata_must_match_observed_runtime": True,
            "tool_failures_must_be_reported": True,
            "role_name_does_not_prove_session_independence": True,
        },
        "privacy": {
            "allowed": [
                "identifiers",
                "timing",
                "token_counts",
                "request_counts",
                "tool_counts",
                "source_hash",
            ],
            "forbidden": [
                "prompt",
                "prose",
                "reasoning",
                "tool_arguments",
                "tool_results",
                "review_body",
            ],
            "unknown_fields_are_ignored": True,
        },
    }


def _read_export(path: Path) -> tuple[dict[str, Any], str]:
    source = Path(path)
    if not source.is_absolute():
        raise SessionAuditError("会话日志 --file 必须是绝对路径。")
    if not source.is_file():
        raise SessionAuditError(f"会话日志不存在：{source}")
    raw = source.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise SessionAuditError(f"会话日志不是有效 UTF-8：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise SessionAuditError(f"会话日志不是有效 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise SessionAuditError("会话日志 JSON 顶层必须是对象。")
    return payload, hashlib.sha256(raw).hexdigest()


def _optional_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _sum_optional(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _canonical_reasoning_effort(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"thinking", "high", "extended", "deep"}:
        return "high"
    if text in {"max", "maximum"}:
        return "max"
    if text in {"standard", "normal", "default"}:
        return "standard"
    return "unknown"


def _split_model(value: Any) -> tuple[str, str]:
    text = str(value or "unknown").strip() or "unknown"
    if "/" in text:
        provider, model = text.split("/", 1)
        return provider.strip().lower() or "unknown", model.strip() or "unknown"
    lowered = text.lower()
    if "minimax" in lowered:
        return "minimax", text
    if "deepseek" in lowered:
        return "deepseek", text
    return "unknown", text


def _context_reset_count(contexts: list[int]) -> int:
    resets = 0
    for previous, current in zip(contexts, contexts[1:]):
        if previous >= 20_000 and current < previous * 0.5:
            resets += 1
    return resets


def _mapping_field(
    payload: Mapping[str, Any], field: str
) -> Mapping[str, Any]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise SessionAuditError(f"标准运行快照缺少对象字段：{field}")
    return value


def _required_text(
    payload: Mapping[str, Any], field: str, *, allow_unknown: bool = True
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SessionAuditError(f"标准运行快照缺少文本字段：{field}")
    text = value.strip()
    if not allow_unknown and text.lower() == "unknown":
        raise SessionAuditError(f"标准运行快照字段不能为 unknown：{field}")
    return text


def _optional_number(value: Any, field: str) -> float | int | None:
    if value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value < 0
    ):
        raise SessionAuditError(
            f"标准运行快照字段必须是非负数或 null：{field}"
        )
    return value


def _optional_count(value: Any, field: str) -> int | None:
    if value is None:
        return None
    count = _optional_int(value)
    if count is None:
        raise SessionAuditError(
            f"标准运行快照字段必须是非负整数或 null：{field}"
        )
    return count


def _audit_canonical(
    payload: Mapping[str, Any], source_hash: str
) -> dict[str, Any]:
    scope = _mapping_field(payload, "scope")
    harness = _mapping_field(payload, "harness")
    model = _mapping_field(payload, "model")
    timing = _mapping_field(payload, "timing")
    usage = _mapping_field(payload, "usage")
    tools = _mapping_field(payload, "tools")

    chapter_count = _optional_int(scope.get("chapter_count"))
    if chapter_count is None or chapter_count < 1:
        raise SessionAuditError(
            "标准运行快照 scope.chapter_count 必须是正整数。"
        )
    if chapter_count != 1:
        raise SessionAuditError(
            "formal 标准运行快照必须遵守每章独立写作会话，"
            "scope.chapter_count 只能为 1。"
        )
    harness_name = _required_text(harness, "name", allow_unknown=False)
    harness_version = _required_text(harness, "version")
    harness_label = (
        harness_name
        if harness_version.lower() == "unknown"
        else f"{harness_name}/{harness_version}"
    )
    by_name_raw = tools.get("by_name")
    if not isinstance(by_name_raw, Mapping):
        raise SessionAuditError(
            "标准运行快照 tools.by_name 必须是计数对象。"
        )
    by_name: dict[str, int] = {}
    for raw_name, raw_count in by_name_raw.items():
        name = str(raw_name).strip()
        if not name:
            raise SessionAuditError(
                "标准运行快照 tools.by_name 含空工具名。"
            )
        by_name[name] = _optional_count(
            raw_count, f"tools.by_name.{name}"
        ) or 0

    return {
        "schema_version": RUNTIME_AUDIT_SCHEMA_VERSION,
        "source_format": "novel-forge-runtime-v1",
        "source_log_sha256": source_hash,
        "session_id": _required_text(
            payload, "session_id", allow_unknown=False
        ),
        "scope_chapter_count": chapter_count,
        "agent_harness": harness_label,
        "provider": _required_text(model, "provider"),
        "model": _required_text(model, "name"),
        "reasoning_effort": _canonical_reasoning_effort(
            _required_text(model, "reasoning_effort")
        ),
        "elapsed_seconds": _optional_number(
            timing.get("elapsed_seconds"),
            "timing.elapsed_seconds",
        ),
        "request_count": _optional_count(
            usage.get("request_count"), "usage.request_count"
        ),
        "tokens": {
            "input": _optional_count(
                usage.get("input_tokens"), "usage.input_tokens"
            ),
            "output": _optional_count(
                usage.get("output_tokens"), "usage.output_tokens"
            ),
            "cached_input": _optional_count(
                usage.get("cached_input_tokens"),
                "usage.cached_input_tokens",
            ),
            "total": _optional_count(
                usage.get("total_tokens"), "usage.total_tokens"
            ),
        },
        "max_context_tokens": _optional_count(
            usage.get("max_request_context_tokens"),
            "usage.max_request_context_tokens",
        ),
        "context_reset_count": _optional_count(
            usage.get("context_reset_count"),
            "usage.context_reset_count",
        ),
        "tool_calls": {
            "total": _optional_count(
                tools.get("call_count"), "tools.call_count"
            ),
            "failed": _optional_count(
                tools.get("failure_count"), "tools.failure_count"
            ),
            "by_name": dict(sorted(by_name.items())),
        },
    }


def _audit_minimax(payload: Mapping[str, Any], source_hash: str) -> dict[str, Any]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise SessionAuditError("MiniMax Code 导出缺少 messages 数组。")
    session = payload.get("session")
    session = session if isinstance(session, dict) else {}
    record = session.get("record")
    record = record if isinstance(record, dict) else {}
    session_id = str(
        payload.get("session_id")
        or session.get("session_id")
        or record.get("sessionId")
        or ""
    ).strip()
    if not session_id:
        raise SessionAuditError("MiniMax Code 导出缺少 session_id。")

    runtime = str(record.get("runtime") or "minimax-code").strip()
    agent = str(record.get("agentName") or "").strip()
    harness = f"{runtime}/{agent}" if agent else runtime
    provider, model = _split_model(record.get("effectiveModel"))

    usage_rows: list[dict[str, Any]] = []
    tools: Counter[str] = Counter()
    failed_tools = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        data = message.get("data")
        if not isinstance(data, dict):
            continue
        usage = data.get("usage")
        if isinstance(usage, dict):
            usage_rows.append(usage)
        calls = data.get("tool_calls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("tool_name") or "unknown").strip() or "unknown"
            tools[name] += 1
            status = call.get("tool_call_status")
            if status in {3, "3", "error", "failed"}:
                failed_tools += 1

    contexts = [
        value
        for value in (
            _optional_int(row.get("total_tokens")) for row in usage_rows
        )
        if value is not None
    ]
    first_ms = _optional_int(payload.get("first_message_at"))
    last_ms = _optional_int(payload.get("last_message_at"))
    if first_ms is None:
        first_ms = _optional_int(record.get("createdAtMs"))
    if last_ms is None:
        last_ms = _optional_int(record.get("updatedAtMs"))
    elapsed = (
        round((last_ms - first_ms) / 1000, 3)
        if first_ms is not None and last_ms is not None and last_ms >= first_ms
        else None
    )
    return {
        "schema_version": RUNTIME_AUDIT_SCHEMA_VERSION,
        "source_format": "minimax-code",
        "source_log_sha256": source_hash,
        "session_id": session_id,
        "agent_harness": harness,
        "provider": provider,
        "model": model,
        "reasoning_effort": _canonical_reasoning_effort(
            record.get("effectiveModelVariant")
        ),
        "elapsed_seconds": elapsed,
        "request_count": len(usage_rows),
        "tokens": {
            "input": _sum_optional(
                [_optional_int(row.get("input_tokens")) for row in usage_rows]
            ),
            "output": _sum_optional(
                [_optional_int(row.get("output_tokens")) for row in usage_rows]
            ),
            "cached_input": _sum_optional(
                [_optional_int(row.get("cache_read")) for row in usage_rows]
            ),
            "total": _sum_optional(contexts),
        },
        "max_context_tokens": max(contexts) if contexts else None,
        "context_reset_count": _context_reset_count(contexts),
        "tool_calls": {
            "total": sum(tools.values()),
            "failed": failed_tools,
            "by_name": dict(sorted(tools.items())),
        },
    }


def _reasonix_session_id(items: list[Any], source_hash: str) -> str:
    for item in items:
        if not isinstance(item, dict) or item.get("kind") != "notice":
            continue
        text = str(item.get("text") or "")
        match = re.search(r"autoresearch task created:\s*([A-Za-z0-9._-]+)", text)
        if match:
            return match.group(1)
    return f"reasonix-{source_hash[:16]}"


def _audit_reasonix(payload: Mapping[str, Any], source_hash: str) -> dict[str, Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise SessionAuditError("Reasonix 导出缺少 items 数组。")
    tools: Counter[str] = Counter()
    failed_tools = 0
    request_count = 0
    work_durations: list[int] = []
    phase_texts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind == "assistant":
            request_count += 1
            duration = _optional_int(item.get("workDurationMs"))
            if duration is not None:
                work_durations.append(duration)
        elif kind == "tool":
            name = str(item.get("name") or "unknown").strip() or "unknown"
            tools[name] += 1
            if item.get("status") not in {"done", "success", "completed"}:
                failed_tools += 1
        elif kind == "phase":
            phase_texts.append(str(item.get("text") or ""))
    phase = " ".join(phase_texts).lower()
    provider = "deepseek" if "deepseek" in phase else "unknown"
    return {
        "schema_version": RUNTIME_AUDIT_SCHEMA_VERSION,
        "source_format": "reasonix",
        "source_log_sha256": source_hash,
        "session_id": _reasonix_session_id(items, source_hash),
        "agent_harness": "reasonix-autoresearch",
        "provider": provider,
        "model": "unknown",
        "reasoning_effort": "unknown",
        "elapsed_seconds": (
            round(max(work_durations) / 1000, 3) if work_durations else None
        ),
        "request_count": request_count,
        "tokens": {
            "input": None,
            "output": None,
            "cached_input": None,
            "total": None,
        },
        "max_context_tokens": None,
        "context_reset_count": None,
        "tool_calls": {
            "total": sum(tools.values()),
            "failed": failed_tools,
            "by_name": dict(sorted(tools.items())),
        },
    }


def audit_session_log(path: Path) -> dict[str, Any]:
    """Parse one standard snapshot or compatibility export into safe metrics."""
    payload, source_hash = _read_export(Path(path))
    if payload.get("schema") == RUNTIME_REPORT_SCHEMA:
        return _audit_canonical(payload, source_hash)
    if isinstance(payload.get("messages"), list):
        return _audit_minimax(payload, source_hash)
    if isinstance(payload.get("items"), list):
        return _audit_reasonix(payload, source_hash)
    raise SessionAuditError(
        "无法识别运行快照；Harness 应输出 novel-forge-runtime/v1，"
        "或使用已提供的兼容性导入格式。"
    )


def evaluate_session_budget(
    report: Mapping[str, Any], chapter_count: int
) -> dict[str, Any]:
    """Return the external continue/stop decision for a session snapshot."""
    if (
        not isinstance(chapter_count, int)
        or isinstance(chapter_count, bool)
        or chapter_count < 1
    ):
        raise SessionAuditError("chapter_count 必须是正整数。")
    request_limit = MAX_REQUESTS_PER_CHAPTER * chapter_count
    cache_limit = MAX_CACHED_INPUT_TOKENS_PER_CHAPTER * chapter_count
    findings: list[dict[str, Any]] = []

    def _check(code: str, actual: Any, limit: int) -> None:
        if isinstance(actual, int) and not isinstance(actual, bool) and actual > limit:
            findings.append({"code": code, "actual": actual, "limit": limit})

    tokens = report.get("tokens")
    tokens = tokens if isinstance(tokens, Mapping) else {}
    _check("session-request-budget", report.get("request_count"), request_limit)
    _check(
        "session-cached-context-budget",
        tokens.get("cached_input"),
        cache_limit,
    )
    _check(
        "request-context-window",
        report.get("max_context_tokens"),
        MAX_REQUEST_CONTEXT_TOKENS,
    )
    assessed = sum(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (
            report.get("request_count"),
            tokens.get("cached_input"),
            report.get("max_context_tokens"),
        )
    )
    status = (
        "exceeded"
        if findings
        else "within_budget"
        if assessed == 3
        else "partial"
        if assessed
        else "unassessed"
    )
    return {
        "status": status,
        "continue_allowed": not findings,
        "chapter_count": chapter_count,
        "findings": findings,
        "limits": {
            "request_count": request_limit,
            "cached_input_tokens": cache_limit,
            "max_context_tokens": MAX_REQUEST_CONTEXT_TOKENS,
        },
    }


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def compare_generation_provenance(
    generation: Mapping[str, Any],
    audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Compare self-recorded generation metadata with an external export."""
    mismatches: list[dict[str, Any]] = []
    for generation_field, audit_field in (
        ("run_id", "session_id"),
        ("provider", "provider"),
        ("model", "model"),
        ("agent_harness", "agent_harness"),
        ("reasoning_effort", "reasoning_effort"),
    ):
        claimed = generation.get(generation_field)
        observed = audit.get(audit_field)
        if _normalized(observed) in {"", "unknown", "unassessed"}:
            continue
        if _normalized(claimed) != _normalized(observed):
            mismatches.append(
                {
                    "field": generation_field,
                    "claimed": claimed,
                    "observed": observed,
                }
            )
    tool_calls = audit.get("tool_calls")
    failed = (
        tool_calls.get("failed")
        if isinstance(tool_calls, Mapping)
        else None
    )
    claimed_failures = generation.get("tool_failures")
    if (
        isinstance(failed, int)
        and failed > 0
        and isinstance(claimed_failures, list)
        and not claimed_failures
    ):
        mismatches.append(
            {
                "field": "tool_failures",
                "claimed": 0,
                "observed": failed,
            }
        )
    return mismatches


def audit_book_session(
    root: Path, slug: str, source_file: Path
) -> tuple[Path, dict[str, Any]]:
    """Audit one export against a books project's generation evidence."""
    book_dir = Path(root) / "books" / slug
    if not book_dir.is_dir():
        raise SessionAuditError(f"books/ 项目不存在：{book_dir}")
    report = audit_session_log(source_file)
    chapter_count = report.get("scope_chapter_count")
    if not isinstance(chapter_count, int) or isinstance(chapter_count, bool):
        chapter_count = max(
            1,
            sum(
                1
                for path in (book_dir / "chapters").glob(
                    "e*/ch-*/正文.md"
                )
                if path.is_file()
            ),
        )
    report["budget"] = evaluate_session_budget(
        report, chapter_count=chapter_count
    )

    from .book_evidence import evidence_status

    generations = evidence_status(root, slug, None)["generation_metrics"]
    matching = [
        generation
        for generation in generations
        if _normalized(generation.get("run_id"))
        == _normalized(report["session_id"])
    ]
    candidates = matching or generations
    mismatches: list[dict[str, Any]] = []
    for generation in candidates:
        for mismatch in compare_generation_provenance(generation, report):
            mismatches.append(
                {
                    "record_id": generation["id"],
                    **mismatch,
                }
            )
    if generations and not matching:
        mismatches.append(
            {
                "record_id": None,
                "field": "generation_binding",
                "claimed": sorted(
                    {
                        str(generation.get("run_id") or "unknown")
                        for generation in generations
                    }
                ),
                "observed": report["session_id"],
            }
        )
    report["provenance_mismatches"] = mismatches
    report["generation_record_ids"] = [
        generation["id"] for generation in candidates
    ]
    report["provenance_status"] = (
        "mismatch"
        if mismatches
        else "verified"
        if generations
        else "unassessed"
    )
    return book_dir, report


def _safe_session_id(session_id: str) -> str:
    safe = _SAFE_ID_RE.sub("-", session_id).strip("-._")
    if not safe:
        raise SessionAuditError("session_id 无法转换为安全文件名。")
    return safe[:160]


def _runtime_audit_path(book_dir: Path, session_id: str) -> Path:
    return Path(book_dir) / RUNTIME_AUDIT_DIRECTORY / (
        _safe_session_id(session_id) + ".json"
    )


def _validate_runtime_report(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report)
    if data.get("schema_version") != RUNTIME_AUDIT_SCHEMA_VERSION:
        raise SessionAuditError("runtime audit schema_version 不受支持。")
    for field in (
        "source_format",
        "source_log_sha256",
        "session_id",
        "agent_harness",
        "provider",
        "model",
        "reasoning_effort",
    ):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise SessionAuditError(f"runtime audit 缺少字段：{field}")
    if not re.fullmatch(r"[0-9a-f]{64}", data["source_log_sha256"]):
        raise SessionAuditError("source_log_sha256 必须是 SHA-256。")
    budget = data.get("budget")
    if not isinstance(budget, dict) or not isinstance(
        budget.get("continue_allowed"), bool
    ):
        raise SessionAuditError("runtime audit 缺少外部预算结论。")
    mismatches = data.get("provenance_mismatches")
    if not isinstance(mismatches, list):
        raise SessionAuditError("runtime audit 缺少 provenance_mismatches。")
    return data


def record_runtime_audit(
    book_dir: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    """Atomically store one sanitized, immutable runtime audit."""
    data = _validate_runtime_report(report)
    target = _runtime_audit_path(Path(book_dir), data["session_id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if target.exists():
        existing = target.read_text(encoding="utf-8-sig")
        if existing == payload:
            return {
                "runtime_audit_id": target.stem,
                "path": target.relative_to(book_dir).as_posix(),
                "session_id": data["session_id"],
                "continue_allowed": data["budget"]["continue_allowed"],
            }
        raise SessionAuditError(
            f"同一 session_id 的 runtime audit 已存在，不得覆盖：{data['session_id']}"
        )
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.stem}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            raise SessionAuditError(
                f"runtime audit 已存在，不得覆盖：{data['session_id']}"
            )
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {
        "runtime_audit_id": target.stem,
        "path": target.relative_to(book_dir).as_posix(),
        "session_id": data["session_id"],
        "continue_allowed": data["budget"]["continue_allowed"],
    }


def find_runtime_audit(book_dir: Path, session_id: str) -> dict[str, Any]:
    """Load one sanitized audit by its externally observed session id."""
    target = _runtime_audit_path(Path(book_dir), session_id)
    if not target.is_file():
        raise SessionAuditError(f"runtime audit 不存在：{session_id}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SessionAuditError(f"runtime audit JSON 损坏：{exc}") from exc
    if not isinstance(payload, dict):
        raise SessionAuditError("runtime audit JSON 顶层必须是对象。")
    data = _validate_runtime_report(payload)
    return {
        **data,
        "runtime_audit_id": target.stem,
        "path": target.relative_to(book_dir).as_posix(),
        "continue_allowed": data["budget"]["continue_allowed"],
    }
