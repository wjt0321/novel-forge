"""Tests for semantic planning gates in the books workflow."""

import hashlib
from pathlib import Path

from app.novel_forge.book_gates import (
    check_project_materials,
    check_scene_package,
    narrative_report,
)


def _scene_package(
    *,
    decision: str | None = None,
    cognition: str | None = None,
    falsification: str | None = None,
    responsibility: str | None = None,
    expertise: str | None = None,
    dialogue: str | None = None,
) -> str:
    decision = decision if decision is not None else (
        "- **不能同时得到的两样东西：** 保住体面 / 请求帮助\n"
        "- **角色拒绝承认什么：** 他没有独自完成计划的能力\n"
        "- **角色误读了谁或什么：** 无需：本场不依赖误读\n"
        "- **哪句话不能说出口：** 请别离开\n"
        "- **最终接受的具体代价：** 暴露自己的软弱\n"
    )
    cognition = cognition if cognition is not None else (
        "| 观察事实 | 人物当前假设 | 替代解释 | 置信度 | 可推翻证据 | 本章状态 |\n"
        "|---|---|---|---|---|---|\n"
        "| 对方没有接过钥匙 | 对方准备拒绝交易 | 对方没有看见钥匙 | 中 | 对方稍后主动索要钥匙 | 未决 |\n"
    )
    falsification = falsification if falsification is not None else (
        "- 时间/日历算术：无具体日期；只验证同夜先后顺序。\n"
        "- 物理动作机制：先拿起听筒，再投币拨号，来电与去电不混用。\n"
        "- 人物知识来源：钥匙用途来自管理员当面说明。\n"
        "- 不可逆性反证：签收后责任登记到主角名下，不能当场归还撤销。\n"
        "- 场景停止点：责任登记完成、下一次敲门响起时立即停。\n"
    )
    responsibility = responsibility if responsibility is not None else (
        "| 动作/条件 | 提出或执行者 | 对象 | 当场知情者 | 来源 beat | 后果承担者 |\n"
        "|---|---|---|---|---|---|\n"
        "| 三日期限 | 债权人 | 主角 | 债权人、主角 | 2 | 主角 |\n"
    )
    expertise = expertise if expertise is not None else (
        "- 无需：本章没有依赖专业判断推动的关键行动。\n"
    )
    dialogue = dialogue if dialogue is not None else (
        "无需：本章关键冲突不依赖对白转移事实或责任"
    )
    return (
        "# Scene Package\n\n"
        "## 1. 场景压力\n- 目标：拿到钥匙\n\n"
        "## 1c. 决策问题\n"
        f"{decision}\n"
        "## 1d. 认知与可证伪假设\n"
        f"{cognition}\n"
        "## 1e. 规划反证与常识检查\n"
        f"{falsification}\n"
        "## 2. 在场者状态\n"
        "| 人物 | 表面目标 |\n|---|---|\n| 甲 | 拿到钥匙 |\n\n"
        "## 3. Beat 因果链\n"
        "| # | 触发 | 人物行动 |\n|---|---|---|\n"
        "| 1 | 门被锁上 | 甲索要钥匙 |\n"
        "| 2 | 乙拒绝 | 甲改变条件 |\n\n"
        "## 3c. 因果归属账本\n"
        f"{responsibility}\n"
        "## 4. 信息账本\n"
        "| 信息 | 来源 |\n|---|---|\n| 门被锁上 | 甲亲眼看见 |\n\n"
        "## 5. 信息预算\n"
        "- 主冲突：钥匙归属\n"
        f"- 关键对白意图：{dialogue}\n\n"
        "## 5b. 专业判断审计\n"
        f"{expertise}\n"
        "## 7. 场景余波\n- 关系：甲欠乙一次解释\n"
    )


def test_formal_scene_package_rejects_all_decision_friction_waived():
    decision = (
        "- **不能同时得到的两样东西：** 无（立章）\n"
        "- **角色拒绝承认什么：** 无（立章）\n"
        "- **角色误读了谁或什么：** 无（立章）\n"
        "- **哪句话不能说出口：** 无（立章）\n"
        "- **最终接受的具体代价：** 无（立章）\n"
    )

    blocking = check_scene_package(
        _scene_package(decision=decision), None, mode="formal"
    )

    assert any("决策问题至少填写 2 项" in item for item in blocking)


