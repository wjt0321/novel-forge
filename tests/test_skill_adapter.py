"""Tests for the Skill-first JSON adapter."""

import json
from pathlib import Path

import pytest

from app.novel_forge.service import NovelForgeService
from app.novel_forge.skill_adapter import main
from tests.conftest import ready_memo


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def test_status_book_and_chapter_no_body(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)

    code = main(["--root", str(tmp_path), "status", "test"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["operation"] == "status"
    assert data["data"]["book"]["slug"] == "test"
    assert len(data["data"]["chapters"]) == 1
    assert '"body":' not in json.dumps(data)

    code = main(["--root", str(tmp_path), "status", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["chapter"]["number"] == 1
    assert data["data"]["finding_counts"] == {
        "blocking": 0,
        "advisory": 0,
        "S1": 0,
        "S2": 0,
        "S3": 0,
        "S4": 0,
    }
    assert '"body":' not in json.dumps(data)


def test_init_book_requires_confirm(tmp_path: Path, capsys):
    code = main(
        ["--root", str(tmp_path), "init-book", "test", "--title", "Test Book"]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"

    assert not (tmp_path / "library" / "test").exists()


def test_init_book_with_confirm(tmp_path: Path, capsys):
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-book",
            "init-book",
            "test",
            "--title",
            "Test Book",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["book"]["slug"] == "test"
    assert (tmp_path / "library" / "test").exists()


def test_write_revision_requires_confirm_and_rejects_library_input(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")

    # Missing confirmation.
    code = main(
        [
            "--root",
            str(tmp_path),
            "write-revision",
            "test",
            "1",
            "--from-file",
            str(src),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"

    # Source inside library is rejected.
    lib_input = tmp_path / "library" / "evil.md"
    lib_input.parent.mkdir(parents=True, exist_ok=True)
    lib_input.write_text("正文。\n", encoding="utf-8")
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision",
            "write-revision",
            "test",
            "1",
            "--from-file",
            str(lib_input),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "library" in data["error"]["message"].lower()

    # Confirmed, valid external path succeeds.
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision",
            "write-revision",
            "test",
            "1",
            "--from-file",
            str(src),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["state_changed"] is True


def test_lint_and_review_report_state_changed(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)

    code = main(["--root", str(tmp_path), "lint", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["operation"] == "lint"
    assert data["state_changed"] is True
    assert "blocking" in data["data"]
    assert "body" not in json.dumps(data)

    ready_memo(svc, "test", 1)
    code = main(["--root", str(tmp_path), "review", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["operation"] == "review"
    assert data["state_changed"] is True
    assert data["data"]["verdict"] == "APPROVE"
    assert "body" not in json.dumps(data)


def test_approve_chapter_requires_confirm(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    svc.lint_chapter("test", 1)
    svc.review_chapter("test", 1)

    code = main(
        ["--root", str(tmp_path), "approve-chapter", "test", "1", "--note", "ok"]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"

    ch = svc.get_chapter("test", 1)
    assert ch.state.value == "reviewed"


def test_bad_slug_rejected(tmp_path: Path, capsys):
    code = main(["--root", str(tmp_path), "status", "../../etc"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "Invalid book slug" in data["error"]["message"]


def test_export_book_requires_confirm_and_returns_manifest(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    svc.lint_chapter("test", 1)
    ready_memo(svc, "test", 1)
    svc.review_chapter("test", 1)
    svc.approve_chapter("test", 1, "ok")

    code = main(
        ["--root", str(tmp_path), "export-book", "test", "--format", "markdown"]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "export-book",
            "export-book",
            "test",
            "--format",
            "markdown",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["format"] == "markdown"
    assert "file_path" in data["data"]
    assert "manifest" in data["data"]
    assert "source_revisions" in data["data"]["manifest"]


# ---------------------------------------------------------------------------
# Adapter input validation
# ---------------------------------------------------------------------------

def test_status_rejects_extra_arguments(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    code = main(["--root", str(tmp_path), "status", "test", "1", "extra"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "invalid_arguments"


def test_status_rejects_non_integer_chapter(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    code = main(["--root", str(tmp_path), "status", "test", "not-a-number"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "invalid_arguments"
    assert "integer" in data["error"]["message"]


def test_relative_root_rejected_and_not_created(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rel_name = "relative-root-test"
    rel_path = tmp_path / rel_name

    code = main(["--root", rel_name, "status", "test"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "invalid_root"
    assert not rel_path.exists()


def test_write_revision_rejects_non_utf8_source(tmp_path: Path, capsys):
    """A non-UTF-8 source file must be rejected before any revision is created."""
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    src = tmp_path / "gbk.md"
    src.write_text("中文。\n", encoding="gbk")

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision",
            "write-revision",
            "test",
            "1",
            "--from-file",
            str(src),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "business_error"
    assert "UTF-8" in data["error"]["message"]

    ch = svc.get_chapter("test", 1)
    assert ch.current_revision_id is None
    revs_dir = tmp_path / "library" / "test" / "manuscript" / "revisions" / "ch0001"
    assert not revs_dir.exists() or len(list(revs_dir.glob("*.md"))) == 0


def test_write_revision_accepts_utf8_with_bom(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    src = tmp_path / "bom.md"
    src.write_bytes("\ufeff正文。\n".encode("utf-8-sig"))

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision",
            "write-revision",
            "test",
            "1",
            "--from-file",
            str(src),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    ch = svc.get_chapter("test", 1)
    assert ch.current_revision_id is not None


def test_lint_legacy_non_utf8_revision_returns_json_error(
    tmp_path: Path, capsys
):
    """A legacy/non-UTF-8 revision file must not crash lint with a traceback."""
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    # Bypass adapter to simulate a legacy GBK revision already in library.
    src = tmp_path / "legacy.md"
    src.write_text("中文。\n", encoding="gbk")
    svc.write_revision("test", 1, src)

    code = main(["--root", str(tmp_path), "lint", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "business_error"
    assert "UTF-8" in data["error"]["message"] or "utf-8" in data["error"]["message"]

    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "UnicodeDecodeError" not in err


# ---------------------------------------------------------------------------
# Human-Readable Fiction Quality Layer adapter tests
# ---------------------------------------------------------------------------

def test_adapter_voice_bible_status_and_write(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    code = main(["--root", str(tmp_path), "voice-bible-status", "test"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["voice_bible"]["exists"] is True
    assert "# Voice Bible" not in json.dumps(data)

    src = tmp_path / "vb.md"
    src.write_text("# Voice Bible\n\nnarrative_distance: close-third\n", encoding="utf-8")

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-voice-bible",
            "write-voice-bible",
            "test",
            "--from-file",
            str(src),
            "--note",
            "v2",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["voice_bible"]["current_revision_number"] == 2


def test_adapter_scene_contract_status_and_write(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    code = main(["--root", str(tmp_path), "scene-contract-status", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["scene_contract"]["exists"] is True
    assert "## scene_question" not in json.dumps(data)

    src = tmp_path / "sc.md"
    src.write_text("# Contract\n\n## scene_question\nq\n", encoding="utf-8")
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-scene-contract",
            "write-scene-contract",
            "test",
            "1",
            "--from-file",
            str(src),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["scene_contract"]["current_revision_number"] == 2


def test_adapter_reader_review_blocks_approval(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    svc.lint_chapter("test", 1)

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "add-reader-review",
            "add-reader-review",
            "test",
            "1",
            "--lens",
            "immersion",
            "--severity",
            "S1",
            "--location-start",
            "1",
            "--location-end",
            "1",
            "--evidence",
            "line 1 vague",
            "--reader-effect",
            "reader loses place",
            "--revision-intent",
            "anchor the scene",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    review_id = data["data"]["reader_review_id"]

    code = main(["--root", str(tmp_path), "review", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["data"]["verdict"] == "REJECT"
    assert data["data"]["reader_review_summary"]["total_open"] == 1
    assert "正文" not in json.dumps(data)

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "resolve-reader-review",
            "resolve-reader-review",
            str(review_id),
            "--note",
            "fixed",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True

    ready_memo(svc, "test", 1)
    code = main(["--root", str(tmp_path), "review", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert data["data"]["verdict"] == "APPROVE"


def test_adapter_status_book_and_chapter_include_quality_metadata(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")

    code = main(["--root", str(tmp_path), "status", "test"])
    assert code == 0
    data = _json_output(capsys)
    assert "voice_bible" in data["data"]

    code = main(["--root", str(tmp_path), "status", "test", "1"])
    assert code == 0
    data = _json_output(capsys)
    assert "scene_contract" in data["data"]
    assert "reader_review_summary" in data["data"]
    assert "正文" not in json.dumps(data)


def test_adapter_quality_writes_reject_library_and_non_utf8(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    lib_src = tmp_path / "library" / "test" / "evil.md"
    lib_src.parent.mkdir(parents=True, exist_ok=True)
    lib_src.write_text("x", encoding="utf-8")
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-voice-bible",
            "write-voice-bible",
            "test",
            "--from-file",
            str(lib_src),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "business_error"

    bad_src = tmp_path / "gbk.md"
    bad_src.write_text("中文。\n", encoding="gbk")
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-scene-contract",
            "write-scene-contract",
            "test",
            "1",
            "--from-file",
            str(bad_src),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "UTF-8" in data["error"]["message"]


# ---------------------------------------------------------------------------
# P3 Human-readable workspace
# ---------------------------------------------------------------------------

def test_init_workspace_requires_confirm(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    code = main(["--root", str(tmp_path), "init-workspace", "test"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"
    assert not (tmp_path / "work" / "test").exists()


def test_init_workspace_creates_human_readable_structure(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-workspace",
            "init-workspace",
            "test",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["state_changed"] is True

    work = tmp_path / "work" / "test"
    for d in ("manuscript", "planning", "research", "reviews", "iterations", "archive"):
        assert (work / d).is_dir()
    assert (work / "README.md").exists()
    assert (work / "CURRENT.md").exists()
    readme_text = (work / "README.md").read_text(encoding="utf-8")
    assert "manuscript/chapter-0001-current.md" in readme_text
    assert "library/test/" in readme_text
    assert "正文" not in json.dumps(data)


def test_refresh_workspace_mirrors_current_revision_without_leakage(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("这是正文第一段。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)

    main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-workspace",
            "init-workspace",
            "test",
        ]
    )
    capsys.readouterr()  # clear previous output
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "refresh-workspace",
            "refresh-workspace",
            "test",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["mirrored_chapters"][0]["number"] == 1
    assert data["data"]["warnings"] == []

    mirror = tmp_path / "work" / "test" / "manuscript" / "chapter-0001-current.md"
    assert mirror.exists()
    assert "这是正文第一段" in mirror.read_text(encoding="utf-8")
    assert "这是正文第一段" not in json.dumps(data)

    current_text = (tmp_path / "work" / "test" / "CURRENT.md").read_text(encoding="utf-8")
    assert "| 1 | One | draft | 7 |" in current_text
    assert "chapter-0001-current.md" in current_text
    assert "正文" not in json.dumps(data)


def test_workspace_operations_preserve_existing_user_files(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    work = tmp_path / "work" / "test"
    work.mkdir(parents=True)
    legacy = work / "legacy-draft.md"
    legacy.write_text("old draft", encoding="utf-8")

    main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-workspace",
            "init-workspace",
            "test",
        ]
    )
    assert legacy.exists()
    assert legacy.read_text(encoding="utf-8") == "old draft"


def test_refresh_workspace_does_not_overwrite_user_edited_mirrors(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("这是正文第一段。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)

    main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-workspace",
            "init-workspace",
            "test",
        ]
    )
    capsys.readouterr()
    main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "refresh-workspace",
            "refresh-workspace",
            "test",
        ]
    )
    capsys.readouterr()

    # User edits the generated mirror.
    mirror = tmp_path / "work" / "test" / "manuscript" / "chapter-0001-current.md"
    mirror.write_text("user edited content", encoding="utf-8")

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "refresh-workspace",
            "refresh-workspace",
            "test",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert any("user-edited" in w for w in data["data"]["warnings"])
    assert mirror.read_text(encoding="utf-8") == "user edited content"


# ---------------------------------------------------------------------------
# P4 Patch revision
# ---------------------------------------------------------------------------

def _write_patch(tmp_path: Path, patches: list[dict]) -> Path:
    p = tmp_path / "patch.json"
    p.write_text(json.dumps(patches, ensure_ascii=False), encoding="utf-8")
    return p


def test_write_revision_patch_requires_confirm_and_applies_patch(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("她走进房间。桌上有一封信。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": "桌上有一封信",
                "replacement": "桌上摆着一封未拆的信",
                "reason": "增加具体性",
            }
        ],
    )

    # Missing confirm.
    code = main(
        [
            "--root",
            str(tmp_path),
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"
    assert svc.get_chapter("test", 1).current_revision_id == rev1

    # Confirmed success (below-minimum allowed because this is a unit test).
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
            "--note",
            "patch test",
            "--allow-below-minimum",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["state_changed"] is True
    ch = svc.get_chapter("test", 1)
    assert ch.current_revision_id != rev1
    rev_path = tmp_path / svc.get_current_revision("test", 1).file_path
    assert "桌上摆着一封未拆的信" in rev_path.read_text(encoding="utf-8")
    assert "正文" not in json.dumps(data)


def test_write_revision_patch_rejects_non_unique_and_missing_evidence(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("她看着窗外。窗外有雨。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    # Non-unique evidence.
    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": "窗外",
                "replacement": "门外",
                "reason": "test",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "2" in data["error"]["message"] or "unique" in data["error"]["message"].lower()
    assert svc.get_chapter("test", 1).current_revision_id == rev1

    # Missing evidence.
    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": "不存在的句子",
                "replacement": "x",
                "reason": "test",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "not found" in data["error"]["message"].lower() or "未找到" in data["error"]["message"]
    assert svc.get_chapter("test", 1).current_revision_id == rev1


def test_write_revision_patch_rejects_empty_replacement_and_invalid_inputs(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("她走进房间。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": "她走进房间",
                "replacement": "",
                "reason": "delete",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "empty" in data["error"]["message"].lower() or "空" in data["error"]["message"]
    assert svc.get_chapter("test", 1).current_revision_id == rev1

    # Non-UTF-8 patch file.
    bad_patch = tmp_path / "bad-patch.json"
    bad_patch.write_text("中文", encoding="gbk")
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(bad_patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "UTF-8" in data["error"]["message"]

    # Patch file inside library.
    lib_patch = tmp_path / "library" / "test" / "patch.json"
    lib_patch.write_text("[]", encoding="utf-8")
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(lib_patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "library" in data["error"]["message"].lower()


def test_write_revision_patch_rejects_overlapping_evidence(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("她走进房间。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": "她走进房间",
                "replacement": "他走进房间",
                "reason": "change subject",
            },
            {
                "location": "第1段",
                "evidence": "走进房间",
                "replacement": "跑出房间",
                "reason": "change verb",
            },
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "overlap" in data["error"]["message"].lower() or "重叠" in data["error"]["message"]
    assert svc.get_chapter("test", 1).current_revision_id == rev1


def test_write_revision_patch_requires_reopen_reason_for_approved_chapter(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    svc.lint_chapter("test", 1)
    ready_memo(svc, "test", 1)
    svc.review_chapter("test", 1)
    svc.approve_chapter("test", 1, "ok")
    rev1 = svc.get_chapter("test", 1).current_revision_id

    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": "正文",
                "replacement": "修正后的正文",
                "reason": "proofread",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
            "--allow-below-minimum",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "reopen" in data["error"]["message"].lower() or "重开" in data["error"]["message"]
    assert svc.get_chapter("test", 1).current_revision_id == rev1

    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
            "--reopen-reason",
            "fix typo",
            "--allow-below-minimum",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert svc.get_chapter("test", 1).current_revision_id != rev1


def test_write_revision_patch_preserves_quote_boundaries(tmp_path: Path, capsys):
    """Regression: evidence must include surrounding quotes to avoid ""...""."""
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text('她问："妈，井水是不是生气了。"\n', encoding="utf-8")
    svc.write_revision("test", 1, src)

    # Correct patch: evidence includes the existing quotes.
    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": '"妈，井水是不是生气了。"',
                "replacement": '"妈，井水是不是生气了？"',
                "reason": "fix question mark",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
            "--allow-below-minimum",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    rev_path = tmp_path / svc.get_current_revision("test", 1).file_path
    text = rev_path.read_text(encoding="utf-8")
    assert '"妈，井水是不是生气了？"' in text
    assert '""妈' not in text
    assert '妈""' not in text


def test_write_revision_patch_reports_before_after_counts(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("她走进房间。桌上有一封信。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)

    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "第1段",
                "evidence": "桌上有一封信",
                "replacement": "桌上摆着一封未拆的信",
                "reason": "add detail",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
            "--allow-below-minimum",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert "before_count" in data["data"]
    assert "after_count" in data["data"]
    assert data["data"]["before_count"] == 11
    assert data["data"]["after_count"] == 15


def test_write_revision_patch_blocks_dropping_below_minimum(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    # 5003 CJK characters, with a unique prefix so evidence is unique.
    body = "开头" + "中" * 5000 + "结尾。\n"
    src.write_text(body, encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    # Patch deletes 48 CJK characters, dropping below 5000.
    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "开头段",
                "evidence": "开头" + "中" * 50,
                "replacement": "开头中",
                "reason": "shrink",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "below" in data["error"]["message"].lower() or "5000" in data["error"]["message"]
    assert svc.get_chapter("test", 1).current_revision_id == rev1


def test_write_revision_patch_allow_below_minimum(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    body = "开头" + "中" * 5000 + "结尾。\n"
    src.write_text(body, encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "开头段",
                "evidence": "开头" + "中" * 50,
                "replacement": "开头中",
                "reason": "shrink",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
            "--allow-below-minimum",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert svc.get_chapter("test", 1).current_revision_id != rev1
    assert "before_count" in data["data"]
    assert "after_count" in data["data"]


def test_write_revision_patch_4999_rejected_5000_accepted(tmp_path: Path, capsys):
    """Boundary: patch result must be >=5000 CJK unless explicitly allowed."""
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"

    # Current 4999; patch keeps it at 4999 -> rejected.
    body_4999 = "起" + "中" * 4997 + "止。\n"
    src.write_text(body_4999, encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    patch_keep_low = _write_patch(
        tmp_path,
        [
            {
                "location": "开头",
                "evidence": "起中",
                "replacement": "起",
                "reason": "shrink",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch_keep_low),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert "5000" in data["error"]["message"]
    assert svc.get_chapter("test", 1).current_revision_id == rev1

    # Current 4999; patch raises it to exactly 5000 -> accepted.
    patch_raise = _write_patch(
        tmp_path,
        [
            {
                "location": "开头",
                "evidence": "起中",
                "replacement": "起中中",
                "reason": "expand",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch_raise),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["after_count"] == 5000


def test_write_revision_patch_5000_to_4999_rejected(tmp_path: Path, capsys):
    """Current >=5000 and patch drops result to 4999 must be rejected."""
    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    body = "起" + "中" * 4998 + "止。\n"
    src.write_text(body, encoding="utf-8")
    svc.write_revision("test", 1, src)
    rev1 = svc.get_chapter("test", 1).current_revision_id

    patch = _write_patch(
        tmp_path,
        [
            {
                "location": "开头",
                "evidence": "起中",
                "replacement": "起",
                "reason": "shrink by one",
            }
        ],
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "write-revision-patch",
            "write-revision-patch",
            "test",
            "1",
            "--patch-file",
            str(patch),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["message"]
    assert svc.get_chapter("test", 1).current_revision_id == rev1
