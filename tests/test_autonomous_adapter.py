"""Tests for the v4 autonomous workflow commands in the JSON skill adapter."""

import json
import subprocess
from pathlib import Path

import pytest

from app.novel_forge.skill_adapter import main as adapter_main
from app.novel_forge.service import NovelForgeService
from tests.conftest import filled_scene_contract_v3, filled_voice_bible, ready_memo


def _run(tmp_path: Path, *argv: str) -> tuple[int, dict, str]:
    """Run the skill adapter and return (exit_code, parsed_json, stderr)."""
    import io
    import sys

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture
    try:
        code = adapter_main(["--root", str(tmp_path), *argv])
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    stdout_text = stdout_capture.getvalue()
    stderr_text = stderr_capture.getvalue()
    data = json.loads(stdout_text.strip().splitlines()[-1]) if stdout_text.strip() else {}
    return code, data, stderr_text


def _setup_book(root: Path, slug: str = "auto") -> None:
    svc = NovelForgeService(root)
    svc.init_book(slug, "Auto Book")
    vb = root / "vb.md"
    filled_voice_bible(vb)
    svc.write_voice_bible(slug, vb)
    svc.create_chapter(slug, 1, "One")
    sc = root / "sc.md"
    filled_scene_contract_v3(sc)
    svc.write_scene_contract(slug, 1, sc)