def test_decision_value_starting_with_wufa_is_not_treated_as_waiver():
    decision = (
        "- **不能同时得到的两样东西：** 保住职位 / 说出真相\n"
        "- **角色拒绝承认什么：** 无法独自完成任务\n"
        "- **角色误读了谁或什么：** 无（立章）\n"
        "- **哪句话不能说出口：** 无（立章）\n"
        "- **最终接受的具体代价：** 无（立章）\n"
    )

    assert check_scene_package(
        _scene_package(decision=decision), None, mode="formal"
    ) == []


def test_formal_scene_package_requires_cognition_ledger_or_explicit_waiver():
    blocking = check_scene_package(
        _scene_package(cognition=""), None, mode="formal"
    )

    assert any("1d. 认知与可证伪假设" in item for item in blocking)


def test_formal_scene_package_requires_all_falsification_checks():
    falsification = (
        "- 时间/日历算术：2026-07-17 是星期五。\n"
        "- 物理动作机制：先拿听筒再投币。\n"
        "- 人物知识来源：管理员当面说明。\n"
        "- 不可逆性反证：签收会登记责任。\n"
        "- 场景停止点：\n"
    )

    blocking = check_scene_package(
        _scene_package(falsification=falsification), None, mode="formal"
    )

    assert any("场景停止点" in item for item in blocking)


def test_formal_scene_package_requires_causal_responsibility_row():
    blocking = check_scene_package(
        _scene_package(responsibility=""), None, mode="formal"
    )

    assert any("因果归属账本至少填写 1 条" in item for item in blocking)


def test_formal_scene_package_accepts_explicit_cognition_and_expertise_waivers():
    package = _scene_package(
        cognition="- 无需：本章没有依赖推断推动的关键行动。\n",
        expertise="- 无需：本章没有依赖专业判断推动的关键行动。\n",
    )

    assert check_scene_package(package, None, mode="formal") == []


def test_exploration_mode_skips_semantic_planning_gates():
    assert check_scene_package("# exploration", None, mode="exploration") == []


def test_degraded_exploration_skips_formal_planning_gates():
    assert check_scene_package(
        "# shell unavailable", None, mode="degraded_exploration"
    ) == []


def test_second_chapter_requires_handoff_section(tmp_path: Path):
    chapter1 = tmp_path / "chapters/e01/ch-01/正文.md"
    chapter2 = tmp_path / "chapters/e01/ch-02/正文.md"
    chapter1.parent.mkdir(parents=True)
    chapter2.parent.mkdir(parents=True)
    chapter1.write_text("# 第一章\n\n晚上九点，陈拾关上门。\n", encoding="utf-8")
    chapter2.write_text("# 第二章\n\n下午三点，陈拾又推开门。\n", encoding="utf-8")
    package = tmp_path / "planning/scene-package-ch02.md"
    package.parent.mkdir()
    package.write_text(_scene_package(), encoding="utf-8")

    report = narrative_report(chapter2, package, mode="formal")

    assert any("章际交接" in item for item in report["blocking"])


def test_same_day_handoff_rejects_time_rollback(tmp_path: Path):
    chapter1 = tmp_path / "chapters/e01/ch-01/正文.md"
    chapter2 = tmp_path / "chapters/e01/ch-02/正文.md"
    chapter1.parent.mkdir(parents=True)
    chapter2.parent.mkdir(parents=True)
    chapter1.write_text("# 第一章\n\n晚上九点，陈拾关上门。\n", encoding="utf-8")
    chapter2.write_text("# 第二章\n\n下午三点，陈拾又推开门。\n", encoding="utf-8")
    digest = hashlib.sha256(chapter1.read_bytes()).hexdigest()
    package = tmp_path / "planning/scene-package-ch02.md"
    package.parent.mkdir()
    package.write_text(
        _scene_package()
        + "\n## 0b. 章际交接\n"
        "- 上一章正文路径：chapters/e01/ch-01/正文.md\n"
        f"- 上一章正文 SHA-256：{digest}\n"
        "- 上一章结尾原文：晚上九点，陈拾关上门。\n"
        "- 本章开头原文：下午三点，陈拾又推开门。\n"
        "- 上一章结束时间：同日晚上九点\n"
        "- 本章开始时间：同日下午三点\n"
        "- 上一章结束地点：门内\n"
        "- 本章开始地点：门内\n"
        "- 上一章结束动作：陈拾关门\n"
        "- 本章开始动作：陈拾推门\n"
        "- 转场类型：same_day_continuous\n",
        encoding="utf-8",
    )

    report = narrative_report(chapter2, package, mode="formal")

    assert any("时间倒退" in item for item in report["blocking"])


