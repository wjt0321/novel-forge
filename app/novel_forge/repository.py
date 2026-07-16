"""Low-level database operations for Novel Forge.

All functions accept an open sqlite3.Connection and use the caller's
transaction boundary.
"""

import sqlite3


class BookRepository:
    @staticmethod
    def create(conn: sqlite3.Connection, slug: str, title: str) -> int:
        cur = conn.execute(
            "INSERT INTO books (slug, title) VALUES (?, ?)",
            (slug, title),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_slug(conn: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
        cur = conn.execute("SELECT * FROM books WHERE slug = ?", (slug,))
        return cur.fetchone()

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, book_id: int) -> sqlite3.Row | None:
        cur = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        return cur.fetchone()

    @staticmethod
    def list(conn: sqlite3.Connection) -> list[sqlite3.Row]:
        cur = conn.execute("SELECT * FROM books ORDER BY slug")
        return cur.fetchall()


class ChapterRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection, book_id: int, number: int, title: str
    ) -> int:
        cur = conn.execute(
            "INSERT INTO chapters (book_id, number, title) VALUES (?, ?, ?)",
            (book_id, number, title),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, chapter_id: int) -> sqlite3.Row | None:
        cur = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
        return cur.fetchone()

    @staticmethod
    def get_by_book_and_number(
        conn: sqlite3.Connection, book_id: int, number: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM chapters WHERE book_id = ? AND number = ?",
            (book_id, number),
        )
        return cur.fetchone()

    @staticmethod
    def list_by_book(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM chapters WHERE book_id = ? ORDER BY number",
            (book_id,),
        )
        return cur.fetchall()

    @staticmethod
    def update_current_revision(
        conn: sqlite3.Connection,
        chapter_id: int,
        revision_id: int | None,
        content_hash: str | None,
    ) -> None:
        conn.execute(
            """UPDATE chapters
               SET current_revision_id = ?, current_hash = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (revision_id, content_hash, chapter_id),
        )

    @staticmethod
    def set_state(
        conn: sqlite3.Connection, chapter_id: int, state: str
    ) -> None:
        conn.execute(
            "UPDATE chapters SET state = ?, updated_at = datetime('now') WHERE id = ?",
            (state, chapter_id),
        )

    @staticmethod
    def get_next_revision_number(
        conn: sqlite3.Connection, chapter_id: int
    ) -> int:
        cur = conn.execute(
            "SELECT COALESCE(MAX(revision_number), 0) + 1 FROM revisions WHERE chapter_id = ?",
            (chapter_id,),
        )
        return cur.fetchone()[0]


class RevisionRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        chapter_id: int,
        revision_number: int,
        file_path: str,
        content_hash: str,
        note: str | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO revisions
               (chapter_id, revision_number, file_path, content_hash, note)
               VALUES (?, ?, ?, ?, ?)""",
            (chapter_id, revision_number, file_path, content_hash, note),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, revision_id: int) -> sqlite3.Row | None:
        cur = conn.execute("SELECT * FROM revisions WHERE id = ?", (revision_id,))
        return cur.fetchone()

    @staticmethod
    def list_by_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM revisions WHERE chapter_id = ? ORDER BY revision_number",
            (chapter_id,),
        )
        return cur.fetchall()


