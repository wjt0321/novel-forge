"""Candidate-fact approval/rejection and canon-fact listing.

Extracted from service.py as a mixin. Expects self._conn(), self.root,
and path helpers from the inheriting NovelForgeService.
"""

import json
import sqlite3

from app.novel_forge.models import NovelForgeError
from app.novel_forge.repository import (
    AuditRepository,
    BookRepository,
    ChapterRepository,
    FactRepository,
)


class CanonMixin:
    """Candidate-fact workflow: add, approve, reject, list canon facts."""

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------
    def add_candidate_fact(
        self,
        slug: str,
        number: int,
        kind: str,
        subject: str,
        predicate: str,
        object: str,
        evidence: str,
    ) -> int:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            if chapter["current_revision_id"] is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; "
                    "add a revision before adding a candidate fact."
                )

            fact_id = FactRepository.add_candidate(
                conn,
                chapter_id=chapter["id"],
                revision_id=chapter["current_revision_id"],
                kind=kind,
                subject=subject,
                predicate=predicate,
                object=object,
                evidence=evidence,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="candidate_fact",
                entity_id=fact_id,
                action="add",
                details=json.dumps(
                    {"subject": subject, "predicate": predicate, "object": object},
                    ensure_ascii=False,
                ),
            )
            return fact_id

    def approve_fact(self, candidate_id: int, note: str | None = None) -> None:
        with self._conn() as conn:
            candidate = FactRepository.get_candidate(conn, candidate_id)
            if candidate is None:
                raise NovelForgeError(f"Candidate fact not found: {candidate_id}")
            if candidate["status"] != "pending":
                raise NovelForgeError(
                    f"Candidate fact {candidate_id} is already {candidate['status']}."
                )

            chapter = ChapterRepository.get_by_id(conn, candidate["chapter_id"])
            if chapter is None:
                raise NovelForgeError(
                    f"Chapter for candidate fact {candidate_id} no longer exists."
                )
            book_id = chapter["book_id"]

            existing = FactRepository.get_canon_by_subject_predicate_book(
                conn, book_id, candidate["subject"], candidate["predicate"]
            )
            if existing is not None:
                raise NovelForgeError(
                    f"Canon conflict in book: {candidate['subject']} "
                    f"{candidate['predicate']} already exists as {existing['object']}."
                )

            FactRepository.update_candidate_status(conn, candidate_id, "approved", note)
            canon_id = FactRepository.add_canon(
                conn,
                source_candidate_id=candidate_id,
                book_id=book_id,
                chapter_id=candidate["chapter_id"],
                revision_id=candidate["revision_id"],
                kind=candidate["kind"],
                subject=candidate["subject"],
                predicate=candidate["predicate"],
                object=candidate["object"],
                evidence=candidate["evidence"],
            )

            AuditRepository.add(
                conn,
                book_id=book_id,
                entity_type="canon_fact",
                entity_id=canon_id,
                action="approve",
                details=json.dumps(
                    {
                        "source_candidate_id": candidate_id,
                        "subject": candidate["subject"],
                        "predicate": candidate["predicate"],
                        "object": candidate["object"],
                        "note": note,
                    },
                    ensure_ascii=False,
                ),
            )

    def reject_fact(self, candidate_id: int, note: str | None = None) -> None:
        with self._conn() as conn:
            candidate = FactRepository.get_candidate(conn, candidate_id)
            if candidate is None:
                raise NovelForgeError(f"Candidate fact not found: {candidate_id}")
            if candidate["status"] != "pending":
                raise NovelForgeError(
                    f"Candidate fact {candidate_id} is already {candidate['status']}."
                )

            FactRepository.update_candidate_status(conn, candidate_id, "rejected", note)
            cur = conn.execute(
                "SELECT book_id FROM chapters WHERE id = ?", (candidate["chapter_id"],)
            )
            book_id = cur.fetchone()["book_id"]
            AuditRepository.add(
                conn,
                book_id=book_id,
                entity_type="candidate_fact",
                entity_id=candidate_id,
                action="reject",
                details=json.dumps({"note": note}, ensure_ascii=False),
            )
    # ------------------------------------------------------------------
    # Canon helpers for API
    # ------------------------------------------------------------------
    def list_canon_facts_for_chapter(
        self, slug: str, number: int
    ) -> list[sqlite3.Row]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            return FactRepository.list_canon_by_chapter(conn, chapter["id"])
