"""SQLite connection, schema, and migrations for Novel Forge."""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

CURRENT_SCHEMA_VERSION = 5


class UnsupportedSchemaVersionError(Exception):
    """Raised when the database schema is newer than this codebase supports."""

    def __init__(self, version: int):
        self.version = version
        super().__init__(
            f"Database schema version {version} is newer than the supported version "
            f"{CURRENT_SCHEMA_VERSION}. Please upgrade Novel Forge."
        )


# First milestone schema (v1). Used by migration tests and to bootstrap
# databases that were created before the migration framework.
V1_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft',
    current_revision_id INTEGER REFERENCES revisions(id) DEFERRABLE INITIALLY DEFERRED,
    current_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(book_id, number)
);

CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(chapter_id, revision_number)
);

-- Legacy scene contract table (v1): one row per chapter, no revision history.
CREATE TABLE IF NOT EXISTS scene_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lint_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    revision_id INTEGER NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('blocking', 'advisory')),
    line_number INTEGER,
    message TEXT NOT NULL,
    evidence TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS review_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
    perspective TEXT NOT NULL CHECK(perspective IN ('structure', 'character', 'narrative', 'continuity')),
    severity TEXT NOT NULL CHECK(severity IN ('S1', 'S2', 'S3', 'S4')),
    location TEXT NOT NULL,
    evidence TEXT NOT NULL,
    issue TEXT NOT NULL,
    fix TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    resolution_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS candidate_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    resolution_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

-- Legacy canon facts (v1): no book_id, global subject/predicate index.
CREATE TABLE IF NOT EXISTS canon_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_candidate_id INTEGER UNIQUE REFERENCES candidate_facts(id) ON DELETE SET NULL,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS canon_facts_subject_predicate
    ON canon_facts(subject, predicate);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    format TEXT NOT NULL,
    file_path TEXT,
    manifest_path TEXT,
    status TEXT NOT NULL CHECK(status IN ('success', 'failure')),
    message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Current schema (v2): adds Voice Bible, Scene Contract revisions, Reader Reviews,
# and book-scoped canon facts.
V2_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft',
    current_revision_id INTEGER REFERENCES revisions(id) DEFERRABLE INITIALLY DEFERRED,
    current_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(book_id, number)
);

CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(chapter_id, revision_number)
);

-- Voice Bible: book-level narrative-voice asset with revision history.
CREATE TABLE IF NOT EXISTS voice_bible_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(book_id, revision_number)
);

CREATE TABLE IF NOT EXISTS voice_bibles (
    book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
    current_revision_id INTEGER REFERENCES voice_bible_revisions(id) DEFERRABLE INITIALLY DEFERRED,
    current_file_path TEXT,
    current_hash TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Scene Contract v2: chapter-level planning asset with revision history.
CREATE TABLE IF NOT EXISTS scene_contract_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(chapter_id, revision_number)
);

CREATE TABLE IF NOT EXISTS scene_contracts (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
    current_revision_id INTEGER REFERENCES scene_contract_revisions(id) DEFERRABLE INITIALLY DEFERRED,
    current_file_path TEXT,
    current_hash TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lint_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    revision_id INTEGER NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('blocking', 'advisory')),
    line_number INTEGER,
    message TEXT NOT NULL,
    evidence TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS review_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
    perspective TEXT NOT NULL CHECK(perspective IN ('structure', 'character', 'narrative', 'continuity')),
    severity TEXT NOT NULL CHECK(severity IN ('S1', 'S2', 'S3', 'S4')),
    location TEXT NOT NULL,
    evidence TEXT NOT NULL,
    issue TEXT NOT NULL,
    fix TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    resolution_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS reader_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
    lens TEXT NOT NULL CHECK(lens IN ('immersion', 'causality', 'character_truth', 'tension', 'language', 'continuity')),
    severity TEXT NOT NULL CHECK(severity IN ('S1', 'S2', 'S3', 'S4')),
    location_start INTEGER NOT NULL,
    location_end INTEGER NOT NULL,
    evidence TEXT NOT NULL,
    reader_effect TEXT NOT NULL,
    revision_intent TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human_or_agent_review',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'resolved')),
    resolution_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS candidate_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    resolution_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS canon_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_candidate_id INTEGER UNIQUE REFERENCES candidate_facts(id) ON DELETE SET NULL,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS canon_facts_book_subject_predicate
    ON canon_facts(book_id, subject, predicate);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    format TEXT NOT NULL,
    file_path TEXT,
    manifest_path TEXT,
    status TEXT NOT NULL CHECK(status IN ('success', 'failure')),
    message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Current schema (v3): adds Editorial Memo ledger per revision.
