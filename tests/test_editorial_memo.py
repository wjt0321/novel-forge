"""Tests for the Narrative Editorial Memo Gate (milestone 5)."""

import json
from pathlib import Path

import pytest

from app.novel_forge.models import ReviewVerdict
from app.novel_forge.service import NovelForgeError, NovelForgeService
from app.novel_forge.skill_adapter import main
from tests.conftest import filled_scene_contract_v3, filled_voice_bible, ready_memo


def _memo_json_file(
    path: Path,
    verdict: str = "ready_for_editor_decision",
    blocking_issues: list[dict] | None = None,
) -> Path:
    data = {
        "narrative_necessity": "Forces protagonist to act rather than wait.",
        "character_agency": "She breaks the window; alternative is surrender; cost is injury.",
        "detail_selection": "rusty key, broken window, blood.",
        "causal_chain": "trap → choice → injury → escape.",
        "prose_observation": "S1: the phrase \"正文\" could be shown through concrete motion rather than summary; revise to visible action.",
        "verdict": verdict,
        "blocking_issues": blocking_issues or [],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _setup_approvable_chapter(svc: NovelForgeService, root: Path) -> None:
    svc.init_book("test", "Test Book")

    vb_src = root / "vb.md"
    filled_voice_bible(vb_src)
    svc.write_voice_bible("test", vb_src)

    svc.create_chapter("test", 1, "One")
    sc_src = root / "sc.md"
    filled_scene_contract_v3(sc_src)
    svc.write_scene_contract("test", 1, sc_src)

    body = root / "c1.md"
    body.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, body)
    svc.lint_chapter("test", 1)


def test_new_chapter_template_is_v4(service: NovelForgeService):
    service.init_book("test", "Test Book")
    service.create_chapter("test", 1, "One")

    sc = service.get_scene_contract("test", 1)
    sc_path = service.root / sc.current_file_path
    text = sc_path.read_text(encoding="utf-8")
    assert "## character_blindspot_or_pressure" in text
    assert "## irreversible_choice" in text
    assert "## choice_consequence" in text
    assert "## detail_payoff_plan" in text
    assert "## scene_necessity" in text
    assert "## ending_change" in text
    assert "## spatial_layout_and_routes" in text
    assert "## body_state_and_contacts" in text
    assert "## object_affordances" in text
    assert "## environmental_constraints" in text
    assert "## embodied_action_chain" in text
    assert "contract_version: 4" in text


def test_review_without_memo_returns_concerns(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)

    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.CONCERNS
    assert result.editorial_memo_status["exists"] is False


def test_approve_without_memo_blocked(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)
    service.review_chapter("test", 1)

    with pytest.raises(NovelForgeError, match="no active editorial memo"):
        service.approve_chapter("test", 1, "ok")


def test_ready_memo_unlocks_approval(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)
    ready_memo(service, "test", 1)

    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.APPROVE
    assert result.editorial_memo_status["exists"] is True
    assert result.editorial_memo_status["verdict"] == "ready_for_editor_decision"

    chapter = service.approve_chapter("test", 1, "ok")
    assert chapter.state.value == "approved"


def test_revision_required_memo_blocks_approval(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)
    ready_memo(service, "test", 1, verdict="revision_required")

    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.CONCERNS

    with pytest.raises(NovelForgeError, match="verdict is not"):
        service.approve_chapter("test", 1, "ok")


def test_blocking_issues_block_approval(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)
    ready_memo(
        service,
        "test",
        1,
        blocking_issues=[
            {
                "location": "paragraph 3",
                "evidence": "protagonist reacts without decision",
                "effect": "reader feels events happen to her",
                "revision_intent": "show her choosing to act",
            }
        ],
    )

    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.CONCERNS

    with pytest.raises(NovelForgeError, match="unresolved blocking issues"):
        service.approve_chapter("test", 1, "ok")


def test_old_memo_does_not_count_for_new_revision(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)
    ready_memo(service, "test", 1)
    service.review_chapter("test", 1)
    service.approve_chapter("test", 1, "ok")

    v2 = service.root / "v2.md"
    v2.write_text("新正文。\n", encoding="utf-8")
    service.write_revision("test", 1, v2, reopen_reason="new pass")
    service.lint_chapter("test", 1)

    # New revision has no active memo.
    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.CONCERNS
    assert result.editorial_memo_status["exists"] is False

    with pytest.raises(NovelForgeError, match="no active editorial memo"):
        service.approve_chapter("test", 1, "ok")


def test_memo_validation_rejects_empty_fields(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)

    with pytest.raises(NovelForgeError, match="narrative_necessity"):
        service.submit_editorial_memo(
            "test",
            1,
            narrative_necessity="",
            character_agency="x",
            detail_selection="x",
            causal_chain="x",
            prose_observation="S1: 可优化为更具体的动作呈现。",
            verdict="ready_for_editor_decision",
            blocking_issues=[],
        )


