from __future__ import annotations

from pathlib import Path

from app.novel_forge import book_arcs
from app.novel_forge.book_gates import check_arc_position
from app.novel_forge.project_templates import init_book_project


def _write_arc(book_dir: Path, name: str = "林晚") -> None:
    (book_dir / "planning/arcs" / f"{name}.md").write_text(
        "# 人物弧线 — "
        + name
        + "\n\n## 信念起点\n- 她一开始坚信什么：规矩能保命\n\n"
        "## 弧线刻度\n| # | 章 | 事件 | 信念变化 | 付出的代价 |\n"
        "|---|---|---|---|---|\n"
        "| 1 | ch03 | 目击同事被牺牲 | 开始怀疑规矩 | 失去搭档 |\n"
        "| 2 | ch07 | 亲手违反规程救人 | 规矩优先级动摇 | 被停职 |\n\n"
        "## 当前位置\n- 截至最新晋升章节，他/她处在哪一格：\n"
        "  怀疑规矩但尚未公开反抗\n"
        "- 下一次动摇的候选触发（不承诺章节）：\n",
        encoding="utf-8",
    )


def test_init_creates_arc_template(tmp_path: Path):
    init_book_project(tmp_path, "demo", "演示书", "都市")
    book_dir = tmp_path / "books" / "demo"
    assert (book_dir / "planning/arcs/_template.md").is_file()
    assert book_arcs.arc_files(book_dir) == []


def test_arc_digest_reports_position_and_latest_beat(tmp_path: Path):
    init_book_project(tmp_path, "demo", "演示书", "都市")
    book_dir = tmp_path / "books" / "demo"
    _write_arc(book_dir)

    digest = book_arcs.arc_digest(book_dir)
    assert digest.startswith("## 人物弧线")
    assert "林晚" in digest
    assert "怀疑规矩但尚未公开反抗" in digest
    assert "ch07" in digest
    assert "已记刻度 2 格" in digest


def test_scene_package_arc_position_advisory_rules():
    package_without = "# Scene Package\n\n## 6. 人物性呼吸段\n- 私人欲望：x\n"
    assert check_arc_position(package_without, chapter_number=1) == []
    advisory = check_arc_position(package_without, chapter_number=2)
    assert advisory and "弧线位置" in advisory[0]
    package_with = (
        "# Scene Package\n\n## 6. 人物性呼吸段\n"
        "- 弧线位置（第 2 章起必填：关键人物本章开始时处于 "
        "planning/arcs/ 账本的哪一格；首章写 起点）：怀疑规矩但未公开\n"
    )
    assert check_arc_position(package_with, chapter_number=2) == []
