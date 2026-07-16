"""Tests for v1 -> v5 schema migration and backups."""

import sqlite3
from pathlib import Path

import pytest

from app.novel_forge.db import (
    CURRENT_SCHEMA_VERSION,
    UnsupportedSchemaVersionError,
    V1_SCHEMA,
    V3_SCHEMA,
    V5_SCHEMA,
    _backup_db,
    _migrate_v5_to_v6,
    _migrate_v6_to_v7,
    get_db_path,
    init_db,
)
from app.novel_forge.service import NovelForgeService


def _create_v1_database(root: Path, set_user_version: bool = True) -> None:
    """Create a first-milestone database with one book, chapter, and old contract.

    Args:
        set_user_version: If False, leaves PRAGMA user_version at 0 to simulate
            real first-milestone databases created before the migration framework.
    """
    db_path = get_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(V1_SCHEMA)
    if set_user_version:
        conn.execute("PRAGMA user_version = 1")

    # Book and chapter.
    cur = conn.execute("INSERT INTO books (slug, title) VALUES (?, ?)", ("test", "Test Book"))
    book_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO chapters (book_id, number, title, state) VALUES (?, ?, ?, ?)",
        (book_id, 1, "One", "draft"),
    )
    chapter_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO revisions (chapter_id, revision_number, file_path, content_hash) VALUES (?, ?, ?, ?)",
        (chapter_id, 1, "library/test/manuscript/revisions/ch0001/0001-abc.md", "abc123"),
    )
    revision_id = cur.lastrowid
    conn.execute(
        "UPDATE chapters SET current_revision_id = ?, current_hash = ? WHERE id = ?",
        (revision_id, "abc123", chapter_id),
    )

    # Old scene contract file and row.
    contract_path = root / "library" / "test" / "planning" / "chapters" / "ch0001-contract.md"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text("# Old Contract\n\ncontent\n", encoding="utf-8")
    content_hash = "sha256ofoldcontract"
    conn.execute(
        "INSERT INTO scene_contracts (chapter_id, file_path, content_hash) VALUES (?, ?, ?)",
        (chapter_id, str(contract_path.relative_to(root)), content_hash),
    )

    # Old canon fact without book_id.
    conn.execute(
        """INSERT INTO canon_facts
           (source_candidate_id, chapter_id, revision_id, kind, subject, predicate, object, evidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (None, chapter_id, revision_id, "trait", "hero", "age", "30", "chapter 1"),
    )

    conn.commit()
    conn.close()


def test_migration_from_v1_to_v5(tmp_path: Path):
    _create_v1_database(tmp_path)
    contract_path = tmp_path / "library" / "test" / "planning" / "chapters" / "ch0001-contract.md"
    assert contract_path.exists()

    # Opening the service triggers migration.
    svc = NovelForgeService(tmp_path)

    # Backup was created.
    backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(backups) == 1

    # Original assets still exist.
    ch = svc.get_chapter("test", 1)
    assert ch.number == 1
    assert ch.current_revision_id is not None
    assert contract_path.exists()

    # Scene contract migrated to v2.
    sc = svc.get_scene_contract("test", 1)
    assert sc.exists is True
    assert sc.current_revision_number == 1
    assert sc.current_file_path == str(contract_path.relative_to(tmp_path))

    # New v2 revision can be written.
    src = tmp_path / "new-contract.md"
    src.write_text("# New Contract\n\n## scene_question\nq\n", encoding="utf-8")
    sc2 = svc.write_scene_contract("test", 1, src, note="v2")
    assert sc2.current_revision_number == 2

    # Voice Bible table exists; old book has no bible yet.
    vb = svc.get_voice_bible("test")
    assert vb.exists is False

    # Reader Review table exists and works.
    review_id = svc.add_reader_review(
        "test", 1, "immersion", "S3", 1, 1, "vague", "lost", "anchor"
    )
    summary = svc.reader_review_summary_for_chapter("test", 1)
    assert summary.total_open == 1
    svc.resolve_reader_review(review_id, "fixed")
    summary = svc.reader_review_summary_for_chapter("test", 1)
    assert summary.total_open == 0

    # Editorial memos table exists.
    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        conn.row_factory = sqlite3.Row
        assert (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='editorial_memos'"
            ).fetchone()
            is not None
        )

    # Canon facts are book-scoped.
    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        conn.row_factory = sqlite3.Row
        canon = conn.execute("SELECT * FROM canon_facts").fetchone()
        assert canon["book_id"] == ch.book_id
        assert canon["subject"] == "hero"
        assert canon["predicate"] == "age"


def test_migration_is_idempotent(tmp_path: Path):
    _create_v1_database(tmp_path)

    svc = NovelForgeService(tmp_path)
    sc = svc.get_scene_contract("test", 1)
    assert sc.current_revision_number == 1

    first_backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(first_backups) == 1

    # Re-running init_db on an up-to-date DB is a no-op and must not create
    # another backup or duplicate migration revisions.
    conn = init_db(tmp_path)
    conn.close()

    second_backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(second_backups) == 1

    sc = svc.get_scene_contract("test", 1)
    assert sc.current_revision_number == 1

    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        conn.row_factory = sqlite3.Row
        rev_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM scene_contract_revisions"
        ).fetchone()["cnt"]
        assert rev_count == 1
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 8


def test_fresh_database_has_no_backup_and_version_5(tmp_path: Path):
    svc = NovelForgeService(tmp_path)
    svc.init_book("fresh", "Fresh Book")

    backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(backups) == 0

    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 8


def test_legacy_unversioned_v1_database_migrates_to_v5(tmp_path: Path):
    """Real first-milestone DBs have user_version=0 but already contain tables."""
    _create_v1_database(tmp_path, set_user_version=False)
    contract_path = tmp_path / "library" / "test" / "planning" / "chapters" / "ch0001-contract.md"
    assert contract_path.exists()

    svc = NovelForgeService(tmp_path)

    # Exactly one backup created for the migration.
    backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(backups) == 1

    # Schema upgraded to v5.
    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 8

    # Old data preserved and usable through v5 metadata.
    ch = svc.get_chapter("test", 1)
    assert ch.number == 1
    assert contract_path.exists()

    sc = svc.get_scene_contract("test", 1)
    assert sc.exists is True
    assert sc.current_revision_number == 1
    assert sc.current_file_path == str(contract_path.relative_to(tmp_path))

    # Canon facts are book-scoped after migration.
    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        conn.row_factory = sqlite3.Row
        canon = conn.execute("SELECT * FROM canon_facts").fetchone()
        assert canon["book_id"] == ch.book_id


def test_unknown_user_version_is_rejected(tmp_path: Path):
    db_path = get_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(V1_SCHEMA)
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()

    with pytest.raises(UnsupportedSchemaVersionError) as exc_info:
        init_db(tmp_path)
    assert "999" in str(exc_info.value)
    assert str(CURRENT_SCHEMA_VERSION) in str(exc_info.value)

    # No backup should be created and the DB must remain untouched.
    backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(backups) == 0

    with sqlite3.connect(str(db_path)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 999


def test_backup_name_never_overwrites_existing(tmp_path: Path):
    """If a backup path already exists, _backup_db picks a unique counter suffix."""
    db_path = get_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"fake db")

    first = _backup_db(db_path)
    assert first.exists()

    # Pretend the same-second backup slot is occupied.
    second = _backup_db(db_path)
    assert second != first
    assert second.exists()
    assert "-001-" in second.name or "-002-" in second.name or second.name != first.name

    backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(backups) == 2


def _create_v3_database(root: Path) -> None:
    """Create a v3 database with a book, chapter, v2 scene contract, and editorial memo."""
    db_path = get_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(V3_SCHEMA)
    conn.execute("PRAGMA user_version = 3")

    cur = conn.execute("INSERT INTO books (slug, title) VALUES (?, ?)", ("v3book", "V3 Book"))
    book_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO chapters (book_id, number, title, state) VALUES (?, ?, ?, ?)",
        (book_id, 1, "One", "draft"),
    )
    chapter_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO revisions (chapter_id, revision_number, file_path, content_hash) VALUES (?, ?, ?, ?)",
        (chapter_id, 1, "library/v3book/manuscript/revisions/ch0001/0001-abc.md", "abc123"),
    )
    revision_id = cur.lastrowid
    conn.execute(
        "UPDATE chapters SET current_revision_id = ?, current_hash = ? WHERE id = ?",
        (revision_id, "abc123", chapter_id),
    )

    contract_path = root / "library" / "v3book" / "planning" / "chapters" / "ch0001-contract.md"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text("# Old v2 Contract\n\ncontent\n", encoding="utf-8")
    cur = conn.execute(
        "INSERT INTO scene_contract_revisions (chapter_id, revision_number, file_path, content_hash, note) VALUES (?, ?, ?, ?, ?)",
        (chapter_id, 1, str(contract_path.relative_to(root)), "sha256ofoldcontract", "v3 fixture"),
    )
    contract_rev_id = cur.lastrowid
    conn.execute(
        "INSERT INTO scene_contracts (chapter_id, current_revision_id, current_file_path, current_hash) VALUES (?, ?, ?, ?)",
        (chapter_id, contract_rev_id, str(contract_path.relative_to(root)), "sha256ofoldcontract"),
    )

    conn.execute(
        """INSERT INTO editorial_memos
           (chapter_id, revision_id, reviewer_role, narrative_necessity, character_agency,
            detail_selection, causal_chain, prose_observation, verdict, blocking_issues)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (chapter_id, revision_id, "independent_reader_editor", "necessary", "agency", "details", "causal", "prose", "ready_for_editor_decision", "[]"),
    )

    conn.commit()
    conn.close()


