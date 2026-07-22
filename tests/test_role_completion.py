"""Tests for vendor-neutral native role completion envelopes."""

from __future__ import annotations

import pytest

from app.novel_forge.role_completion import (
    RoleCompletionError,
    parse_role_run_state,
    require_role_result,
)


def test_native_operation_handle_preserves_host_kind_and_value():
    state = parse_role_run_state(
        {
            "status": "launched",
            "operation_handle": {
                "kind": "host_team_member",
                "value": "opaque-member-01",
            },
        }
    )

    assert state.operation_kind == "host_team_member"
    assert state.operation_id == "opaque-member-01"
    assert state.status == "launched"


def test_raw_agent_id_is_not_treated_as_a_task_handle():
    with pytest.raises(
        RoleCompletionError,
        match="operation_handle",
    ):
        parse_role_run_state(
            {
                "status": "launched",
                "agent_id": "writer-role-name@host-team",
            }
        )


def test_idle_notification_without_role_result_is_not_completion():
    state = parse_role_run_state(
        {
            "status": "completed",
            "operation_handle": {
                "kind": "host_team_member",
                "value": "reviewer-01",
            },
            "event": {
                "type": "idle_notification",
                "idle_reason": "available",
            },
        }
    )

    with pytest.raises(
        RoleCompletionError,
        match="角色产物",
    ):
        require_role_result(state, expected_role="blind-reader")


def test_mailbox_completion_requires_bound_structured_role_result():
    state = parse_role_run_state(
        {
            "status": "completed",
            "operation_handle": {
                "kind": "host_team_member",
                "value": "reviewer-01",
            },
            "result_transport": "mailbox",
            "resolved_model": "host-resolved-model",
            "role_result": {
                "schema": "novel-forge-role-result/v1",
                "role": "blind-reader",
                "payload": {
                    "verdict": "pass",
                },
            },
        }
    )

    result = require_role_result(
        state,
        expected_role="blind-reader",
    )

    assert result["payload"]["verdict"] == "pass"
    assert state.result_transport == "mailbox"
    assert state.resolved_model == "host-resolved-model"


def test_role_result_cannot_be_relabelled_for_another_role():
    state = parse_role_run_state(
        {
            "status": "completed",
            "operation_handle": {
                "kind": "host_background_task",
                "value": "task-01",
            },
            "result_transport": "background_output",
            "role_result": {
                "schema": "novel-forge-role-result/v1",
                "role": "blind-reader",
                "payload": {
                    "verdict": "pass",
                },
            },
        }
    )

    with pytest.raises(
        RoleCompletionError,
        match="角色不匹配",
    ):
        require_role_result(state, expected_role="chapter-editor")