def test_handoff_rejects_quotes_from_chapter_middle(tmp_path: Path):
    chapter1 = tmp_path / "chapters/e01/ch-01/正文.md"
    chapter2 = tmp_path / "chapters/e01/ch-02/正文.md"
    chapter1.parent.mkdir(parents=True)
    chapter2.parent.mkdir(parents=True)
    chapter1.write_text(
        "# 第一章\n\n开头。\n\n上一章中段引文。\n\n真正的章末。\n",
        encoding="utf-8",
    )
    chapter2.write_text(
        "# 第二章\n\n真正的章首。\n\n本章中段引文。\n\n结尾。\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(chapter1.read_bytes()).hexdigest()
    package = tmp_path / "planning/scene-package-ch02.md"
    package.parent.mkdir()
    package.write_text(
        _scene_package()
        + "\n## 0b. 章际交接\n"
        "- 上一章正文路径：chapters/e01/ch-01/正文.md\n"
        f"- 上一章正文 SHA-256：{digest}\n"
        "- 上一章结尾原文：上一章中段引文。\n"
        "- 本章开头原文：本章中段引文。\n"
        "- 上一章结束时间：第一天晚上九点\n"
        "- 本章开始时间：第二天上午九点\n"
        "- 上一章结束地点：门内\n"
        "- 本章开始地点：街上\n"
        "- 上一章结束动作：关门\n"
        "- 本章开始动作：走路\n"
        "- 转场类型：cross_day\n",
        encoding="utf-8",
    )

    report = narrative_report(chapter2, package, mode="formal")

    assert any("不在上一章结尾" in item for item in report["blocking"])
    assert any("不在当前章开头" in item for item in report["blocking"])


def test_formal_scene_package_does_not_require_separate_dialogue_ledger():
    package = _scene_package().replace(
        "## 5. 信息预算\n- 主冲突：钥匙归属\n",
        "## 5. 信息预算\n- 主冲突：钥匙归属\n- 关键对白：是\n",
    )

    blocking = check_scene_package(package, None, mode="formal")

    assert not any("关键对白账本" in item for item in blocking)


def test_formal_scene_package_requires_dialogue_intent_or_explicit_waiver():
    blocking = check_scene_package(
        _scene_package(dialogue=""),
        None,
        mode="formal",
    )

    assert any("关键对白意图" in item for item in blocking)


def test_formal_materials_reject_unfilled_story_engine(tmp_path: Path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "planning").mkdir()
    (tmp_path / "memory/worldbuilding.md").write_text(
        "# 世界\n\n- 无需：现实题材。\n", encoding="utf-8"
    )
    (tmp_path / "planning/research-boundaries.md").write_text(
        "# 研究\n\n- 无需：不依赖外部事实。\n", encoding="utf-8"
    )
    (tmp_path / "planning/story-engine.md").write_text(
        "# 故事发动机\n\n## 欲望\n- 主角想要什么？__________\n",
        encoding="utf-8",
    )
    (tmp_path / "memory/voice-bible.md").write_text(
        "# Voice\n\n## exemplar_notes\n- ch01 暂无。\n", encoding="utf-8"
    )

    blocking, _ = check_project_materials(tmp_path, 1)

    assert any("planning/story-engine.md 未填写" in item for item in blocking)