def test_migration_from_v3_to_v5(tmp_path: Path):
    """A v3 database migrates to v5, preserving editorial memos and creating new tables."""
    _create_v3_database(tmp_path)

    svc = NovelForgeService(tmp_path)

    backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(backups) == 1

    ch = svc.get_chapter("v3book", 1)
    assert ch.number == 1

    # Scene contract still accessible (migrated to v2 revision-aware structure in earlier migration).
    sc = svc.get_scene_contract("v3book", 1)
    assert sc.exists is True

    # v5 tables exist.
    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        conn.row_factory = sqlite3.Row
        for table in ("research_entries", "story_engines", "chapter_plans", "promise_ledger", "iteration_runs"):
            assert (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                is not None
            )

    # Auto service can use v5 features.
    from app.novel_forge.autonomous import AutonomousWritingService

    auto = AutonomousWritingService(tmp_path)
    engine = auto.set_story_engine(
        "v3book",
        secret="s",
        desire="d",
        alternative_actions=["a", "b"],
        irreversible_choice="c",
        immediate_cost="cost",
        thematic_pressure="p",
    )
    assert engine.book_id == ch.book_id


def _create_v5_database(root: Path) -> None:
    """Create a v5 database with legacy promise statuses."""
    db_path = get_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(V5_SCHEMA)
    conn.execute("PRAGMA user_version = 5")

    cur = conn.execute(
        "INSERT INTO books (slug, title) VALUES (?, ?)", ("v5book", "V5 Book")
    )
    book_id = cur.lastrowid
    promises = [
        ("advanced promise", "advanced", "s1", "adv1", None),
        ("resolved promise", "resolved", "s1", None, "res1"),
        ("planted promise", "planted", "s1", None, None),
        ("abandoned promise", "abandoned", "s1", None, None),
    ]
    for text, status, planted, advanced, resolved in promises:
        conn.execute(
            """INSERT INTO promise_ledger
               (book_id, promise_text, status, planted_scene_ref,
                advanced_scene_ref, resolved_scene_ref)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (book_id, text, status, planted, advanced, resolved),
        )
    conn.commit()
    conn.close()


def test_migration_from_v5_to_v6_maps_legacy_statuses(tmp_path: Path) -> None:
    """Old advanced/resolved statuses map to partially_paid/paid_off."""
    _create_v5_database(tmp_path)

    svc = NovelForgeService(tmp_path)
    from app.novel_forge.autonomous import AutonomousWritingService

    auto = AutonomousWritingService(tmp_path)
    promises = {p.promise_text: p for p in auto.list_promises("v5book")}

    assert promises["advanced promise"].status == "partially_paid"
    assert promises["advanced promise"].advanced_scene_ref == "adv1"
    assert promises["resolved promise"].status == "paid_off"
    assert promises["resolved promise"].resolved_scene_ref == "res1"
    assert promises["planted promise"].status == "planted"
    assert promises["abandoned promise"].status == "abandoned"

    with sqlite3.connect(str(get_db_path(tmp_path))) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION


def test_migration_v5_to_v6_rolls_back_on_insert_failure(tmp_path: Path) -> None:
    """If the data copy fails, the original v5 table remains intact."""

    class _FailingConnection:
        def __init__(self, conn: sqlite3.Connection):
            self._conn = conn

        @property
        def isolation_level(self):
            return self._conn.isolation_level

        @isolation_level.setter
        def isolation_level(self, value):
            self._conn.isolation_level = value

        def execute(self, sql, parameters=None):
            if isinstance(sql, str) and "INSERT INTO promise_ledger" in sql:
                raise sqlite3.OperationalError("simulated insert failure")
            if parameters is None:
                return self._conn.execute(sql)
            return self._conn.execute(sql, parameters)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            return self._conn.close()

        def __getattr__(self, name):
            return getattr(self._conn, name)

    _create_v5_database(tmp_path)
    db_path = get_db_path(tmp_path)

    raw_conn = sqlite3.connect(str(db_path))
    raw_conn.row_factory = sqlite3.Row
    conn = _FailingConnection(raw_conn)

    with pytest.raises(sqlite3.OperationalError, match="simulated insert failure"):
        _migrate_v5_to_v6(conn)

    conn.close()

    with sqlite3.connect(str(db_path)) as check:
        check.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "promise_ledger" in tables
        assert "_old_promise_ledger_v5" not in tables

        row = check.execute(
            "SELECT status FROM promise_ledger WHERE promise_text = ?",
            ("advanced promise",),
        ).fetchone()
        assert row is not None
        assert row["status"] == "advanced"

        version = check.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5


def test_migration_v6_to_v7_failure_restores_v5_backup(tmp_path: Path) -> None:
    """If v5->v6 succeeds but v6->v7 fails, the on-disk DB is restored to v5."""
    _create_v5_database(tmp_path)
    db_path = get_db_path(tmp_path)

    original_migrate_v6_to_v7 = _migrate_v6_to_v7

    def _partial_v6_to_v7(conn: sqlite3.Connection) -> None:
        # Create the v7 table but fail before the index, leaving partial v7
        # schema in the database. This simulates a mid-migration crash.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS blind_experience_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
                revision_id INTEGER NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
                reviewer_role TEXT NOT NULL DEFAULT 'blind_reader',
                source_scope TEXT NOT NULL DEFAULT 'prose_only',
                spatial_reconstruction TEXT NOT NULL,
                body_position_and_contact TEXT NOT NULL,
                action_constraints TEXT NOT NULL,
                emotional_trajectory TEXT NOT NULL,
                dialogue_dynamics TEXT NOT NULL,
                memorable_images TEXT NOT NULL DEFAULT '[]',
                knowledge_gaps TEXT NOT NULL DEFAULT '[]',
                verdict TEXT NOT NULL,
                blocking_issues TEXT NOT NULL DEFAULT '[]',
                superseded_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )"""
        )
        raise sqlite3.OperationalError("simulated v6->v7 failure")

    # Pre-migration snapshot for comparison.
    pre_migration_bytes = db_path.read_bytes()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.novel_forge.db._migrate_v6_to_v7", _partial_v6_to_v7
        )
        with pytest.raises(sqlite3.OperationalError, match="simulated v6->v7 failure"):
            init_db(tmp_path)

    # The backup file must still exist.
    backups = list((tmp_path / "data").glob("novel-forge.backup-*-migration-to-v8.db"))
    assert len(backups) == 1

    # The on-disk database must be restored to the pre-migration v5 state.
    with sqlite3.connect(str(db_path)) as check:
        check.row_factory = sqlite3.Row
        version = check.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5

        tables = {
            row["name"]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "promise_ledger" in tables
        assert "blind_experience_reviews" not in tables
        assert "_old_promise_ledger_v5" not in tables

        row = check.execute(
            "SELECT status FROM promise_ledger WHERE promise_text = ?",
            ("advanced promise",),
        ).fetchone()
        assert row is not None
        assert row["status"] == "advanced"

    # The restored DB file matches the pre-migration snapshot.
    assert db_path.read_bytes() == pre_migration_bytes