def test_add_research_entry_requires_confirm(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    code, data, _ = _run(
        tmp_path,
        "add-research-entry",
        "auto",
        "--url",
        "https://example.com",
        "--retrieved-at",
        "2026-07-15",
        "--source-type",
        "official",
        "--confidence",
        "A",
        "--claim",
        "claim",
        "--allowed-use",
        "background_only",
        "--fiction-boundary",
        "boundary",
    )
    assert code == 0
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"


def test_add_research_entry_confirmed(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    code, data, _ = _run(
        tmp_path,
        "--confirm",
        "add-research-entry",
        "add-research-entry",
        "auto",
        "--url",
        "https://example.com",
        "--retrieved-at",
        "2026-07-15",
        "--source-type",
        "official",
        "--confidence",
        "A",
        "--claim",
        "claim text",
        "--allowed-use",
        "background_only",
        "--fiction-boundary",
        "boundary",
    )
    assert code == 0
    assert data["ok"] is True
    assert "research_entry_id" in data["data"]


def test_status_book_shows_research_summary(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    _run(
        tmp_path,
        "--confirm",
        "add-research-entry",
        "add-research-entry",
        "auto",
        "--url",
        "u",
        "--retrieved-at",
        "2026-07-15",
        "--source-type",
        "official",
        "--confidence",
        "A",
        "--claim",
        "c",
        "--allowed-use",
        "plot_support",
        "--fiction-boundary",
        "b",
    )
    code, data, _ = _run(tmp_path, "status", "auto")
    assert code == 0
    assert data["data"]["research"]["entry_count"] == 1


def test_update_research_entry_requires_confirm(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    _, data, _ = _run(
        tmp_path,
        "--confirm",
        "add-research-entry",
        "add-research-entry",
        "auto",
        "--url",
        "u",
        "--retrieved-at",
        "2026-07-15",
        "--source-type",
        "official",
        "--confidence",
        "A",
        "--claim",
        "c",
        "--allowed-use",
        "plot_support",
        "--fiction-boundary",
        "b",
    )
    entry_id = data["data"]["research_entry_id"]
    code, data, _ = _run(
        tmp_path,
        "update-research-entry",
        "auto",
        str(entry_id),
        "--verification-state",
        "verified",
    )
    assert code == 0
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"


def test_update_research_entry_confirmed(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    _, data, _ = _run(
        tmp_path,
        "--confirm",
        "add-research-entry",
        "add-research-entry",
        "auto",
        "--url",
        "u",
        "--retrieved-at",
        "2026-07-15",
        "--source-type",
        "official",
        "--confidence",
        "A",
        "--claim",
        "c",
        "--allowed-use",
        "plot_support",
        "--fiction-boundary",
        "b",
    )
    entry_id = data["data"]["research_entry_id"]
    code, data, _ = _run(
        tmp_path,
        "--confirm",
        "update-research-entry",
        "update-research-entry",
        "auto",
        str(entry_id),
        "--verification-state",
        "verified",
    )
    assert code == 0
    assert data["ok"] is True
    assert data["data"]["verification_state"] == "verified"


def test_set_story_engine_confirmed(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    code, data, _ = _run(
        tmp_path,
        "--confirm",
        "set-story-engine",
        "set-story-engine",
        "auto",
        "--secret",
        "s",
        "--desire",
        "d",
        "--alternative-actions",
        "a1",
        "a2",
        "--irreversible-choice",
        "c",
        "--immediate-cost",
        "cost",
        "--thematic-pressure",
        "p",
    )
    assert code == 0
    assert data["data"]["story_engine"]["secret"] == "s"


def test_set_chapter_plan_rejects_library_input(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    plan_file = tmp_path / "library" / "auto" / "plan.json"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    plan_file.write_text("[]", encoding="utf-8")
    code, data, _ = _run(
        tmp_path,
        "--confirm",
        "set-chapter-plan",
        "set-chapter-plan",
        "auto",
        "1",
        "--plan-file",
        str(plan_file),
    )
    assert code == 0
    assert data["ok"] is False
    assert "library" in data["error"]["message"]


def test_set_chapter_plan_rejects_non_utf8(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    plan_file = tmp_path / "plan.json"
    plan_file.write_bytes("不是UTF8".encode("gbk"))
    code, data, _ = _run(
        tmp_path,
        "--confirm",
        "set-chapter-plan",
        "set-chapter-plan",
        "auto",
        "1",
        "--plan-file",
        str(plan_file),
    )
    assert code == 0
    assert data["ok"] is False
    assert "UTF-8" in data["error"]["message"]


def test_set_and_get_chapter_plan(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            [
                {
                    "scene_ref": "s1",
                    "goal": "g",
                    "obstacle": "o",
                    "choice": "c",
                    "cost": "cost",
                    "ending_change": "e",
                },
                {
                    "scene_ref": "s2",
                    "goal": "g2",
                    "obstacle": "o2",
                    "choice": "c2",
                    "cost": "cost2",
                    "ending_change": "e2",
                },
                {
                    "scene_ref": "s3",
                    "goal": "g3",
                    "obstacle": "o3",
                    "choice": "c3",
                    "cost": "cost3",
                    "ending_change": "e3",
                },
                {
                    "scene_ref": "s4",
                    "goal": "g4",
                    "obstacle": "o4",
                    "choice": "c4",
                    "cost": "cost4",
                    "ending_change": "e4",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    code, data, _ = _run(
        tmp_path,
        "--confirm",
        "set-chapter-plan",
        "set-chapter-plan",
        "auto",
        "1",
        "--plan-file",
        str(plan_file),
        "--status",
        "approved_for_writing",
    )
    assert code == 0
    assert data["data"]["chapter_plan"]["status"] == "approved_for_writing"

    code, data, _ = _run(tmp_path, "get-chapter-plan", "auto", "1")
    assert code == 0
    assert len(data["data"]["chapter_plan"]["scenes"]) == 4


def test_record_iteration_requires_confirm(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    issues_file = tmp_path / "issues.json"
    issues_file.write_text("[]", encoding="utf-8")
    code, data, _ = _run(
        tmp_path,
        "record-iteration",
        "auto",
        "1",
        "--writer-role",
        "w",
        "--editor-verdict",
        "revision_required",
        "--blocking-issues-file",
        str(issues_file),
        "--revision-targets",
        "t",
        "--word-count",
        "100",
    )
    assert data["error"]["code"] == "confirmation_required"


def test_check_acceptance_returns_decision(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    code, data, _ = _run(tmp_path, "check-acceptance", "auto", "1")
    assert code == 0
    assert data["data"]["decision"] == "revision_required"
    assert "has_plan" in data["data"]["checks"]


def test_git_checkpoint_requires_confirm(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True, capture_output=True)
    code, data, _ = _run(tmp_path, "git-checkpoint", "auto", "--message", "m")
    assert data["error"]["code"] == "confirmation_required"


def test_status_chapter_includes_plan_and_acceptance(tmp_path: Path) -> None:
    _setup_book(tmp_path)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            [
                {
                    "scene_ref": "s1",
                    "goal": "g",
                    "obstacle": "o",
                    "choice": "c",
                    "cost": "cost",
                    "ending_change": "e",
                }
                for _ in range(4)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _run(
        tmp_path,
        "--confirm",
        "set-chapter-plan",
        "set-chapter-plan",
        "auto",
        "1",
        "--plan-file",
        str(plan_file),
    )
    code, data, _ = _run(tmp_path, "status", "auto", "1")
    assert code == 0
    assert data["data"]["chapter_plan"] is not None
    assert "iteration_count" in data["data"]
    assert "acceptance" in data["data"]