class FindingRepository:
    @staticmethod
    def add_lint_finding(
        conn: sqlite3.Connection,
        revision_id: int,
        rule_code: str,
        severity: str,
        line_number: int | None,
        message: str,
        evidence: str | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO lint_findings
               (revision_id, rule_code, severity, line_number, message, evidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (revision_id, rule_code, severity, line_number, message, evidence),
        )
        return cur.lastrowid

    @staticmethod
    def lint_counts_for_revision(
        conn: sqlite3.Connection, revision_id: int | None
    ) -> dict[str, int]:
        """Return unresolved lint counts for a specific revision only."""
        counts = {"blocking": 0, "advisory": 0}
        if revision_id is None:
            return counts
        cur = conn.execute(
            """SELECT severity, COUNT(*) AS cnt
               FROM lint_findings
               WHERE revision_id = ? AND resolved = 0
               GROUP BY severity""",
            (revision_id,),
        )
        for row in cur.fetchall():
            counts[row["severity"]] = row["cnt"]
        return counts

    @staticmethod
    def add_review_finding(
        conn: sqlite3.Connection,
        chapter_id: int,
        perspective: str,
        severity: str,
        location: str,
        evidence: str,
        issue: str,
        fix: str,
        revision_id: int | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO review_findings
               (chapter_id, revision_id, perspective, severity, location, evidence, issue, fix)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chapter_id,
                revision_id,
                perspective,
                severity,
                location,
                evidence,
                issue,
                fix,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_review_finding(
        conn: sqlite3.Connection, finding_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM review_findings WHERE id = ?", (finding_id,)
        )
        return cur.fetchone()

    @staticmethod
    def resolve_review_finding(
        conn: sqlite3.Connection, finding_id: int, note: str
    ) -> None:
        conn.execute(
            """UPDATE review_findings
               SET resolved = 1, resolution_note = ?, resolved_at = datetime('now')
               WHERE id = ?""",
            (note, finding_id),
        )

    @staticmethod
    def resolve_open_by_chapter_and_location(
        conn: sqlite3.Connection,
        chapter_id: int | None,
        location: str,
        perspective: str,
        note: str,
        book_id: int | None = None,
    ) -> int:
        """Resolve all open findings for a chapter/location/perspective.

        Cross-chapter resolution requires book_id so findings from another
        book cannot be closed by a matching synthetic location. Returns the
        number of rows updated.
        """
        if chapter_id is None:
            if book_id is None:
                raise ValueError("book_id is required when chapter_id is None")
            cur = conn.execute(
                """UPDATE review_findings
                   SET resolved = 1, resolution_note = ?, resolved_at = datetime('now')
                   WHERE chapter_id IN (
                           SELECT id FROM chapters WHERE book_id = ?
                       )
                     AND location = ? AND perspective = ? AND resolved = 0""",
                (note, book_id, location, perspective),
            )
        else:
            cur = conn.execute(
                """UPDATE review_findings
                   SET resolved = 1, resolution_note = ?, resolved_at = datetime('now')
                   WHERE chapter_id = ? AND location = ? AND perspective = ? AND resolved = 0""",
                (note, chapter_id, location, perspective),
            )
        return cur.rowcount

    @staticmethod
    def open_review_counts_for_revision(
        conn: sqlite3.Connection, revision_id: int | None
    ) -> dict[str, int]:
        """Return unresolved review counts for a specific revision only."""
        counts = {"S1": 0, "S2": 0, "S3": 0, "S4": 0}
        if revision_id is None:
            return counts
        cur = conn.execute(
            """SELECT severity, COUNT(*) AS cnt
               FROM review_findings
               WHERE revision_id = ? AND resolved = 0
               GROUP BY severity""",
            (revision_id,),
        )
        for row in cur.fetchall():
            counts[row["severity"]] = row["cnt"]
        return counts

    @staticmethod
    def list_open_by_revision(
        conn: sqlite3.Connection, revision_id: int | None
    ) -> list[sqlite3.Row]:
        if revision_id is None:
            return []
        cur = conn.execute(
            """SELECT * FROM review_findings
               WHERE revision_id = ? AND resolved = 0
               ORDER BY severity, id""",
            (revision_id,),
        )
        return cur.fetchall()


class FactRepository:
    @staticmethod
    def add_candidate(
        conn: sqlite3.Connection,
        chapter_id: int,
        kind: str,
        subject: str,
        predicate: str,
        object: str,
        evidence: str,
        revision_id: int | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO candidate_facts
               (chapter_id, revision_id, kind, subject, predicate, object, evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                chapter_id,
                revision_id,
                kind,
                subject,
                predicate,
                object,
                evidence,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_candidate(conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM candidate_facts WHERE id = ?", (candidate_id,)
        )
        return cur.fetchone()

    @staticmethod
    def update_candidate_status(
        conn: sqlite3.Connection,
        candidate_id: int,
        status: str,
        note: str | None = None,
    ) -> None:
        conn.execute(
            """UPDATE candidate_facts
               SET status = ?, resolution_note = ?, resolved_at = datetime('now')
               WHERE id = ?""",
            (status, note, candidate_id),
        )

    @staticmethod
    def add_canon(
        conn: sqlite3.Connection,
        source_candidate_id: int | None,
        book_id: int,
        chapter_id: int,
        kind: str,
        subject: str,
        predicate: str,
        object: str,
        evidence: str,
        revision_id: int | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO canon_facts
               (source_candidate_id, book_id, chapter_id, revision_id, kind, subject, predicate, object, evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_candidate_id,
                book_id,
                chapter_id,
                revision_id,
                kind,
                subject,
                predicate,
                object,
                evidence,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_canon_by_subject_predicate_book(
        conn: sqlite3.Connection, book_id: int, subject: str, predicate: str
    ) -> sqlite3.Row | None:
        """Return a canon fact only if it belongs to the given book."""
        cur = conn.execute(
            """SELECT cf.* FROM canon_facts cf
               JOIN chapters c ON cf.chapter_id = c.id
               WHERE c.book_id = ? AND cf.subject = ? AND cf.predicate = ?""",
            (book_id, subject, predicate),
        )
        return cur.fetchone()

    @staticmethod
    def list_canon_by_book(
        conn: sqlite3.Connection, book_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            """SELECT cf.* FROM canon_facts cf
               JOIN chapters c ON cf.chapter_id = c.id
               WHERE c.book_id = ?
               ORDER BY cf.subject, cf.predicate""",
            (book_id,),
        )
        return cur.fetchall()

    @staticmethod
    def list_canon_by_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM canon_facts WHERE chapter_id = ? ORDER BY subject, predicate",
            (chapter_id,),
        )
        return cur.fetchall()


class AuditRepository:
    @staticmethod
    def add(
        conn: sqlite3.Connection,
        book_id: int,
        entity_type: str,
        action: str,
        entity_id: int | None = None,
        details: str | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO audit_events
               (book_id, entity_type, entity_id, action, details)
               VALUES (?, ?, ?, ?, ?)""",
            (book_id, entity_type, entity_id, action, details),
        )
        return cur.lastrowid

    @staticmethod
    def list(
        conn: sqlite3.Connection, book_id: int, limit: int | None = None
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM audit_events WHERE book_id = ? ORDER BY id DESC"
        params: tuple = (book_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (book_id, limit)
        cur = conn.execute(sql, params)
        return cur.fetchall()


class ExportRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        book_id: int,
        format: str,
        status: str,
        file_path: str | None = None,
        manifest_path: str | None = None,
        message: str | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO exports
               (book_id, format, file_path, manifest_path, status, message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (book_id, format, file_path, manifest_path, status, message),
        )
        return cur.lastrowid

    @staticmethod
    def list(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM exports WHERE book_id = ? ORDER BY id DESC",
            (book_id,),
        )
        return cur.fetchall()


class VoiceBibleRepository:
    @staticmethod
    def create_revision(
        conn: sqlite3.Connection,
        book_id: int,
        revision_number: int,
        file_path: str,
        content_hash: str,
        note: str | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO voice_bible_revisions
               (book_id, revision_number, file_path, content_hash, note)
               VALUES (?, ?, ?, ?, ?)""",
            (book_id, revision_number, file_path, content_hash, note),
        )
        return cur.lastrowid

    @staticmethod
    def get_revision(
        conn: sqlite3.Connection, revision_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM voice_bible_revisions WHERE id = ?", (revision_id,)
        )
        return cur.fetchone()

    @staticmethod
    def get_current(
        conn: sqlite3.Connection, book_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM voice_bibles WHERE book_id = ?", (book_id,)
        )
        return cur.fetchone()

    @staticmethod
    def update_current(
        conn: sqlite3.Connection,
        book_id: int,
        revision_id: int,
        file_path: str,
        content_hash: str,
    ) -> None:
        conn.execute(
            """INSERT INTO voice_bibles (book_id, current_revision_id, current_file_path, current_hash, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(book_id) DO UPDATE SET
                   current_revision_id = excluded.current_revision_id,
                   current_file_path = excluded.current_file_path,
                   current_hash = excluded.current_hash,
                   updated_at = excluded.updated_at""",
            (book_id, revision_id, file_path, content_hash),
        )

    @staticmethod
    def list_revisions(
        conn: sqlite3.Connection, book_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM voice_bible_revisions WHERE book_id = ? ORDER BY revision_number",
            (book_id,),
        )
        return cur.fetchall()

    @staticmethod
    def get_next_revision_number(
        conn: sqlite3.Connection, book_id: int
    ) -> int:
        cur = conn.execute(
            "SELECT COALESCE(MAX(revision_number), 0) + 1 FROM voice_bible_revisions WHERE book_id = ?",
            (book_id,),
        )
        return cur.fetchone()[0]


class SceneContractRepository:
    @staticmethod
    def create_revision(
        conn: sqlite3.Connection,
        chapter_id: int,
        revision_number: int,
        file_path: str,
        content_hash: str,
        note: str | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO scene_contract_revisions
               (chapter_id, revision_number, file_path, content_hash, note)
               VALUES (?, ?, ?, ?, ?)""",
            (chapter_id, revision_number, file_path, content_hash, note),
        )
        return cur.lastrowid

    @staticmethod
    def get_revision(
        conn: sqlite3.Connection, revision_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM scene_contract_revisions WHERE id = ?", (revision_id,)
        )
        return cur.fetchone()

    @staticmethod
    def get_current(
        conn: sqlite3.Connection, chapter_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM scene_contracts WHERE chapter_id = ?", (chapter_id,)
        )
        return cur.fetchone()

    @staticmethod
    def update_current(
        conn: sqlite3.Connection,
        chapter_id: int,
        revision_id: int,
        file_path: str,
        content_hash: str,
    ) -> None:
        conn.execute(
            """INSERT INTO scene_contracts (chapter_id, current_revision_id, current_file_path, current_hash, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(chapter_id) DO UPDATE SET
                   current_revision_id = excluded.current_revision_id,
                   current_file_path = excluded.current_file_path,
                   current_hash = excluded.current_hash,
                   updated_at = excluded.updated_at""",
            (chapter_id, revision_id, file_path, content_hash),
        )

    @staticmethod
    def list_revisions(
        conn: sqlite3.Connection, chapter_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM scene_contract_revisions WHERE chapter_id = ? ORDER BY revision_number",
            (chapter_id,),
        )
        return cur.fetchall()

    @staticmethod
    def get_next_revision_number(
        conn: sqlite3.Connection, chapter_id: int
    ) -> int:
        cur = conn.execute(
            "SELECT COALESCE(MAX(revision_number), 0) + 1 FROM scene_contract_revisions WHERE chapter_id = ?",
            (chapter_id,),
        )
        return cur.fetchone()[0]


class ReaderReviewRepository:
    @staticmethod
    def add(
        conn: sqlite3.Connection,
        chapter_id: int,
        revision_id: int | None,
        lens: str,
        severity: str,
        location_start: int,
        location_end: int,
        evidence: str,
        reader_effect: str,
        revision_intent: str,
        actor: str = "human_or_agent_review",
    ) -> int:
        cur = conn.execute(
            """INSERT INTO reader_reviews
               (chapter_id, revision_id, lens, severity, location_start, location_end,
                evidence, reader_effect, revision_intent, actor)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chapter_id,
                revision_id,
                lens,
                severity,
                location_start,
                location_end,
                evidence,
                reader_effect,
                revision_intent,
                actor,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection, review_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM reader_reviews WHERE id = ?", (review_id,)
        )
        return cur.fetchone()

    @staticmethod
    def resolve(
        conn: sqlite3.Connection, review_id: int, note: str
    ) -> None:
        conn.execute(
            """UPDATE reader_reviews
               SET status = 'resolved', resolution_note = ?, resolved_at = datetime('now')
               WHERE id = ?""",
            (note, review_id),
        )

    @staticmethod
    def open_counts_for_revision(
        conn: sqlite3.Connection, revision_id: int | None
    ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
        """Return (lens_counts, severity_counts) for open reviews on a revision."""
        lens_counts: dict[str, dict[str, int]] = {}
        severity_counts: dict[str, int] = {"S1": 0, "S2": 0, "S3": 0, "S4": 0}
        if revision_id is None:
            return lens_counts, severity_counts
        cur = conn.execute(
            """SELECT lens, severity, COUNT(*) AS cnt
               FROM reader_reviews
               WHERE revision_id = ? AND status = 'open'
               GROUP BY lens, severity""",
            (revision_id,),
        )
        for row in cur.fetchall():
            lens = row["lens"]
            severity = row["severity"]
            severity_counts[severity] += row["cnt"]
            lens_counts.setdefault(lens, {"S1": 0, "S2": 0, "S3": 0, "S4": 0})
            lens_counts[lens][severity] += row["cnt"]
        return lens_counts, severity_counts

    @staticmethod
    def list_open_by_revision(
        conn: sqlite3.Connection, revision_id: int | None
    ) -> list[sqlite3.Row]:
        if revision_id is None:
            return []
        cur = conn.execute(
            """SELECT * FROM reader_reviews
               WHERE revision_id = ? AND status = 'open'
               ORDER BY severity, id""",
            (revision_id,),
        )
        return cur.fetchall()


class EditorialMemoRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        chapter_id: int,
        revision_id: int,
        reviewer_role: str,
        narrative_necessity: str,
        character_agency: str,
        detail_selection: str,
        causal_chain: str,
        prose_observation: str,
        verdict: str,
        blocking_issues: str,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO editorial_memos
               (chapter_id, revision_id, reviewer_role, narrative_necessity,
                character_agency, detail_selection, causal_chain, prose_observation,
                verdict, blocking_issues)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chapter_id,
                revision_id,
                reviewer_role,
                narrative_necessity,
                character_agency,
                detail_selection,
                causal_chain,
                prose_observation,
                verdict,
                blocking_issues,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection, memo_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute("SELECT * FROM editorial_memos WHERE id = ?", (memo_id,))
        return cur.fetchone()

    @staticmethod
    def get_active_by_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            """SELECT * FROM editorial_memos
               WHERE chapter_id = ? AND superseded_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (chapter_id,),
        )
        return cur.fetchone()

    @staticmethod
    def get_active_by_revision(
        conn: sqlite3.Connection, chapter_id: int, revision_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            """SELECT * FROM editorial_memos
               WHERE chapter_id = ? AND revision_id = ? AND superseded_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (chapter_id, revision_id),
        )
        return cur.fetchone()

    @staticmethod
    def supersede_active_for_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> None:
        conn.execute(
            """UPDATE editorial_memos
               SET superseded_at = datetime('now')
               WHERE chapter_id = ? AND superseded_at IS NULL""",
            (chapter_id,),
        )

    @staticmethod
    def list_by_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            """SELECT * FROM editorial_memos
               WHERE chapter_id = ?
               ORDER BY created_at DESC""",
            (chapter_id,),
        )
        return cur.fetchall()


class BlindExperienceRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        chapter_id: int,
        revision_id: int,
        spatial_reconstruction: str,
        body_position_and_contact: str,
        action_constraints: str,
        emotional_trajectory: str,
        dialogue_dynamics: str,
        memorable_images: str,
        knowledge_gaps: str,
        verdict: str,
        blocking_issues: str,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO blind_experience_reviews
               (chapter_id, revision_id, spatial_reconstruction,
                body_position_and_contact, action_constraints,
                emotional_trajectory, dialogue_dynamics, memorable_images,
                knowledge_gaps, verdict, blocking_issues)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chapter_id,
                revision_id,
                spatial_reconstruction,
                body_position_and_contact,
                action_constraints,
                emotional_trajectory,
                dialogue_dynamics,
                memorable_images,
                knowledge_gaps,
                verdict,
                blocking_issues,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, review_id: int) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM blind_experience_reviews WHERE id = ?", (review_id,)
        ).fetchone()

    @staticmethod
    def get_active_by_revision(
        conn: sqlite3.Connection, chapter_id: int, revision_id: int
    ) -> sqlite3.Row | None:
        return conn.execute(
            """SELECT * FROM blind_experience_reviews
               WHERE chapter_id = ? AND revision_id = ? AND superseded_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (chapter_id, revision_id),
        ).fetchone()

    @staticmethod
    def supersede_active_for_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> None:
        conn.execute(
            """UPDATE blind_experience_reviews
               SET superseded_at = datetime('now')
               WHERE chapter_id = ? AND superseded_at IS NULL""",
            (chapter_id,),
        )


class ResearchRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        book_id: int,
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
    ) -> int:
        cur = conn.execute(
            """INSERT INTO research_entries
               (book_id, url, retrieved_at, source_type, confidence, claim,
                allowed_use, fiction_boundary, unresolved, verification_state,
                verification_ref, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                book_id,
                url,
                retrieved_at,
                source_type,
                confidence,
                claim,
                allowed_use,
                fiction_boundary,
                1 if unresolved else 0,
                verification_state,
                verification_ref,
                notes,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection, entry_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM research_entries WHERE id = ?", (entry_id,)
        )
        return cur.fetchone()

    @staticmethod
    def list_by_book(
        conn: sqlite3.Connection, book_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM research_entries WHERE book_id = ? ORDER BY id",
            (book_id,),
        )
        return cur.fetchall()

    @staticmethod
    def count_unresolved_plot_support(
        conn: sqlite3.Connection, book_id: int
    ) -> int:
        cur = conn.execute(
            """SELECT COUNT(*) AS cnt FROM research_entries
               WHERE book_id = ? AND unresolved = 1 AND allowed_use = 'plot_support'""",
            (book_id,),
        )
        return cur.fetchone()["cnt"]

    @staticmethod
    def update(
        conn: sqlite3.Connection,
        entry_id: int,
        verification_state: str | None = None,
        verification_ref: int | None = None,
    ) -> None:
        fields = []
        params: list = []
        if verification_state is not None:
            fields.append("verification_state = ?")
            params.append(verification_state)
        if verification_ref is not None:
            fields.append("verification_ref = ?")
            params.append(verification_ref)
        if not fields:
            return
        params.append(entry_id)
        conn.execute(
            f"UPDATE research_entries SET {', '.join(fields)} WHERE id = ?",
            params,
        )


class StoryEngineRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        book_id: int,
        secret: str,
        desire: str,
        alternative_actions: str,
        irreversible_choice: str,
        immediate_cost: str,
        thematic_pressure: str,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO story_engines
               (book_id, secret, desire, alternative_actions,
                irreversible_choice, immediate_cost, thematic_pressure)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                book_id,
                secret,
                desire,
                alternative_actions,
                irreversible_choice,
                immediate_cost,
                thematic_pressure,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_book(
        conn: sqlite3.Connection, book_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM story_engines WHERE book_id = ? ORDER BY id DESC LIMIT 1",
            (book_id,),
        )
        return cur.fetchone()


class ChapterPlanRepository:
    @staticmethod
    def create_or_update(
        conn: sqlite3.Connection,
        chapter_id: int,
        plan_json: str,
        status: str = "draft",
    ) -> int:
        existing = conn.execute(
            "SELECT id FROM chapter_plans WHERE chapter_id = ?", (chapter_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE chapter_plans
                   SET plan_json = ?, status = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (plan_json, status, existing["id"]),
            )
            return existing["id"]
        cur = conn.execute(
            """INSERT INTO chapter_plans (chapter_id, plan_json, status)
               VALUES (?, ?, ?)""",
            (chapter_id, plan_json, status),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            """SELECT * FROM chapter_plans
               WHERE chapter_id = ? ORDER BY id DESC LIMIT 1""",
            (chapter_id,),
        )
        return cur.fetchone()


class PromiseRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        book_id: int,
        promise_text: str,
        status: str,
        planted_scene_ref: str | None = None,
        target_chapter_number: int | None = None,
        target_scene_ref: str | None = None,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO promise_ledger
               (book_id, promise_text, status, planted_scene_ref,
                target_chapter_number, target_scene_ref)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                book_id,
                promise_text,
                status,
                planted_scene_ref,
                target_chapter_number,
                target_scene_ref,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection, promise_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM promise_ledger WHERE id = ?", (promise_id,)
        )
        return cur.fetchone()

    @staticmethod
    def list_by_book(
        conn: sqlite3.Connection, book_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            "SELECT * FROM promise_ledger WHERE book_id = ? ORDER BY id",
            (book_id,),
        )
        return cur.fetchall()

    @staticmethod
    def list_open_by_book(
        conn: sqlite3.Connection, book_id: int
    ) -> list[sqlite3.Row]:
        """Return promises that are not yet paid off or abandoned."""
        cur = conn.execute(
            """SELECT * FROM promise_ledger
               WHERE book_id = ?
                 AND status NOT IN ('paid_off', 'abandoned')
               ORDER BY id""",
            (book_id,),
        )
        return cur.fetchall()

    @staticmethod
    def update_status(
        conn: sqlite3.Connection,
        promise_id: int,
        status: str,
        scene_ref: str,
        resolution_note: str | None = None,
    ) -> None:
        col = {
            "planted": "planted_scene_ref",
            "partially_paid": "advanced_scene_ref",
            "paid_off": "resolved_scene_ref",
            "abandoned": "abandoned_scene_ref",
        }.get(status)
        if col is None:
            raise ValueError(f"Invalid promise status transition: {status}")
        conn.execute(
            f"""UPDATE promise_ledger
                SET status = ?, {col} = ?, resolution_note = ?,
                    updated_at = datetime('now')
                WHERE id = ?""",
            (status, scene_ref, resolution_note, promise_id),
        )

    @staticmethod
    def update_target(
        conn: sqlite3.Connection,
        promise_id: int,
        target_chapter_number: int | None,
        target_scene_ref: str | None,
    ) -> None:
        conn.execute(
            """UPDATE promise_ledger
               SET target_chapter_number = ?, target_scene_ref = ?,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (target_chapter_number, target_scene_ref, promise_id),
        )


class IterationRepository:
    @staticmethod
    def create(
        conn: sqlite3.Connection,
        chapter_id: int,
        round_number: int,
        writer_role: str,
        editor_role: str,
        editor_verdict: str,
        blocking_issues: str,
        revision_targets: str,
        word_count: int,
        status: str,
    ) -> int:
        cur = conn.execute(
            """INSERT INTO iteration_runs
               (chapter_id, round_number, writer_role, editor_role,
                editor_verdict, blocking_issues, revision_targets,
                word_count, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chapter_id,
                round_number,
                writer_role,
                editor_role,
                editor_verdict,
                blocking_issues,
                revision_targets,
                word_count,
                status,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def get_by_id(
        conn: sqlite3.Connection, run_id: int
    ) -> sqlite3.Row | None:
        cur = conn.execute(
            "SELECT * FROM iteration_runs WHERE id = ?", (run_id,)
        )
        return cur.fetchone()

    @staticmethod
    def list_by_chapter(
        conn: sqlite3.Connection, chapter_id: int
    ) -> list[sqlite3.Row]:
        cur = conn.execute(
            """SELECT * FROM iteration_runs
               WHERE chapter_id = ? ORDER BY round_number, id""",
            (chapter_id,),
        )
        return cur.fetchall()
