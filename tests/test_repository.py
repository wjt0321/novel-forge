import sqlite3
from pathlib import Path

import pytest

from app.novel_forge.db import init_db
from app.novel_forge.repository import (
    AuditRepository,
    BookRepository,
    ChapterRepository,
    FactRepository,
    FindingRepository,
    RevisionRepository,
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return init_db(tmp_path)


def test_create_and_get_book(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    book = BookRepository.get_by_slug(conn, "test")
    assert book is not None
    assert book["id"] == book_id
    assert book["slug"] == "test"


def test_book_slug_unique(conn: sqlite3.Connection):
    BookRepository.create(conn, slug="test", title="Test")
    with pytest.raises(sqlite3.IntegrityError):
        BookRepository.create(conn, slug="test", title="Other")


def test_create_and_get_chapter(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    chapter_id = ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    chapter = ChapterRepository.get_by_book_and_number(conn, book_id, 1)
    assert chapter is not None
    assert chapter["id"] == chapter_id
    assert chapter["state"] == "draft"


def test_chapter_number_unique(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    with pytest.raises(sqlite3.IntegrityError):
        ChapterRepository.create(conn, book_id=book_id, number=1, title="Duplicate")


def test_create_revision_and_update_chapter(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    chapter_id = ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    rev_id = RevisionRepository.create(
        conn,
        chapter_id=chapter_id,
        revision_number=1,
        file_path="library/test/manuscript/revisions/ch0001/r1.md",
        content_hash="abc",
        note="first",
    )
    ChapterRepository.update_current_revision(conn, chapter_id, rev_id, "abc")
    chapter = ChapterRepository.get_by_id(conn, chapter_id)
    assert chapter["current_revision_id"] == rev_id
    assert chapter["current_hash"] == "abc"


def test_revision_number_unique(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    chapter_id = ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    RevisionRepository.create(
        conn,
        chapter_id=chapter_id,
        revision_number=1,
        file_path="a.md",
        content_hash="abc",
    )
    with pytest.raises(sqlite3.IntegrityError):
        RevisionRepository.create(
            conn,
            chapter_id=chapter_id,
            revision_number=1,
            file_path="b.md",
            content_hash="def",
        )


def test_add_lint_finding_and_counts(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    chapter_id = ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    rev_id = RevisionRepository.create(
        conn,
        chapter_id=chapter_id,
        revision_number=1,
        file_path="a.md",
        content_hash="abc",
    )
    FindingRepository.add_lint_finding(
        conn,
        revision_id=rev_id,
        rule_code="ellipsis",
        severity="blocking",
        line_number=5,
        message="no ellipsis",
        evidence="……",
    )
    counts = FindingRepository.lint_counts_for_revision(conn, rev_id)
    assert counts["blocking"] == 1


def test_lint_counts_for_revision_empty_when_no_revision(conn: sqlite3.Connection):
    counts = FindingRepository.lint_counts_for_revision(conn, None)
    assert counts == {"blocking": 0, "advisory": 0}


def test_add_review_finding_and_resolve(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    chapter_id = ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    rev_id = RevisionRepository.create(
        conn,
        chapter_id=chapter_id,
        revision_number=1,
        file_path="a.md",
        content_hash="abc",
    )
    finding_id = FindingRepository.add_review_finding(
        conn,
        chapter_id=chapter_id,
        revision_id=rev_id,
        perspective="structure",
        severity="S1",
        location="1",
        evidence="x",
        issue="y",
        fix="z",
    )
    FindingRepository.resolve_review_finding(conn, finding_id, "fixed")
    open_counts = FindingRepository.open_review_counts_for_revision(conn, rev_id)
    assert open_counts["S1"] == 0


def test_review_counts_scoped_to_revision(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    chapter_id = ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    rev1 = RevisionRepository.create(
        conn,
        chapter_id=chapter_id,
        revision_number=1,
        file_path="a.md",
        content_hash="abc",
    )
    rev2 = RevisionRepository.create(
        conn,
        chapter_id=chapter_id,
        revision_number=2,
        file_path="b.md",
        content_hash="def",
    )
    FindingRepository.add_review_finding(
        conn,
        chapter_id=chapter_id,
        revision_id=rev1,
        perspective="structure",
        severity="S1",
        location="1",
        evidence="x",
        issue="y",
        fix="z",
    )
    counts = FindingRepository.open_review_counts_for_revision(conn, rev2)
    assert counts["S1"] == 0


def test_candidate_fact_lifecycle(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    chapter_id = ChapterRepository.create(conn, book_id=book_id, number=1, title="One")
    fact_id = FactRepository.add_candidate(
        conn,
        chapter_id=chapter_id,
        kind="attribute",
        subject="Hero",
        predicate="age",
        object="30",
        evidence="chapter 1",
    )
    FactRepository.update_candidate_status(conn, fact_id, "approved", "ok")
    candidate = FactRepository.get_candidate(conn, fact_id)
    assert candidate["status"] == "approved"


def test_canon_conflict_is_book_scoped(conn: sqlite3.Connection):
    book_a = BookRepository.create(conn, slug="book-a", title="Book A")
    chapter_a = ChapterRepository.create(conn, book_id=book_a, number=1, title="One")
    FactRepository.add_canon(
        conn,
        source_candidate_id=None,
        book_id=book_a,
        chapter_id=chapter_a,
        kind="attribute",
        subject="Hero",
        predicate="age",
        object="30",
        evidence="chapter 1",
    )

    # Same subject+predicate in a different book is allowed.
    book_b = BookRepository.create(conn, slug="book-b", title="Book B")
    chapter_b = ChapterRepository.create(conn, book_id=book_b, number=1, title="One")
    FactRepository.add_canon(
        conn,
        source_candidate_id=None,
        book_id=book_b,
        chapter_id=chapter_b,
        kind="attribute",
        subject="Hero",
        predicate="age",
        object="40",
        evidence="chapter 1b",
    )

    # Same subject+predicate in the same book is rejected by the DB.
    with pytest.raises(sqlite3.IntegrityError):
        FactRepository.add_canon(
            conn,
            source_candidate_id=None,
            book_id=book_a,
            chapter_id=chapter_a,
            kind="attribute",
            subject="Hero",
            predicate="age",
            object="40",
            evidence="chapter 2",
        )


def test_audit_event(conn: sqlite3.Connection):
    book_id = BookRepository.create(conn, slug="test", title="Test")
    AuditRepository.add(conn, book_id=book_id, entity_type="book", action="create")
    events = AuditRepository.list(conn, book_id)
    assert len(events) == 1
    assert events[0]["action"] == "create"
