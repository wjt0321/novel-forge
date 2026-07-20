"""Pure vendor-neutral contract data for isolated writer capsules."""

from __future__ import annotations

from typing import Any

from .session_audit import RUNTIME_REPORT_SCHEMA
from .writer_prompt import (
    FORMAL_WRITER_PROMPT_ID,
    MAX_FORMAL_WRITER_PROMPT_CHARS,
)


GUARDIAN_CONTRACT_SCHEMA = "novel-forge-guardian-contract/v1"


def guardian_contract() -> dict[str, Any]:
    """Return the provider-neutral isolated writer workspace contract."""
    return {
        "schema": GUARDIAN_CONTRACT_SCHEMA,
        "purpose": (
            "Keep prose generation outside the book control plane and import "
            "only a bounded draft plus a compact runtime snapshot."
        ),
        "workspace": {
            "mode": "isolated_writer_capsule",
            "must_be_outside_repository": True,
            "filesystem_sandbox_required": True,
            "book_control_plane_visible": False,
            "validator_source_visible": False,
            "other_chapters_visible": False,
            "network_policy": "owned_by_external_harness",
        },
        "inputs": {
            "allowed": [
                "capsule.json",
                "guardian-contract.json",
                "instructions.md",
                "handoff.md",
                "draft/正文.md for a bounded patch capsule",
            ],
            "handoff_is_bounded": True,
            "patch_capsule_seeds_current_draft": True,
            "full_project_context_forbidden": True,
            "old_session_context_forbidden": True,
        },
        "prompt": {
            "template_id": FORMAL_WRITER_PROMPT_ID,
            "compiled_file": "instructions.md",
            "max_characters": MAX_FORMAL_WRITER_PROMPT_CHARS,
            "protected_input": True,
            "full_skill_reinjection": False,
        },
        "outputs": {
            "allowed": [
                "draft/正文.md",
            ],
            "unexpected_file_result": "compromised",
            "path_escape_result": "compromised",
            "control_plane_mutation_result": "compromised",
        },
        "runtime": {
            "schema": RUNTIME_REPORT_SCHEMA,
            "mode": "cumulative_compact_snapshot",
            "written_by": "external_harness",
            "writer_may_write_runtime_snapshot": False,
            "record_operation": "record-capsule-runtime",
            "stored_in_external_guardian_sidecar": True,
            "full_transcript_required": False,
            "prompt_or_prose_in_snapshot_forbidden": True,
            "complete_budget_observation_required": True,
            "isolation_attestation": {
                "reported_by": {"const": "external_harness"},
                "capsule_id": "must_match_prepared_capsule",
                "workspace_mode": {"const": "isolated_writer_capsule"},
                "filesystem_scope": {"const": "capsule_only"},
                "book_control_plane_visible": {"const": False},
                "validator_source_visible": {"const": False},
            },
        },
        "session": {
            "one_native_writer_session_per_chapter": True,
            "one_initial_draft_plus_one_bounded_patch_supported": True,
            "third_body_requires_prior_human_authorization": True,
            "authorization_operation": "authorize-regeneration",
            "authorization_is_signed_and_chapter_bound": True,
            "compromised_session_must_be_invalidated": True,
            "same_session_retry_forbidden": True,
        },
        "token_policy": {
            "guardian_checks_use_model_context": False,
            "full_transcript_reinjection": False,
            "bounded_handoff_only": True,
            "savings_may_weaken_integrity_gates": False,
        },
        "authority": {
            "writer_may_write_book_control_plane": False,
            "writer_may_create_evidence": False,
            "writer_may_advance_state": False,
            "guardian_import_receipt_required_for_formal_agent_ready": True,
            "receipt_hmac_and_external_ledger_required": True,
        },
    }
