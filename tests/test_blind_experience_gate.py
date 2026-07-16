"""Blind Experience Gate tests.

The blind reader must judge only the prose revision, never planning assets.
"""

import json
from pathlib import Path

import pytest

from app.novel_forge.models import ReviewVerdict
from app.novel_forge.service import NovelForgeError, NovelForgeService
from app.novel_forge.skill_adapter import main
from tests.conftest import filled_scene_contract_v3, filled_voice_bible


def _setup_revision(svc: NovelForgeService, root: Path) -> Path:
    svc.init_book("test", "Test Book")
    vb = root / "voice.md"
    filled_voice_bible(vb)
    svc.write_voice_bible("test", vb)
    svc.create_chapter("test", 1, "One")
    sc = root / "scene.md"
    filled_scene_contract_v3(sc)
    svc.write_scene_contract("test", 1, sc)
    body = root / "chapter.md"
    body.write_text(
        "她坐下时，膝盖顶住控制台下沿。想把右脚挪开，鞋跟又碰响身后的泵壳。\n\n"
        "门外的脚步停了。她把钥匙攥进掌心，锯齿硌出四个白印。\n\n"
        "‘开门。’\n\n"
        "她没回答，只把椅子横过来卡住门把。\n",
        encoding="utf-8",
    )
    svc.write_revision("test", 1, body)
    svc.lint_chapter("test", 1)
    return body


def _passing_report() -> dict:
    return {
        "spatial_reconstruction": "人物坐在控制台和泵壳之间，膝盖前顶、鞋跟后碰，活动空间不足以直接转身。",
        "body_position_and_contact": "膝盖抵住控制台，鞋跟碰泵壳，钥匙锯齿压在掌心。",
        "action_constraints": "狭窄空间限制腿部移动；门外来人后，她只能用椅子卡门。",
        "emotional_trajectory": "身体受限的烦躁转为警戒，最后落实为拒绝开门的行动。",
        "dialogue_dynamics": "门外命令她开门，她用沉默和卡门动作拒绝，关系从催促升级为对抗。",
        "memorable_images": [
            {
                "location": "line 1",
                "evidence": "膝盖顶住控制台下沿",
                "reader_image": "人物被夹在座椅与控制台之间，腿无法自然伸展",
            },
            {
                "location": "line 1",
                "evidence": "鞋跟又碰响身后的泵壳",
                "reader_image": "脚稍微后移就会撞上身后的机械外壳",
            },
            {
                "location": "line 3",
                "evidence": "锯齿硌出四个白印",
                "reader_image": "她在门外压力下攥紧钥匙，掌心被压出清楚痕迹",
            },
        ],
        "knowledge_gaps": [],
        "verdict": "experience_reconstructable",
        "blocking_issues": [],
    }


