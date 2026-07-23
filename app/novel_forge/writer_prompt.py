"""Compact vendor-neutral prompt rendering for isolated formal writers."""

from __future__ import annotations

from dataclasses import dataclass

from .models import NovelForgeError
from .planning_spec import MIN_FORMAL_CJK


FORMAL_WRITER_PROMPT_ID = "formal-writer/v1"
MAX_FORMAL_WRITER_PROMPT_CHARS = 1200


class WriterPromptError(NovelForgeError):
    """Raised when a writer prompt cannot be rendered safely."""


@dataclass(frozen=True)
class WriterPrompt:
    """One immutable compiled writer instruction."""

    template_id: str
    text: str


def render_formal_writer_instructions(
    chapter: int,
    *,
    operation: str = "draft",
    patch_directive: str | None = None,
) -> WriterPrompt:
    """Render the bounded instructions for one formal chapter writer."""
    if (
        not isinstance(chapter, int)
        or isinstance(chapter, bool)
        or chapter < 1
    ):
        raise WriterPromptError("chapter 必须是正整数。")
    if operation not in {"draft", "patch"}:
        raise WriterPromptError("operation 必须是 draft 或 patch。")
    if operation == "patch":
        directive = str(patch_directive or "").strip()
        if len(directive) > 420:
            raise WriterPromptError("MUST 修订指令超过字符预算。")
        directive_text = (
            "\n\n本次只处理以下 MUST，不扩写 MAY 或无关段落：\n"
            f"{directive}"
            if directive
            else ""
        )
        writing_task = (
            "读取 handoff.md 与已预置的 draft/正文.md，按审稿结论完成一次"
            "集中修订。只做最小且因果完整的改动，保留未受影响的正文，不得"
            "借 patch 重写整章；不得把 finding 改写成解释段或审稿口吻。"
            "优先把必要动机分散到动作、停顿、关系反应和物件后果中。修订后"
            "仍须形成清晰的场景压力、人物选择、行动后果和停止点。"
            f"{directive_text}"
        )
    else:
        writing_task = (
            "只读取 handoff.md，并据此完成一篇完整章节。正文必须形成清晰的"
            "场景压力、人物选择、行动后果和停止点；保持既有叙事距离与信息释放"
            "方式，但不要复制 Voice exemplar 的具体措辞、动作、物件或句法。"
        )
    literary_boundary = (
        "规划是后台故事义务，不得在正文中逐条证明。允许人物误判、遗漏、自欺和"
        "反应迟半拍；主动选择要落到具体私人代价，身体、物件和位置必须连续。"
        "高压对白要保留不对称目的，不得退化为整齐问答记录，也不要机械插入动作。"
        "慎用完美证据链，禁止机械三连、连续否定翻转和解释性修补。"
    )
    text = (
        f"# Formal Writer Instructions - 第 {chapter:02d} 章\n\n"
        "你是本次 formal chapter writer，只负责当前一章。\n\n"
        f"{writing_task}\n\n{literary_boundary}\n\n"
        "唯一允许写入的文件是 draft/正文.md。除 Markdown 章节标题外，"
        f"文件中只能包含小说叙事正文；正式章节不少于 {MIN_FORMAL_CJK} 个"
        " CJK 汉字。\n\n"
        "不得创建脚本、状态、证据、审稿或 runtime 文件，不得尝试访问"
        "书项目控制面。若输入冲突、能力不足或正式条件无法满足，不要伪造"
        "结果，也不要创建替代文件；停止并向 Harness 返回阻断原因。\n"
    )
    if len(text) > MAX_FORMAL_WRITER_PROMPT_CHARS:
        raise WriterPromptError("formal writer instructions 超过字符预算。")
    return WriterPrompt(
        template_id=FORMAL_WRITER_PROMPT_ID,
        text=text,
    )