V3_SCHEMA = (
    V2_SCHEMA
    + """
CREATE TABLE IF NOT EXISTS editorial_memos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_id INTEGER NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
    reviewer_role TEXT NOT NULL DEFAULT 'independent_reader_editor',
    narrative_necessity TEXT NOT NULL,
    character_agency TEXT NOT NULL,
    detail_selection TEXT NOT NULL,
    causal_chain TEXT NOT NULL,
    prose_observation TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('ready_for_editor_decision', 'revision_required')),
    blocking_issues TEXT NOT NULL DEFAULT '[]',
    superseded_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS editorial_memos_chapter_revision
    ON editorial_memos(chapter_id, revision_id);
"""
)

# Current schema (v5): adds Research Ledger verification_state/verification_ref
# for corroboration rules, plus Story Engine, Chapter Plan, Promise Ledger,
# and Iteration Run tables for autonomous research-to-fiction.
V5_SCHEMA = (
    V3_SCHEMA
    + """
CREATE TABLE IF NOT EXISTS research_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('official', 'academic', 'news', 'other')),
    confidence TEXT NOT NULL CHECK(confidence IN ('A', 'B', 'C')),
    claim TEXT NOT NULL,
    allowed_use TEXT NOT NULL CHECK(allowed_use IN ('plot_support', 'background_only', 'fiction_seed')),
    fiction_boundary TEXT NOT NULL,
    unresolved INTEGER NOT NULL DEFAULT 0,
    verification_state TEXT NOT NULL DEFAULT 'collected' CHECK(verification_state IN ('collected', 'verified', 'unresolved')),
    verification_ref INTEGER REFERENCES research_entries(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS research_entries_book
    ON research_entries(book_id);

CREATE INDEX IF NOT EXISTS research_entries_verification_ref
    ON research_entries(verification_ref);

CREATE TABLE IF NOT EXISTS story_engines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    secret TEXT NOT NULL,
    desire TEXT NOT NULL,
    alternative_actions TEXT NOT NULL,
    irreversible_choice TEXT NOT NULL,
    immediate_cost TEXT NOT NULL,
    thematic_pressure TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS story_engines_book
    ON story_engines(book_id);

CREATE TABLE IF NOT EXISTS chapter_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    plan_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'approved_for_writing')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS chapter_plans_chapter
    ON chapter_plans(chapter_id);

CREATE TABLE IF NOT EXISTS promise_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    promise_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planted' CHECK(status IN ('planted', 'advanced', 'resolved', 'abandoned')),
    planted_scene_ref TEXT NOT NULL,
    advanced_scene_ref TEXT,
    resolved_scene_ref TEXT,
    abandoned_scene_ref TEXT,
    resolution_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS promise_ledger_book
    ON promise_ledger(book_id);

CREATE TABLE IF NOT EXISTS iteration_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    writer_role TEXT NOT NULL,
    editor_role TEXT NOT NULL DEFAULT 'independent_reader_editor',
    editor_verdict TEXT NOT NULL CHECK(editor_verdict IN ('revision_required', 'ready_for_human_editor_decision')),
    blocking_issues TEXT NOT NULL DEFAULT '[]',
    revision_targets TEXT NOT NULL DEFAULT '[]',
    word_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS iteration_runs_chapter
    ON iteration_runs(chapter_id);
"""
)


def get_db_path(root: Path) -> Path:
    """Return the canonical SQLite path for a project root."""
    return root / "data" / "novel-forge.db"


