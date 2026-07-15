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
    src.write_text("正文。\n", encoding="utf-8")
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
    main(["--root", str(tmp_path), "review-chapter", "test", "1"])

    code = main(["--root", str(tmp_path), "approve-chapter", "test", "1", "--note", "ok"])
    assert code == 0


def test_cli_export_markdown(tmp_path: Path):
    main(["--root", str(tmp_path), "init-book", "test", "--title", "Test"])
    main(["--root", str(tmp_path), "create-chapter", "test", "1", "--title", "One"])
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
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
    main(["--root", str(tmp_path), "review-chapter", "test", "1"])
    main(["--root", str(tmp_path), "approve-chapter", "test", "1", "--note", "ok"])

    code = main(["--root", str(tmp_path), "export-book", "test", "--format", "markdown"])
    assert code == 0


def test_cli_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
