"""Vendor-neutral normalization for native role lifecycle and results."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import NovelForgeError


ROLE_RESULT_SCHEMA = "novel-forge-role-result/v1"
RESULT_TRANSPORT_ORDER = (
    "inline",
    "background_output",
    "mailbox",
    "artifact",
)
RESULT_TRANSPORTS = frozenset(RESULT_TRANSPORT_ORDER)
_HANDLE_KIND_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_LAUNCHED_STATUSES = frozenset(
    {
        "accepted",
        "async_launched",
        "created",
        "launched",
        "progress",
        "remote_launched",
        "running",
        "working",
    }
)
_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "timed_out",
    }
)


class RoleCompletionError(NovelForgeError):
    """Raised when a host role lifecycle or result cannot be verified."""


@dataclass(frozen=True)
class SessionRunState:
    """One normalized native role launch or terminal state."""

    operation_id: str
    status: str
    operation_kind: str = "opaque_host_operation"
    resolved_model: str | None = None
    result_transport: str | None = None
    role_result: dict[str, Any] | None = field(
        default=None,
        compare=False,
    )


def _operation_handle(payload: dict[str, Any]) -> tuple[str, str]:
    handle = payload.get("operation_handle")
    if isinstance(handle, dict):
        kind = str(handle.get("kind") or "").strip()
        value = str(
            handle.get("value")
            or handle.get("id")
            or ""
        ).strip()
    else:
        kind = str(payload.get("operation_kind") or "").strip()
        value = str(payload.get("operation_id") or "").strip()
    if (
        not kind
        or not value
        or _HANDLE_KIND_RE.fullmatch(kind) is None
    ):
        raise RoleCompletionError(
            "宿主必须返回带 kind 和 value 的 operation_handle。"
        )
    return kind, value


def parse_role_run_state(payload: dict[str, Any]) -> SessionRunState:
    """Normalize a host lifecycle payload without guessing identifier types."""
    if not isinstance(payload, dict):
        raise RoleCompletionError("宿主角色状态必须是对象。")
    operation_kind, operation_id = _operation_handle(payload)
    raw_status = str(
        payload.get("status")
        or payload.get("completion_status")
        or ""
    ).strip()
    if raw_status in _LAUNCHED_STATUSES:
        status = "launched"
    elif raw_status in _TERMINAL_STATUSES:
        status = raw_status
    else:
        raise RoleCompletionError(
            "宿主没有返回可验证的角色生命周期状态。"
        )
    resolved_model = payload.get("resolved_model")
    if resolved_model is None:
        resolved_model = payload.get("resolvedModel")
    result_transport = payload.get("result_transport")
    role_result = payload.get("role_result")
    return SessionRunState(
        operation_id=operation_id,
        operation_kind=operation_kind,
        status=status,
        resolved_model=(
            str(resolved_model).strip() if resolved_model else None
        ),
        result_transport=(
            str(result_transport).strip()
            if result_transport is not None
            else None
        ),
        role_result=(
            dict(role_result)
            if isinstance(role_result, dict)
            else None
        ),
    )


def require_role_result(
    state: SessionRunState,
    *,
    expected_role: str,
) -> dict[str, Any]:
    """Return a completed result bound to the expected creative role."""
    if state.status != "completed":
        raise RoleCompletionError("角色会话尚未到达官方完成终态。")
    result = state.role_result
    if not isinstance(result, dict):
        raise RoleCompletionError("角色完成后没有返回可验证的角色产物。")
    if state.result_transport not in RESULT_TRANSPORTS:
        raise RoleCompletionError("角色产物没有通过有效结果通道返回。")
    if result.get("schema") != ROLE_RESULT_SCHEMA:
        raise RoleCompletionError("角色产物 schema 无效。")
    if str(result.get("role") or "").strip() != expected_role:
        raise RoleCompletionError("角色产物与当前角色不匹配。")
    payload = result.get("payload")
    if not isinstance(payload, dict):
        raise RoleCompletionError("角色产物 payload 无效。")
    return result