def _get_user_version(conn: sqlite3.Connection) -> int:
    cur = conn.execute("PRAGMA user_version")
    return int(cur.fetchone()[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {version}")


def _backup_db(db_path: Path, target_version: int = CURRENT_SCHEMA_VERSION) -> Path:
    """Create a unique, timestamped backup of the SQLite file before migration.

    If multiple backups land in the same second, an incremental counter is
    appended so existing backups are never overwritten.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"{db_path.stem}.backup-{timestamp}-migration-to-v{target_version}.db"
    backup_path = db_path.parent / base_name
    counter = 1
    while backup_path.exists():
        backup_path = db_path.parent / (
            f"{db_path.stem}.backup-{timestamp}-{counter:03d}-migration-to-v{target_version}.db"
        )
        counter += 1
    shutil.copy2(db_path, backup_path)
    return backup_path


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    )
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in cur.fetchall())


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Apply idempotent v1 -> v2 migration inside an open transaction."""
    # 1. New tables added in v2.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS voice_bible_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            revision_number INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(book_id, revision_number)
        );

        CREATE TABLE IF NOT EXISTS voice_bibles (
            book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
            current_revision_id INTEGER REFERENCES voice_bible_revisions(id) DEFERRABLE INITIALLY DEFERRED,
            current_file_path TEXT,
            current_hash TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS scene_contract_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
            revision_number INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(chapter_id, revision_number)
        );

        CREATE TABLE IF NOT EXISTS reader_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
            revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
            lens TEXT NOT NULL CHECK(lens IN ('immersion', 'causality', 'character_truth', 'tension', 'language', 'continuity')),
            severity TEXT NOT NULL CHECK(severity IN ('S1', 'S2', 'S3', 'S4')),
            location_start INTEGER NOT NULL,
            location_end INTEGER NOT NULL,
            evidence TEXT NOT NULL,
            reader_effect TEXT NOT NULL,
            revision_intent TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'human_or_agent_review',
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'resolved')),
            resolution_note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT
        );
        """
    )

    # 2. Migrate scene_contracts to revision-aware v2 structure.
    if _table_exists(conn, "scene_contracts") and _column_exists(
        conn, "scene_contracts", "file_path"
    ):
        # Old v1 table has a single row per chapter. Rename and rebuild.
        conn.execute("ALTER TABLE scene_contracts RENAME TO _old_scene_contracts_v1")
        conn.executescript(
            """
            CREATE TABLE scene_contracts (
                chapter_id INTEGER PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
                current_revision_id INTEGER REFERENCES scene_contract_revisions(id) DEFERRABLE INITIALLY DEFERRED,
                current_file_path TEXT,
                current_hash TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        old_rows = conn.execute(
            "SELECT id, chapter_id, file_path, content_hash FROM _old_scene_contracts_v1"
        ).fetchall()
        for row in old_rows:
            cur = conn.execute(
                """INSERT INTO scene_contract_revisions
                   (chapter_id, revision_number, file_path, content_hash, note)
                   VALUES (?, 1, ?, ?, 'migrated from v1')""",
                (row["chapter_id"], row["file_path"], row["content_hash"]),
            )
            rev_id = cur.lastrowid
            conn.execute(
                """INSERT INTO scene_contracts
                   (chapter_id, current_revision_id, current_file_path, current_hash)
                   VALUES (?, ?, ?, ?)""",
                (row["chapter_id"], rev_id, row["file_path"], row["content_hash"]),
            )
        conn.execute("DROP TABLE _old_scene_contracts_v1")

    # 3. Migrate canon_facts to book-scoped v2 structure.
    if _table_exists(conn, "canon_facts") and not _column_exists(
        conn, "canon_facts", "book_id"
    ):
        conn.execute("ALTER TABLE canon_facts RENAME TO _old_canon_facts_v1")
        conn.executescript(
            """
            CREATE TABLE canon_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_candidate_id INTEGER UNIQUE REFERENCES candidate_facts(id) ON DELETE SET NULL,
                book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
                revision_id INTEGER REFERENCES revisions(id) ON DELETE SET NULL,
                kind TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                evidence TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        old_rows = conn.execute(
            """SELECT cf.id, cf.source_candidate_id, cf.chapter_id, cf.revision_id,
                      cf.kind, cf.subject, cf.predicate, cf.object, cf.evidence
               FROM _old_canon_facts_v1 cf"""
        ).fetchall()
        for row in old_rows:
            book_row = conn.execute(
                "SELECT book_id FROM chapters WHERE id = ?", (row["chapter_id"],)
            ).fetchone()
            book_id = book_row["book_id"] if book_row else 0
            conn.execute(
                """INSERT INTO canon_facts
                   (source_candidate_id, book_id, chapter_id, revision_id,
                    kind, subject, predicate, object, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["source_candidate_id"],
                    book_id,
                    row["chapter_id"],
                    row["revision_id"],
                    row["kind"],
                    row["subject"],
                    row["predicate"],
                    row["object"],
                    row["evidence"],
                ),
            )
        conn.execute("DROP TABLE _old_canon_facts_v1")
        # Replace global unique index with book-scoped unique index.
        conn.execute("DROP INDEX IF EXISTS canon_facts_subject_predicate")
        conn.execute(
            """CREATE UNIQUE INDEX canon_facts_book_subject_predicate
               ON canon_facts(book_id, subject, predicate)"""
        )


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Apply idempotent v2 -> v3 migration inside an open transaction."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS editorial_memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
            revision_id INTEGER NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
            reviewer_role TEXT NOT NULL DEFAULT 'independent_reader_editor',
            narrative_necessity TEXT NOT NULL,
            character_agency TEXT NOT NULL,
            detail_selection TEXT NOT NULL,
            causal_chain TEXT NOT NULL,
            prose_observation TEXT NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN ('ready_for_editor_decision', 'revision_required')),
            blocking_issues TEXT NOT NULL DEFAULT '[]',
            superseded_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS editorial_memos_chapter_revision
            ON editorial_memos(chapter_id, revision_id);
        """
    )


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Apply idempotent v3 -> v4 migration inside an open transaction."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK(source_type IN ('official', 'academic', 'news', 'other')),
            confidence TEXT NOT NULL CHECK(confidence IN ('A', 'B', 'C')),
            claim TEXT NOT NULL,
            allowed_use TEXT NOT NULL CHECK(allowed_use IN ('plot_support', 'background_only', 'fiction_seed')),
            fiction_boundary TEXT NOT NULL,
            unresolved INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS research_entries_book ON research_entries(book_id);

        CREATE TABLE IF NOT EXISTS story_engines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            secret TEXT NOT NULL,
            desire TEXT NOT NULL,
            alternative_actions TEXT NOT NULL,
            irreversible_choice TEXT NOT NULL,
            immediate_cost TEXT NOT NULL,
            thematic_pressure TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS story_engines_book ON story_engines(book_id);

        CREATE TABLE IF NOT EXISTS chapter_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
            plan_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'approved_for_writing')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS chapter_plans_chapter ON chapter_plans(chapter_id);

        CREATE TABLE IF NOT EXISTS promise_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            promise_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planted' CHECK(status IN ('planted', 'advanced', 'resolved', 'abandoned')),
            planted_scene_ref TEXT NOT NULL,
            advanced_scene_ref TEXT,
            resolved_scene_ref TEXT,
            abandoned_scene_ref TEXT,
            resolution_note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS promise_ledger_book ON promise_ledger(book_id);

        CREATE TABLE IF NOT EXISTS iteration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
            round_number INTEGER NOT NULL,
            writer_role TEXT NOT NULL,
            editor_role TEXT NOT NULL DEFAULT 'independent_reader_editor',
            editor_verdict TEXT NOT NULL CHECK(editor_verdict IN ('revision_required', 'ready_for_human_editor_decision')),
            blocking_issues TEXT NOT NULL DEFAULT '[]',
            revision_targets TEXT NOT NULL DEFAULT '[]',
            word_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS iteration_runs_chapter ON iteration_runs(chapter_id);
        """
    )


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Apply idempotent v4 -> v5 migration inside an open transaction.

    Adds research verification fields so B/C plot_support claims can be
    linked to verified A-level corroboration.
    """
    if not _column_exists(conn, "research_entries", "verification_state"):
        conn.execute(
            """ALTER TABLE research_entries
               ADD COLUMN verification_state TEXT NOT NULL DEFAULT 'collected'
               CHECK(verification_state IN ('collected', 'verified', 'unresolved'))"""
        )
    if not _column_exists(conn, "research_entries", "verification_ref"):
        conn.execute(
            "ALTER TABLE research_entries ADD COLUMN verification_ref INTEGER"
        )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS research_entries_verification_ref
           ON research_entries(verification_ref)"""
    )


def init_db(root: Path) -> sqlite3.Connection:
    """Create or migrate the SQLite database to the current schema version.

    Returns an open connection with foreign keys enabled and row factory.
    The caller is responsible for closing the connection.
    """
    db_path = get_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    try:
        version = _get_user_version(conn)
        is_fresh = not _table_exists(conn, "books")

        if version == 0 and is_fresh:
            # Fresh database: create current schema directly, no backup needed.
            conn.executescript(V5_SCHEMA)
            _set_user_version(conn, CURRENT_SCHEMA_VERSION)
            conn.commit()
        elif version < CURRENT_SCHEMA_VERSION:
            # Legacy database: single backup before the full migration chain.
            _backup_db(db_path, target_version=CURRENT_SCHEMA_VERSION)
            try:
                if version < 2:
                    _migrate_v1_to_v2(conn)
                if version < 3:
                    _migrate_v2_to_v3(conn)
                if version < 4:
                    _migrate_v3_to_v4(conn)
                if version < 5:
                    _migrate_v4_to_v5(conn)
                _set_user_version(conn, CURRENT_SCHEMA_VERSION)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        elif version > CURRENT_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(version)
        # else: up to date, leave connection open for caller.
    except Exception:
        conn.rollback()
        raise

    return conn
