"""Autonomous research-to-fiction workflow layer for Novel Forge.

This module is intentionally separate from the core state-machine service
so that the experimental "agent loop" features do not entangle with the
stable revision/lint/approval pipeline. It shares the same SQLite database
and audit trail.
"""

import json
import re
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.novel_forge.db import get_db_path, init_db
from app.novel_forge.models import (
    AcceptanceResult,
    ChapterPlan,
    IterationRun,
    Promise,
    ResearchEntry,
    ScenePlan,
    StoryEngine,
)
from app.novel_forge.repository import (
    AuditRepository,
    BookRepository,
    ChapterPlanRepository,
    ChapterRepository,
    EditorialMemoRepository,
    FindingRepository,
    IterationRepository,
    PromiseRepository,
    ReaderReviewRepository,
    ResearchRepository,
    StoryEngineRepository,
)


class AutonomousError(Exception):
    """Base exception with a user-facing message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AutonomousWritingService:
    """Service for research-driven, multi-scene autonomous writing workflows."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        # Ensure DB is initialized and migrated on first use.
        conn = init_db(self.root)
        conn.close()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(get_db_path(self.root)))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ------------------------------------------------------------------
    # Research Ledger
    # ------------------------------------------------------------------
    def _validate_verification_ref(
        self,
        conn: sqlite3.Connection,
        book_id: int,
        verification_ref: int | None,
    ) -> None:
        """Ensure verification_ref points to a verified A-level plot_support entry."""
        if verification_ref is None:
            return
        ref = ResearchRepository.get_by_id(conn, verification_ref)
        if ref is None:
            raise AutonomousError(f"Verification reference not found: {verification_ref}")
        if ref["book_id"] != book_id:
            raise AutonomousError(
                f"Verification reference {verification_ref} belongs to a different book."
            )
        if ref["confidence"] != "A":
            raise AutonomousError(
                f"Verification reference {verification_ref} must be confidence A."
            )
        if ref["verification_state"] != "verified":
            raise AutonomousError(
                f"Verification reference {verification_ref} must be verification_state 'verified'."
            )
        if ref["allowed_use"] != "plot_support":
            raise AutonomousError(
                f"Verification reference {verification_ref} must be allowed_use 'plot_support'."
            )

    def add_research_entry(
        self,
        slug: str,
        url: str,
        retrieved_at: str,
        source_type: str,
        confidence: str,
        claim: str,
        allowed_use: str,
        fiction_boundary: str,
        unresolved: bool = False,
        verification_state: str = "collected",
        verification_ref: int | None = None,
        notes: str | None = None,
    ) -> ResearchEntry:
        if source_type not in {"official", "academic", "news", "other"}:
            raise AutonomousError(f"Invalid source_type: {source_type}")
        if confidence not in {"A", "B", "C"}:
            raise AutonomousError(f"Invalid confidence: {confidence}")
        if allowed_use not in {"plot_support", "background_only", "fiction_seed"}:
            raise AutonomousError(f"Invalid allowed_use: {allowed_use}")
        if verification_state not in {"collected", "verified", "unresolved"}:
            raise AutonomousError(f"Invalid verification_state: {verification_state}")
        if not url or not url.strip():
            raise AutonomousError("Research URL cannot be empty.")
        if not claim or not claim.strip():
            raise AutonomousError("Research claim cannot be empty.")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            self._validate_verification_ref(conn, book["id"], verification_ref)
            entry_id = ResearchRepository.create(
                conn,
                book_id=book["id"],
                url=url.strip(),
                retrieved_at=retrieved_at,
                source_type=source_type,
                confidence=confidence,
                claim=claim.strip(),
                allowed_use=allowed_use,
                fiction_boundary=fiction_boundary.strip(),
                unresolved=unresolved,
                verification_state=verification_state,
                verification_ref=verification_ref,
                notes=notes,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="research_entry",
                entity_id=entry_id,
                action="create",
                details=json.dumps(
                    {
                        "url": url,
                        "confidence": confidence,
                        "allowed_use": allowed_use,
                        "unresolved": unresolved,
                        "verification_state": verification_state,
                        "verification_ref": verification_ref,
                    },
                    ensure_ascii=False,
                ),
            )
            row = ResearchRepository.get_by_id(conn, entry_id)
        return ResearchEntry.model_validate(dict(row))

    def update_research_entry(
        self,
        slug: str,
        entry_id: int,
        verification_state: str | None = None,
        verification_ref: int | None = None,
    ) -> ResearchEntry:
        if verification_state is not None and verification_state not in {
            "collected",
            "verified",
            "unresolved",
        }:
            raise AutonomousError(f"Invalid verification_state: {verification_state}")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            entry = ResearchRepository.get_by_id(conn, entry_id)
            if entry is None or entry["book_id"] != book["id"]:
                raise AutonomousError(
                    f"Research entry {entry_id} not found in book {slug}."
                )
            self._validate_verification_ref(conn, book["id"], verification_ref)
            ResearchRepository.update(
                conn,
                entry_id,
                verification_state=verification_state,
                verification_ref=verification_ref,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="research_entry",
                entity_id=entry_id,
                action="update",
                details=json.dumps(
                    {
                        "verification_state": verification_state,
                        "verification_ref": verification_ref,
                    },
                    ensure_ascii=False,
                ),
            )
            row = ResearchRepository.get_by_id(conn, entry_id)
        return ResearchEntry.model_validate(dict(row))

    def list_research_entries(self, slug: str) -> list[ResearchEntry]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            rows = ResearchRepository.list_by_book(conn, book["id"])
            return [ResearchEntry.model_validate(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Story Engine
    # ------------------------------------------------------------------
    def set_story_engine(
        self,
        slug: str,
        secret: str,
        desire: str,
        alternative_actions: list[str],
        irreversible_choice: str,
        immediate_cost: str,
        thematic_pressure: str,
    ) -> StoryEngine:
        if not alternative_actions:
            raise AutonomousError("At least one alternative action is required.")
        for field_name, value in (
            ("secret", secret),
            ("desire", desire),
            ("irreversible_choice", irreversible_choice),
            ("immediate_cost", immediate_cost),
            ("thematic_pressure", thematic_pressure),
        ):
            if not value or not str(value).strip():
                raise AutonomousError(f"Story engine field '{field_name}' cannot be empty.")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            engine_id = StoryEngineRepository.create(
                conn,
                book_id=book["id"],
                secret=secret.strip(),
                desire=desire.strip(),
                alternative_actions=json.dumps(alternative_actions, ensure_ascii=False),
                irreversible_choice=irreversible_choice.strip(),
                immediate_cost=immediate_cost.strip(),
                thematic_pressure=thematic_pressure.strip(),
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="story_engine",
                entity_id=engine_id,
                action="set",
                details=json.dumps(
                    {"alternative_actions_count": len(alternative_actions)},
                    ensure_ascii=False,
                ),
            )
            row = StoryEngineRepository.get_by_book(conn, book["id"])
        return StoryEngine.model_validate(dict(row))

    def get_story_engine(self, slug: str) -> StoryEngine | None:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            row = StoryEngineRepository.get_by_book(conn, book["id"])
            if row is None:
                return None
            return StoryEngine.model_validate(dict(row))

    # ------------------------------------------------------------------
    # Chapter Plan
    # ------------------------------------------------------------------
    def set_chapter_plan(
        self,
        slug: str,
        number: int,
        scenes: list[ScenePlan],
        status: str = "draft",
    ) -> ChapterPlan:
        if len(scenes) < 4 or len(scenes) > 6:
            raise AutonomousError(
                f"Chapter plan must have 4-6 scenes; got {len(scenes)}."
            )
        if status not in {"draft", "approved_for_writing"}:
            raise AutonomousError(f"Invalid plan status: {status}")
        for idx, scene in enumerate(scenes):
            for required in ("scene_ref", "goal", "obstacle", "choice", "cost", "ending_change"):
                value = getattr(scene, required, None)
                if not value or not str(value).strip():
                    raise AutonomousError(
                        f"Scene {idx + 1} is missing '{required}'."
                    )

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise AutonomousError(f"Chapter {number} not found in book {slug}.")

            plan_data = [s.model_dump() for s in scenes]
            plan_json = json.dumps(plan_data, ensure_ascii=False)
            plan_id = ChapterPlanRepository.create_or_update(
                conn, chapter["id"], plan_json, status
            )

            # Register any newly planted promises. Existing promises are never
            # auto-deleted or auto-abandoned here; use update-promise to abandon.
            for scene in scenes:
                for promise_text in scene.promises:
                    existing = conn.execute(
                        """SELECT id, status FROM promise_ledger
                           WHERE book_id = ? AND promise_text = ?""",
                        (book["id"], promise_text),
                    ).fetchone()
                    if existing is None:
                        PromiseRepository.create(
                            conn,
                            book_id=book["id"],
                            promise_text=promise_text,
                            planted_scene_ref=scene.scene_ref,
                        )

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter_plan",
                entity_id=plan_id,
                action="set",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "scene_count": len(scenes),
                        "status": status,
                    },
                    ensure_ascii=False,
                ),
            )
            row = ChapterPlanRepository.get_by_chapter(conn, chapter["id"])
        return ChapterPlan.model_validate(dict(row))

    def get_chapter_plan(self, slug: str, number: int) -> ChapterPlan | None:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise AutonomousError(f"Chapter {number} not found in book {slug}.")
            row = ChapterPlanRepository.get_by_chapter(conn, chapter["id"])
            if row is None:
                return None
            return ChapterPlan.model_validate(dict(row))

    # ------------------------------------------------------------------
    # Promise Ledger
    # ------------------------------------------------------------------
    def list_promises(self, slug: str) -> list[Promise]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            rows = PromiseRepository.list_by_book(conn, book["id"])
            return [Promise.model_validate(dict(r)) for r in rows]

    def update_promise_status(
        self,
        slug: str,
        promise_id: int,
        status: str,
        scene_ref: str,
        resolution_note: str | None = None,
    ) -> Promise:
        if status not in {"advanced", "resolved", "abandoned"}:
            raise AutonomousError(
                f"Invalid promise status transition: {status}. "
                "Use advanced, resolved, or abandoned."
            )
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            row = PromiseRepository.get_by_id(conn, promise_id)
            if row is None or row["book_id"] != book["id"]:
                raise AutonomousError(f"Promise {promise_id} not found in book {slug}.")
            PromiseRepository.update_status(
                conn, promise_id, status, scene_ref, resolution_note
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="promise",
                entity_id=promise_id,
                action=status,
                details=json.dumps(
                    {"scene_ref": scene_ref, "note": resolution_note},
                    ensure_ascii=False,
                ),
            )
            row = PromiseRepository.get_by_id(conn, promise_id)
        return Promise.model_validate(dict(row))

    # ------------------------------------------------------------------
    # Iteration Runs
    # ------------------------------------------------------------------
    def start_iteration_run(
        self,
        slug: str,
        number: int,
        writer_role: str,
        editor_verdict: str,
        blocking_issues: list[dict[str, Any]],
        revision_targets: list[str],
        word_count: int,
        status: str = "completed",
    ) -> IterationRun:
        if editor_verdict not in {
            "revision_required",
            "ready_for_human_editor_decision",
        }:
            raise AutonomousError(f"Invalid editor_verdict: {editor_verdict}")
        if status not in {"running", "completed", "failed"}:
            raise AutonomousError(f"Invalid iteration status: {status}")
        if word_count < 0:
            raise AutonomousError("word_count cannot be negative.")
        if not writer_role or not writer_role.strip():
            raise AutonomousError("writer_role cannot be empty.")
        if writer_role == "independent_reader_editor":
            raise AutonomousError(
                "writer_role cannot be 'independent_reader_editor'; "
                "that role is reserved for the independent editor."
            )

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise AutonomousError(f"Chapter {number} not found in book {slug}.")

            previous = IterationRepository.list_by_chapter(conn, chapter["id"])
            round_number = max((r["round_number"] for r in previous), default=0) + 1

            run_id = IterationRepository.create(
                conn,
                chapter_id=chapter["id"],
                round_number=round_number,
                writer_role=writer_role,
                editor_role="independent_reader_editor",
                editor_verdict=editor_verdict,
                blocking_issues=json.dumps(blocking_issues, ensure_ascii=False),
                revision_targets=json.dumps(revision_targets, ensure_ascii=False),
                word_count=word_count,
                status=status,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="iteration_run",
                entity_id=run_id,
                action="record",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "round_number": round_number,
                        "editor_verdict": editor_verdict,
                        "word_count": word_count,
                        "status": status,
                    },
                    ensure_ascii=False,
                ),
            )
            row = IterationRepository.get_by_id(conn, run_id)
        return IterationRun.model_validate(dict(row))

    def list_iteration_runs(self, slug: str, number: int) -> list[IterationRun]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise AutonomousError(f"Chapter {number} not found in book {slug}.")
            rows = IterationRepository.list_by_chapter(conn, chapter["id"])
            return [IterationRun.model_validate(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Auto-acceptance
    # ------------------------------------------------------------------
    def check_auto_acceptance(
        self, slug: str, number: int, max_rounds: int = 3
    ) -> AcceptanceResult:
        """Check whether the chapter revision can be recommended for human decision.

        This is a coverage gate, not a literature grade. It splits the result
        into five auditable dimensions so that "workflow complete" is never
        mistaken for "proofread complete", "prose-edited complete", or
        "publication ready".
        """
        from app.novel_forge.lint import lint_file
        from app.novel_forge.repository import RevisionRepository

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise AutonomousError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise AutonomousError(f"Chapter {number} not found in book {slug}.")

            checks: dict[str, Any] = {}
            current_revision_id = chapter["current_revision_id"]

            # ------------------------------------------------------------------
            # 1. Workflow coverage: required artifacts and hard process gates.
            # ------------------------------------------------------------------
            plan_row = ChapterPlanRepository.get_by_chapter(conn, chapter["id"])
            scene_count = 0
            if plan_row:
                scenes = json.loads(plan_row["plan_json"] or "[]")
                scene_count = len(scenes)
            word_count = 0
            if current_revision_id:
                rev = RevisionRepository.get_by_id(conn, current_revision_id)
                if rev:
                    body_path = self.root / rev["file_path"]
                    if body_path.exists():
                        word_count = _count_cjk_han(
                            body_path.read_text(encoding="utf-8")
                        )
            unresolved_plot_support = ResearchRepository.count_unresolved_plot_support(
                conn, book["id"]
            )
            bc_entries = conn.execute(
                """SELECT id, verification_ref FROM research_entries
                   WHERE book_id = ? AND confidence IN ('B', 'C')
                     AND allowed_use = 'plot_support'""",
                (book["id"],),
            ).fetchall()
            bc_without_a_ref = 0
            for e in bc_entries:
                ok = False
                if e["verification_ref"] is not None:
                    ref = ResearchRepository.get_by_id(conn, e["verification_ref"])
                    if (
                        ref is not None
                        and ref["book_id"] == book["id"]
                        and ref["confidence"] == "A"
                        and ref["verification_state"] == "verified"
                        and ref["allowed_use"] == "plot_support"
                    ):
                        ok = True
                if not ok:
                    bc_without_a_ref += 1
            open_promises = conn.execute(
                """SELECT COUNT(*) AS cnt FROM promise_ledger
                   WHERE book_id = ? AND status IN ('planted', 'advanced')""",
                (book["id"],),
            ).fetchone()["cnt"]
            runs = IterationRepository.list_by_chapter(conn, chapter["id"])
            iteration_count = len(runs)

            checks["has_plan"] = plan_row is not None
            checks["scene_count"] = scene_count
            checks["scene_count_ok"] = 4 <= scene_count <= 6
            checks["has_revision"] = current_revision_id is not None
            checks["word_count"] = word_count
            checks["word_count_ok"] = word_count >= 5000
            checks["unresolved_plot_support"] = unresolved_plot_support
            checks["unresolved_plot_support_ok"] = unresolved_plot_support == 0
            checks["bc_plot_support_count"] = len(bc_entries)
            checks["bc_plot_support_ok"] = bc_without_a_ref == 0
            checks["open_promises"] = open_promises
            checks["promises_ok"] = open_promises == 0
            checks["iteration_count"] = iteration_count
            checks["max_rounds"] = max_rounds
            checks["under_max_rounds"] = iteration_count < max_rounds
            checks["has_independent_edit_round"] = iteration_count >= 1

            workflow_coverage = (
                checks["has_plan"]
                and checks["scene_count_ok"]
                and checks["has_revision"]
                and checks["word_count_ok"]
                and checks["unresolved_plot_support_ok"]
                and checks["bc_plot_support_ok"]
                and checks["promises_ok"]
                and checks["has_independent_edit_round"]
            )
            checks["workflow_coverage"] = workflow_coverage

            # ------------------------------------------------------------------
            # 2. Proofread status: surface-level Chinese proofreading findings.
            # ------------------------------------------------------------------
            proofread_rules = {
                "question-mark-mismatch",
                "quote-consistency",
                "common-error",
            }
            prose_rules = {
                "rhythm-monotony",
                "mechanical-triplet",
                "explanatory-punchline",
            }
            proofread_count = 0
            prose_count = 0
            blocking_lint = 0
            if current_revision_id:
                rev = RevisionRepository.get_by_id(conn, current_revision_id)
                if rev:
                    body_path = self.root / rev["file_path"]
                    if body_path.exists():
                        lint_findings = lint_file(body_path)
                        for f in lint_findings:
                            if f.severity == "blocking":
                                blocking_lint += 1
                            if f.rule_code in proofread_rules:
                                proofread_count += 1
                            if f.rule_code in prose_rules:
                                prose_count += 1

            checks["blocking_lint"] = blocking_lint
            checks["proofread_findings"] = proofread_count
            checks["proofread_status"] = "clean" if proofread_count == 0 else "concerns"
            checks["prose_edit_findings"] = prose_count
            checks["prose_edit_status"] = "clean" if prose_count == 0 else "concerns"

            # ------------------------------------------------------------------
            # 3. Independent editorial status.
            # ------------------------------------------------------------------
            memo_status = "missing"
            memo_blocks = 0
            if current_revision_id:
                memo = EditorialMemoRepository.get_active_by_revision(
                    conn, chapter["id"], current_revision_id
                )
                if memo is not None:
                    memo_blocks = len(
                        json.loads(memo["blocking_issues"] or "[]")
                    )
                    if memo["verdict"] == "ready_for_editor_decision" and memo_blocks == 0:
                        memo_status = "ready"
                    elif memo["verdict"] == "revision_required" or memo_blocks > 0:
                        memo_status = "revision_required"
            checks["independent_editorial_status"] = memo_status
            checks["editorial_memo_blocking_issues"] = memo_blocks

            # ------------------------------------------------------------------
            # 4. Legacy S1/S2 review findings / reader reviews (still hard gates).
            # ------------------------------------------------------------------
            lint_counts = FindingRepository.lint_counts_for_revision(
                conn, current_revision_id
            )
            review_counts = FindingRepository.open_review_counts_for_revision(
                conn, current_revision_id
            )
            _, rr_severity = ReaderReviewRepository.open_counts_for_revision(
                conn, current_revision_id
            )
            checks["open_s1"] = review_counts["S1"] + rr_severity["S1"]
            checks["open_s2"] = review_counts["S2"] + rr_severity["S2"]
            checks["quality_gates_ok"] = (
                lint_counts["blocking"] == 0
                and review_counts["S1"] == 0
                and review_counts["S2"] == 0
                and rr_severity["S1"] == 0
                and rr_severity["S2"] == 0
            )

            # ------------------------------------------------------------------
            # 5. Publication eligibility: always false; never auto-publish.
            # ------------------------------------------------------------------
            checks["publication_eligibility"] = False

            # ------------------------------------------------------------------
            # Decision.
            # ------------------------------------------------------------------
            all_hard_checks = (
                workflow_coverage
                and checks["quality_gates_ok"]
                and memo_status == "ready"
            )
            all_quality_clean = (
                checks["proofread_status"] == "clean"
                and checks["prose_edit_status"] == "clean"
            )

            if all_hard_checks and all_quality_clean:
                decision = "autonomous_acceptance_complete"
                message = (
                    "Workflow coverage, independent editorial review, proofreading, "
                    "and prose-edit checks are all clean. Autonomous acceptance is complete. "
                    "This is still not a literary endorsement, market guarantee, or publication "
                    "approval. The user may choose to review or export through the normal "
                    "approval gate."
                )
            elif iteration_count >= max_rounds:
                decision = "failed_needs_human"
                message = (
                    f"Autonomous loop reached the maximum of {max_rounds} rounds "
                    "without passing all coverage checks. "
                    "自主循环停止，需要外部人工或Agent介入。"
                )
            else:
                decision = "revision_required"
                failures = [
                    name
                    for name, ok in {
                        "workflow_coverage": workflow_coverage,
                        "quality_gates_ok": checks["quality_gates_ok"],
                        "independent_editorial_ready": memo_status == "ready",
                        "proofread_clean": checks["proofread_status"] == "clean",
                        "prose_edit_clean": checks["prose_edit_status"] == "clean",
                    }.items()
                    if not ok
                ]
                message = (
                    "Coverage checks not yet passed. Failures: "
                    + ", ".join(failures)
                )

            return AcceptanceResult(
                decision=decision,
                checks=checks,
                iteration_count=iteration_count,
                max_rounds=max_rounds,
                message=message,
            )

    # ------------------------------------------------------------------
    # Git checkpoint
    # ------------------------------------------------------------------
    def git_checkpoint(self, slug: str, message: str) -> dict[str, Any]:
        """Create a scoped git checkpoint for the book's assets.

        Only files under library/<slug>/ and docs/<slug>/ (if it exists) are
        staged. data/ and global docs/ are never staged or committed.
        """
        import re

        book_dir = self.root / "library" / slug
        if not book_dir.exists():
            raise AutonomousError(f"Book library directory not found: {book_dir}")

        if not message or not message.strip():
            raise AutonomousError("Commit message cannot be empty.")
        if re.search(r"[\x00-\x1f]", message):
            raise AutonomousError(
                "Commit message contains control characters."
            )

        # Verify we are inside a git worktree.
        try:
            repo_proc = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AutonomousError(
                "git executable not found; cannot create checkpoint."
            ) from exc
        if repo_proc.returncode != 0 or repo_proc.stdout.strip() != "true":
            raise AutonomousError(
                f"Not inside a git worktree: {self.root}"
            )

        # Refuse to run if the index already contains staged changes.
        # This prevents a scoped checkpoint from accidentally committing
        # globally-staged files (data/, docs/, secrets, etc.).
        index_proc = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )
        if index_proc.returncode != 0:
            raise AutonomousError(
                "Git index is not empty. "
                "git-checkpoint refuses to commit while other files are staged, "
                "to avoid including out-of-scope changes. "
                "Commit or unstage the existing changes first; the index was not modified."
            )

        # Stage only book-scoped paths.
        allowed_paths = [str(book_dir)]
        book_docs_dir = self.root / "docs" / slug
        if book_docs_dir.exists():
            allowed_paths.append(str(book_docs_dir))

        for path in allowed_paths:
            subprocess.run(
                ["git", "add", "--", path],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                check=False,
            )

        # Check whether anything relevant was staged.
        diff_proc = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )
        if diff_proc.returncode == 0:
            return {
                "committed": False,
                "commit_hash": None,
                "message": "No changes to commit.",
            }

        commit_proc = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )
        if commit_proc.returncode != 0:
            raise AutonomousError(
                f"Git commit failed: {commit_proc.stderr.strip() or commit_proc.stdout.strip()}"
            )

        # Get short hash.
        hash_proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )
        commit_hash = hash_proc.stdout.strip() if hash_proc.returncode == 0 else None
        return {
            "committed": True,
            "commit_hash": commit_hash,
            "message": message,
        }


def _count_cjk_han(text: str) -> int:
    """Count CJK Unified Ideographs (Han characters) in text."""
    return len(re.findall(r"[\u4e00-\u9fff]", text))
