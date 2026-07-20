"""Skill-first JSON adapter for Novel Forge.

This module provides a restricted, JSON-only CLI surface for automation
(Skills, scripts, orchestrators). It forwards to NovelForgeService and never
exposes full Markdown bodies or raw SQLite access.

Usage:
    PYTHONPATH=. python -m app.novel_forge.skill_adapter --root <path> <operation> ...
"""

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from app.novel_forge.autonomous import AutonomousError, AutonomousWritingService
from app.novel_forge import book_project
from app.novel_forge.chapter_sequence import (
    advance_chapter_sequence,
    begin_chapter_sequence,
    chapter_sequence_status,
    claim_chapter_session,
    invalidate_chapter_session,
)
from app.novel_forge.book_evidence import evidence_status, record_evidence
from app.novel_forge.book_git import (
    book_git_status,
    checkpoint_book,
    initialize_book_git,
    restore_book_worktree,
)
from app.novel_forge.book_memory import (
    build_context_packet,
    memory_status,
    promote_candidate,
    rebuild_memory_index,
    record_candidate,
)
from app.novel_forge.models import ReviewFinding, ScenePlan
from app.novel_forge.guardian import (
    authorize_regeneration,
    guardian_contract,
    ingest_writer_capsule,
    prepare_writer_capsule,
    record_capsule_runtime,
)
from app.novel_forge.session_audit import (
    audit_book_session,
    harness_contract,
    record_runtime_audit,
)
from app.novel_forge.service import NovelForgeError, NovelForgeService


# Operations that mutate data or produce external artifacts. They require
# an explicit `--confirm <operation-name>` guard.
MUTATING_OPS = {
    "init-book",
    "init-novel-project",
    "create-chapter",
    "write-revision",
    "add-finding",
    "resolve-finding",
    "add-candidate-fact",
    "approve-fact",
    "reject-fact",
    "approve-chapter",
    "rollback-chapter",
    "export-book",
    "write-voice-bible",
    "write-scene-contract",
    "add-reader-review",
    "resolve-reader-review",
    "build-drafting-packet",
    "submit-editorial-memo",
    "build-blind-reader-packet",
    "submit-blind-experience-review",
    "add-research-entry",
    "update-research-entry",
    "set-story-engine",
    "set-chapter-plan",
    "update-promise",
    "set-promise-target",
    "record-iteration",
    "git-checkpoint",
    "init-workspace",
    "refresh-workspace",
    "write-revision-patch",
    "record-review",
    "advance-state",
    "sync-tools",
    "record-memory-candidate",
    "promote-memory-candidate",
    "rebuild-memory-index",
    "build-memory-context",
    "record-evidence",
    "set-draft-mode",
    "record-session-audit",
    "begin-chapter-sequence",
    "claim-chapter-session",
    "advance-chapter-sequence",
    "invalidate-chapter-session",
    "authorize-regeneration",
    "prepare-writer-capsule",
    "record-capsule-runtime",
    "ingest-writer-capsule",
    "init-book-git",
    "book-git-checkpoint",
    "restore-book-git",
}


