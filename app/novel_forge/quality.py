"""Lint, review, and approval gates for the Novel Forge service.

Extracted from service.py as a mixin. Expects self._conn(), self.root,
and path helpers from the inheriting NovelForgeService.
"""

import json
import shutil
from datetime import datetime, timezone

from app.novel_forge.lint import lint_file
from app.novel_forge.models import (
    BlindExperienceSummary,
    Chapter,
    ChapterState,
    NovelForgeError,
    ReaderReview,
    ReaderReviewSummary,
    ReviewFinding,
    ReviewResult,
    ReviewVerdict,
)
from app.novel_forge.repository import (
    AuditRepository,
    BlindExperienceRepository,
    BookRepository,
    ChapterRepository,
    FindingRepository,
    ReaderReviewRepository,
    RevisionRepository,
)


# State-machine guards. Each operation verifies the chapter is in an
# allowed state before mutating it, preventing skip-level approvals.
_ALLOWED_LINT_STATES = {"draft", "linted", "revised", "reviewed", "revision_requested"}
_ALLOWED_REVIEW_STATES = {"linted", "revised", "reviewed"}
_ALLOWED_APPROVE_STATES = {"reviewed"}
_ALLOWED_ROLLBACK_STATES = {
    "linted",
    "reviewed",
    "revision_requested",
    "revised",
    "approved",
    "exported",
}


