"""Tests for vendor-neutral literary role task compilation."""

from __future__ import annotations

import pytest

from app.novel_forge.review_prompt import (
    MAX_REVIEW_PROMPT_CHARS,
    ReviewPromptError,
    render_planning_instructions,
    render_review_instructions,
)


def test_planning_task_separates_editor_reasoning_from_writer_story_material():
    prompt = render_planning_instructions()

    assert "完整 Scene Package 是编辑控制面" in prompt.text
    assert "不要预写正文句子" in prompt.text
    assert "替代解释和反证留在编辑专用小节" in prompt.text
    assert "high" in prompt.text
    assert len(prompt.text) <= MAX_REVIEW_PROMPT_CHARS


def test_blind_reader_task_judges_life_not_only_clarity_or_mystery():
    prompt = render_review_instructions("blind-reader")

    assert "只读当前正文" in prompt.text
    assert "谜题成立不等于愿意追读" in prompt.text
    assert "整齐问答记录" in prompt.text
    assert "逐项列完所有替代解释" in prompt.text
    assert "修补接缝" in prompt.text
    assert "每轮都从头完整阅读" in prompt.text
    assert "人物欲望是否进入动作、关系和代价" in prompt.text
    assert "漂亮结论替代现场余波" in prompt.text
    assert len(prompt.text) <= MAX_REVIEW_PROMPT_CHARS


def test_chapter_editor_task_requires_complete_review_every_round():
    prompt = render_review_instructions("chapter-editor")

    assert "每轮都完整执行五项审查" in prompt.text
    assert "不得只核对上一轮 finding" in prompt.text
    assert "编辑控制面泄漏" in prompt.text
    assert "人物可替换性" in prompt.text
    assert "身体、空间或权力变化" in prompt.text
    assert "集中解释段" in prompt.text
    assert "固定台词句数" in prompt.text
    assert "用户硬锚合同优先于 Scene Package" in prompt.text
    assert "时间方向、金额或数量、物件位置、人物知识来源" in prompt.text
    assert len(prompt.text) <= MAX_REVIEW_PROMPT_CHARS


def test_review_tasks_are_vendor_neutral():
    combined = (
        render_planning_instructions().text
        + render_review_instructions("blind-reader").text
        + render_review_instructions("chapter-editor").text
    ).lower()

    for vendor in ("claude", "deepseek", "openai", "anthropic", "codex"):
        assert vendor not in combined


def test_review_task_rejects_unknown_role():
    with pytest.raises(ReviewPromptError, match="role"):
        render_review_instructions("lead")
