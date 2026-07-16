import subprocess
import sys
from pathlib import Path

import pytest

from app.novel_forge.cli import main


def _memo_file(tmp_path: Path, verdict: str = "ready_for_editor_decision") -> Path:
    path = tmp_path / "memo.json"
    path.write_text(
        "{\n"
        '  "narrative_necessity": "Forces the protagonist to act rather than wait.",\n'
        '  "character_agency": "She breaks the window; alternative is surrender; cost is injury.",\n'
        '  "detail_selection": "rusty key, broken window, blood.",\n'
        '  "causal_chain": "trap → choice → injury → escape.",\n'
        '  "prose_observation": "S1: the phrase \\"正文\\" could be shown through concrete motion rather than summary; revise to visible action.",\n'
        f'  "verdict": "{verdict}",\n'
        '  "blocking_issues": []\n'
        "}\n",
        encoding="utf-8",
    )
    return path


def _blind_report_file(tmp_path: Path) -> Path:
    path = tmp_path / "blind.json"
    path.write_text(
        "{\n"
        '  "spatial_reconstruction": "The prose places the character in a bounded space.",\n'
        '  "body_position_and_contact": "The body contacts the immediate setting.",\n'
        '  "action_constraints": "The setting limits action and forces a choice.",\n'
        '  "emotional_trajectory": "Pressure becomes visible through action.",\n'
        '  "dialogue_dynamics": "Speech or silence changes the immediate resistance.",\n'
        '  "memorable_images": ['
        '{"location": "line 1", "evidence": "第一段正文内容", "reader_image": "bounded space"}, '
        '{"location": "line 2", "evidence": "第二段正文内容", "reader_image": "physical obstacle"}, '
        '{"location": "line 3", "evidence": "第三段正文内容", "reader_image": "consequential action"}],\n'
        '  "knowledge_gaps": [],\n'
        '  "verdict": "experience_reconstructable",\n'
        '  "blocking_issues": []\n'
        "}\n",
        encoding="utf-8",
    )
    return path


def _submit_blind_review(tmp_path: Path) -> None:
    from app.novel_forge.service import NovelForgeService

    svc = NovelForgeService(tmp_path)
    report = __import__("json").loads(_blind_report_file(tmp_path).read_text(encoding="utf-8"))
    svc.submit_blind_experience_review("test", 1, **report)


def run_cli(args: list[str]) -> tuple[int, str, str]:
    code = main(args)
    # main prints to stdout/stderr directly; use subprocess for capture.
    return code, "", ""


def test_cli_init_book_and_create_chapter(tmp_path: Path):
    code = main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    assert code == 0

    code = main(
        ["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"]
    )
    assert code == 0


def test_cli_duplicate_book_rejected(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    code = main(["--root", str(tmp_path), "init-book", "test", "--title", "Other"])
    assert code == 1


def test_cli_write_revision_and_lint(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text("他喊道——停下。\n", encoding="utf-8")

    code = main(
        [
            "--root",
            str(tmp_path),
            "write-revision",
            "test",
            "1",
            "--from-file",
            str(src),
            "--note",
            "first",
        ]
    )
    assert code == 0

    code = main(["--root", str(tmp_path), "lint-chapter", "test", "1"])
    assert code == 1  # blocking lint


def test_cli_approve_blocked_by_blocking_lint(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text("他喊道——停下。\n", encoding="utf-8")
    main(["--root", str(tmp_path), "write-revision", "test", "1", "--from-file", str(src)])
    main(["--root", str(tmp_path), "lint-chapter", "test", "1"])
    main(["--root", str(tmp_path), "review-chapter", "test", "1"])

    code = main(["--root", str(tmp_path), "approve-chapter", "test", "1", "--note", "ok"])
    assert code == 1


def test_cli_approve_success(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text(
        "第一段正文内容。第二段正文内容。第三段正文内容。\n", encoding="utf-8"
    )
    main(["--root", str(tmp_path), "write-revision", "test", "1", "--from-file", str(src)])
    main(["--root", str(tmp_path), "lint-chapter", "test", "1"])
    main(
        [
            "--root",
            str(tmp_path),
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(_memo_file(tmp_path)),
        ]
    )
    _submit_blind_review(tmp_path)
    main(["--root", str(tmp_path), "review-chapter", "test", "1"])

    code = main(["--root", str(tmp_path), "approve-chapter", "test", "1", "--note", "ok"])
    assert code == 0


def test_cli_export_markdown(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text(
        "第一段正文内容。第二段正文内容。第三段正文内容。\n", encoding="utf-8"
    )
    main(["--root", str(tmp_path), "write-revision", "test", "1", "--from-file", str(src)])
    main(["--root", str(tmp_path), "lint-chapter", "test", "1"])
    main(
        [
            "--root",
            str(tmp_path),
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(_memo_file(tmp_path)),
        ]
    )
    _submit_blind_review(tmp_path)
    main(["--root", str(tmp_path), "review-chapter", "test", "1"])
    main(["--root", str(tmp_path), "approve-chapter", "test", "1", "--note", "ok"])

    code = main(["--root", str(tmp_path), "export-book", "test", "--format", "markdown"])
    assert code == 0


def test_cli_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_build_blind_reader_packet(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text("第一段正文内容。\n", encoding="utf-8")
    main(["--root", str(tmp_path), "write-revision", "test", "1", "--from-file", str(src)])

    out = tmp_path / "blind.md"
    code = main([
        "--root", str(tmp_path),
        "build-blind-reader-packet", "test", "1",
        "--output-file", str(out),
    ])
    assert code == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "第一段正文内容" in text
    assert "Scene Contract" not in text


def test_cli_submit_blind_experience_review(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text(
        "第一段正文内容。第二段正文内容。第三段正文内容。\n", encoding="utf-8"
    )
    main(["--root", str(tmp_path), "write-revision", "test", "1", "--from-file", str(src)])

    report_file = _blind_report_file(tmp_path)
    code = main([
        "--root", str(tmp_path),
        "submit-blind-experience-review", "test", "1",
        "--report-file", str(report_file),
    ])
    assert code == 0

    code = main([
        "--root", str(tmp_path),
        "blind-experience-status", "test", "1",
    ])
    assert code == 0


def test_cli_blind_commands_end_to_end_approval(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text(
        "第一段正文内容。第二段正文内容。第三段正文内容。\n", encoding="utf-8"
    )
    main(["--root", str(tmp_path), "write-revision", "test", "1", "--from-file", str(src)])
    main(["--root", str(tmp_path), "lint-chapter", "test", "1"])
    main(
        [
            "--root",
            str(tmp_path),
            "submit-editorial-memo",
            "test",
            "1",
            "--memo-file",
            str(_memo_file(tmp_path)),
        ]
    )

    out = tmp_path / "blind.md"
    code = main([
        "--root", str(tmp_path),
        "build-blind-reader-packet", "test", "1",
        "--output-file", str(out),
    ])
    assert code == 0

    report_file = _blind_report_file(tmp_path)
    code = main([
        "--root", str(tmp_path),
        "submit-blind-experience-review", "test", "1",
        "--report-file", str(report_file),
    ])
    assert code == 0

    code = main(["--root", str(tmp_path), "review-chapter", "test", "1"])
    assert code == 0

    code = main(["--root", str(tmp_path), "approve-chapter", "test", "1", "--note", "ok"])
    assert code == 0
