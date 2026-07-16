"""Command-line interface for Novel Forge."""

import argparse
import json
import sys
from pathlib import Path

from app.novel_forge.autonomous import AutonomousError, AutonomousWritingService
from app.novel_forge.models import ScenePlan
from app.novel_forge.service import NovelForgeError, NovelForgeService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel-forge",
        description="S-Black Novel Forge: auditable fiction production.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current directory).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init-book
    p = sub.add_parser("init-book", help="Initialize a new book.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--title", required=True, help="Book title.")

    # create-chapter
    p = sub.add_parser("create-chapter", help="Create a new chapter.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--title", required=True, help="Chapter title.")

    # write-revision
    p = sub.add_parser("write-revision", help="Write a new revision from a Markdown file.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--from-file", required=True, type=Path, help="Source Markdown file.")
    p.add_argument("--note", default=None, help="Revision note.")
    p.add_argument("--reopen-reason", default=None, help="Reason for reopening an approved chapter.")

    # lint-chapter
    p = sub.add_parser("lint-chapter", help="Run prose lint on the current revision.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    # add-finding
    p = sub.add_parser("add-finding", help="Add a review finding.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--perspective",
        required=True,
        choices=["structure", "character", "narrative", "continuity"],
    )
    p.add_argument("--severity", required=True, choices=["S1", "S2", "S3", "S4"])
    p.add_argument("--location", required=True, help="Location string.")
    p.add_argument("--evidence", required=True, help="Evidence text.")
    p.add_argument("--issue", required=True, help="Issue description.")
    p.add_argument("--fix", required=True, help="Fix suggestion.")

    # resolve-finding
    p = sub.add_parser("resolve-finding", help="Resolve a review finding.")
    p.add_argument("finding_id", type=int, help="Finding ID.")
    p.add_argument("--note", required=True, help="Resolution note.")

    # add-candidate-fact
    p = sub.add_parser("add-candidate-fact", help="Add a candidate fact.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--kind", required=True, help="Fact kind.")
    p.add_argument("--subject", required=True, help="Subject.")
    p.add_argument("--predicate", required=True, help="Predicate.")
    p.add_argument("--object", required=True, help="Object.")
    p.add_argument("--evidence", required=True, help="Evidence text.")

    # approve-fact
    p = sub.add_parser("approve-fact", help="Approve a candidate fact into canon.")
    p.add_argument("candidate_id", type=int, help="Candidate fact ID.")
    p.add_argument("--note", default=None, help="Approval note.")

    # reject-fact
    p = sub.add_parser("reject-fact", help="Reject a candidate fact.")
    p.add_argument("candidate_id", type=int, help="Candidate fact ID.")
    p.add_argument("--note", default=None, help="Rejection note.")

    # review-chapter
    p = sub.add_parser("review-chapter", help="Review a chapter and produce a verdict.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    # submit-editorial-memo
    p = sub.add_parser(
        "submit-editorial-memo",
        help="Submit a narrative editorial memo for the current revision.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--memo-file", required=True, type=Path, help="JSON file with the memo."
    )

    # build-blind-reader-packet
    p = sub.add_parser(
        "build-blind-reader-packet",
        help="Build a prose-only packet for an isolated blind reader.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--output-file", required=True, type=Path, help="Absolute output path."
    )

    # submit-blind-experience-review
    p = sub.add_parser(
        "submit-blind-experience-review",
        help="Submit a prose-only blind reader reconstruction report.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--report-file", required=True, type=Path, help="JSON report file."
    )

    # blind-experience-status
    p = sub.add_parser(
        "blind-experience-status",
        help="Show Blind Experience Gate status for the current revision.",
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    # approve-chapter
    p = sub.add_parser("approve-chapter", help="Approve a chapter.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--note", required=True, help="Approval note.")

    # rollback-chapter
    p = sub.add_parser("rollback-chapter", help="Rollback to a previous revision.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("revision_id", type=int, help="Target revision ID.")
    p.add_argument("--note", required=True, help="Rollback note.")

    # export-book
    p = sub.add_parser("export-book", help="Export approved chapters.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--format", required=True, choices=["markdown", "docx", "epub", "pdf"])

    # audit
    p = sub.add_parser("audit", help="Show audit log for a book.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--limit", type=int, default=None, help="Limit number of events.")

    # Autonomous research-to-fiction workflow (v4)
    p = sub.add_parser("add-research-entry", help="Add a research ledger entry.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--url", required=True, help="Source URL.")
    p.add_argument("--retrieved-at", required=True, help="Retrieval timestamp (ISO-8601).")
    p.add_argument(
        "--source-type",
        required=True,
        choices=["official", "academic", "news", "other"],
        help="Source type.",
    )
    p.add_argument("--confidence", required=True, choices=["A", "B", "C"])
    p.add_argument("--claim", required=True, help="Factual claim.")
    p.add_argument(
        "--allowed-use",
        required=True,
        choices=["plot_support", "background_only", "fiction_seed"],
        help="How this claim may be used in fiction.",
    )
    p.add_argument(
        "--fiction-boundary", required=True, help="Boundary between fact and invention."
    )
    p.add_argument(
        "--verification-state",
        default="collected",
        choices=["collected", "verified", "unresolved"],
        help="Verification state of this claim.",
    )
    p.add_argument(
        "--verification-ref",
        type=int,
        default=None,
        help="ID of a verified A-level plot_support entry that corroborates this claim.",
    )
    p.add_argument(
        "--unresolved", action="store_true", help="Mark claim as unresolved."
    )
    p.add_argument("--notes", default=None, help="Optional notes.")

    p = sub.add_parser("update-research-entry", help="Update a research entry's verification.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("entry_id", type=int, help="Research entry ID.")
    p.add_argument(
        "--verification-state",
        choices=["collected", "verified", "unresolved"],
        help="New verification state.",
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
        "--alternative-actions",
        required=True,
        nargs="+",
        help="One or more alternative actions the protagonist could take.",
    )
    p.add_argument("--irreversible-choice", required=True)
    p.add_argument("--immediate-cost", required=True)
    p.add_argument("--thematic-pressure", required=True)

    p = sub.add_parser("get-story-engine", help="Get the book-level story engine.")
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser(
        "set-chapter-plan", help="Set a chapter plan from a JSON file."
    )
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--plan-file", required=True, type=Path, help="Absolute path to scene plan JSON."
    )
    p.add_argument(
        "--status",
        default="draft",
        choices=["draft", "approved_for_writing"],
        help="Plan status.",
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
    p.add_argument("--scene-ref", required=True, help="Scene reference.")
    p.add_argument("--note", default=None, help="Resolution note.")

    p = sub.add_parser("set-promise-target", help="Set or clear a promise payoff target.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("promise_id", type=int, help="Promise ID.")
    p.add_argument("--target-chapter-number", type=int, default=None)
    p.add_argument("--target-scene-ref", default=None)
    p.add_argument("--clear", action="store_true", help="Clear the target.")

    p = sub.add_parser("list-promises", help="List promises for a book.")
    p.add_argument("slug", help="Book slug.")

    p = sub.add_parser("record-iteration", help="Record an iteration run.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument("--writer-role", required=True, help="Writer role identifier.")
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
    p.add_argument(
        "--revision-targets",
        required=True,
        nargs="+",
        help="One or more revision targets.",
    )
    p.add_argument("--word-count", required=True, type=int)
    p.add_argument(
        "--status",
        default="completed",
        choices=["running", "completed", "failed"],
    )

    p = sub.add_parser("list-iterations", help="List iteration runs for a chapter.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")

    p = sub.add_parser("check-acceptance", help="Check auto-acceptance gate.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("number", type=int, help="Chapter number.")
    p.add_argument(
        "--max-rounds", type=int, default=3, help="Maximum autonomous rounds."
    )

    p = sub.add_parser("git-checkpoint", help="Create a scoped git checkpoint.")
    p.add_argument("slug", help="Book slug.")
    p.add_argument("--message", required=True, help="Commit message.")

    return parser


def cmd_init_book(svc: NovelForgeService, args: argparse.Namespace) -> int:
    book = svc.init_book(args.slug, args.title)
    print(f"Initialized book: {book.slug} ({book.title})")
    return 0


def cmd_create_chapter(svc: NovelForgeService, args: argparse.Namespace) -> int:
    ch = svc.create_chapter(args.slug, args.number, args.title)
    print(f"Created chapter {ch.number}: {ch.title} (state={ch.state.value})")
    return 0


def cmd_write_revision(svc: NovelForgeService, args: argparse.Namespace) -> int:
    ch = svc.write_revision(
        args.slug,
        args.number,
        args.from_file,
        note=args.note,
        reopen_reason=args.reopen_reason,
    )
    print(
        f"Wrote revision {ch.current_revision_id} for chapter {ch.number} "
        f"(state={ch.state.value})"
    )
    return 0


def cmd_lint_chapter(svc: NovelForgeService, args: argparse.Namespace) -> int:
    blocking, advisory = svc.lint_chapter(args.slug, args.number)
    print(f"Lint complete: {blocking} blocking, {advisory} advisory")
    return 0 if blocking == 0 else 1


def cmd_add_finding(svc: NovelForgeService, args: argparse.Namespace) -> int:
    fid = svc.add_finding(
        args.slug,
        args.number,
        args.perspective,
        args.severity,
        args.location,
        args.evidence,
        args.issue,
        args.fix,
    )
    print(f"Added finding {fid}")
    return 0


def cmd_resolve_finding(svc: NovelForgeService, args: argparse.Namespace) -> int:
    svc.resolve_finding(args.finding_id, args.note)
    print(f"Resolved finding {args.finding_id}")
    return 0


def cmd_add_candidate_fact(svc: NovelForgeService, args: argparse.Namespace) -> int:
    fid = svc.add_candidate_fact(
        args.slug,
        args.number,
        args.kind,
        args.subject,
        args.predicate,
        args.object,
        args.evidence,
    )
    print(f"Added candidate fact {fid}")
    return 0


def cmd_approve_fact(svc: NovelForgeService, args: argparse.Namespace) -> int:
    svc.approve_fact(args.candidate_id, args.note)
    print(f"Approved candidate fact {args.candidate_id}")
    return 0


def cmd_reject_fact(svc: NovelForgeService, args: argparse.Namespace) -> int:
    svc.reject_fact(args.candidate_id, args.note)
    print(f"Rejected candidate fact {args.candidate_id}")
    return 0


def cmd_review_chapter(svc: NovelForgeService, args: argparse.Namespace) -> int:
    result = svc.review_chapter(args.slug, args.number)
    print(f"Verdict: {result.verdict.value}")
    print(f"Severity counts: {json.dumps(result.severity_counts)}")
    print(f"Lint counts: {json.dumps(result.lint_counts)}")
    for f in result.findings:
        print(f"  [{f.severity}] {f.perspective} at {f.location}: {f.issue}")
    return 0 if result.verdict.value != "REJECT" else 1


def cmd_submit_editorial_memo(
    svc: NovelForgeService, args: argparse.Namespace
) -> int:
    memo_data = json.loads(args.memo_file.read_text(encoding="utf-8-sig"))
    memo = svc.submit_editorial_memo(
        args.slug,
        args.number,
        narrative_necessity=memo_data["narrative_necessity"],
        character_agency=memo_data["character_agency"],
        detail_selection=memo_data["detail_selection"],
        causal_chain=memo_data["causal_chain"],
        prose_observation=memo_data["prose_observation"],
        verdict=memo_data["verdict"],
        blocking_issues=memo_data.get("blocking_issues", []),
    )
    print(f"Submitted editorial memo {memo.id} (verdict={memo.verdict})")
    return 0


def cmd_build_blind_reader_packet(
    svc: NovelForgeService, args: argparse.Namespace
) -> int:
    packet = svc.build_blind_reader_packet(
        args.slug, args.number, args.output_file
    )
    print(f"Built blind reader packet: {packet.file_path}")
    return 0


def cmd_submit_blind_experience_review(
    svc: NovelForgeService, args: argparse.Namespace
) -> int:
    report = json.loads(args.report_file.read_text(encoding="utf-8-sig"))
    review = svc.submit_blind_experience_review(
        args.slug,
        args.number,
        spatial_reconstruction=report["spatial_reconstruction"],
        body_position_and_contact=report["body_position_and_contact"],
        action_constraints=report["action_constraints"],
        emotional_trajectory=report["emotional_trajectory"],
        dialogue_dynamics=report["dialogue_dynamics"],
        memorable_images=report["memorable_images"],
        knowledge_gaps=report.get("knowledge_gaps", []),
        verdict=report["verdict"],
        blocking_issues=report.get("blocking_issues", []),
    )
    print(
        f"Submitted blind review {review.id} (verdict={review.verdict}, "
        f"images={len(review.memorable_images)})"
    )
    return 0


def cmd_blind_experience_status(
    svc: NovelForgeService, args: argparse.Namespace
) -> int:
    summary = svc.blind_experience_status(args.slug, args.number)
    print(f"Blind experience status: exists={summary.exists} passes={summary.passes}")
    if summary.exists:
        print(f"  review_id={summary.review_id} verdict={summary.verdict}")
        print(
            f"  images={summary.memorable_image_count} "
            f"gaps={summary.knowledge_gap_count} "
            f"issues={summary.blocking_issue_count}"
        )
    return 0


def cmd_approve_chapter(svc: NovelForgeService, args: argparse.Namespace) -> int:
    ch = svc.approve_chapter(args.slug, args.number, args.note)
    print(f"Approved chapter {ch.number} (state={ch.state.value})")
    return 0


def cmd_rollback_chapter(svc: NovelForgeService, args: argparse.Namespace) -> int:
    ch = svc.rollback_chapter(args.slug, args.number, args.revision_id, args.note)
    print(f"Rolled back chapter {ch.number} (state={ch.state.value})")
    return 0


def cmd_export_book(svc: NovelForgeService, args: argparse.Namespace) -> int:
    path = svc.export_book(args.slug, args.format)
    print(f"Exported to: {path}")
    return 0


def cmd_audit(svc: NovelForgeService, args: argparse.Namespace) -> int:
    events = svc.audit(args.slug, limit=args.limit)
    for ev in events:
        print(
            f"{ev.created_at} [{ev.entity_type}:{ev.entity_id}] {ev.action} "
            f"{ev.details or ''}"
        )
    return 0


def _load_plan_file(plan_file: Path) -> list[ScenePlan]:
    if not plan_file.exists():
        raise NovelForgeError(f"Plan file not found: {plan_file}")
    try:
        data = json.loads(plan_file.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NovelForgeError(f"Invalid plan file: {exc}")
    if not isinstance(data, list):
        raise NovelForgeError("Plan file must contain a JSON array of scenes.")
    try:
        return [ScenePlan.model_validate(s) for s in data]
    except Exception as exc:
        raise NovelForgeError(f"Invalid scene plan: {exc}")


def _load_blocking_issues(path: Path) -> list[dict]:
    if not path.exists():
        raise NovelForgeError(f"Blocking issues file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NovelForgeError(f"Invalid blocking issues file: {exc}")
    if not isinstance(data, list):
        raise NovelForgeError("Blocking issues must be a JSON array.")
    for idx, issue in enumerate(data):
        if not isinstance(issue, dict):
            raise NovelForgeError(f"Blocking issue {idx} must be an object.")
        for required in ("location", "evidence", "effect", "revision_intent"):
            if not issue.get(required):
                raise NovelForgeError(
                    f"Blocking issue {idx} is missing '{required}'."
                )
    return data


def cmd_add_research_entry(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    entry = auto.add_research_entry(
        args.slug,
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
    print(f"Added research entry {entry.id}")
    return 0


def cmd_update_research_entry(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    entry = auto.update_research_entry(
        args.slug,
        entry_id=args.entry_id,
        verification_state=args.verification_state,
        verification_ref=args.verification_ref,
    )
    print(
        f"Updated research entry {entry.id} "
        f"(verification_state={entry.verification_state}, "
        f"verification_ref={entry.verification_ref})"
    )
    return 0


def cmd_list_research(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    entries = auto.list_research_entries(args.slug)
    for e in entries:
        unresolved = "UNRESOLVED" if e.unresolved else "resolved"
        print(
            f"{e.id}: [{e.confidence}/{e.source_type}/{e.allowed_use}/{unresolved}] "
            f"{e.claim[:80]}{'...' if len(e.claim) > 80 else ''}"
        )
    return 0


def cmd_set_story_engine(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    engine = auto.set_story_engine(
        args.slug,
        secret=args.secret,
        desire=args.desire,
        alternative_actions=args.alternative_actions,
        irreversible_choice=args.irreversible_choice,
        immediate_cost=args.immediate_cost,
        thematic_pressure=args.thematic_pressure,
    )
    print(f"Set story engine {engine.id} for book {args.slug}")
    return 0


def cmd_get_story_engine(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    engine = auto.get_story_engine(args.slug)
    if engine is None:
        print("No story engine set.")
        return 0
    print(f"Story engine for {args.slug} (id={engine.id})")
    print(f"  secret: {engine.secret}")
    print(f"  desire: {engine.desire}")
    print(f"  alternatives: {', '.join(engine.alternative_actions)}")
    print(f"  irreversible_choice: {engine.irreversible_choice}")
    print(f"  immediate_cost: {engine.immediate_cost}")
    print(f"  thematic_pressure: {engine.thematic_pressure}")
    return 0


def cmd_set_chapter_plan(svc: NovelForgeService, args: argparse.Namespace) -> int:
    scenes = _load_plan_file(args.plan_file)
    auto = AutonomousWritingService(svc.root)
    plan = auto.set_chapter_plan(
        args.slug, args.number, scenes, status=args.status
    )
    print(
        f"Set chapter plan {plan.id} for chapter {args.number} "
        f"({len(plan.scenes)} scenes, status={plan.status})"
    )
    return 0


def cmd_get_chapter_plan(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    plan = auto.get_chapter_plan(args.slug, args.number)
    if plan is None:
        print("No chapter plan set.")
        return 0
    print(f"Chapter {args.number} plan (id={plan.id}, status={plan.status})")
    for s in plan.scenes:
        print(f"  {s.scene_ref}: {s.goal}")
    return 0


def cmd_update_promise(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    promise = auto.update_promise_status(
        args.slug,
        promise_id=args.promise_id,
        status=args.status,
        scene_ref=args.scene_ref,
        resolution_note=args.note,
    )
    print(f"Updated promise {promise.id} to {promise.status}")
    return 0


def cmd_set_promise_target(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    promise = auto.set_promise_target(
        args.slug,
        promise_id=args.promise_id,
        target_chapter_number=args.target_chapter_number,
        target_scene_ref=args.target_scene_ref,
        clear=args.clear,
    )
    if args.clear:
        print(f"Cleared promise {promise.id} target")
    else:
        target = f"chapter {promise.target_chapter_number}"
        if promise.target_scene_ref:
            target += f", scene {promise.target_scene_ref}"
        print(f"Set promise {promise.id} target to {target}")
    return 0


def cmd_list_promises(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    promises = auto.list_promises(args.slug)
    for p in promises:
        print(
            f"{p.id}: [{p.status}] {p.promise_text[:60]}"
            f"{'...' if len(p.promise_text) > 60 else ''}"
        )
    return 0


def cmd_record_iteration(svc: NovelForgeService, args: argparse.Namespace) -> int:
    blocking_issues = _load_blocking_issues(args.blocking_issues_file)
    auto = AutonomousWritingService(svc.root)
    run = auto.start_iteration_run(
        args.slug,
        args.number,
        writer_role=args.writer_role,
        editor_verdict=args.editor_verdict,
        blocking_issues=blocking_issues,
        revision_targets=args.revision_targets,
        word_count=args.word_count,
        status=args.status,
    )
    print(
        f"Recorded iteration run {run.id} round {run.round_number} "
        f"(verdict={run.editor_verdict}, status={run.status})"
    )
    return 0


def cmd_list_iterations(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    runs = auto.list_iteration_runs(args.slug, args.number)
    for r in runs:
        print(
            f"Round {r.round_number}: {r.editor_verdict} "
            f"({r.word_count} Han chars, status={r.status})"
        )
    return 0


def cmd_check_acceptance(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    result = auto.check_auto_acceptance(args.slug, args.number, max_rounds=args.max_rounds)
    print(f"Decision: {result.decision}")
    print(f"Checks: {json.dumps(result.checks, ensure_ascii=False)}")
    print(result.message)
    return 0 if result.decision == "autonomous_acceptance_complete" else 1


def cmd_git_checkpoint(svc: NovelForgeService, args: argparse.Namespace) -> int:
    auto = AutonomousWritingService(svc.root)
    result = auto.git_checkpoint(args.slug, args.message)
    if result["committed"]:
        print(f"Checkpoint {result['commit_hash']}: {result['message']}")
    else:
        print(result["message"])
    return 0


COMMANDS = {
    "init-book": cmd_init_book,
    "create-chapter": cmd_create_chapter,
    "write-revision": cmd_write_revision,
    "lint-chapter": cmd_lint_chapter,
    "add-finding": cmd_add_finding,
    "resolve-finding": cmd_resolve_finding,
    "add-candidate-fact": cmd_add_candidate_fact,
    "approve-fact": cmd_approve_fact,
    "reject-fact": cmd_reject_fact,
    "review-chapter": cmd_review_chapter,
    "submit-editorial-memo": cmd_submit_editorial_memo,
    "build-blind-reader-packet": cmd_build_blind_reader_packet,
    "submit-blind-experience-review": cmd_submit_blind_experience_review,
    "blind-experience-status": cmd_blind_experience_status,
    "approve-chapter": cmd_approve_chapter,
    "rollback-chapter": cmd_rollback_chapter,
    "export-book": cmd_export_book,
    "audit": cmd_audit,
    "add-research-entry": cmd_add_research_entry,
    "update-research-entry": cmd_update_research_entry,
    "list-research": cmd_list_research,
    "set-story-engine": cmd_set_story_engine,
    "get-story-engine": cmd_get_story_engine,
    "set-chapter-plan": cmd_set_chapter_plan,
    "get-chapter-plan": cmd_get_chapter_plan,
    "update-promise": cmd_update_promise,
    "set-promise-target": cmd_set_promise_target,
    "list-promises": cmd_list_promises,
    "record-iteration": cmd_record_iteration,
    "list-iterations": cmd_list_iterations,
    "check-acceptance": cmd_check_acceptance,
    "git-checkpoint": cmd_git_checkpoint,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    svc = NovelForgeService(args.root)
    handler = COMMANDS[args.command]
    try:
        return handler(svc, args)
    except NovelForgeError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except AutonomousError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: file not found: {exc.filename}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
