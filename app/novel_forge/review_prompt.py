"""Vendor-neutral task compilation for planning and literary review roles."""

from __future__ import annotations

from dataclasses import dataclass

from .models import NovelForgeError
from .planning_spec import render_literary_micro_rules


MAX_REVIEW_PROMPT_CHARS = 2200


class ReviewPromptError(NovelForgeError):
    """Raised when a literary role task cannot be compiled safely."""


@dataclass(frozen=True)
class RolePrompt:
    """One bounded, vendor-neutral role task."""

    role: str
    text: str


def _prompt(role: str, text: str) -> RolePrompt:
    rendered = text.strip() + "\n"
    if len(rendered) > MAX_REVIEW_PROMPT_CHARS:
        raise ReviewPromptError(f"{role} instructions 超过字符预算。")
    return RolePrompt(role=role, text=rendered)


def render_planning_instructions() -> RolePrompt:
    """Compile the Writer's planning-only task."""
    return _prompt(
        "writer-planning",
        """
你是当前章 Writer 的规划阶段，只设计本章，不写正文。

完整 Scene Package 是编辑控制面。目标、阻力、主动选择、可见代价、场景停止点和章末
钩子必须具体可执行；替代解释和反证留在编辑专用小节，不要把它们都变成正文必须逐项
说出的推理。只保留一个主选择和少量真正会改变行动的信息，不要预写正文句子、漂亮
收尾、比喻、固定动作或可复制句法。

人物必须有任务之外的私人欲望、不会自动配合的关系摩擦，以及影响观察顺序的感知偏差；
这些内容写入现有 Scene Package，不增加额外规划文件。人物仍可有不肯承认的压力和可能
出错的判断。专业信息只规划实际操作、限制、成本与风险，不用术语证明人物聪明。规划可
使用 high 推理，但输出只交付允许列表内的 Markdown 文件，不创作证据、审稿或状态。
""",
    )


