"""Tests for the Human-Readable Fiction Quality Layer."""

import json
from pathlib import Path

import pytest

from app.novel_forge.models import ReviewVerdict
from app.novel_forge.service import NovelForgeError, NovelForgeService
from tests.conftest import ready_memo


@pytest.fixture
def service(tmp_path: Path) -> NovelForgeService:
    return NovelForgeService(tmp_path)


def test_init_book_creates_voice_bible_template(service: NovelForgeService):
    service.init_book("test", "Test Book")
    vb = service.get_voice_bible("test")
    assert vb.exists is True
    assert vb.current_revision_number == 1
    assert vb.current_file_path is not None

    vb_path = service.root / vb.current_file_path
    assert vb_path.exists()
    text = vb_path.read_text(encoding="utf-8")
    assert "## 叙述距离 (narrative_distance)" in text
    assert "## 情绪克制规则 (emotional_restraint)" in text
    assert "## 正反例说明 (exemplar_notes)" in text


def test_write_voice_bible_creates_new_revision(service: NovelForgeService):
    service.init_book("test", "Test Book")
    src = service.root / "vb.md"
    src.write_text("# Voice Bible\n\n## narrative_distance\nclose-third.\n", encoding="utf-8")

    vb = service.write_voice_bible("test", src, note="v2")
    assert vb.exists is True
    assert vb.current_revision_number == 2

    revs_dir = service.root / "library" / "test" / "planning" / "voice-bible" / "revisions"
    assert len(list(revs_dir.glob("*.md"))) == 2


def test_write_voice_bible_rejects_library_input_and_bad_encoding(
    service: NovelForgeService,
):
    service.init_book("test", "Test Book")

    lib_src = service.root / "library" / "evil.md"
    lib_src.parent.mkdir(parents=True, exist_ok=True)
    lib_src.write_text("x", encoding="utf-8")
    with pytest.raises(NovelForgeError, match="library"):
        service.write_voice_bible("test", lib_src)

    bad_src = service.root / "gbk.md"
    bad_src.write_text("中文。\n", encoding="gbk")
    with pytest.raises(NovelForgeError, match="UTF-8"):
        service.write_voice_bible("test", bad_src)


def test_scene_contract_v2_template_and_revisions(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")

    sc = service.get_scene_contract("test", 1)
    assert sc.exists is True
    assert sc.current_revision_number == 1

    sc_path = service.root / sc.current_file_path
    text = sc_path.read_text(encoding="utf-8")
    assert "## scene_question" in text
    assert "## viewpoint_character" in text
    assert "## irreversible_turn" in text
    assert "## concrete_anchor" in text
    assert "## forbidden_easy_moves" in text
    assert "## ending_pressure" in text

    src = service.root / "sc.md"
    src.write_text("# Contract\n\n## scene_question\nWill he escape?\n", encoding="utf-8")
    sc2 = service.write_scene_contract("test", 1, src, note="v2")
    assert sc2.current_revision_number == 2

    revs_dir = service.root / "library" / "test" / "planning" / "chapters" / "ch0001-contract" / "revisions"
    assert len(list(revs_dir.glob("*.md"))) == 2


def test_reader_review_validation(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)

    with pytest.raises(NovelForgeError, match="evidence"):
        service.add_reader_review(
            "test", 1, "immersion", "S2", 1, 1, "   ", "confused", "clarify"
        )

    with pytest.raises(NovelForgeError, match="location_start"):
        service.add_reader_review(
            "test", 1, "immersion", "S2", 0, 1, "x", "confused", "clarify"
        )

    with pytest.raises(NovelForgeError, match="location_end"):
        service.add_reader_review(
            "test", 1, "immersion", "S2", 3, 1, "x", "confused", "clarify"
        )

    with pytest.raises(NovelForgeError, match="lens"):
        service.add_reader_review(
            "test", 1, "bad-lens", "S2", 1, 1, "x", "confused", "clarify"
        )


def test_reader_review_blocks_approval_and_scopes_to_revision(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)

    review_id = service.add_reader_review(
        "test", 1, "immersion", "S1", 1, 1, "line 1 is vague", "reader loses place", "anchor the scene"
    )
    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.REJECT
    assert result.reader_review_summary.total_open == 1

    with pytest.raises(NovelForgeError, match="reader reviews"):
        service.approve_chapter("test", 1, "ok")

    service.resolve_reader_review(review_id, "fixed")
    ready_memo(service, "test", 1)
    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.APPROVE


def test_reader_reviews_old_revision_do_not_block_new_revision(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")

    v1 = service.root / "v1.md"
    v1.write_text("旧正文。\n", encoding="utf-8")
    service.write_revision("test", 1, v1)
    service.lint_chapter("test", 1)
    service.add_reader_review(
        "test", 1, "tension", "S1", 1, 1, "old tension missing", "bored", "raise stakes"
    )

    v2 = service.root / "v2.md"
    v2.write_text("新正文。\n", encoding="utf-8")
    service.write_revision("test", 1, v2)
    service.lint_chapter("test", 1)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)
    chapter = service.approve_chapter("test", 1, "ok")
    assert chapter.state.value == "approved"


def test_reader_review_s2_concerns(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)
    service.lint_chapter("test", 1)

    service.add_reader_review(
        "test", 1, "causality", "S2", 1, 1, "motivation unclear", "reader questions why", "add trigger"
    )
    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.CONCERNS


def test_status_reports_metadata_without_content(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")
    src = service.root / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    service.write_revision("test", 1, src)

    vb = service.get_voice_bible("test")
    assert "# Voice Bible" not in json.dumps(vb.model_dump(mode="json"))
    sc = service.get_scene_contract("test", 1)
    assert "## scene_question" not in json.dumps(sc.model_dump(mode="json"))
