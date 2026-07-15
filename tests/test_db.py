import sqlite3
from pathlib import Path

from app.novel_forge.db import get_db_path, init_db


def test_get_db_path(tmp_path: Path):
    assert get_db_path(tmp_path) == tmp_path / "data" / "novel-forge.db"


def test_init_db_creates_tables_and_enables_foreign_keys(tmp_path: Path):
    conn = init_db(tmp_path)
    assert isinstance(conn, sqlite3.Connection)

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cur.fetchall()}
    expected = {
        "audit_events",
        "books",
        "canon_facts",
        "candidate_facts",
        "chapters",
        "exports",
        "lint_findings",
        "review_findings",
        "revisions",
        "scene_contracts",
    }
    assert expected <= tables

    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