def render_review_instructions(
    role: str,
    *,
    lean: bool = False,
) -> RolePrompt:
    """Compile one complete literary review task."""
    if role == "blind-reader":
        micro_rules = render_literary_micro_rules(role)
        delivery = (
            "只把简短 JSON 结论写入动作指定的 result_file：verdict、must、"
            "human_likeness、reader_desire、emotional_residue、"
            "next_chapter_pull、summary、evidence_quote 和 uncertain_note。"
            "每条 MUST 用紧凑对象"
            "标注 scope=local|structural|blocking，并保留位置、原文和理由；该分类"
            "只用于成本观测，不决定修订路径。evidence_quote 必须逐字来自当前"
            "正文：打开正文文件直接复制完整原句，不要凭记忆改写或截断；若找不到，"
            "改用正文中确实存在的另一句。物件位置/归属/数量矛盾类 MUST，若能给出"
            "正文中唯一原文片段，标 scope=local 并以该片段为 evidence；需跨多段"
            "协调才标 structural。不要填写技术终态、哈希、Session、Runtime、"
            "Guardian、Git 或其他表格。"
            if lean
            else (
                "通过宿主正式结果通道返回结构化判断，不直接写 reviews、状态或"
                "证据；idle/available 不等于报告已送达。"
            )
        )
        return _prompt(
            role,
            f"""
你是独立 Blind Reader，只读当前正文，不读取规划、Canon、机器报告、旧审稿或未来章。
每轮都从头完整阅读，不得只检查上轮问题。

短规则：
{micro_rules}

先按普通读者复述空间、身体、行动约束、情绪移动、对白中的欲望变化和三个可记忆画面，
再判断它是否像一个具体的人在具体关系里行动。清楚、专业、悬疑和谜题成立都不自动等于
有人味；谜题成立不等于愿意追读。

重点识别：高压场景退化为整齐问答记录；人物逐项列完所有替代解释；职业细节只用于证明
聪明；每个动作都像完成规划清单；漂亮结论替读者解释情绪；局部修订形成可见修补接缝；
钩子很多但人物没有不可替代的损失。也要允许真正属于人物的克制、职业语言、仪式复沓和
纯对白，不按固定句数判错。

`human_likeness` 只用 `convincing|uncertain|synthetic`：具体人物的私欲、关系和不整齐
余波成立才是 convincing；好读但仍有通用、工整或解释充分的段落是 uncertain。uncertain 不视为通过：
给 pass 必须 human_likeness=convincing 且 reader_desire=continue；给 uncertain 时必须在 uncertain_note
用一句具体说明指出哪段像通用、工整或解释充分，说明为空则结果无效。
人物主要执行规划、对白主要解释、重复反应或旁白持续替读者总结时是 synthetic。synthetic 必须引用最能
代表人工编排感的正文原句，并最多一条 structural MUST；convincing 则引用最具人物特异性的原句。
`reader_desire` 只用 `continue|conditional|stop`，不能填数字。其他 MUST 仍只用于不改就会破坏人物
选择、逻辑、可读性或核心钩子的问题，不为显得严格而制造。{delivery}
""",
        )
    if role == "chapter-editor":
        micro_rules = render_literary_micro_rules(role)
        if lean:
            return _prompt(
                role,
                f"""
你是独立 Chapter Editor。完整阅读当前暂存正文、当前场景包与必要 Canon（若输入中
提供 Blind Reader 结论，则核对其中问题是否遍布全章），只判断本章是否成立。检查因果、
主角选择与私人代价、对白信息流、句子肌理和连续性；不得直接修改正文，也不得把规划表
翻译成审稿表。

短规则：
{micro_rules}

先独立检查因果与连续性；文学纹理上只确认 Blind Reader 指出的问题是否遍布全章、是否值得消耗
唯一一次修订。机器纹理与 lint 抽样提示只是低成本抽样，不是文学结论，不得据此单独判错。若存在不改就会破坏
人物选择、逻辑、可读性或核心钩子的问题，返回 `verdict=needs_revision` 并一次列全；分布式人工编排
最多一条 structural MUST。每条 MUST 标注 scope=local|structural|blocking，并保留位置、原文和理由；
该分类只用于成本观测，Python 仍按现行章节级集中修订。evidence_quote 必须逐字来自当前正文：打开
正文文件直接复制完整原句，不要凭记忆改写或截断。物件位置/归属/数量矛盾类 MUST，若能给出正文中
唯一原文片段，标 scope=local 并以该片段为 evidence；需跨多段协调才标 structural。风格偏好不要放进
MUST。本章成立则直接 `verdict=pass`，另写简短 `summary` 和一条正文原句 `evidence_quote`。不填写
hard anchor、分析维度、哈希、状态、Session、Runtime、Guardian 或 Git 表格。
""",
            )
        return _prompt(
            role,
            f"""
你是独立 Chapter Editor。先只读正文重建事件、人物选择、代价和停止点，再读取允许的
用户硬锚合同、Scene Package、必要 Canon、Blind Reader 结果和机器诊断。每轮都完整执行五项审查：
因果、能动性、对白信息流、句子肌理、连续性；不得只核对上一轮 finding 是否消失。

短规则：
{micro_rules}

除常规五项外，重点检查四类生产性缺陷：
1. 编辑控制面泄漏：人物是否把替代解释、反证或因果审计逐项说完。
2. 人物可替换性：去掉姓名和职业后，关键选择与关系反应是否仍像通用的冷静能人。
3. 对白现场：高压对白中身体、空间或权力变化是否持续在场；不要用固定台词句数或机械
插动作判错，只有现场退化为整齐记录并削弱冲突时才升级。
4. 修订接缝：因果是否被一个集中解释段补齐，finding 用语是否被直接翻译进正文，局部
修复是否制造新问题。

Scene Package 只能用于比较，不能证明正文已经交付。Blind Reader 的 pass 不能替代
独立判断。用户硬锚合同优先于 Scene Package。必须逐项返回 protagonist、world、
conflict、ending_hook 的 hard_anchor_coverage，填写 status、正文原句 evidence 和
普通读者实际能重建出的 reader_reconstruction。身份、亲缘、方向、数量、物件归属或
行动目标与合同不一致时必须标 conflicted；正文没有交付时标 missing；含蓄但普通读者
仍只能重建出另一种关系，不能标 implicit_but_unambiguous。只有 world 中明确留给后续
章节的部分可标 deferred_by_scene_boundary。missing/conflicted 必须同时形成开放 MUST。

每轮一次列全当前 MUST，避免第一次只抓因果、复审才发现对白。MUST 只用于不处理就不能
认定本章成立的问题；风格偏好和可提升项保持 MAY。通过宿主正式结果通道返回结构化判断，
不直接写 reviews、状态或证据；idle/available 不等于报告已送达。
""",
        )
    raise ReviewPromptError(f"unknown review role: {role}")
