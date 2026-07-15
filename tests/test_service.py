import sqlite3
from pathlib import Path

import pytest

from app.novel_forge.models import ReviewVerdict
from app.novel_forge.service import NovelForgeError, NovelForgeService
from tests.conftest import ready_memo


@pytest.fixture
def service(tmp_path: Path) -> NovelForgeService:
    return NovelForgeService(tmp_path)


def test_init_book_creates_directories_and_db(service: NovelForgeService):
    book = service.init_book("test", "Test Book")
    assert book.slug == "test"
    assert (service.root / "library" / "test" / "manuscript" / "revisions").exists()
    assert (service.root / "data" / "novel-forge.db").exists()


def test_init_book_rejects_duplicate_slug(service: NovelForgeService):
    service.init_book("test", "Test Book")
    with pytest.raises(NovelForgeError):
        service.init_book("test", "Other")


def test_create_chapter_and_reject_duplicate(service: NovelForgeService):
    service.init_book("test", "Test Book")
    ch = service.create_chapter("test", 1, "One")
    assert ch.number == 1
    assert ch.state.value == "draft"

    # Scene Contract v2 is stored as a revision under its own directory.
    contract_dir = service.root / "library" / "test" / "planning" / "chapters" / "ch0001-contract" / "revisions"
    assert contract_dir.exists()
    contract_files = list(contract_dir.glob("*.md"))
    assert len(contract_files) == 1
    contract_text = contract_files[0].read_text(encoding="utf-8")
    assert "## scene_question" in contract_text
    assert "## viewpoint_character" in contract_text
    assert "## irreversible_turn" in contract_text
    assert "## concrete_anchor" in contract_text
    assert "## forbidden_easy_moves" in contract_text

    with pytest.raises(NovelForgeError):
        service.create_chapter("test", 1, "Duplicate")