def test_memo_validation_rejects_invalid_reviewer_role(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)

    with pytest.raises(NovelForgeError, match="independent_reader_editor"):
        service.submit_editorial_memo(
            "test",
            1,
            narrative_necessity="x",
            character_agency="x",
            detail_selection="x",
            causal_chain="x",
            prose_observation="S1: 可优化为更具体的动作呈现。",
            verdict="ready_for_editor_decision",
            blocking_issues=[],
            reviewer_role="human_editor_jane",
        )


def test_memo_validation_rejects_bad_blocking_issue(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)

    with pytest.raises(NovelForgeError, match="missing 'revision_intent'"):
        service.submit_editorial_memo(
            "test",
            1,
            narrative_necessity="x",
            character_agency="x",
            detail_selection="x",
            causal_chain="x",
            prose_observation="S1: 可优化为更具体的动作呈现。",
            verdict="ready_for_editor_decision",
            blocking_issues=[{"location": "p1", "evidence": "x", "effect": "y"}],
        )


def test_memo_status_metadata_only(service: NovelForgeService):
    _setup_approvable_chapter(service, service.root)
    ready_memo(service, "test", 1)

    summary = service.editorial_memo_status("test", 1)
    assert summary.exists is True
    assert summary.verdict == "ready_for_editor_decision"
    assert summary.blocking_issue_count == 0


def test_adapter_submit_editorial_memo_requires_confirm_and_validates(
    tmp_path: Path, capsys
):
    svc = NovelForgeService(tmp_path)
    _setup_approvable_chapter(svc, tmp_path)

    memo_path = _memo_json_file(tmp_path / "memo.json")

    # Missing confirmation.
    code = main(
        [
            "--root",
            str(tmp_path),
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(memo_path),
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"

    # Bad UTF-8 memo file.
    bad_path = tmp_path / "bad-memo.json"
    bad_path.write_text("中文。\n", encoding="gbk")
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "submit-editorial-memo",
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(bad_path),
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is False
    assert "UTF-8" in data["error"]["message"]

    # Invalid reviewer_role.
    bad_role_path = tmp_path / "bad-role.json"
    bad_role_path.write_text(
        json.dumps(
            {
                "narrative_necessity": "x",
                "character_agency": "x",
                "detail_selection": "x",
                "causal_chain": "x",
                "prose_observation": "S1: 可优化为更具体的动作呈现。",
                "verdict": "ready_for_editor_decision",
                "blocking_issues": [],
                "reviewer_role": "human_editor",
            }
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "submit-editorial-memo",
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(bad_role_path),
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is False
    assert "independent_reader_editor" in data["error"]["message"]

    # Omitted reviewer_role defaults to independent_reader_editor.
    no_role_path = tmp_path / "no-role.json"
    no_role_path.write_text(
        json.dumps(
            {
                "narrative_necessity": "x",
                "character_agency": "x",
                "detail_selection": "x",
                "causal_chain": "x",
                "prose_observation": "S1: 可优化为更具体的动作呈现。",
                "verdict": "ready_for_editor_decision",
                "blocking_issues": [],
            }
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "submit-editorial-memo",
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(no_role_path),
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True

    # Library input rejected.
    lib_path = tmp_path / "library" / "memo.json"
    lib_path.parent.mkdir(parents=True, exist_ok=True)
    _memo_json_file(lib_path)
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "submit-editorial-memo",
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(lib_path),
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is False
    assert "library" in data["error"]["message"]

    # Confirmed success.
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "submit-editorial-memo",
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(memo_path),
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True
    assert data["data"]["editorial_memo"]["verdict"] == "ready_for_editor_decision"
    assert data["state_changed"] is True

    # JSON must not leak memo prose or manuscript body.
    json_text = json.dumps(data)
    assert "Forces protagonist" not in json_text
    assert "正文" not in json_text


def test_adapter_editorial_memo_status_read_only(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    _setup_approvable_chapter(svc, tmp_path)
    ready_memo(svc, "test", 1)

    code = main(
        ["--root", str(tmp_path), "editorial-memo-status", "test", "1"]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True
    assert data["data"]["editorial_memo"]["exists"] is True
    assert data["data"]["editorial_memo"]["verdict"] == "ready_for_editor_decision"

    # No memo prose in JSON.
    assert "Forces protagonist" not in json.dumps(data)


def test_status_chapter_includes_memo_summary(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    _setup_approvable_chapter(svc, tmp_path)
    ready_memo(svc, "test", 1)

    code = main(["--root", str(tmp_path), "status", "test", "1"])
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True
    assert "editorial_memo" in data["data"]
    assert data["data"]["editorial_memo"]["exists"] is True
    assert data["data"]["editorial_memo"]["verdict"] == "ready_for_editor_decision"


def test_adapter_review_includes_memo_status(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    _setup_approvable_chapter(svc, tmp_path)
    ready_memo(svc, "test", 1)

    code = main(["--root", str(tmp_path), "review", "test", "1"])
    assert code == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True
    assert data["data"]["verdict"] == "APPROVE"
    assert data["data"]["editorial_memo"]["exists"] is True
    assert data["data"]["editorial_memo"]["verdict"] == "ready_for_editor_decision"
