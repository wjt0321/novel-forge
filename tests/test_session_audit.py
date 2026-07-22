"""Tests for external harness session auditing and runtime evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.novel_forge.session_audit import (
    SessionAuditError,
    audit_book_session,
    audit_session_log,
    compare_generation_provenance,
    evaluate_session_budget,
    find_runtime_audit,
    harness_contract,
    record_runtime_audit,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _minimax_log(tmp_path: Path) -> Path:
    messages = [
        {
            "role": "user",
            "created_at_ms": 1_000,
            "data": {
                "msg_id": "user-1",
                "msg_type": 1,
                "role": "user",
                "msg_content": "SECRET PROMPT AND PROSE",
                "timestamp": 1_000,
            },
        },
        {
            "role": "assistant",
            "created_at_ms": 2_000,
            "data": {
                "msg_id": "assistant-1",
                "msg_type": 2,
                "role": "assistant",
                "msg_content": "SECRET RESPONSE",
                "thinking_content": "SECRET REASONING",
                "timestamp": 2_000,
                "finish_reason": "toolUse",
                "usage": {
                    "total_tokens": 150_000,
                    "context_window": 400_000,
                    "input_tokens": 1_000,
                    "output_tokens": 500,
                    "cache_read": 148_500,
                },
                "tool_calls": [
                    {
                        "tool_name": "bash",
                        "tool_call_status": 2,
                        "tool_call_result_data": {"content": "SECRET TOOL RESULT"},
                    }
                ],
            },
        },
        {
            "role": "assistant",
            "created_at_ms": 3_000,
            "data": {
                "msg_id": "assistant-2",
                "msg_type": 2,
                "role": "assistant",
                "msg_content": "",
                "timestamp": 3_000,
                "finish_reason": "toolUse",
                "usage": {
                    "total_tokens": 160_000,
                    "context_window": 400_000,
                    "input_tokens": 2_000,
                    "output_tokens": 700,
                    "cache_read": 157_300,
                },
                "tool_calls": [
                    {
                        "tool_name": "edit",
                        "tool_call_status": 3,
                        "tool_call_result_data": {"content": "SECRET ERROR"},
                    }
                ],
            },
        },
        {
            "role": "assistant",
            "created_at_ms": 4_000,
            "data": {
                "msg_id": "assistant-3",
                "msg_type": 2,
                "role": "assistant",
                "msg_content": "done",
                "timestamp": 4_000,
                "finish_reason": "stop",
                "usage": {
                    "total_tokens": 20_000,
                    "context_window": 400_000,
                    "input_tokens": 300,
                    "output_tokens": 100,
                    "cache_read": 19_600,
                },
                "tool_calls": [],
            },
        },
    ]
    return _write_json(
        tmp_path / "minimax.json",
        {
            "session_id": "mvs-test-session",
            "first_message_at": 1_000,
            "last_message_at": 4_000,
            "messages": messages,
            "session": {
                "session_id": "mvs-test-session",
                "record": {
                    "sessionId": "mvs-test-session",
                    "runtime": "pi-agent",
                    "agentName": "mavis",
                    "effectiveModel": "minimax/MiniMax-M3",
                    "effectiveModelVariant": "thinking",
                    "createdAtMs": 1_000,
                    "updatedAtMs": 4_000,
                },
            },
        },
    )


def _reasonix_log(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "reasonix.json",
        {
            "title": "Reasonix executor benchmark",
            "exportedAt": "2026-07-19T02:00:00Z",
            "items": [
                {
                    "kind": "notice",
                    "id": "n0",
                    "text": "autoresearch task created: run-reasonix-001",
                },
                {"kind": "phase", "id": "p1", "text": "deepseek · planning"},
                {
                    "kind": "assistant",
                    "id": "a1",
                    "text": "SECRET RESPONSE",
                    "reasoning": "SECRET REASONING",
                    "workDurationMs": 10_000,
                },
                {
                    "kind": "tool",
                    "id": "t1",
                    "name": "read_file",
                    "status": "done",
                    "durationMs": 100,
                },
                {
                    "kind": "assistant",
                    "id": "a2",
                    "text": "SECRET RESPONSE 2",
                    "workDurationMs": 20_000,
                },
                {
                    "kind": "tool",
                    "id": "t2",
                    "name": "bash",
                    "status": "error",
                    "durationMs": 200,
                    "summary": "SECRET ERROR",
                },
            ],
        },
    )


def _canonical_harness_log(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "generic-harness.json",
        {
            "schema": "novel-forge-runtime/v1",
            "session_id": "generic-writer-session-001",
            "scope": {"chapter_count": 1},
            "harness": {
                "name": "Acme Fiction Runner",
                "version": "7.2",
            },
            "model": {
                "provider": "acme-ai",
                "name": "Writer-Pro",
                "reasoning_effort": "high",
            },
            "timing": {"elapsed_seconds": 321.5},
            "usage": {
                "request_count": 12,
                "input_tokens": 12000,
                "output_tokens": 8000,
                "cached_input_tokens": 250000,
                "total_tokens": 270000,
                "max_request_context_tokens": 48000,
                "context_reset_count": 0,
            },
            "tools": {
                "call_count": 20,
                "failure_count": 2,
                "by_name": {"read": 8, "write": 2, "review": 10},
            },
            "content": "THIS FIELD MUST NEVER BE RETURNED",
        },
    )


def test_harness_contract_is_vendor_neutral_and_machine_readable():
    contract = harness_contract()

    assert contract["schema"] == "novel-forge-harness-contract/v1"
    assert contract["execution_modes"] == {
        "default": "skill_native",
        "skill_native": {
            "session_authority": "host_native_roles",
            "requires_command_environment": False,
            "fresh_role_session_required": True,
            "wait_for_role_completion_required": True,
            "deterministic_control_plane_only": True,
            "creative_roles_can_mutate_control_plane": False,
            "lead_can_author_role_artifacts": False,
        },
        "headless_command": {
            "optional": True,
            "environment_variable": "NOVEL_FORGE_HARNESS_COMMAND",
            "trusted_external_entry_required": True,
        },
    }
    assert contract["native_role_handoff"] == {
        "create_via_host_native_api": True,
        "wait_for_host_terminal_state": True,
        "accepted_or_progress_is_not_complete": True,
        "file_stability_is_not_complete": True,
        "returned_operation_handle_required": True,
        "role_name_is_not_operation_handle": True,
        "fixed_sleep_or_file_polling_forbidden": True,
        "default_terminal_wait_seconds": 1800,
        "working_status_must_continue_waiting": True,
        "host_session_identity_required": True,
        "late_result_after_retirement_is_invalid": True,
        "blind_reader_must_complete_before_chapter_editor": True,
        "context_isolation_is_not_filesystem_isolation": True,
    }
    assert contract["role_model_selection"] == {
        "workflow_binds_provider_or_model": False,
        "per_role_preference_allowed": True,
        "inherit_parent_model_allowed": True,
        "preference_is_not_provenance": True,
        "terminal_resolved_model_is_authoritative": True,
        "fallback_must_be_recorded_as_resolved": True,
    }
    assert contract["runtime_report_schema"]["const"] == (
        "novel-forge-runtime/v1"
    )
    assert contract["runtime_report_schema"]["scope"]["chapter_count"] == {
        "const": 1
    }
    assert contract["lifecycle"]["observe_after_each_model_response"] is True
    assert contract["lifecycle"]["stop_before_next_request_when_denied"] is True
    assert contract["lifecycle"]["next_chapter_requires_new_session"] is True
    assert contract["review_orchestration"] == {
        "auto_launch_after_surface_checked": True,
        "user_confirmation_required": False,
        "blind_reader_requires_new_native_session": True,
            "when_session_unavailable": "review_session_required",
            "open_ended_review_question_forbidden": True,
            "distinct_session_instance_required": True,
        }
    assert contract["chapter_sequence"]["default_chapter_count"] == 1
    assert contract["chapter_sequence"]["maximum_chapter_count"] == 4
    assert (
        contract["chapter_sequence"]["previous_chapter_must_be_ready"]
        is True
    )
    assert contract["limits_per_chapter"]["request_count"] == 30
    assert (
        contract["limits_per_chapter"]["cached_input_tokens_interpretation"]
        == "hard_ceiling_not_target"
    )
    assert contract["local_git_policy"] == {
        "mode": "per_book_external_gitdir",
        "metadata_directory": ".local-book-git/<slug>.git",
        "remote_allowed": False,
        "automatic_checkpoints": [
            "generation_bound_draft",
            "chapter_ready",
        ],
        "checkpoint_interval": 5,
        "authority": "recovery_not_approval",
    }
    assert contract["adapter_operations"]["audit_snapshot"].startswith(
        "session-audit "
    )
    assert contract["adapter_operations"]["begin_sequence"].startswith(
        "begin-chapter-sequence "
    )
    assert contract["guardian"] == {
        "contract_operation": "guardian-contract",
        "formal_writer_workspace": "isolated_writer_capsule",
        "prepare_operation": "prepare-writer-capsule",
        "ingest_operation": "ingest-writer-capsule",
        "runtime_operation": "record-capsule-runtime",
        "authorization_operation": "authorize-regeneration",
        "invalidate_operation": "invalidate-chapter-session",
        "prompt_template_id": "formal-writer/v1",
        "prompt_file": "instructions.md",
        "prompt_max_characters": 1200,
        "book_control_plane_visible_to_writer": False,
        "validator_source_visible_to_writer": False,
        "full_transcript_required": False,
        "acp_required": False,
    }
    serialized = json.dumps(contract, ensure_ascii=False).lower()
    for vendor in ("minimax", "reasonix", "claude", "deepseek"):
        assert vendor not in serialized


def test_audit_accepts_vendor_neutral_runtime_contract(tmp_path: Path):
    report = audit_session_log(_canonical_harness_log(tmp_path))

    assert report["source_format"] == "novel-forge-runtime-v1"
    assert report["session_id"] == "generic-writer-session-001"
    assert report["scope_chapter_count"] == 1
    assert report["agent_harness"] == "Acme Fiction Runner/7.2"
    assert report["provider"] == "acme-ai"
    assert report["model"] == "Writer-Pro"
    assert report["reasoning_effort"] == "high"
    assert report["request_count"] == 12
    assert report["tokens"]["cached_input"] == 250000
    assert report["tool_calls"]["failed"] == 2
    assert "THIS FIELD" not in json.dumps(report, ensure_ascii=False)


def test_canonical_scope_controls_budget_instead_of_existing_book_size(
    tmp_path: Path,
):
    book_dir = tmp_path / "books" / "demo"
    for number in range(1, 6):
        chapter = (
            book_dir
            / "chapters"
            / "e01"
            / f"ch-{number:02d}"
            / "正文.md"
        )
        chapter.parent.mkdir(parents=True, exist_ok=True)
        chapter.write_text("正文。\n", encoding="utf-8")
    log = _canonical_harness_log(tmp_path)
    payload = json.loads(log.read_text(encoding="utf-8"))
    payload["usage"]["request_count"] = 31
    _write_json(log, payload)

    _, report = audit_book_session(tmp_path, "demo", log)

    assert report["budget"]["chapter_count"] == 1
    assert report["budget"]["continue_allowed"] is False
    assert report["budget"]["findings"] == [
        {
            "code": "session-request-budget",
            "actual": 31,
            "limit": 30,
        }
    ]


def test_canonical_formal_snapshot_rejects_multi_chapter_session(
    tmp_path: Path,
):
    log = _canonical_harness_log(tmp_path)
    payload = json.loads(log.read_text(encoding="utf-8"))
    payload["scope"]["chapter_count"] = 5
    _write_json(log, payload)

    with pytest.raises(SessionAuditError, match="每章独立"):
        audit_session_log(log)


def test_audit_minimax_pi_export_extracts_metrics_without_content(
    tmp_path: Path,
):
    report = audit_session_log(_minimax_log(tmp_path))

    assert report["source_format"] == "minimax-code"
    assert report["session_id"] == "mvs-test-session"
    assert report["agent_harness"] == "pi-agent/mavis"
    assert report["provider"] == "minimax"
    assert report["model"] == "MiniMax-M3"
    assert report["reasoning_effort"] == "high"
    assert report["request_count"] == 3
    assert report["tokens"] == {
        "input": 3_300,
        "output": 1_300,
        "cached_input": 325_400,
        "total": 330_000,
    }
    assert report["max_context_tokens"] == 160_000
    assert report["context_reset_count"] == 1
    assert report["tool_calls"]["total"] == 2
    assert report["tool_calls"]["failed"] == 1
    assert report["tool_calls"]["by_name"] == {"bash": 1, "edit": 1}
    serialized = json.dumps(report, ensure_ascii=False)
    assert "SECRET" not in serialized
    assert "thinking_content" not in serialized
    assert "msg_content" not in serialized


def test_audit_reasonix_export_extracts_harness_and_failures(tmp_path: Path):
    report = audit_session_log(_reasonix_log(tmp_path))

    assert report["source_format"] == "reasonix"
    assert report["session_id"] == "run-reasonix-001"
    assert report["agent_harness"] == "reasonix-autoresearch"
    assert report["provider"] == "deepseek"
    assert report["model"] == "unknown"
    assert report["request_count"] == 2
    assert report["tokens"]["total"] is None
    assert report["elapsed_seconds"] == 20.0
    assert report["tool_calls"]["failed"] == 1
    assert report["tool_calls"]["by_name"] == {"bash": 1, "read_file": 1}
    assert "SECRET" not in json.dumps(report, ensure_ascii=False)


def test_session_budget_is_external_and_blocks_runaway_context():
    report = {
        "request_count": 199,
        "tokens": {"cached_input": 42_432_000},
        "max_context_tokens": 375_300,
    }

    budget = evaluate_session_budget(report, chapter_count=5)

    assert budget["status"] == "exceeded"
    assert budget["continue_allowed"] is False
    assert {item["code"] for item in budget["findings"]} == {
        "session-request-budget",
        "session-cached-context-budget",
        "request-context-window",
    }


def test_provenance_comparison_detects_false_generation_metadata():
    audit = {
        "session_id": "mvs-real",
        "provider": "minimax",
        "model": "MiniMax-M3",
        "agent_harness": "pi-agent/mavis",
        "reasoning_effort": "high",
        "tool_calls": {"failed": 3},
    }
    generation = {
        "id": "generation.ch01",
        "run_id": "unknown",
        "provider": "anthropic",
        "model": "claude-sonnet-4",
        "agent_harness": "unknown",
        "reasoning_effort": "standard",
        "tool_failures": [],
    }

    mismatches = compare_generation_provenance(generation, audit)

    assert {item["field"] for item in mismatches} == {
        "run_id",
        "provider",
        "model",
        "agent_harness",
        "reasoning_effort",
        "tool_failures",
    }


def test_provenance_comparison_does_not_invent_unknown_observations():
    mismatches = compare_generation_provenance(
        {
            "run_id": "reasonix-run",
            "provider": "deepseek",
            "model": "DeepSeek-V4-Pro",
            "agent_harness": "reasonix-autoresearch",
            "reasoning_effort": "max",
            "tool_failures": [],
        },
        {
            "session_id": "reasonix-run",
            "provider": "deepseek",
            "model": "unknown",
            "agent_harness": "reasonix-autoresearch",
            "reasoning_effort": "unknown",
            "tool_calls": {"failed": 0},
        },
    )

    assert mismatches == []


def test_runtime_audit_record_is_sanitized_immutable_and_findable(
    tmp_path: Path,
):
    book_dir = tmp_path / "books" / "demo"
    book_dir.mkdir(parents=True)
    report = audit_session_log(_minimax_log(tmp_path))
    report["budget"] = evaluate_session_budget(report, chapter_count=1)
    report["provenance_mismatches"] = []

    stored = record_runtime_audit(book_dir, report)
    loaded = find_runtime_audit(book_dir, "mvs-test-session")

    assert stored["runtime_audit_id"] == loaded["runtime_audit_id"]
    assert loaded["continue_allowed"] is False
    assert "SECRET" not in json.dumps(loaded, ensure_ascii=False)
    with pytest.raises(SessionAuditError, match="不得覆盖"):
        record_runtime_audit(
            book_dir,
            {**report, "request_count": report["request_count"] + 1},
        )
