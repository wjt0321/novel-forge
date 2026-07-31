from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.novel_forge.project_templates import init_book_project
from app.novel_forge.workflow import ReviewFinding, WorkflowError, WorkflowRequest
from app.novel_forge.workflow_iteration import (
    apply_local_replacements,
    approve_writer_model_switch,
    compile_writer_package,
    display_workflow_state,
    evaluate_budget_breaker,
    evaluate_writer_model,
    plan_local_patch,
    require_high_risk_confirmation,
)


def _book(root: Path) -> Path:
    init_book_project(root, "demo", "演示书", "现实悬疑")
    book = root / "books/demo"
    (book / "planning/scene-package-ch02.md").write_text(
        "# Scene Package\n\n"
        "## 场景契约\n"
        "主角必须在封锁前进入戏楼，并承担暴露身份的私人代价。\n"
        "## 硬锚点\n"
        "旧钥匙只能转动一次。\n"
        "## 章末目标\n"
        "门内的人先叫出追兵的名字。\n",
        encoding="utf-8",
    )
    chapter = book / "chapters/e01/ch-01"
    chapter.mkdir(parents=True)
    chapter.joinpath("正文.md").write_text(
        "开头不应进入最小包。" * 300
        + "\n\n"
        + "结尾的铜铃响了三次，林舟把旧钥匙压进掌心。" * 80,
        encoding="utf-8",
    )
    (book / "memory/worldbuilding.md").write_text(
        "# World\n\n旧城建筑会保存死者留下的声音。" * 80,
        encoding="utf-8",
    )
    return book


def test_minimal_writer_package_is_tiered_bounded_and_uses_previous_ending(
    tmp_path: Path,
):
    book = _book(tmp_path)
    handoff = book / "planning/chapter-sequences/handoff.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("完整旧包" * 5000, encoding="utf-8")

    package = compile_writer_package(
        tmp_path,
        "demo",
        chapter=2,
        volume=1,
        handoff_path=handoff,
        mode="minimal",
    )

    text = package["text"]
    assert package["mode"] == "minimal"
    assert package["tiers"]["P0"]["cjk"] <= 2000
    assert package["tiers"]["P1"]["cjk"] <= 1200
    assert package["tiers"]["P2"]["cjk"] <= 800
    assert "结尾的铜铃响了三次" in text
    assert "开头不应进入最小包" not in text
    assert "完整旧包" not in text
    assert (book / "memory/voice-bible-v01.md").is_file()


def test_full_writer_package_keeps_legacy_handoff_as_comparison_mode(tmp_path: Path):
    book = _book(tmp_path)
    handoff = book / "handoff.md"
    handoff.write_text("完整旧包内容", encoding="utf-8")

    package = compile_writer_package(
        tmp_path,
        "demo",
        chapter=2,
        volume=1,
        handoff_path=handoff,
        mode="full",
    )

    assert package["mode"] == "full"
    assert "完整旧包内容" in package["text"]


def test_writer_model_switch_requires_author_calibration(tmp_path: Path):
    _book(tmp_path)

    first = evaluate_writer_model(tmp_path, "demo", volume=1, model="writer-a")
    same = evaluate_writer_model(tmp_path, "demo", volume=1, model="writer-a")
    switched = evaluate_writer_model(tmp_path, "demo", volume=1, model="writer-b")

    assert first["status"] == "baseline_recorded"
    assert same["status"] == "matched"
    assert switched["status"] == "calibration_required"
    approve_writer_model_switch(
        tmp_path,
        "demo",
        volume=1,
        model="writer-b",
        decision_reference="author-approved-sample-2026-07-31",
    )
    approved = evaluate_writer_model(
        tmp_path, "demo", volume=1, model="writer-b"
    )
    assert approved["status"] == "matched"
    voice = (tmp_path / "books/demo/memory/voice-bible-v01.md").read_text(
        encoding="utf-8"
    )
    assert "writer-b" in voice
    assert "author-approved-sample-2026-07-31" in voice


def test_local_patch_requires_all_open_must_to_be_local_and_unique():
    body = "甲段保留。\n\n乙段有重复解释，需要压缩。\n\n丙段保留。"
    findings = (
        ReviewFinding(
            severity="MUST",
            location="第二段",
            evidence="乙段有重复解释，需要压缩。",
            reader_effect="节奏停滞",
            revision_intent="删去重复解释",
            scope="local",
        ),
    )

    plan = plan_local_patch(body, findings)

    assert plan is not None
    assert plan[0]["target"] == "乙段有重复解释，需要压缩。"
    assert plan[0]["before"] == "甲段保留。"
    assert plan[0]["after"] == "丙段保留。"
    assert plan_local_patch(
        body,
        (ReviewFinding(**{**findings[0].__dict__, "scope": "structural"}),),
    ) is None
    assert plan_local_patch(
        body + "\n\n乙段有重复解释，需要压缩。", findings
    ) is None


def test_local_patch_exact_replacement_rejects_stale_or_duplicate_targets():
    body = "甲。\n\n乙要修改。\n\n丙。"
    replaced = apply_local_replacements(
        body,
        [{"target": "乙要修改。", "replacement": "乙改成动作。"}],
    )
    assert replaced == "甲。\n\n乙改成动作。\n\n丙。"
    with pytest.raises(ValueError, match="精确定位"):
        apply_local_replacements(
            body,
            [{"target": "不存在。", "replacement": "替换。"}],
        )


def test_capability_risk_budget_and_display_policies_are_explicit():
    formal = WorkflowRequest(
        title="书", genre="悬疑", protagonist="甲", world="城",
        conflict="开门", ending_hook="铃响",
        host_capability="native-isolated", chapter_risk="standard",
    )
    formal.validate()
    with pytest.raises(WorkflowError, match="宿主能力"):
        WorkflowRequest(
            title="书", genre="悬疑", protagonist="甲", world="城",
            conflict="开门", ending_hook="铃响",
            host_capability="exploration", chapter_risk="standard",
        ).validate_formal_production()
    assert require_high_risk_confirmation("volume_end") is True
    assert require_high_risk_confirmation("standard") is False
    assert evaluate_budget_breaker(999, soft_limit=1000, hard_limit=2000) == "within"
    assert evaluate_budget_breaker(1000, soft_limit=1000, hard_limit=2000) == "soft"
    assert evaluate_budget_breaker(2000, soft_limit=1000, hard_limit=2000) == "hard"
    assert display_workflow_state("awaiting_writer", patch_round=0) == "写作中"
    assert display_workflow_state("awaiting_writer", patch_round=1) == "待局部修订"
    assert display_workflow_state("decision_required", patch_round=1) == "待作者决定"
