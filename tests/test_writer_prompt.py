"""Tests for the compact vendor-neutral formal writer prompt."""

from __future__ import annotations

import pytest

from app.novel_forge.writer_prompt import (
    FORMAL_WRITER_PROMPT_ID,
    MAX_FORMAL_WRITER_PROMPT_CHARS,
    WriterPromptError,
    render_formal_writer_instructions,
)


def test_formal_writer_prompt_is_short_complete_and_vendor_neutral():
    prompt = render_formal_writer_instructions(1)

    assert prompt.template_id == FORMAL_WRITER_PROMPT_ID
    assert prompt.template_id == "formal-writer/v1"
    assert "第 01 章" in prompt.text
    assert "handoff.md" in prompt.text
    assert "draft/正文.md" in prompt.text
    assert "5000" in prompt.text
    assert "场景压力" in prompt.text
    assert "人物选择" in prompt.text
    assert "行动后果" in prompt.text
    assert "停止点" in prompt.text
    assert "停止并向 Harness 返回阻断原因" in prompt.text
    assert "脚本、状态、证据、审稿或 runtime" in prompt.text
    assert len(prompt.text) <= MAX_FORMAL_WRITER_PROMPT_CHARS

    lowered = prompt.text.lower()
    for vendor in ("claude", "deepseek", "openai", "anthropic", "minimax"):
        assert vendor not in lowered
    for forbidden in (
        "句长",
        "对白率",
        "比喻密度",
        "validator",
        "校验器源码",
        "ready",
        "sha-256",
    ):
        assert forbidden not in lowered


def test_formal_writer_patch_prompt_preserves_unaffected_prose():
    prompt = render_formal_writer_instructions(3, operation="patch")

    assert prompt.template_id == "formal-writer/v1"
    assert "第 03 章" in prompt.text
    assert "读取 handoff.md 与已预置的 draft/正文.md" in prompt.text
    assert "集中修订" in prompt.text
    assert "保留未受影响的正文" in prompt.text
    assert "重写整章" in prompt.text
    assert len(prompt.text) <= MAX_FORMAL_WRITER_PROMPT_CHARS


@pytest.mark.parametrize("chapter", [0, -1, True])
def test_formal_writer_prompt_rejects_invalid_chapter(chapter):
    with pytest.raises(WriterPromptError, match="chapter"):
        render_formal_writer_instructions(chapter)


def test_formal_writer_prompt_rejects_unknown_operation():
    with pytest.raises(WriterPromptError, match="operation"):
        render_formal_writer_instructions(1, operation="rewrite")