class _ArgparseAdapterError(Exception):
    """Raised when argparse encounters a usage error; converted to JSON."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _is_valid_slug(slug: str) -> bool:
    return bool(slug) and slug.replace("-", "").replace("_", "").isalnum()


def _validate_slug(slug: str) -> None:
    if not _is_valid_slug(slug):
        raise NovelForgeError(
            f"Invalid book slug: {slug!r}. Use alphanumeric, dash, or underscore."
        )


def _print_json(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def _ok(operation: str, data: dict, state_changed: bool = False) -> int:
    _print_json({"ok": True, "operation": operation, "state_changed": state_changed, "data": data})
    return 0


def _fail(code: str, message: str) -> int:
    _print_json({"ok": False, "error": {"code": code, "message": message}})
    return 0


def _argparse_error(message: str) -> None:
    raise _ArgparseAdapterError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel-forge-skill",
        description="Skill-first JSON adapter for Novel Forge.",
    )
    parser.error = _argparse_error
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Project root directory (must be an absolute, resolved path).",
    )
    parser.add_argument(
        "--confirm",
        default=None,
        help="Confirm a mutating operation by repeating its exact name.",
    )

    sub = parser.add_subparsers(dest="operation", required=True)

    # Read-only / diagnostic
    sub.add_parser("status", help="Show book or chapter status.")
    sub.add_parser(
        "harness-contract",
        help="Return the vendor-neutral runtime contract for any Agent harness.",
    )
    sub.add_parser(
        "guardian-contract",
        help="Return the vendor-neutral isolated writer capsule contract.",
    )

    p = sub.add_parser("lint", help="Run prose lint on the current revision.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    p = sub.add_parser("review", help="Review a chapter and produce a verdict.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    # Book / chapter lifecycle
    p = sub.add_parser("init-book", help="Initialize a new book.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--title", required=True, help="Book title.")

    p = sub.add_parser(
        "init-novel-project",
        help="Create the recommended books/<slug>/ project layout.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--title", required=True, help="Book title.")
    p.add_argument("--genre", required=True, help="Book genre.")

    p = sub.add_parser("create-chapter", help="Create a new chapter.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--title", required=True, help="Chapter title.")

    p = sub.add_parser("write-revision", help="Write a new revision from a Markdown file.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--from-file", required=True, type=Path, help="Source Markdown file (absolute path).")
    p.add_argument("--note", default=None, help="Revision note.")
    p.add_argument("--reopen-reason", default=None, help="Reason for reopening an approved chapter.")

    # Findings
    p = sub.add_parser("add-finding", help="Add a review finding.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--perspective", required=True, choices=["structure", "character", "narrative", "continuity"])
    p.add_argument("--severity", required=True, choices=["S1", "S2", "S3", "S4"])
    p.add_argument("--location", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--issue", required=True)
    p.add_argument("--fix", required=True)

    p = sub.add_parser("resolve-finding", help="Resolve a review finding.")
    p.add_argument("finding_id", type=int)
    p.add_argument("--note", required=True)

    # Facts
    p = sub.add_parser("add-candidate-fact", help="Add a candidate fact.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--kind", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--predicate", required=True)
    p.add_argument("--object", required=True)
    p.add_argument("--evidence", required=True)

    p = sub.add_parser("approve-fact", help="Approve a candidate fact into canon.")
    p.add_argument("candidate_id", type=int)
    p.add_argument("--note", default=None)

    p = sub.add_parser("reject-fact", help="Reject a candidate fact.")
    p.add_argument("candidate_id", type=int)
    p.add_argument("--note", default=None)

    # Approval
    p = sub.add_parser("approve-chapter", help="Approve a chapter.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int)
    p.add_argument("--note", required=True)

    p = sub.add_parser("rollback-chapter", help="Rollback to a previous revision.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int)
    p.add_argument("revision_id", type=int)
    p.add_argument("--note", required=True)

    p = sub.add_parser("export-book", help="Export approved chapters.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--format", required=True, choices=["markdown", "docx", "epub", "pdf"])

    # Audit
    p = sub.add_parser("audit", help="Show audit log.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--limit", type=int, default=None)

    # Voice Bible
    p = sub.add_parser("voice-bible-status", help="Show voice bible metadata.")
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser("write-voice-bible", help="Write a new voice bible revision.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--from-file", required=True, type=Path, help="Source Markdown file (absolute path).")
    p.add_argument("--note", default=None, help="Revision note.")

    # Scene Contract v2
    p = sub.add_parser("scene-contract-status", help="Show scene contract metadata.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    p = sub.add_parser("write-scene-contract", help="Write a new scene contract revision.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--from-file", required=True, type=Path, help="Source Markdown file (absolute path).")
    p.add_argument("--note", default=None, help="Revision note.")

    # Reader Reviews
    p = sub.add_parser("add-reader-review", help="Add a reader review.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--lens",
        required=True,
        choices=[
            "immersion",
            "causality",
            "character_truth",
            "tension",
            "language",
            "continuity",
        ],
    )
    p.add_argument("--severity", required=True, choices=["S1", "S2", "S3", "S4"])
    p.add_argument("--location-start", required=True, type=int)
    p.add_argument("--location-end", required=True, type=int)
    p.add_argument("--evidence", required=True)
    p.add_argument("--reader-effect", required=True)
    p.add_argument("--revision-intent", required=True)
    p.add_argument("--actor", default="human_or_agent_review")

    p = sub.add_parser("resolve-reader-review", help="Resolve a reader review.")
    p.add_argument("review_id", type=int)
    p.add_argument("--note", required=True)

    p = sub.add_parser(
        "submit-editorial-memo",
        help="Submit a narrative editorial memo for the current revision.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--memo-file",
        required=True,
        type=Path,
        help="Absolute path to a UTF-8 JSON file containing the memo.",
    )

    p = sub.add_parser(
        "editorial-memo-status", help="Get metadata-only status of the active editorial memo."
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    p = sub.add_parser("build-drafting-packet", help="Build an external drafting packet.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--output-file", required=True, type=Path, help="Absolute output Markdown file.")
    p.add_argument("--note", default=None, help="Optional note.")
    p.add_argument(
        "--previous-context-chars",
        type=int,
        default=1200,
        help="Characters from the approved previous chapter (0-4000).",
    )
    p.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Bypass the drafting readiness gate (requires explicit user authorization).",
    )

    p = sub.add_parser("drafting-readiness", help="Assess drafting readiness for a chapter.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    # Autonomous research-to-fiction workflow (v4)
    p = sub.add_parser("add-research-entry", help="Add a research ledger entry.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--url", required=True)
    p.add_argument("--retrieved-at", required=True)
    p.add_argument(
        "--source-type", required=True, choices=["official", "academic", "news", "other"]
    )
    p.add_argument("--confidence", required=True, choices=["A", "B", "C"])
    p.add_argument("--claim", required=True)
    p.add_argument(
        "--allowed-use",
        required=True,
        choices=["plot_support", "background_only", "fiction_seed"],
    )
    p.add_argument("--fiction-boundary", required=True)
    p.add_argument(
        "--verification-state",
        default="collected",
        choices=["collected", "verified", "unresolved"],
    )
    p.add_argument(
        "--verification-ref",
        type=int,
        default=None,
        help="ID of a verified A-level plot_support entry that corroborates this claim.",
    )
    p.add_argument("--unresolved", action="store_true")
    p.add_argument("--notes", default=None)

    p = sub.add_parser("update-research-entry", help="Update a research entry's verification.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("entry_id", type=int, help="Research entry ID.")
    p.add_argument(
        "--verification-state",
        choices=["collected", "verified", "unresolved"],
    )
    p.add_argument(
        "--verification-ref",
        type=int,
        default=None,
        help="ID of a verified A-level plot_support entry that corroborates this claim.",
    )

    p = sub.add_parser("list-research", help="List research entries for a book.")
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser("set-story-engine", help="Set the book-level story engine.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--secret", required=True)
    p.add_argument("--desire", required=True)
    p.add_argument(
        "--alternative-actions", required=True, nargs="+", help="One or more alternatives."
    )
    p.add_argument("--irreversible-choice", required=True)
    p.add_argument("--immediate-cost", required=True)
    p.add_argument("--thematic-pressure", required=True)

    p = sub.add_parser("get-story-engine", help="Get the book-level story engine.")
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser("set-chapter-plan", help="Set a chapter plan from a JSON file.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--plan-file", required=True, type=Path, help="Absolute path to scene plan JSON."
    )
    p.add_argument(
        "--status", default="draft", choices=["draft", "approved_for_writing"]
    )

    p = sub.add_parser("get-chapter-plan", help="Get a chapter plan.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    p = sub.add_parser("update-promise", help="Update promise ledger status.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("promise_id", type=int, help="Promise ID.")
    p.add_argument(
        "--status",
        required=True,
        choices=["planted", "partially_paid", "paid_off", "abandoned"],
    )
    p.add_argument("--scene-ref", required=True)
    p.add_argument("--note", default=None)

    p = sub.add_parser("set-promise-target", help="Set or clear a promise payoff target.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("promise_id", type=int, help="Promise ID.")
    p.add_argument("--target-chapter-number", type=int, default=None)
    p.add_argument("--target-scene-ref", default=None)
    p.add_argument(
        "--clear", action="store_true", help="Clear the target chapter and scene."
    )

    p = sub.add_parser("list-promises", help="List promises for a book.")
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser("record-iteration", help="Record an iteration run.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--writer-role", required=True)
    p.add_argument(
        "--editor-verdict",
        required=True,
        choices=["revision_required", "ready_for_human_editor_decision"],
    )
    p.add_argument(
        "--blocking-issues-file",
        required=True,
        type=Path,
        help="Absolute path to JSON array of blocking issues.",
    )
    p.add_argument("--revision-targets", required=True, nargs="+")
    p.add_argument("--word-count", required=True, type=int)
    p.add_argument(
        "--status", default="completed", choices=["running", "completed", "failed"]
    )

    p = sub.add_parser("list-iterations", help="List iteration runs for a chapter.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    p = sub.add_parser("check-acceptance", help="Check auto-acceptance gate.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--max-rounds", type=int, default=3)

    p = sub.add_parser("git-checkpoint", help="Create a scoped git checkpoint.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--message", required=True)

    p = sub.add_parser(
        "init-workspace", help="Create the human-readable work directory for a book."
    )
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser(
        "refresh-workspace", help="Refresh read-only mirrors in the work directory."
    )
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser(
        "write-revision-patch",
        help="Write a new revision by applying a JSON patch to the current revision.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--patch-file",
        required=True,
        type=Path,
        help="Absolute path to a UTF-8 JSON patch file.",
    )
    p.add_argument("--note", default=None, help="Revision note.")
    p.add_argument(
        "--reopen-reason", default=None, help="Reason for reopening an approved chapter."
    )
    p.add_argument(
        "--allow-below-minimum",
        action="store_true",
        help=(
            "Allow the patched revision to remain below 5000 CJK characters. "
            "For exploratory drafts only; formal short stories must meet 5000."
        ),
    )

    p = sub.add_parser(
        "build-blind-reader-packet",
        help="Build a prose-only packet for an isolated blind reader.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--output-file", required=True, type=Path)

    p = sub.add_parser(
        "submit-blind-experience-review",
        help="Submit a prose-only blind reader reconstruction report.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--report-file", required=True, type=Path)

    p = sub.add_parser(
        "blind-experience-status",
        help="Show Blind Experience Gate status for the current revision.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    # books/<slug>/ front-of-house workflow ops (filesystem-only, no DB)
    p = sub.add_parser(
        "project-status",
        help="Show books/<slug>/ project progress, chapter states and review verdicts.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, nargs="?", default=None, help="Chapter number.")

    p = sub.add_parser(
        "book-git-status",
        help="Show metadata-only status for a book's local Git history.",
    )
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser(
        "init-book-git",
        help="Initialize isolated local-only Git history for an existing book.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--title", required=True, help="Book title for the initial commit.")

    p = sub.add_parser(
        "book-git-checkpoint",
        help="Create an explicit checkpoint in a book's local Git history.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--message", required=True, help="Checkpoint commit message.")
    p.add_argument(
        "--tag",
        default=None,
        help="Optional immutable tag such as checkpoint/ch01-ch05.",
    )

    p = sub.add_parser(
        "restore-book-git",
        help="Restore a missing book worktree from its external local Git history.",
    )
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser(
        "begin-chapter-sequence",
        help=(
            "Create a one-to-four chapter sequence and issue the first "
            "fresh-session launch directive."
        ),
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--start-chapter", required=True, type=int)
    p.add_argument("--chapter-count", type=int, default=1)
    p.add_argument("--sequence-id", default=None)
    p.add_argument("--orchestrator-run-id", default=None)

    p = sub.add_parser(
        "claim-chapter-session",
        help="Bind the current chapter to a real native writer session ID.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("sequence_id", help="Chapter sequence ID.")
    p.add_argument("--session-id", required=True)

    p = sub.add_parser(
        "advance-chapter-sequence",
        help=(
            "Verify the current chapter is ready and issue the next "
            "fresh-session launch directive."
        ),
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("sequence_id", help="Chapter sequence ID.")
    p.add_argument("--session-id", required=True)

    p = sub.add_parser(
        "invalidate-chapter-session",
        help="Invalidate a compromised writer session and require a fresh claim.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("sequence_id", help="Chapter sequence ID.")
    p.add_argument("--session-id", required=True)
    p.add_argument("--reason", required=True)

    p = sub.add_parser(
        "authorize-regeneration",
        help=(
            "Record one signed human authorization for a third distinct body."
        ),
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("sequence_id", help="Chapter sequence ID.")
    p.add_argument("--session-id", required=True)
    p.add_argument(
        "--authority",
        required=True,
        choices=["author", "human_delegate"],
    )
    p.add_argument("--decision-reference", required=True)

    p = sub.add_parser(
        "prepare-writer-capsule",
        help="Create a repository-external isolated workspace for one writer.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("sequence_id", help="Chapter sequence ID.")
    p.add_argument("--session-id", required=True)
    p.add_argument("--capsule-dir", required=True, type=Path)
    p.add_argument("--target-path", required=True)
    p.add_argument("--regeneration-authorization-id", default=None)

    p = sub.add_parser(
        "record-capsule-runtime",
        help="Store a Harness-owned runtime sidecar outside the book workspace.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("capsule_id", help="Writer capsule ID.")
    p.add_argument("--file", required=True, type=Path)

    p = sub.add_parser(
        "ingest-writer-capsule",
        help="Import one isolated draft and record a Guardian receipt.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("capsule_id", help="Writer capsule ID.")

    p = sub.add_parser(
        "chapter-sequence-status",
        help="Show chapter sequence metadata without returning handoff prose.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("sequence_id", help="Chapter sequence ID.")

    p = sub.add_parser(
        "run-gates",
        help="Run quality_check + narrative gate on a books/ chapter; JSON findings only.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--mode",
        choices=("formal", "exploration"),
        default=None,
        help="Assert the persisted chapter mode; never overrides chapter-state.",
    )

    p = sub.add_parser(
        "set-draft-mode",
        help="Persist a books/ chapter mode and invalidate mode-bound evidence.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--mode", required=True, choices=("formal", "exploration")
    )

    p = sub.add_parser(
        "record-review",
        help="Validate and store a review file under books/<slug>/reviews/.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--role", required=True, help="Review role (causal-editor, line-editor, consistency-guard, blind-reader, chapter-editor).")
    p.add_argument("--file", required=True, type=Path, help="Absolute path to the review Markdown file.")

    p = sub.add_parser(
        "advance-state",
        help="Advance a books/ chapter's state machine position.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--to", required=True, help="Target state.")
    p.add_argument("--evidence", default=None, help="Evidence pointer (file ref or command result).")
    p.add_argument("--next-action", default=None, help="Next action note.")

    p = sub.add_parser(
        "sync-tools",
        help="Refresh a books/ project's managed tool/agent/template files from the current templates.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--dry-run", action="store_true", help="Only report what would change.")

    p = sub.add_parser(
        "memory-status",
        help="Show whether a books/ project's derived memory index matches Markdown.",
    )
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser(
        "record-memory-candidate",
        help="Validate and store a Markdown memory candidate without promoting it.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--file", required=True, type=Path, help="Absolute UTF-8 Markdown file.")

    p = sub.add_parser(
        "promote-memory-candidate",
        help="Promote a candidate into canonical Markdown and rebuild the index.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("candidate_id", help="Candidate memory record ID.")

    p = sub.add_parser(
        "rebuild-memory-index",
        help="Rebuild the disposable per-book SQLite memory index from Markdown.",
    )
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser(
        "build-memory-context",
        help="Build a chapter-scoped context cache from a clean memory index.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("chapter", type=int, help="Target chapter number.")

    p = sub.add_parser(
        "evidence-status",
        help="Show creative evidence inventory without returning record bodies.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument(
        "chapter", type=int, nargs="?", default=None, help="Optional chapter number."
    )

    p = sub.add_parser(
        "session-audit",
        help="Audit a standard runtime snapshot or compatibility export.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Absolute path to the UTF-8 session JSON export.",
    )

    p = sub.add_parser(
        "record-session-audit",
        help="Store a sanitized immutable runtime audit for ready-state verification.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Absolute path to the UTF-8 session JSON export.",
    )

    p = sub.add_parser(
        "record-evidence",
        help="Validate and store one Markdown creative evidence record.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--file", required=True, type=Path, help="Absolute UTF-8 Markdown file.")

    # Status: book or chapter. Use positional slug and optional number.
    # argparse does not easily support optional positional after required ones,
    # so we parse remaining args manually in run().
    return parser


def _check_confirm(args: argparse.Namespace) -> bool:
    op = args.operation
    if op not in MUTATING_OPS:
        return True
    # A dry run never writes, so it needs no confirmation.
    if op == "sync-tools" and getattr(args, "dry_run", False):
        return True
    if args.confirm == op:
        return True
    return False


def _validate_from_file(root: Path, from_file: Path) -> Path:
    if not from_file.is_absolute():
        raise NovelForgeError("--from-file must be an absolute path.")
    resolved = from_file.resolve()
    if not resolved.exists():
        raise NovelForgeError(f"Source file not found: {from_file}")
    # Enforce UTF-8 (with optional BOM) before any revision is created.
    try:
        resolved.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NovelForgeError(
            f"Source file is not valid UTF-8: {from_file} ({exc})"
        )
    library_root = (root / "library").resolve()
    try:
        resolved.relative_to(library_root)
        is_inside = True
    except ValueError:
        is_inside = False
    if is_inside:
        raise NovelForgeError(
            "--from-file must not be inside the project library directory."
        )
    return resolved


def _validate_output_file(root: Path, output_file: Path) -> Path:
    if not output_file.is_absolute():
        raise NovelForgeError("--output-file must be an absolute path.")
    resolved = output_file.resolve()
    if resolved.exists():
        raise NovelForgeError(f"--output-file already exists: {output_file}")
    library_root = (root / "library").resolve()
    try:
        resolved.relative_to(library_root)
        is_inside = True
    except ValueError:
        is_inside = False
    if is_inside:
        raise NovelForgeError(
            "--output-file must not be inside the project library directory."
        )
    return resolved


_REQUIRED_MEMO_FIELDS = {
    "narrative_necessity",
    "character_agency",
    "detail_selection",
    "causal_chain",
    "prose_observation",
    "verdict",
    "blocking_issues",
}


def _validate_memo_file(root: Path, memo_file: Path) -> dict:
    if not memo_file.is_absolute():
        raise NovelForgeError("--memo-file must be an absolute path.")
    resolved = memo_file.resolve()
    if not resolved.exists():
        raise NovelForgeError(f"Memo file not found: {memo_file}")
    try:
        raw_bytes = resolved.read_bytes()
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NovelForgeError(f"Memo file is not valid UTF-8: {memo_file} ({exc})")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NovelForgeError(f"Memo file is not valid JSON: {memo_file} ({exc})")
    if not isinstance(data, dict):
        raise NovelForgeError("Memo file must contain a JSON object.")

    reviewer_role = data.get("reviewer_role", "independent_reader_editor")
    if reviewer_role != "independent_reader_editor":
        raise NovelForgeError(
            f"Invalid reviewer_role: {reviewer_role!r}. "
            "Only 'independent_reader_editor' is allowed."
        )
    data["reviewer_role"] = reviewer_role

    missing = _REQUIRED_MEMO_FIELDS - set(data.keys())
    if missing:
        raise NovelForgeError(
            f"Memo file is missing required fields: {', '.join(sorted(missing))}"
        )

    verdict = data.get("verdict")
    if verdict not in {"ready_for_editor_decision", "revision_required"}:
        raise NovelForgeError(
            f"Memo verdict must be 'ready_for_editor_decision' or 'revision_required', got {verdict!r}"
        )

    issues = data.get("blocking_issues")
    if not isinstance(issues, list):
        raise NovelForgeError("Memo 'blocking_issues' must be a JSON array.")
    for idx, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise NovelForgeError(
                f"Blocking issue at index {idx} must be an object."
            )
        for required in ("location", "evidence", "effect", "revision_intent"):
            if not issue.get(required):
                raise NovelForgeError(
                    f"Blocking issue at index {idx} is missing '{required}'."
                )

    library_root = (root / "library").resolve()
    try:
        resolved.relative_to(library_root)
        is_inside = True
    except ValueError:
        is_inside = False
    if is_inside:
        raise NovelForgeError(
            "--memo-file must not be inside the project library directory."
        )

    return data


def _validate_json_file(root: Path, file_path: Path) -> Any:
    """Validate an absolute, external, UTF-8 JSON file and return parsed data."""
    if not file_path.is_absolute():
        raise NovelForgeError("JSON file path must be absolute.")
    resolved = file_path.resolve()
    if not resolved.exists():
        raise NovelForgeError(f"JSON file not found: {file_path}")
    try:
        raw_bytes = resolved.read_bytes()
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NovelForgeError(f"JSON file is not valid UTF-8: {file_path} ({exc})")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NovelForgeError(f"JSON file is not valid JSON: {file_path} ({exc})")

    library_root = (root / "library").resolve()
    try:
        resolved.relative_to(library_root)
        is_inside = True
    except ValueError:
        is_inside = False
    if is_inside:
        raise NovelForgeError("JSON file must not be inside the project library directory.")
    return data


def _validate_patch_file(root: Path, patch_file: Path) -> Path:
    """Validate a JSON patch file: absolute, UTF-8, outside library, exists."""
    if not patch_file.is_absolute():
        raise NovelForgeError("--patch-file must be an absolute path.")
    resolved = patch_file.resolve()
    if not resolved.exists():
        raise NovelForgeError(f"Patch file not found: {patch_file}")
    try:
        resolved.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NovelForgeError(
            f"Patch file is not valid UTF-8: {patch_file} ({exc})"
        )
    library_root = (root / "library").resolve()
    try:
        resolved.relative_to(library_root)
        is_inside = True
    except ValueError:
        is_inside = False
    if is_inside:
        raise NovelForgeError(
            "--patch-file must not be inside the project library directory."
        )
    return resolved


def _validate_plan_file(root: Path, plan_file: Path) -> list[ScenePlan]:
    data = _validate_json_file(root, plan_file)
    if not isinstance(data, list):
        raise NovelForgeError("Plan file must contain a JSON array of scenes.")
    try:
        return [ScenePlan.model_validate(s) for s in data]
    except Exception as exc:
        raise NovelForgeError(f"Invalid scene plan: {exc}")


def _validate_blocking_issues_file(root: Path, path: Path) -> list[dict[str, Any]]:
    data = _validate_json_file(root, path)
    if not isinstance(data, list):
        raise NovelForgeError("Blocking issues must be a JSON array.")
    for idx, issue in enumerate(data):
        if not isinstance(issue, dict):
            raise NovelForgeError(f"Blocking issue at index {idx} must be an object.")
        for required in ("location", "evidence", "effect", "revision_intent"):
            if not issue.get(required):
                raise NovelForgeError(
                    f"Blocking issue at index {idx} is missing '{required}'."
                )
    return data


def _chapter_summary_dict(svc: NovelForgeService, chapter_summary) -> dict:
    return chapter_summary.model_dump(mode="json")


def _book_dict(book) -> dict:
    return book.model_dump(mode="json")


def _chapter_dict(chapter) -> dict:
    return chapter.model_dump(mode="json")


def _revision_dict(revision) -> dict | None:
    if revision is None:
        return None
    return revision.model_dump(mode="json")


def _review_finding_dict(finding: ReviewFinding) -> dict:
    return finding.model_dump(mode="json")


def _audit_event_dict(event) -> dict:
    return event.model_dump(mode="json")


def _voice_bible_dict(vb) -> dict:
    return vb.model_dump(mode="json")


def _scene_contract_dict(sc) -> dict:
    return sc.model_dump(mode="json")


def _reader_review_summary_dict(summary) -> dict:
    return summary.model_dump(mode="json")


def _reader_review_dict(review) -> dict:
    return review.model_dump(mode="json")


def _drafting_packet_dict(packet) -> dict:
    return packet.model_dump(mode="json")


def _blind_reader_packet_dict(packet) -> dict:
    return packet.model_dump(mode="json")


def _blind_experience_review_dict(review) -> dict:
    return review.model_dump(mode="json")


def _blind_experience_summary_dict(summary) -> dict:
    return summary.model_dump(mode="json")


def _drafting_readiness_dict(readiness) -> dict:
    return readiness.model_dump(mode="json")


def _editorial_memo_summary_dict(summary) -> dict:
    return summary.model_dump(mode="json")


def _research_entry_dict(entry) -> dict:
    return entry.model_dump(mode="json")


def _story_engine_dict(engine) -> dict | None:
    if engine is None:
        return None
    return engine.model_dump(mode="json")


def _chapter_plan_dict(plan) -> dict | None:
    if plan is None:
        return None
    return plan.model_dump(mode="json")


def _promise_dict(promise) -> dict:
    return promise.model_dump(mode="json")


def _iteration_run_dict(run) -> dict:
    return run.model_dump(mode="json")


def _acceptance_result_dict(result) -> dict:
    return result.model_dump(mode="json")


def _readiness_summary_dict(readiness) -> dict:
    return {
        "ready": readiness.ready,
        "blocker_codes": [b["code"] for b in readiness.blockers],
    }


def run(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args, remaining = parser.parse_known_args(argv)
    except _ArgparseAdapterError as exc:
        return _fail("invalid_arguments", exc.message)

    root_path = Path(args.root)
    if not root_path.is_absolute():
        return _fail("invalid_root", "--root must be an absolute path.")
    root = root_path.resolve()

    op = args.operation
    if op in MUTATING_OPS and not _check_confirm(args):
        return _fail("confirmation_required", f"Operation '{op}' requires --confirm {op}")

    if op in {"harness-contract", "guardian-contract"}:
        if remaining:
            return _fail(
                "invalid_arguments",
                f"{op} does not accept positional arguments.",
            )
        return _ok(
            op,
            harness_contract() if op == "harness-contract" else guardian_contract(),
        )

    svc = NovelForgeService(root)

    # Status accepts exactly <slug> [number].
    if op == "status":
        if len(remaining) < 1 or len(remaining) > 2:
            return _fail(
                "invalid_arguments",
                "status requires <slug> [chapter-number]",
            )
        slug = remaining[0]
        _validate_slug(slug)
        auto = AutonomousWritingService(root)
        if len(remaining) == 1:
            book = svc.get_book(slug)
            chapters = svc.list_chapters(slug)
            voice_bible = svc.get_voice_bible(slug)
            research_entries = auto.list_research_entries(slug)
            story_engine = auto.get_story_engine(slug)
            promises = auto.list_promises(slug)
            unresolved_plot_support = sum(
                1
                for e in research_entries
                if e.unresolved and e.allowed_use == "plot_support"
            )
            return _ok(
                op,
                {
                    "book": _book_dict(book),
                    "voice_bible": _voice_bible_dict(voice_bible),
                    "chapters": [_chapter_summary_dict(svc, c) for c in chapters],
                    "research": {
                        "entry_count": len(research_entries),
                        "unresolved_plot_support": unresolved_plot_support,
                    },
                    "story_engine": _story_engine_dict(story_engine),
                    "promises": {
                        "count": len(promises),
                        "open_count": sum(
                            1 for p in promises if p.status not in ("paid_off", "abandoned")
                        ),
                    },
                },
            )
        try:
            number = int(remaining[1])
        except ValueError:
            return _fail(
                "invalid_arguments",
                f"Chapter number must be an integer: {remaining[1]!r}",
            )
        if number < 1:
            return _fail(
                "invalid_arguments",
                f"Chapter number must be positive: {number}",
            )
        chapter = svc.get_chapter(slug, number)
        finding_counts = svc.get_chapter_finding_counts(slug, number)
        current_revision = svc.get_current_revision(slug, number)
        scene_contract = svc.get_scene_contract(slug, number)
        reader_summary = svc.reader_review_summary_for_chapter(slug, number)
        readiness = svc.assess_drafting_readiness(slug, number)
        memo_summary = svc.editorial_memo_status(slug, number)
        blind_summary = svc.blind_experience_status(slug, number)
        chapter_plan = auto.get_chapter_plan(slug, number)
        iterations = auto.list_iteration_runs(slug, number)
        acceptance = auto.check_auto_acceptance(slug, number, max_rounds=3)
        return _ok(
            op,
            {
                "chapter": _chapter_dict(chapter),
                "finding_counts": finding_counts,
                "current_revision": _revision_dict(current_revision),
                "scene_contract": _scene_contract_dict(scene_contract),
                "reader_review_summary": _reader_review_summary_dict(reader_summary),
                "drafting_readiness": _readiness_summary_dict(readiness),
                "editorial_memo": _editorial_memo_summary_dict(memo_summary),
                "blind_experience": _blind_experience_summary_dict(blind_summary),
                "chapter_plan": _chapter_plan_dict(chapter_plan),
                "iteration_count": len(iterations),
                "acceptance": {
                    "decision": acceptance.decision,
                    "workflow_coverage": acceptance.checks.get("workflow_coverage"),
                    "proofread_status": acceptance.checks.get("proofread_status"),
                    "prose_edit_status": acceptance.checks.get("prose_edit_status"),
                    "independent_editorial_status": acceptance.checks.get(
                        "independent_editorial_status"
                    ),
                    "publication_eligibility": acceptance.checks.get(
                        "publication_eligibility"
                    ),
                    "word_count": acceptance.checks.get("word_count"),
                    "scene_count": acceptance.checks.get("scene_count"),
                    "iteration_count": acceptance.iteration_count,
                    "max_rounds": acceptance.max_rounds,
                },
            },
        )

    # Shared autonomous service for v4 operations.
    auto = AutonomousWritingService(root)

    # Operations keyed by ID rather than book slug must be handled before
    # assuming args.slug exists.
    if op == "resolve-finding":
        svc.resolve_finding(args.finding_id, args.note)
        return _ok(op, {}, state_changed=True)

    if op == "approve-fact":
        svc.approve_fact(args.candidate_id, args.note)
        return _ok(op, {}, state_changed=True)

    if op == "reject-fact":
        svc.reject_fact(args.candidate_id, args.note)
        return _ok(op, {}, state_changed=True)

    if op == "resolve-reader-review":
        svc.resolve_reader_review(args.review_id, args.note)
        return _ok(op, {}, state_changed=True)

    slug = args.slug
    _validate_slug(slug)

    if op == "init-book":
        book = svc.init_book(slug, args.title)
        return _ok(op, {"book": _book_dict(book)}, state_changed=True)

    if op == "init-novel-project":
        result = svc.init_novel_project(slug, args.title, args.genre)
        return _ok(op, result, state_changed=True)

    if op == "book-git-status":
        return _ok(op, {"local_git": book_git_status(root, slug)})

    if op == "init-book-git":
        data = initialize_book_git(root, slug, args.title)
        return _ok(op, {"local_git": data}, state_changed=True)

    if op == "book-git-checkpoint":
        data = checkpoint_book(root, slug, args.message, tag=args.tag)
        return _ok(op, {"local_git": data}, state_changed=data["committed"])

    if op == "restore-book-git":
        data = restore_book_worktree(root, slug)
        return _ok(op, {"local_git": data}, state_changed=True)

    if op == "project-status":
        data = book_project.project_status(root, slug, args.number)
        return _ok(op, data)

    if op == "begin-chapter-sequence":
        data = begin_chapter_sequence(
            root,
            slug,
            args.start_chapter,
            args.chapter_count,
            sequence_id=args.sequence_id,
            orchestrator_run_id=args.orchestrator_run_id,
        )
        return _ok(op, data, state_changed=True)

    if op == "claim-chapter-session":
        data = claim_chapter_session(
            root,
            slug,
            args.sequence_id,
            args.session_id,
        )
        return _ok(op, data, state_changed=True)

    if op == "advance-chapter-sequence":
        data = advance_chapter_sequence(
            root,
            slug,
            args.sequence_id,
            args.session_id,
        )
        return _ok(op, data, state_changed=True)

    if op == "invalidate-chapter-session":
        data = invalidate_chapter_session(
            root,
            slug,
            args.sequence_id,
            args.session_id,
            reason=args.reason,
        )
        return _ok(op, data, state_changed=True)

    if op == "prepare-writer-capsule":
        data = prepare_writer_capsule(
            root,
            slug,
            args.sequence_id,
            args.session_id,
            args.capsule_dir,
            args.target_path,
            regeneration_authorization_id=(
                args.regeneration_authorization_id
            ),
        )
        return _ok(op, data, state_changed=True)

    if op == "authorize-regeneration":
        data = authorize_regeneration(
            root,
            slug,
            args.sequence_id,
            args.session_id,
            authority=args.authority,
            decision_reference=args.decision_reference,
        )
        return _ok(op, data, state_changed=True)

    if op == "ingest-writer-capsule":
        data = ingest_writer_capsule(
            root,
            slug,
            args.capsule_id,
        )
        return _ok(op, data, state_changed=True)

    if op == "record-capsule-runtime":
        data = record_capsule_runtime(
            root,
            slug,
            args.capsule_id,
            args.file,
        )
        return _ok(op, data, state_changed=True)

    if op == "chapter-sequence-status":
        return _ok(
            op,
            chapter_sequence_status(
                root,
                slug,
                args.sequence_id,
            ),
        )

    if op == "run-gates":
        data = book_project.run_gates(
            root, slug, args.number, expected_mode=args.mode
        )
        return _ok(op, data)

    if op == "set-draft-mode":
        data = book_project.set_draft_mode(
            root, slug, args.number, args.mode
        )
        return _ok(op, data, state_changed=True)

    if op == "record-review":
        data = book_project.record_review(root, slug, args.number, args.role, args.file)
        return _ok(op, data, state_changed=True)

    if op == "advance-state":
        data = book_project.advance_state(
            root,
            slug,
            args.number,
            args.to,
            evidence=args.evidence,
            next_action=args.next_action,
        )
        return _ok(op, data, state_changed=True)

    if op == "sync-tools":
        data = book_project.sync_tools(root, slug, dry_run=args.dry_run)
        return _ok(op, data, state_changed=not args.dry_run)

    if op == "memory-status":
        return _ok(op, memory_status(root, slug))

    if op == "record-memory-candidate":
        data = record_candidate(root, slug, args.file)
        return _ok(op, data, state_changed=True)

    if op == "promote-memory-candidate":
        data = promote_candidate(root, slug, args.candidate_id)
        return _ok(op, data, state_changed=True)

    if op == "rebuild-memory-index":
        data = rebuild_memory_index(root, slug)
        return _ok(op, data, state_changed=True)

    if op == "build-memory-context":
        data = build_context_packet(root, slug, args.chapter)
        return _ok(op, data, state_changed=True)

    if op == "evidence-status":
        return _ok(op, evidence_status(root, slug, args.chapter))

    if op in {"session-audit", "record-session-audit"}:
        book_dir, report = audit_book_session(root, slug, args.file)
        if op == "session-audit":
            return _ok(op, report)
        stored = record_runtime_audit(book_dir, report)
        return _ok(
            op,
            {
                **stored,
                "budget": report["budget"],
                "provenance_status": report["provenance_status"],
                "provenance_mismatches": report["provenance_mismatches"],
            },
            state_changed=True,
        )

    if op == "record-evidence":
        data = record_evidence(root, slug, args.file)
        if data["kind"] == "generation":
            data["binding"] = book_project.bind_generation(
                root, slug, data["chapter"], data["record_id"]
            )
        return _ok(op, data, state_changed=True)

    if op == "create-chapter":
        chapter = svc.create_chapter(slug, args.number, args.title)
        return _ok(op, {"chapter": _chapter_dict(chapter)}, state_changed=True)

    if op == "write-revision":
        from_file = _validate_from_file(root, args.from_file)
        before = svc.get_chapter(slug, args.number)
        chapter = svc.write_revision(
            slug,
            args.number,
            from_file,
            note=args.note,
            reopen_reason=args.reopen_reason,
        )
        return _ok(
            op,
            {
                "chapter": _chapter_dict(chapter),
                "current_revision_id": chapter.current_revision_id,
            },
            state_changed=(before.current_revision_id != chapter.current_revision_id),
        )

    if op == "write-revision-patch":
        patch_file = _validate_patch_file(root, args.patch_file)
        before = svc.get_chapter(slug, args.number)
        patch_result = svc.write_revision_patch(
            slug,
            args.number,
            patch_file,
            note=args.note,
            reopen_reason=args.reopen_reason,
            allow_below_minimum=args.allow_below_minimum,
        )
        chapter = patch_result["chapter"]
        return _ok(
            op,
            {
                "chapter": _chapter_dict(chapter),
                "current_revision_id": chapter.current_revision_id,
                "before_count": patch_result["before_count"],
                "after_count": patch_result["after_count"],
            },
            state_changed=(before.current_revision_id != chapter.current_revision_id),
        )

    if op == "lint":
        before = svc.get_chapter(slug, args.number)
        try:
            blocking, advisory = svc.lint_chapter(slug, args.number)
        except (UnicodeDecodeError, FileNotFoundError) as exc:
            raise NovelForgeError(
                f"Current revision is not valid UTF-8 or is a damaged asset; "
                f"cannot lint chapter {args.number}: {exc}"
            )
        after = svc.get_chapter(slug, args.number)
        return _ok(
            op,
            {"blocking": blocking, "advisory": advisory},
            state_changed=(before.state.value != after.state.value),
        )

    if op == "review":
        before = svc.get_chapter(slug, args.number)
        result = svc.review_chapter(slug, args.number)
        after = svc.get_chapter(slug, args.number)
        return _ok(
            op,
            {
                "verdict": result.verdict.value,
                "severity_counts": result.severity_counts,
                "lint_counts": result.lint_counts,
                "findings": [_review_finding_dict(f) for f in result.findings],
                "reader_review_summary": _reader_review_summary_dict(
                    result.reader_review_summary
                ),
                "reader_reviews": [_reader_review_dict(r) for r in result.reader_reviews],
                "editorial_memo": result.editorial_memo_status,
                "blind_experience": result.blind_experience_status,
            },
            state_changed=(before.state.value != after.state.value),
        )

    if op == "add-finding":
        finding_id = svc.add_finding(
            slug,
            args.number,
            args.perspective,
            args.severity,
            args.location,
            args.evidence,
            args.issue,
            args.fix,
        )
        return _ok(op, {"finding_id": finding_id}, state_changed=True)

    if op == "add-candidate-fact":
        fact_id = svc.add_candidate_fact(
            slug,
            args.number,
            args.kind,
            args.subject,
            args.predicate,
            args.object,
            args.evidence,
        )
        return _ok(op, {"candidate_fact_id": fact_id}, state_changed=True)

    if op == "approve-chapter":
        chapter = svc.approve_chapter(slug, args.number, args.note)
        return _ok(op, {"chapter": _chapter_dict(chapter)}, state_changed=True)

    if op == "rollback-chapter":
        chapter = svc.rollback_chapter(slug, args.number, args.revision_id, args.note)
        return _ok(op, {"chapter": _chapter_dict(chapter)}, state_changed=True)

    if op == "export-book":
        out_path = svc.export_book(slug, args.format)
        data: dict = {
            "format": args.format,
            "file_path": str(out_path.relative_to(root)),
        }
        if args.format == "markdown":
            manifest_path = out_path.with_name(f"{out_path.stem}-manifest.json")
            if manifest_path.exists():
                data["manifest"] = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
        return _ok(op, data, state_changed=True)

    if op == "voice-bible-status":
        vb = svc.get_voice_bible(slug)
        return _ok(op, {"voice_bible": _voice_bible_dict(vb)})

    if op == "write-voice-bible":
        from_file = _validate_from_file(root, args.from_file)
        vb = svc.write_voice_bible(slug, from_file, note=args.note)
        return _ok(op, {"voice_bible": _voice_bible_dict(vb)}, state_changed=True)

    if op == "scene-contract-status":
        sc = svc.get_scene_contract(slug, args.number)
        return _ok(op, {"scene_contract": _scene_contract_dict(sc)})

    if op == "write-scene-contract":
        from_file = _validate_from_file(root, args.from_file)
        sc = svc.write_scene_contract(slug, args.number, from_file, note=args.note)
        return _ok(op, {"scene_contract": _scene_contract_dict(sc)}, state_changed=True)

    if op == "add-reader-review":
        review_id = svc.add_reader_review(
            slug,
            args.number,
            args.lens,
            args.severity,
            args.location_start,
            args.location_end,
            args.evidence,
            args.reader_effect,
            args.revision_intent,
            actor=args.actor,
        )
        return _ok(op, {"reader_review_id": review_id}, state_changed=True)

    if op == "submit-editorial-memo":
        memo_data = _validate_memo_file(root, args.memo_file)
        svc.submit_editorial_memo(
            slug,
            args.number,
            narrative_necessity=memo_data["narrative_necessity"],
            character_agency=memo_data["character_agency"],
            detail_selection=memo_data["detail_selection"],
            causal_chain=memo_data["causal_chain"],
            prose_observation=memo_data["prose_observation"],
            verdict=memo_data["verdict"],
            blocking_issues=memo_data["blocking_issues"],
        )
        summary = svc.editorial_memo_status(slug, args.number)
        return _ok(
            op,
            {"editorial_memo": _editorial_memo_summary_dict(summary)},
            state_changed=True,
        )

    if op == "editorial-memo-status":
        summary = svc.editorial_memo_status(slug, args.number)
        return _ok(op, {"editorial_memo": _editorial_memo_summary_dict(summary)})

    if op == "build-blind-reader-packet":
        output_file = _validate_output_file(root, args.output_file)
        packet = svc.build_blind_reader_packet(slug, args.number, output_file)
        return _ok(
            op,
            {"packet": _blind_reader_packet_dict(packet)},
            state_changed=False,
        )

    if op == "submit-blind-experience-review":
        report = _validate_json_file(root, args.report_file)
        if not isinstance(report, dict):
            raise NovelForgeError("Blind experience report must be a JSON object.")
        required = {
            "spatial_reconstruction",
            "body_position_and_contact",
            "action_constraints",
            "emotional_trajectory",
            "dialogue_dynamics",
            "memorable_images",
            "knowledge_gaps",
            "verdict",
            "blocking_issues",
        }
        missing = sorted(required - set(report))
        if missing:
            raise NovelForgeError(
                f"Blind experience report is missing fields: {', '.join(missing)}"
            )
        review = svc.submit_blind_experience_review(
            slug,
            args.number,
            spatial_reconstruction=report["spatial_reconstruction"],
            body_position_and_contact=report["body_position_and_contact"],
            action_constraints=report["action_constraints"],
            emotional_trajectory=report["emotional_trajectory"],
            dialogue_dynamics=report["dialogue_dynamics"],
            memorable_images=report["memorable_images"],
            knowledge_gaps=report["knowledge_gaps"],
            verdict=report["verdict"],
            blocking_issues=report["blocking_issues"],
        )
        return _ok(
            op,
            _blind_experience_review_dict(review),
            state_changed=True,
        )

    if op == "blind-experience-status":
        summary = svc.blind_experience_status(slug, args.number)
        return _ok(op, {"blind_experience": _blind_experience_summary_dict(summary)})

    if op == "build-drafting-packet":
        output_file = _validate_output_file(root, args.output_file)
        readiness = svc.assess_drafting_readiness(slug, args.number)
        packet = svc.build_drafting_packet(
            slug,
            args.number,
            output_file,
            note=args.note,
            previous_context_chars=args.previous_context_chars,
            allow_incomplete=args.allow_incomplete,
        )
        return _ok(
            op,
            {
                "packet": _drafting_packet_dict(packet),
                "readiness": _readiness_summary_dict(readiness),
                "readiness_bypassed": args.allow_incomplete and not readiness.ready,
            },
            state_changed=False,
        )

    if op == "drafting-readiness":
        readiness = svc.assess_drafting_readiness(slug, args.number)
        return _ok(op, {"readiness": _drafting_readiness_dict(readiness)})

    if op == "add-research-entry":
        entry = auto.add_research_entry(
            slug,
            url=args.url,
            retrieved_at=args.retrieved_at,
            source_type=args.source_type,
            confidence=args.confidence,
            claim=args.claim,
            allowed_use=args.allowed_use,
            fiction_boundary=args.fiction_boundary,
            unresolved=args.unresolved,
            verification_state=args.verification_state,
            verification_ref=args.verification_ref,
            notes=args.notes,
        )
        return _ok(
            op,
            {"research_entry_id": entry.id, "unresolved": entry.unresolved},
            state_changed=True,
        )

    if op == "update-research-entry":
        entry = auto.update_research_entry(
            slug,
            entry_id=args.entry_id,
            verification_state=args.verification_state,
            verification_ref=args.verification_ref,
        )
        return _ok(
            op,
            {
                "research_entry_id": entry.id,
                "verification_state": entry.verification_state,
                "verification_ref": entry.verification_ref,
            },
            state_changed=True,
        )

    if op == "list-research":
        entries = auto.list_research_entries(slug)
        return _ok(op, {"research_entries": [_research_entry_dict(e) for e in entries]})

    if op == "set-story-engine":
        engine = auto.set_story_engine(
            slug,
            secret=args.secret,
            desire=args.desire,
            alternative_actions=args.alternative_actions,
            irreversible_choice=args.irreversible_choice,
            immediate_cost=args.immediate_cost,
            thematic_pressure=args.thematic_pressure,
        )
        return _ok(op, {"story_engine": _story_engine_dict(engine)}, state_changed=True)

    if op == "get-story-engine":
        engine = auto.get_story_engine(slug)
        return _ok(op, {"story_engine": _story_engine_dict(engine)})

    if op == "set-chapter-plan":
        scenes = _validate_plan_file(root, args.plan_file)
        plan = auto.set_chapter_plan(slug, args.number, scenes, status=args.status)
        return _ok(
            op,
            {"chapter_plan": _chapter_plan_dict(plan)},
            state_changed=True,
        )

    if op == "get-chapter-plan":
        plan = auto.get_chapter_plan(slug, args.number)
        return _ok(op, {"chapter_plan": _chapter_plan_dict(plan)})

    if op == "update-promise":
        promise = auto.update_promise_status(
            slug,
            promise_id=args.promise_id,
            status=args.status,
            scene_ref=args.scene_ref,
            resolution_note=args.note,
        )
        return _ok(op, {"promise": _promise_dict(promise)}, state_changed=True)

    if op == "set-promise-target":
        promise = auto.set_promise_target(
            slug,
            promise_id=args.promise_id,
            target_chapter_number=args.target_chapter_number,
            target_scene_ref=args.target_scene_ref,
            clear=args.clear,
        )
        return _ok(op, {"promise": _promise_dict(promise)}, state_changed=True)

    if op == "list-promises":
        promises = auto.list_promises(slug)
        return _ok(op, {"promises": [_promise_dict(p) for p in promises]})

    if op == "record-iteration":
        blocking_issues = _validate_blocking_issues_file(root, args.blocking_issues_file)
        run = auto.start_iteration_run(
            slug,
            args.number,
            writer_role=args.writer_role,
            editor_verdict=args.editor_verdict,
            blocking_issues=blocking_issues,
            revision_targets=args.revision_targets,
            word_count=args.word_count,
            status=args.status,
        )
        return _ok(op, {"iteration_run": _iteration_run_dict(run)}, state_changed=True)

    if op == "list-iterations":
        runs = auto.list_iteration_runs(slug, args.number)
        return _ok(op, {"iteration_runs": [_iteration_run_dict(r) for r in runs]})

    if op == "check-acceptance":
        result = auto.check_auto_acceptance(slug, args.number, max_rounds=args.max_rounds)
        return _ok(
            op,
            {
                "decision": result.decision,
                "checks": result.checks,
                "iteration_count": result.iteration_count,
                "max_rounds": result.max_rounds,
                "message": result.message,
            },
            state_changed=False,
        )

    if op == "git-checkpoint":
        result = auto.git_checkpoint(slug, args.message)
        return _ok(op, {"git_checkpoint": result}, state_changed=True)

    if op == "init-workspace":
        result = svc.initialize_book_workspace(slug)
        return _ok(op, result, state_changed=True)

    if op == "refresh-workspace":
        result = svc.refresh_book_workspace(slug)
        return _ok(op, result, state_changed=True)

    if op == "audit":
        events = svc.audit(slug, limit=args.limit)
        return _ok(op, {"events": [_audit_event_dict(e) for e in events]})

    return _fail("unknown_operation", f"Unsupported operation: {op}")


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except NovelForgeError as exc:
        return _fail("business_error", exc.message)
    except AutonomousError as exc:
        return _fail("business_error", exc.message)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