def test_write_revision_creates_new_file_and_updates_pointer(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文第一段。\n", encoding="utf-8")

    ch = service.write_revision("test", 1, src, note="first")
    assert ch.current_revision_id is not None
    assert ch.current_hash is not None

    revs = list((service.root / "library" / "test" / "manuscript" / "revisions" / "ch0001").glob("*.md"))
    assert len(revs) == 1


def test_revision_never_overwrites_previous(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文第一段。\n", encoding="utf-8")
    service.write_revision("test", 1, src, note="v1")

    src.write_text("正文第二段。\n", encoding="utf-8")
    service.write_revision("test", 1, src, note="v2")

    revs = list((service.root / "library" / "test" / "manuscript" / "revisions" / "ch0001").glob("*.md"))
    assert len(revs) == 2


def test_approved_chapter_requires_reopen_reason(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)
    service.approve_chapter("test", 1, note="ok")

    with pytest.raises(NovelForgeError):
        service.write_revision("test", 1, src)

    ch = service.write_revision("test", 1, src, reopen_reason="fix typo")
    assert ch.state.value == "revised"


def test_lint_finding_but_hash_unchanged(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("他喊道——停下。\n", encoding="utf-8")
    service.write_revision("test", 1, src)

    blocking, advisory = service.lint_chapter("test", 1)
    assert blocking == 1
    ch = service.get_chapter("test", 1)
    assert ch.state.value == "linted"

    # Source file unchanged, hash unchanged, revision file still exists.
    revs = list((service.root / "library" / "test" / "manuscript" / "revisions" / "ch0001").glob("*.md"))
    assert len(revs) == 1


def test_add_and_resolve_finding(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)

    fid = service.add_finding(
        "test", 1, "structure", "S1", "1", "evidence", "issue", "fix it"
    )
    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.REJECT

    service.resolve_finding(fid, "fixed")
    ready_memo(service, "test", 1)
    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.APPROVE


def test_approve_blocked_by_s1_or_blocking_lint(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)

    service.add_finding("test", 1, "structure", "S1", "1", "x", "y", "z")
    service.lint_chapter("test", 1)
    service.review_chapter("test", 1)
    with pytest.raises(NovelForgeError):
        service.approve_chapter("test", 1, "ok")


def test_approve_success(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)

    ch = service.approve_chapter("test", 1, "ok")
    assert ch.state.value == "approved"


def test_candidate_fact_approval_and_conflict(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)

    cid = service.add_candidate_fact(
        "test", 1, "attribute", "Hero", "age", "30", "birthday scene"
    )
    service.approve_fact(cid, "accepted")

    cid2 = service.add_candidate_fact(
        "test", 1, "attribute", "Hero", "age", "40", "wrong scene"
    )
    with pytest.raises(NovelForgeError, match="Canon conflict in book"):
        service.approve_fact(cid2)


def test_reject_fact(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    cid = service.add_candidate_fact(
        "test", 1, "attribute", "Hero", "age", "30", "scene"
    )
    service.reject_fact(cid, "unsupported")


def test_rollback_creates_new_revision(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("第一版。\n", encoding="utf-8")
    ch = service.write_revision("test", 1, src, note="v1")
    rev1 = ch.current_revision_id

    src.write_text("第二版。\n", encoding="utf-8")
    service.write_revision("test", 1, src, note="v2")
    service.lint_chapter("test", 1)

    ch = service.rollback_chapter("test", 1, rev1, "revert to v1")
    assert ch.state.value == "revised"

    revs = list((service.root / "library" / "test" / "manuscript" / "revisions" / "ch0001").glob("*.md"))
    assert len(revs) == 3


def test_export_markdown_only_approved_and_manifest(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    service.create_chapter("test", 2, "Two")

    src1 = service.root / "c1.md"
    src1.write_text("第一章正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src1)
    service.lint_chapter("test", 1)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)
    service.approve_chapter("test", 1, "ok")

    src2 = service.root / "c2.md"
    src2.write_text("第二章正文。\n", encoding="utf-8")
    service.write_revision("test", 2, src2)
    # Chapter 2 not approved.

    md_path = service.export_book("test", "markdown")
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "第一章正文" in content
    assert "第二章正文" not in content

    manifest_files = list(md_path.parent.glob("*-manifest.json"))
    assert len(manifest_files) == 1
    assert "sha256" in manifest_files[0].read_text(encoding="utf-8")


def test_export_non_markdown_without_pandoc_fails_cleanly(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)
    service.approve_chapter("test", 1, "ok")

    with pytest.raises(NovelForgeError, match="Pandoc"):
        service.export_book("test", "docx")


def test_audit_logged(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    events = service.audit("test")
    actions = {e.action for e in events}
    assert "init" in actions
    assert "create" in actions


# ---------------------------------------------------------------------------
# State-machine guards and revision-scoped findings
# ---------------------------------------------------------------------------

def test_review_requires_lint_first(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)

    with pytest.raises(NovelForgeError, match="linted"):
        service.review_chapter("test", 1)


def test_approve_requires_review_first(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)

    with pytest.raises(NovelForgeError, match="reviewed"):
        service.approve_chapter("test", 1, "ok")


def test_lint_advances_state_even_with_zero_findings(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)

    blocking, advisory = service.lint_chapter("test", 1)
    assert blocking == 0
    assert advisory == 0
    ch = service.get_chapter("test", 1)
    assert ch.state.value == "linted"


def test_old_revision_finding_does_not_block_new_revision(service: NovelForgeService):
    """A new revision starts with a clean slate; unresolved S1 on an old
    revision must not prevent approval of the current revision.
    """
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")

    v1 = service.root / "v1.md"
    v1.write_text("旧正文。\n", encoding="utf-8")
    service.write_revision("test", 1, v1)
    service.add_finding("test", 1, "structure", "S1", "1", "x", "y", "z")
    service.lint_chapter("test", 1)
    assert service.review_chapter("test", 1).verdict == ReviewVerdict.REJECT

    v2 = service.root / "v2.md"
    v2.write_text("新正文。\n", encoding="utf-8")
    service.write_revision("test", 1, v2)
    service.lint_chapter("test", 1)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)
    ch = service.approve_chapter("test", 1, "ok")
    assert ch.state.value == "approved"


def test_resolve_finding_missing_id(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")

    with pytest.raises(NovelForgeError, match="Finding not found"):
        service.resolve_finding(9999, "note")


def test_resolve_finding_already_resolved(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)
    fid = service.add_finding(
        "test", 1, "structure", "S3", "1", "x", "y", "z"
    )
    service.resolve_finding(fid, "fixed")

    with pytest.raises(NovelForgeError, match="already resolved"):
        service.resolve_finding(fid, "fixed again")


def test_rollback_rejected_from_draft(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    ch = service.write_revision("test", 1, src)

    with pytest.raises(NovelForgeError, match="draft"):
        service.rollback_chapter("test", 1, ch.current_revision_id, "nope")


def test_lint_blocked_on_approved_chapter(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "tmp.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)
    service.approve_chapter("test", 1, "ok")

    with pytest.raises(NovelForgeError, match="reopen-reason"):
        service.lint_chapter("test", 1)


# ---------------------------------------------------------------------------
# Canon fact isolation and candidate fact guards
# ---------------------------------------------------------------------------

def test_canon_conflict_is_book_scoped(service: NovelForgeService):
    """A canon fact with the same subject+predicate in one book must not
    block the same subject+predicate in another book.
    """
    # Book A
    service.init_book("book-a", "Book A")
    service.create_chapter("book-a", 1, "One")
    src_a = service.root / "a.md"
    src_a.write_text("正文。\n", encoding="utf-8")
    service.write_revision("book-a", 1, src_a)
    cid_a = service.add_candidate_fact(
        "book-a", 1, "attribute", "Hero", "age", "30", "scene A"
    )
    service.approve_fact(cid_a, "accepted A")

    # Book B with identical subject+predicate+object
    service.init_book("book-b", "Book B")
    service.create_chapter("book-b", 1, "One")
    src_b = service.root / "b.md"
    src_b.write_text("正文。\n", encoding="utf-8")
    service.write_revision("book-b", 1, src_b)
    cid_b = service.add_candidate_fact(
        "book-b", 1, "attribute", "Hero", "age", "30", "scene B"
    )
    service.approve_fact(cid_b, "accepted B")


def test_candidate_fact_requires_current_revision(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")

    with pytest.raises(NovelForgeError, match="current revision"):
        service.add_candidate_fact(
            "test", 1, "attribute", "Hero", "age", "30", "scene"
        )
