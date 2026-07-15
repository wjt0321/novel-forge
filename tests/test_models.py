from app.novel_forge.models import (
    Book,
    BookSummary,
    Chapter,
    ChapterSummary,
    ReviewResult,
    ReviewVerdict,
)


def test_book_creation():
    book = Book(
        id=1,
        slug="test-book",
        title="Test Book",
        created_at="2026-07-15T00:00:00",
        updated_at="2026-07-15T00:00:00",
    )
    assert book.slug == "test-book"
    assert book.title == "Test Book"


def test_chapter_summary_excludes_body():
    summary = ChapterSummary(
        id=1,
        book_id=1,
        number=1,
        title="Chapter One",
        state="draft",
        current_revision_id=None,
        open_s1=0,
        open_s2=0,
        open_s3=0,
        open_s4=0,
        blocking_lint=0,
    )
    assert "body" not in summary.model_dump()
    assert summary.state == "draft"


def test_review_result_verdict():
    result = ReviewResult(
        verdict=ReviewVerdict.CONCERNS,
        severity_counts={"S1": 0, "S2": 1, "S3": 0, "S4": 0},
        findings=[],
    )
    assert result.verdict == ReviewVerdict.CONCERNS
