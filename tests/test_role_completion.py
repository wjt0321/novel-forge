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
            "session_binding": {
                "role": "blind-reader",
                "session_id": "blind-session-01",
                "session_instance_id": "blind-instance-01",
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
        expected_session_id="blind-session-01",
        expected_session_instance_id="blind-instance-01",
    )

    assert result["payload"]["verdict"] == "pass"
    assert state.result_transport == "mailbox"
    assert state.resolved_model == "host-resolved-model"
    assert state.role == "blind-reader"
    assert state.session_id == "blind-session-01"
    assert state.session_instance_id == "blind-instance-01"


def test_role_result_cannot_be_relabelled_for_another_role():
    state = parse_role_run_state(
        {
            "status": "completed",
            "operation_handle": {
                "kind": "host_background_task",
                "value": "task-01",
            },
            "session_binding": {
                "role": "blind-reader",
                "session_id": "blind-session-01",
                "session_instance_id": "blind-instance-01",
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


def test_completed_result_requires_exact_native_session_binding():
    state = parse_role_run_state(
        {
            "status": "completed",
            "operation_handle": {
                "kind": "host_background_task",
                "value": "task-02",
            },
            "result_transport": "background_output",
            "role_result": {
                "schema": "novel-forge-role-result/v1",
                "role": "chapter-editor",
                "payload": {
                    "verdict": "ready_for_editor_decision",
                },
            },
        }
    )

    with pytest.raises(
        RoleCompletionError,
        match="会话绑定",
    ):
        require_role_result(
            state,
            expected_role="chapter-editor",
            expected_session_id="editor-session-01",
            expected_session_instance_id="editor-instance-01",
        )


def test_late_result_from_retired_session_is_rejected():
    state = parse_role_run_state(
        {
            "status": "completed",
            "operation_handle": {
                "kind": "host_background_task",
                "value": "task-old",
            },
            "session_binding": {
                "role": "blind-reader",
                "session_id": "blind-session-old",
                "session_instance_id": "blind-instance-old",
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
        match="会话不匹配",
    ):
        require_role_result(
            state,
            expected_role="blind-reader",
            expected_session_id="blind-session-new",
            expected_session_instance_id="blind-instance-new",
        )