class QualityMixin:
    """Lint, review-finding, review, approve, and rollback gates."""

    def lint_chapter(self, slug: str, number: int) -> tuple[int, int]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            current_state = chapter["state"]
            current_revision_id = chapter["current_revision_id"]
            if current_revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no revision to lint."
                )
            if current_state == "approved":
                raise NovelForgeError(
                    f"Chapter {number} is approved. Use write-revision with "
                    "--reopen-reason before linting."
                )
            if current_state not in _ALLOWED_LINT_STATES:
                raise NovelForgeError(
                    f"Cannot lint chapter {number} from state {current_state}."
                )

            rev = RevisionRepository.get_by_id(conn, current_revision_id)
            rev_path = self.root / rev["file_path"]
            findings = lint_file(rev_path)

            # Clear previous unresolved lint findings for this revision.
            conn.execute(
                "UPDATE lint_findings SET resolved = 1 WHERE revision_id = ? AND resolved = 0",
                (current_revision_id,),
            )

            blocking = 0
            advisory = 0
            for f in findings:
                if f.rule_code == "colon-density":
                    continue
                FindingRepository.add_lint_finding(
                    conn,
                    revision_id=current_revision_id,
                    rule_code=f.rule_code,
                    severity=f.severity,
                    line_number=f.line_number,
                    message=f.message,
                    evidence=f.evidence,
                )
                if f.severity == "blocking":
                    blocking += 1
                else:
                    advisory += 1

            # A successful lint run always advances the chapter to linted,
            # regardless of whether any findings were reported.
            ChapterRepository.set_state(conn, chapter["id"], "linted")

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="lint",
                details=json.dumps(
                    {
                        "revision_id": current_revision_id,
                        "blocking": blocking,
                        "advisory": advisory,
                    }
                ),
            )

        return blocking, advisory

    # ------------------------------------------------------------------
    # Review findings
    # ------------------------------------------------------------------
    def add_finding(
        self,
        slug: str,
        number: int,
        perspective: str,
        severity: str,
        location: str,
        evidence: str,
        issue: str,
        fix: str,
    ) -> int:
        if perspective not in {"structure", "character", "narrative", "continuity"}:
            raise NovelForgeError(f"Invalid perspective: {perspective}")
        if severity not in {"S1", "S2", "S3", "S4"}:
            raise NovelForgeError(f"Invalid severity: {severity}")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            if chapter["current_revision_id"] is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; add a revision before adding findings."
                )
            if chapter["state"] == "approved":
                raise NovelForgeError(
                    f"Chapter {number} is approved. Use write-revision with "
                    "--reopen-reason before adding findings."
                )

            finding_id = FindingRepository.add_review_finding(
                conn,
                chapter_id=chapter["id"],
                revision_id=chapter["current_revision_id"],
                perspective=perspective,
                severity=severity,
                location=location,
                evidence=evidence,
                issue=issue,
                fix=fix,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="finding",
                entity_id=finding_id,
                action="add",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "perspective": perspective,
                        "severity": severity,
                    },
                    ensure_ascii=False,
                ),
            )
            return finding_id

    def resolve_finding(self, finding_id: int, note: str) -> None:
        with self._conn() as conn:
            finding = FindingRepository.get_review_finding(conn, finding_id)
            if finding is None:
                raise NovelForgeError(f"Finding not found: {finding_id}")
            if finding["resolved"]:
                raise NovelForgeError(
                    f"Finding {finding_id} is already resolved."
                )

            FindingRepository.resolve_review_finding(conn, finding_id, note)
            cur = conn.execute(
                "SELECT book_id FROM chapters WHERE id = ?",
                (finding["chapter_id"],),
            )
            row = cur.fetchone()
            if row is None:  # pragma: no cover - foreign key should prevent this
                raise NovelForgeError(
                    f"Chapter for finding {finding_id} no longer exists."
                )
            AuditRepository.add(
                conn,
                book_id=row["book_id"],
                entity_type="finding",
                entity_id=finding_id,
                action="resolve",
                details=json.dumps({"note": note}, ensure_ascii=False),
            )

    # ------------------------------------------------------------------
    # Review & approval
    # ------------------------------------------------------------------
    def review_chapter(self, slug: str, number: int) -> ReviewResult:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            current_state = chapter["state"]
            if current_state not in _ALLOWED_REVIEW_STATES:
                raise NovelForgeError(
                    f"Review requires chapter state linted, revised, or reviewed. "
                    f"Current state: {current_state}."
                )

            current_revision_id = chapter["current_revision_id"]
            lint_counts = FindingRepository.lint_counts_for_revision(
                conn, current_revision_id
            )
            review_counts = FindingRepository.open_review_counts_for_revision(
                conn, current_revision_id
            )
            open_findings = FindingRepository.list_open_by_revision(
                conn, current_revision_id
            )

            # Reader review ledger for the current revision.
            rr_lens_counts, rr_severity_counts = ReaderReviewRepository.open_counts_for_revision(
                conn, current_revision_id
            )
            open_reader_reviews = ReaderReviewRepository.list_open_by_revision(
                conn, current_revision_id
            )

            # Narrative editorial memo gate.
            active_memo = self._active_memo_for_current_revision(conn, chapter)
            memo_status = self._editorial_memo_status_from_row(active_memo)
            memo_blocks = (
                active_memo is None
                or active_memo["verdict"] != "ready_for_editor_decision"
                or len(json.loads(active_memo["blocking_issues"] or "[]")) > 0
            )

            blind_row = BlindExperienceRepository.get_active_by_revision(
                conn, chapter["id"], current_revision_id
            )
            blind_summary = self._blind_experience_summary_from_row(blind_row)
            blind_blocks = not blind_summary.passes

            if review_counts["S1"] > 0 or rr_severity_counts["S1"] > 0:
                verdict = ReviewVerdict.REJECT
            elif (
                review_counts["S2"] > 0
                or rr_severity_counts["S2"] > 0
                or lint_counts["blocking"] > 0
                or memo_blocks
                or blind_blocks
            ):
                verdict = ReviewVerdict.CONCERNS
            else:
                verdict = ReviewVerdict.APPROVE

            ChapterRepository.set_state(conn, chapter["id"], "reviewed")
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="review",
                details=json.dumps(
                    {
                        "verdict": verdict.value,
                        "severity_counts": review_counts,
                        "lint_counts": lint_counts,
                        "reader_review_severity_counts": rr_severity_counts,
                        "editorial_memo_id": memo_status.get("memo_id"),
                        "editorial_memo_verdict": memo_status.get("verdict"),
                        "editorial_memo_blocking_issues": memo_status.get(
                            "blocking_issue_count", 0
                        ),
                        "blind_experience_review_id": blind_summary.review_id,
                        "blind_experience_passes": blind_summary.passes,
                        "blind_experience_blocking_issues": blind_summary.blocking_issue_count,
                        "blind_experience_knowledge_gaps": blind_summary.knowledge_gap_count,
                    },
                    ensure_ascii=False,
                ),
            )

            from app.novel_forge.models import ReviewFinding

            return ReviewResult(
                verdict=verdict,
                severity_counts=review_counts,
                lint_counts=lint_counts,
                findings=[ReviewFinding.model_validate(dict(r)) for r in open_findings],
                reader_review_summary=ReaderReviewSummary(
                    lens_counts=rr_lens_counts,
                    severity_counts=rr_severity_counts,
                    total_open=sum(rr_severity_counts.values()),
                ),
                reader_reviews=[
                    ReaderReview.model_validate(dict(r)) for r in open_reader_reviews
                ],
                editorial_memo_status=memo_status,
                blind_experience_status=blind_summary.model_dump(mode="json"),
            )

    def approve_chapter(self, slug: str, number: int, note: str) -> Chapter:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            current_state = chapter["state"]
            if current_state not in _ALLOWED_APPROVE_STATES:
                raise NovelForgeError(
                    f"Approve requires chapter state reviewed. Current state: {current_state}."
                )

            current_revision_id = chapter["current_revision_id"]
            if current_revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no revision to approve."
                )

            lint_counts = FindingRepository.lint_counts_for_revision(
                conn, current_revision_id
            )
            if lint_counts["blocking"] > 0:
                raise NovelForgeError(
                    "Cannot approve: unresolved blocking lint findings on the current revision."
                )

            review_counts = FindingRepository.open_review_counts_for_revision(
                conn, current_revision_id
            )
            if review_counts["S1"] > 0 or review_counts["S2"] > 0:
                raise NovelForgeError(
                    "Cannot approve: unresolved S1/S2 review findings on the current revision."
                )

            _, rr_severity_counts = ReaderReviewRepository.open_counts_for_revision(
                conn, current_revision_id
            )
            if rr_severity_counts["S1"] > 0 or rr_severity_counts["S2"] > 0:
                raise NovelForgeError(
                    "Cannot approve: unresolved S1/S2 reader reviews on the current revision."
                )

            # Narrative editorial memo gate.
            active_memo = self._active_memo_for_current_revision(conn, chapter)
            if active_memo is None:
                raise NovelForgeError(
                    "Cannot approve: no active editorial memo for the current revision. "
                    "A coverage review must be recorded before approval."
                )
            if active_memo["verdict"] != "ready_for_editor_decision":
                raise NovelForgeError(
                    "Cannot approve: editorial memo verdict is not "
                    "'ready_for_editor_decision'."
                )
            blocking_issue_count = len(
                json.loads(active_memo["blocking_issues"] or "[]")
            )
            if blocking_issue_count > 0:
                raise NovelForgeError(
                    "Cannot approve: editorial memo has unresolved blocking issues."
                )

            blind_row = BlindExperienceRepository.get_active_by_revision(
                conn, chapter["id"], current_revision_id
            )
            blind_summary = self._blind_experience_summary_from_row(blind_row)
            if not blind_summary.passes:
                raise NovelForgeError(
                    "Cannot approve: no passing blind experience review for the "
                    "current revision. A prose-only reader must reconstruct space, "
                    "body, action constraints, emotion, dialogue change, and images."
                )

            ChapterRepository.set_state(conn, chapter["id"], "approved")
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="approve",
                details=json.dumps({"note": note}, ensure_ascii=False),
            )
            row = ChapterRepository.get_by_id(conn, chapter["id"])

        return Chapter.model_validate(dict(row))
    def rollback_chapter(
        self, slug: str, number: int, revision_id: int, note: str
    ) -> Chapter:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            if chapter["current_revision_id"] is None:
                raise NovelForgeError(
                    f"Chapter {number} has no revision to roll back."
                )
            if chapter["state"] == "draft":
                raise NovelForgeError(
                    f"Rollback is not allowed from draft state for chapter {number}."
                )

            old_rev = RevisionRepository.get_by_id(conn, revision_id)
            if old_rev is None or old_rev["chapter_id"] != chapter["id"]:
                raise NovelForgeError(
                    f"Revision {revision_id} does not belong to chapter {number}."
                )

            old_path = self.root / old_rev["file_path"]
            if not old_path.exists():
                raise NovelForgeError(
                    f"Revision file missing: {old_rev['file_path']}"
                )

            revs_dir = self._revisions_dir(slug, number)
            revs_dir.mkdir(parents=True, exist_ok=True)
            revision_number = ChapterRepository.get_next_revision_number(
                conn, chapter["id"]
            )
            content_hash = self._hash_file(old_path)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            dest_name = f"{revision_number:04d}-{ts}-{content_hash[:16]}.md"
            dest_path = revs_dir / dest_name
            shutil.copy2(old_path, dest_path)

            new_rev_id = RevisionRepository.create(
                conn,
                chapter_id=chapter["id"],
                revision_number=revision_number,
                file_path=str(dest_path.relative_to(self.root)),
                content_hash=content_hash,
                note=f"rollback from revision {revision_id}: {note}",
            )
            ChapterRepository.update_current_revision(
                conn, chapter["id"], new_rev_id, content_hash
            )
            ChapterRepository.set_state(conn, chapter["id"], "revised")

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="rollback",
                details=json.dumps(
                    {
                        "from_revision_id": revision_id,
                        "new_revision_id": new_rev_id,
                        "note": note,
                    },
                    ensure_ascii=False,
                ),
            )
            row = ChapterRepository.get_by_id(conn, chapter["id"])

        return Chapter.model_validate(dict(row))

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
