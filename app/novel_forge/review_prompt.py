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

人物必须有不肯承认的压力、与他人不对称的关系和可能出错的判断。专业信息只规划
实际操作、限制、成本与风险，不用术语证明人物聪明。规划可使用 high 推理，但输出
只交付允许列表内的 Markdown 文件，不创作证据、审稿或状态。
""",
    )


def render_review_instructions(role: str) -> RolePrompt:
    """Compile one complete literary review task."""
    if role == "blind-reader":
        micro_rules = render_literary_micro_rules(role)
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

只有正文同时具有可重建现场、人物特异性、关系摩擦、主动选择及其余波，并让你自愿继续
阅读，才能给 convincing + continue + pass。MUST 只用于不改就会破坏人物选择、逻辑、
可读性或核心钩子的问题，不为显得严格而制造。
""",
        )
    if role == "chapter-editor":
        micro_rules = render_literary_micro_rules(role)
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
独立判断。每轮一次列全当前 MUST，避免第一次只抓因果、复审才发现对白。MUST 只用于
不处理就不能认定本章成立的问题；风格偏好和可提升项保持 MAY。
""",
        )
    raise ReviewPromptError(f"unknown review role: {role}")