def test_blind_packet_contains_body_but_no_planning(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    out = tmp_path / "blind.md"

    packet = service.build_blind_reader_packet("test", 1, out)
    text = out.read_text(encoding="utf-8")

    assert packet.revision_id == service.get_chapter("test", 1).current_revision_id
    assert "膝盖顶住控制台" in text
    assert "Scene Contract" not in text
    assert "Voice Bible" not in text
    assert "Can she escape" not in text
    assert "rusty key" not in text
    assert "作者意图" not in text
    assert "001 |" in text


def test_submit_passing_blind_review_is_bound_to_current_revision(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    review = service.submit_blind_experience_review("test", 1, **_passing_report())

    chapter = service.get_chapter("test", 1)
    assert review.revision_id == chapter.current_revision_id
    assert review.source_scope == "prose_only"
    assert review.verdict == "experience_reconstructable"
    assert len(review.memorable_images) == 3

    summary = service.blind_experience_status("test", 1)
    assert summary.exists is True
    assert summary.passes is True
    assert summary.blocking_issue_count == 0


def test_passing_report_requires_three_concrete_images(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["memorable_images"] = report["memorable_images"][:2]

    with pytest.raises(NovelForgeError, match="at least 3 memorable_images"):
        service.submit_blind_experience_review("test", 1, **report)


def test_memorable_image_evidence_must_exist_in_revision(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["memorable_images"][0]["evidence"] = "舷窗外有一颗红色恒星"

    with pytest.raises(NovelForgeError, match="evidence was not found"):
        service.submit_blind_experience_review("test", 1, **report)


def test_report_rejects_planning_based_language(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["spatial_reconstruction"] = "根据Scene Contract，房间很狭窄。"

    with pytest.raises(NovelForgeError, match="planning-source language"):
        service.submit_blind_experience_review("test", 1, **report)


def test_revision_required_needs_blocking_issue(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["verdict"] = "revision_required"

    with pytest.raises(NovelForgeError, match="requires blocking_issues"):
        service.submit_blind_experience_review("test", 1, **report)


def test_blocking_issue_requires_reader_effect_and_revision_intent(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["verdict"] = "revision_required"
    report["blocking_issues"] = [
        {
            "location": "line 1",
            "evidence": "房间只有三平方米",
            "reader_effect": "读者只收到数字，无法重建人物与物体的相对位置",
        }
    ]

    with pytest.raises(NovelForgeError, match="revision_intent"):
        service.submit_blind_experience_review("test", 1, **report)


def test_review_and_approval_require_passing_blind_gate(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    # Editorial memo alone is no longer enough.
    service.submit_editorial_memo(
        "test",
        1,
        narrative_necessity="The chapter forces action.",
        character_agency="She blocks the door instead of obeying.",
        detail_selection="console, pump shell, key, chair.",
        causal_chain="footsteps → command → silence → chair blocks door.",
        prose_observation="S1 动作可见，空间限制进入了人物选择。",
        verdict="ready_for_editor_decision",
        blocking_issues=[],
    )

    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.CONCERNS
    assert result.blind_experience_status["exists"] is False

    with pytest.raises(NovelForgeError, match="blind experience review"):
        service.approve_chapter("test", 1, "ok")

    service.submit_blind_experience_review("test", 1, **_passing_report())
    result = service.review_chapter("test", 1)
    assert result.verdict == ReviewVerdict.APPROVE
    assert result.blind_experience_status["passes"] is True


def test_old_blind_review_does_not_count_for_new_revision(service: NovelForgeService, tmp_path: Path):
    body = _setup_revision(service, tmp_path)
    service.submit_blind_experience_review("test", 1, **_passing_report())

    body.write_text(body.read_text(encoding="utf-8") + "\n门轴响了一声。\n", encoding="utf-8")
    service.write_revision("test", 1, body)
    service.lint_chapter("test", 1)

    summary = service.blind_experience_status("test", 1)
    assert summary.exists is False
    assert summary.passes is False


def test_adapter_requires_confirmation_and_accepts_report_file(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    _setup_revision(svc, tmp_path)
    report_file = tmp_path / "blind-report.json"
    report_file.write_text(json.dumps(_passing_report(), ensure_ascii=False), encoding="utf-8")

    code = main([
        "--root", str(tmp_path),
        "submit-blind-experience-review", "test", "1",
        "--report-file", str(report_file),
    ])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"

    code = main([
        "--root", str(tmp_path),
        "--confirm", "submit-blind-experience-review",
        "submit-blind-experience-review", "test", "1",
        "--report-file", str(report_file),
    ])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["data"]["verdict"] == "experience_reconstructable"


def test_adapter_builds_blind_packet(tmp_path: Path, capsys):
    svc = NovelForgeService(tmp_path)
    _setup_revision(svc, tmp_path)
    out = tmp_path / "blind.md"

    code = main([
        "--root", str(tmp_path),
        "--confirm", "build-blind-reader-packet",
        "build-blind-reader-packet", "test", "1",
        "--output-file", str(out),
    ])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert out.exists()
    assert "Scene Contract" not in out.read_text(encoding="utf-8")


def test_memorable_image_evidence_must_be_at_least_six_chars(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["memorable_images"][0]["evidence"] = "下"

    with pytest.raises(NovelForgeError, match="at least 6 characters"):
        service.submit_blind_experience_review("test", 1, **report)


def test_memorable_image_evidence_must_be_unique(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["memorable_images"][1]["evidence"] = report["memorable_images"][0]["evidence"]

    with pytest.raises(NovelForgeError, match="duplicates evidence"):
        service.submit_blind_experience_review("test", 1, **report)


def test_nested_fields_also_reject_planning_language(service: NovelForgeService, tmp_path: Path):
    _setup_revision(service, tmp_path)
    report = _passing_report()
    report["memorable_images"][0]["reader_image"] = "The Voice Bible says she feels trapped."

    with pytest.raises(NovelForgeError, match="planning-source language"):
        service.submit_blind_experience_review("test", 1, **report)


def test_write_revision_supersedes_old_blind_review(service: NovelForgeService, tmp_path: Path):
    import sqlite3

    body = _setup_revision(service, tmp_path)
    review = service.submit_blind_experience_review("test", 1, **_passing_report())
    first_review_id = review.id

    body.write_text(body.read_text(encoding="utf-8") + "\n门轴响了一声。\n", encoding="utf-8")
    service.write_revision("test", 1, body)
    service.lint_chapter("test", 1)

    # The old review row is now superseded at the database level.
    db_path = tmp_path / "data" / "novel-forge.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT superseded_at FROM blind_experience_reviews WHERE id = ?",
            (first_review_id,),
        ).fetchone()
        assert row is not None
        assert row["superseded_at"] is not None

    summary = service.blind_experience_status("test", 1)
    assert summary.exists is False
    assert summary.passes is False
