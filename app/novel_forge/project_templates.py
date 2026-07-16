"""Templates for the new `books/<slug>/` front-of-house project layout.

This module is intentionally separate from the core SQLite-backed service.
The new layout does not require a database to be usable by a writing Agent;
legacy `library/` workflows remain intact.

Rule single-sourcing: the generated `tools/*.py` are thin shells delegating
to `app.novel_forge.lint` / `app.novel_forge.book_gates`, and structural
constants (section headings, chapter states, review roles) come from
`app.novel_forge.planning_spec`. Never fork rule logic into these strings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .planning_spec import (
    CHAPTER_STATES,
    MECHANISM_CLAUSES,
    genre_preset,
)


class ProjectTemplateError(Exception):
    """Raised when project template arguments are invalid."""


_REPO_PROBE = '''def _find_repo_root() -> Path:
    import os

    override = os.environ.get("NOVEL_FORGE_ROOT")
    candidates = [Path(override)] if override else []
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "app" / "novel_forge" / "lint.py").exists():
            return candidate
    raise SystemExit(
        "Cannot locate the novel-forge repository root (app/novel_forge not found). "
        "Run inside the repository, or set NOVEL_FORGE_ROOT to the repository root; "
        "regenerate tools via sync-tools if the layout changed."
    )


_REPO_ROOT = _find_repo_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
'''


QUALITY_CHECK_PY = '''"""Surface prose quality gate for one Markdown file (thin shell).

All rules live in the canonical `app.novel_forge.lint` module at the
repository root; this script only locates the repo and delegates, so every
book always runs the current ruleset. It flags locations for human review;
it does NOT judge literary quality and never auto-edits the text. A passing
result does not mean the prose is literary, publishable, or user-approved.

Usage:
    python tools/quality_check.py PATH_TO_CHAPTER.md
"""

import sys
from pathlib import Path

''' + _REPO_PROBE + '''
from app.novel_forge.lint import format_report, lint_file


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("Usage: python tools/quality_check.py <markdown-file>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    print(format_report(path, lint_file(path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


NARRATIVE_GATE_PY = '''"""Structural narrative gate (thin shell over app.novel_forge.book_gates).

Checks the scene package, dialogue ledger, chapter body, and book-level
materials (worldbuilding / research boundaries / voice-bible). It does not
score literary quality.

Usage: python tools/narrative_gate.py CHAPTER.md SCENE_PACKAGE.md
"""

import sys
from pathlib import Path

''' + _REPO_PROBE + '''
from app.novel_forge.book_gates import narrative_gate_main


if __name__ == "__main__":
    raise SystemExit(narrative_gate_main())
'''


_STATE_CHAIN = " → ".join(CHAPTER_STATES)


def _claude_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    mechanism = MECHANISM_CLAUSES[genre_preset(genre)]
    return f"""# 小说宪法：《{title}》

## 基本信息
- slug: `{slug}`
- 标题: 《{title}》
- 类型: {genre}
- 创建时间: {timestamp}
- **工作流版本**: v3.1（场景包、动作稿、对白账本、双编辑、盲读者、宏观编辑与章节编排）

## 正文明确定义
本书唯一正文入口：

```
books/{slug}/chapters/eXX/ch-XX/正文.md
```

- 每章一个目录，命名规则 `e{{序号}}/ch-{{序号}}`。
- 目录内只放 `正文.md`，不放多个草稿版本。
- 历史版本由外部 Git 管理；不要在此目录堆叠 `正文-v2.md`。

## 当前进度
- 最新场景/章节: ________________
- 下一场目标: ________________
- 未回收承诺（最多列 3 条）: ________________

## 写作输入优先级
当接到“写下一章/场景”时，按以下顺序读取：
1. `planning/story-engine.md` — 核心张力
2. `memory/voice-bible.md` — 本书声音宪法：距离、节奏、语言指纹、感官调色板、范文锚定
3. `memory/past.md` — 已发生事实
4. `memory/worldbuilding.md` — 世界规则
5. `planning/scene-package-chXX.md` — 目标、阻力、beat 因果链与信息账本
6. `planning/action-draft-chXX.md` — 动作版因果底稿
7. `planning/dialogue-ledger-chXX.md` — 关键对白账本（如有）
8. 上一条 `chapters/eXX/ch-XX/正文.md` 的最后 20%
9. `planning/research-boundaries.md` — 事实红线

## 严格边界
- 禁止自动批量生成多章。
- 禁止在未读 `memory/`（含 voice-bible）和 `planning/story-engine.md` 的情况下写正文。
- {mechanism}
- 禁止 `——`、`……`、`不是X而是Y`、结论性旁白升华。
- 正式章节不少于 5000 个 CJK 汉字；更短的只能标为实验片段。字数是底线不是目标：靠复述与注水凑字数的章同样不合格（见信息预算与 line-editor 重复簇审查）。
- 起草前完成本章场景包和动作稿；存在关键对白时完成对白账本。正文润色不得新增动作稿外的关键事件、设定、人物动机或长线谜团。
- 起草前按 voice-bible 的写前仪式写一段角色独白（不进入正文），并用 exemplar_notes 的范文段落校准本章目标声音。
- 每章写完后必须运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md` 与 `python tools/narrative_gate.py chapters/eXX/ch-XX/正文.md planning/scene-package-chXX.md`。
- 审稿必须落盘：每个审稿角色的结论写入 `reviews/chXX-<role>.md`（格式见 `reviews/review-template.md`），chapter-state 证据表只存文件指针与 verdict。
- 修订优先局部 patch；因果或信息失败时回到场景包/动作稿，结构失败才重写场景。
- patch 命名：`patches/ch-{{章节号}}-{{功能}}.md`；只记录局部修订意图、位置、替换范围和验证结果，不替换整章正文。应用后重跑质检、相关编辑和一致性检查。
- `tools/*.py` 是仓库规则的薄壳，不要手工编辑；由 `sync-tools` 统一刷新。
- 本模板默认包含 v3 编排资产；所有状态、记忆、审稿和上下文材料只留在本书目录内，严禁复制其他书的正文、`memory/`、`reviews/`、`context-cache/` 或已填写 `chXX` 实例。

## 角色团队（按子代理职责分派，定义见 `.claude/agents/`）
- `context-collector`: 写前收集最小上下文，输出到 `memory/context-cache/`。
- `orchestrator`: 维护章节状态、门禁证据与回退决策，不写正文。
- `causal-editor`: 审场景因果、信息账本、术语预算与人物行动后果。
- `line-editor`: 审对白归属、重复、节奏方差与解释性行文。
- `consistency-guard`: 写后检查实体、时间线、未回收承诺，输出报告。
- `blind-reader`: 只读正文，重建空间/身体/行动/情绪轨迹/对话动态与可记忆画面。
- `chapter-editor`: 宏观五维审稿（轻量 Editorial Memo），输出 verdict。
"""


def _readme_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    return f"""# 《{title}》

- 类型: {genre}
- 创建时间: {timestamp}
- 默认工作流: v3.1；完整编排说明见 `.agents/skills/novel-forge/SKILL.md`。

## 如何阅读
打开最新正文：

```
books/{slug}/chapters/eXX/ch-XX/正文.md
```

## 目录
- `chapters/` — 正文唯一入口
- `memory/` — 人物、历史、世界设定、voice-bible
- `planning/` — 故事发动机、研究边界、场景包、章节状态
- `reviews/` — 审稿记录（每个角色一份，含 verdict）
- `patches/` — 局部修订 patch
- `.snapshots/` — 临时快照

## 默认工作流
1. `context-collector` 收集最小上下文，并建立章节状态。
2. 填写 `scene-package`、`action-draft`；有关键对白时填写 `dialogue-ledger`。
3. 按 `CLAUDE.md` 宪法与 `memory/voice-bible.md` 起草 `正文.md`，润色不得偷渡关键事件、设定或动机。
4. 运行 `quality_check.py` 和 `narrative_gate.py`。
5. 依次交 `causal-editor`、`line-editor`、`consistency-guard`、`blind-reader`、`chapter-editor` 审阅，结论落盘到 `reviews/`；由 `orchestrator` 记录门禁及回退。
6. 修订：结构问题回到场景包/动作稿，纯行文问题才用局部 patch。

所有 v3 资产只在本书目录内使用；不得复制其他书的正文、记忆、审稿报告、上下文缓存或已填写章节实例。完整约定见 `.agents/skills/novel-forge/SKILL.md`。
"""


def _memory_past_md() -> str:
    return """# 过去时间线

## 已锁定事实
- 记录既成事件，不写未发生内容。
- 每条事实尽量带场景出处。

## 待揭示 / 角色未知
- 写角色不知道的真相，并标注“角色未知”。

## 当前时间锚
- 故事现在时: ________________
"""


def _memory_worldbuilding_md() -> str:
    return """# 世界设定

> 本章/本书若确无世界规则可填（如纯现实题材），在任意一节写明“无需”并给一句理由；
> 空模板会被 narrative_gate 判为未填写。

## 物理规则
- 现实世界还是奇幻？__________
- 限制 / 不可能发生的事：__________

## 社会规则
- 时代、地点、权力结构：__________
- 日常物件与语言：__________

## 禁忌
- 人物不能说什么、做什么：__________
"""


def _memory_future_index_md() -> str:
    return """# 未来索引

## 已规划但尚未写的场景
- 场景 ref / 目标 / 关键转折

## 未回收承诺
- 承诺内容 / 预计回收场景

## 备用结局 / 分支
- 仅供参考，不自动执行
"""


_VOICE_PALETTES: dict[str, str] = {
    "urban": """都市现实调色板：日常物件与社会纹理优先——价格、牌子、磨损程度、别人的眼光。
- 听觉具体到来源（打印机、叫号喇叭、免提外放的电视声）；嗅觉不诗化（消毒水、油烟）。
- 金钱与面子的数目字可以出现，但必须落到动作（输密码的手、凭条的温度），不得悬空报数。
- 示例方向："卡片贴着凹槽滑到他指尖前"，而不是"他尴尬地接过卡"。""",
    "fantasy": """幻想调色板：超自然感对应一种核心身体感官通道（温度/压力/纹理/节奏），区分质地而非只说"强大"。
- 视觉给出稳定的色调偏好；听觉具体到频率与间隔。
- 每个生造术语第一次出现必须伴随身体代价或操作动作，永远不得以解释性旁白落地。
- 示例方向："灵力过处先热后寒"，而不是"一股强大的灵力波动"。""",
    "wasteland": """末世/科幻调色板：感官降级——可用感官被世界削减（没有鸟叫、没有新鲜气味），写"缺席"而非堆砌。
- 痛觉、口渴、疲劳作为常驻底噪，但同一感受不得用同一措辞出现两次。
- 物件以残缺状态出现（烧剩的、压扁的、褪色的），功能性物件写清操作与故障。
- 示例方向："空气里没有活物的声音"，而不是"死一般的寂静"。""",
    "generic": """选一种主导感官通道并全书保持一致；听觉具体到来源与频率；嗅觉不诗化。
- 每个抽象判断都要能换成一个具体物象；写不出物象时，删掉那个判断。""",
}


def _memory_voice_bible_md(title: str, genre: str) -> str:
    preset = genre_preset(genre)
    palette = _VOICE_PALETTES[preset]
    return f"""# Voice Bible — 《{title}》

> 本书的声音宪法。硬禁令只保留机器可检测的少数几条；其余全部是正面引导：
> 给方向与示范，不给填空表。每章起草前必读；修改本文件属于书级决策，需记录原因。

## narrative_distance
第三人称有限视角，锚定 ______。读者只感知 ______ 能感知的；不跳入其他角色内心，不以叙述者口吻解释世界。
- 动作场景：收紧到"当下身体感知"级别（体温、肌肉、呼吸）。
- 静态场景：维持在"选择性注意"级别（他注意到什么、忽略什么、为什么）。

## focalization
全程 ______。他/她对世界的认知受限于：______。
他/她还不知道的：______。

## 节奏蓝图（每章写作前必读）
一章的节奏不是均匀的，像呼吸一样有起伏：
```
[开场] 密集建立空间与身体 → 用具体物象锚定感官
[升温] 对话交锋，节奏加快 → 冲突通过"对话—动作—对话"推进
[慢拍] 纯粹感知段落 → 1-2 段，不推进情节、不给新信息
[加速] 危机逼近 → 感知先行，句子趋短但不均匀
[高潮] 不可逆动作 → 每句只承载一个动作或一个感知
[收束] 回到身体 → 呼吸、心跳、温度
```
**人物性呼吸段**：不按字数配额插入。呼吸段必须标注人物功能（回避/拖延/误读/身体失控/关系余温/价值暴露），并记录在 scene-package 第 6 节。

## sentence_rhythm
管的是"方差"，不是"长短"。一段之内句长应有可感的起伏；连续三句长度相近就拆开或合并。
- 全短的均匀段是碎，全长的均匀段是糊——两者都是机械节奏。
- 对话场景的节奏由说话人此刻想说什么、不想说什么、被什么打断来驱动，不由性格标签驱动。
- 想用三个以上结构相似的短句（"他感觉到……他看见……他意识到……"）时，删掉其中两句，用物象替代情绪。

## 角色语言指纹
不用标签写对话（"X=命令句"）。每个主要角色写一段症状化指纹：他的语言习惯来自什么经历，紧张时句子怎么变，他永远不说哪种话。
- ______（主角）：
- ______：

### 对白铁律（仅 2 条）
- 台词卡禁止：连续四句以上仅有引号、无动作/心理/场景穿插的纯对白 → MUST。
- 归属感强制：三句以上无说话人标识的短对话连续出现 → MUST。

## sensory_palette
{palette}

## 术语纪律
- 本章新生造术语预算：0-2 条，须登记在 scene-package 第 5 节。
- 每条术语必须落到身体接触、相对位置、可操作物或受阻动作，不得以解释性旁白落地。

## emotional_restraint
情绪用生理变化 + 决定 + 行动延迟呈现，不用内心独白总结。
想写"他感到愤怒/绝望/悲哀"时停下来问：此刻他的身体哪里在变化？他的手在做什么？他选择了不说哪句话？

## 硬禁令（仅 3 条，全部机器可检）
1. 禁止 `——` 和 `……`。
2. 禁止 `不是X，而是Y / 不是X，是Y` 式否定翻转。
3. 禁止"他意识到/他终于明白"式解释性导语——用身体反应呈现认知。

## 正面引导
- 替代"仿佛在说/似乎在宣告"：换成角色注意到了什么。
- 替代感叹号：删掉它，重新找那个准确的词。
- 替代套话（"冷光闪烁""数据流如瀑布"）：用这间屋子里真正能看到、听到、摸到的东西。

## 写前仪式：角色独白
动笔前以主角第一人称写 300-500 字独白（不进入正文，不留档）。问自己：此刻他/她最不想想的是什么？让他/她去想到那个。

## exemplar_notes
> 第 2 章起必填（narrative_gate 会检查本节）：从本书已写章节中选一段最能代表目标声音的正文贴在此处，注明选自哪章、为什么它是标杆。起草前用它校准方向——校准感觉，不抄句子。

________________
"""


def _planning_story_engine_md() -> str:
    return """# 故事发动机

## 核心秘密
- 主角或世界隐藏什么？__________

## 欲望
- 主角想要什么？__________

## 替代行动
- 主角本可以做但未做的选择：__________

## 不可逆选择
- 一旦作出便改变后续的选择：__________

## 即时代价
- 选择立刻失去 / 暴露 / 伤害什么？__________

## 主题压力
- 贯穿全篇的追问或张力：__________
"""


def _planning_research_boundaries_md() -> str:
    return """# 研究边界

> 本书若确无外部事实依赖（如纯架空），在任意一节写明“无需”并给一句理由；
> 空模板会被 narrative_gate 判为未填写。

## 已验证事实
| 来源 | 日期 | 用途 | 事实红线 |
|------|------|------|----------|
|      |      |      |          |

## 虚构种子
- 明确标注为虚构的内容：__________

## B/C 级或不确定声明
- 不能作为唯一关键情节支点：__________
"""


def _agent_context_collector_md() -> str:
    return """# Context Collector

## 角色
只收集，不写正文。

## 任务
当用户要求“准备写第 X 章/场景”时：
1. 读 `CLAUDE.md` 宪法。
2. 读 `memory/voice-bible.md`（节奏蓝图与感官调色板）。
3. 读 `planning/story-engine.md` 和 `planning/research-boundaries.md`。
4. 读 `memory/past.md` 和 `memory/worldbuilding.md`。
5. 读上一条 `chapters/eXX/ch-XX/正文.md` 的最后 20%。
6. 读 `memory/future/00-index.md` 中的相关条目。
7. 输出一份 **最小上下文摘要** 到 `memory/context-cache/`。

## 输出格式
- 场景目标（1 句）
- 必须出现的物件/动作（最多 3 个）
- 不能违反的设定红线（最多 3 条）
- 上一条未回收的张力（最多 2 条）
- 本章节奏与感官要点（从 voice-bible 摘 1-2 条）
- 禁止在正文中出现的内容（如机制解释、结论升华）

## 边界
- 不生成正文。
- 不修改 `chapters/`。
- 不调用外部搜索。
"""


def _agent_consistency_guard_md() -> str:
    return """# Consistency Guard

## 角色
写后检查员，不写正文。

## 任务
在完成一段正文后，读：
1. 刚写的 `chapters/eXX/ch-XX/正文.md`
2. `memory/past.md`
3. `memory/worldbuilding.md`
4. `memory/entities/` 中相关实体卡（如存在）
5. `memory/future/00-index.md`：未回收承诺与计划兑现窗口

## 检查清单
- [ ] 实体名称与已记录一致
- [ ] 角色认知不超过其已知信息
- [ ] 时间线无矛盾
- [ ] 已埋承诺有回收或明确未回收
- [ ] 本章内容与 `memory/future/00-index.md` 中的承诺及兑现窗口对齐；偏离时明确标记“偏离：X”并说明处理方式
- [ ] 无现代语汇/网络用语出现在非现代背景
- [ ] 无突兀背景卸货句

## 输出
报告写入 `reviews/chXX-consistency-guard.md`（格式见 `reviews/review-template.md`）：
- 问题（最多 3 条）
- 位置（场景/行）
- 建议修订方向
- 承诺状态：兑现 / 保持未回收 / 延后 / **偏离：X**
- verdict: pass / needs_revision

## 边界
- 不生成新正文。
- 不修改 `chapters/` 与 `memory/`。
"""


def _dot_gitignore() -> str:
    return """# Per-book ignore rules for books/<slug>/
.snapshots/
memory/context-cache/
__pycache__/
*.pyc
"""


def _agent_chapter_editor_md() -> str:
    return """# Chapter Editor

## 角色
宏观独立编辑（轻量 Editorial Memo）。最后一个审稿环节，只审读，不重写正文。

## 输入
1. 当前 `chapters/eXX/ch-XX/正文.md`
2. `planning/scene-package-chXX.md` 与 `planning/action-draft-chXX.md`
3. 本章 `reviews/` 下已有的全部审稿记录

## 五维审稿（每维一条，每条必须附可定位的原文证据）
1. **叙事必要性**：这一章删掉，读者会失去什么？（答“推动剧情”判无效）
2. **人物能动性**：关键转折由人物的主动选择驱动，还是被环境或旁白推着走？
3. **细节选择**：留下的细节是否都服务于此刻的目标、误判或行动？有无解释性赘余？
4. **因果链**：章内每个关键 beat 如何造成下一 beat？有无靠巧合或情绪硬转？
5. **prose 观察**：一处具体行文判断（节奏、归属、重复、感官落地），引用原文。

## 输出（写入 `reviews/chXX-chapter-editor.md`）
- 五维逐条：位置、原文证据、读者效果、修订意图。
- MUST 总数 ≤ 6；存在未关闭 MUST 时不得给出通过 verdict。
- 纯抽象赞扬（“写得好”“画面感强”而无原文证据）判为无效审稿，必须重写。
- verdict: `ready_for_editor_decision` / `needs_revision`

## 边界
- 不生成新正文。
- 不判断文学价值或市场潜力。
- `ready_for_editor_decision` 不等于用户批准，只表示流程材料齐备。
"""


def _agent_blind_reader_md() -> str:
    return """# Blind Reader

## 角色
盲读者。只读当前章的 `正文.md`——严禁读取 `planning/`、`memory/`、voice-bible、其他章节或任何规划材料。用"规划知识"填补正文未渲染的画面，正是本环节要抓的作弊。

## 任务
仅凭正文重建以下六项：
1. **空间**：场景布局、出入口、人物相对位置。
2. **身体**：谁的身体处于什么状态（伤、累、冷、汗），身体与环境的接触点。
3. **行动约束**：此刻什么动作做不到，为什么（时间、钱、伤、规则）。
4. **情绪轨迹**：开场到章末情绪如何移动，由什么具体事件推动。
5. **对话动态**：每个话轮谁说、对谁说、想要什么。
6. **可记忆画面**：至少 3 个，每个必须附原文引用（≤2 句）。

## 输出（写入 `reviews/chXX-blind-reader.md`）
- 六项重建结果逐项给出；任何一项重建失败即 MUST，注明卡在哪个位置、正文缺什么信息。
- 每条结论必须有原文证据；禁止抽象赞扬。
- verdict: pass / needs_revision

## 边界
- 不重写正文。
- 不评价文学价值。
- 只报告一件事：仅凭正文，读者能不能看见。
"""


def _reviews_review_template_md() -> str:
    return """# Review — chXX / <role>

- chapter: chXX
- role: <causal-editor|line-editor|consistency-guard|blind-reader|chapter-editor>
- verdict: <pass|needs_revision|ready_for_editor_decision>
- date: YYYY-MM-DD

## Findings
| # | 级别 (MUST/MAY) | 位置 | 原文证据 | 读者效果 | 修订意图 | 状态 (open/closed) |
|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |

## 复审记录
- 复审人 / 日期 / 关闭的 finding 编号
"""


def _planning_scene_package_template_md() -> str:
    return """# Scene Package — 第XX章「标题」

## 0. 边界
- 承接上文：
- 本场景从何处开始、在何处停止：
- 允许新增的长线谜团（默认至多 1 条）：
- 不得在本场景解决的问题：

## 1. 场景压力
- **视角角色此刻想要什么：**
- **若什么都不做会失去什么：**
- **最直接的阻力：**
- **阻力背后的人的诉求：**
- **不可逆选择：**
- **选择立即造成的后果：**
- **章末遗留的具体压力：**

## 1b. 情感弧（可选）
- **开场情感状态：**
- **不可逆选择时刻的情感状态：**
- **章末残余情感状态：**
- **本场不应替角色解释的情绪：**

## 2. 在场者状态
> “不肯说/尚不知道”列必须填写真秘密；没有秘密的人物不必列表。

| 人物 | 表面目标 | 不肯说/尚不知道 | 对他人的判断 | 此场结束后的变化 |
|---|---|---|---|---|
|  |  |  |  |  |

## 3. Beat 因果链
| # | 触发 | 人物行动/决定 | 阻力或反应 | 局势变化 | 进入下一 beat 的原因 |
|---|---|---|---|---|---|
| 1 |  |  |  |  |  |

## 3b. 锚定物象（3-5 个）
> 本章依赖的实物：必须可操作、可磨损、有价格或来历；可记忆画面应骑在这些物件上，而非骑在形容词上。

| 物象 | 它承载的压力/关系 | 首次出现 beat |
|---|---|---|
|  |  |  |

## 4. 信息账本
| 信息 | 来源/证据 | 谁得到它 | 当场造成的决定 | 后续兑现 | 状态 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 5. 信息预算
- 主冲突（1 条）：
- 关系/权力变化（1 条）：
- 新世界规则（0-1 条）：
- 长线伏笔（0-1 条）：
- 新生造术语（0-2 条，每条注明如何落到身体/动作而非解释）：
- 延后信息：

## 6. 人物性呼吸段（可选）
- 放置在 beat # 之后：
- 人物功能（回避/拖延/误读/身体失控/关系余温/价值暴露）：
- 具体可见物或动作：
- 它不能新增的情节信息：
"""


def _planning_action_draft_template_md() -> str:
    return """# Action Draft — 第XX章「标题」

> 这是因果底稿，不追求文采。润色不得新增关键事件、设定、人物动机或长线谜团。

- 对应场景包：`planning/scene-package-chXX.md`
- 对应对白账本：`planning/dialogue-ledger-chXX.md` / 无关键对白
- 开场计划：
- 结尾计划如何被迫改变：

## 动作链
### Beat 1
- 触发：
- 行动：
- 阻力/反应：
- 决定：
- 立即后果：

### Beat 2
- 触发：
- 行动：
- 阻力/反应：
- 决定：
- 立即后果：

## 润色边界检查
- [ ] 每个关键事件均能回指到本动作稿。
- [ ] 删除感官描写后，仍能读出目标、阻力、选择与后果。
"""


def _planning_chapter_state_template_md() -> str:
    return f"""# Chapter State — 第XX章「标题」

- chapter: chXX
- status: planned
- revision: 0
- updated_at: YYYY-MM-DDTHH:MM:SSZ
- next_action:
- blocked_from: （仅 status=blocked 时填写）
- blocked_reason: （仅 status=blocked 时填写）
- required_human_decision: （仅 status=blocked 时填写）
- resume_state: （仅 status=blocked 时填写）
- resume_evidence: （仅 status=blocked 时填写）

> 合法状态链：{_STATE_CHAIN}
> blocked 为异常态，恢复后回到 blocked_from 或更早状态，并重跑后续门禁。

## 状态证据
证据列只存文件指针与 verdict（如 `reviews/ch01-causal-editor.md: pass`），不存散文。

| 状态 | 证据文件/报告 | verdict/结果 | 时间 | 备注 |
|---|---|---|---|---|
| planned |  |  |  |  |

## 当前阻断项
- 无 / 说明问题、来源与应回退状态。

## 本章最小上下文预算
- 当前场景材料：
- 近场连续材料：
- 相关人物/承诺：
- 世界/故事发动机摘要：
- 不加载的历史材料及原因：
"""


def _planning_dialogue_ledger_template_md() -> str:
    return """# Dialogue Ledger — 第XX章「标题」

- 本场景是否有关键对白：是 / 否
- 若否，原因：

| # | 发言者 → 对象 | 触发 | 表面目标 | 隐瞒 | 归属锚点 | 回应/误解 | 局势变化 |
|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |

- [ ] 每个关键话轮都可判断谁对谁说话。
- [ ] 每段关键对白至少改变计划、权力、认知或关系之一。
"""


def _agent_causal_editor_md() -> str:
    return """# Causal Editor

## 角色
叙事因果编辑。只审读，不重写正文。

## 输入
1. `planning/scene-package-chXX.md`
2. `planning/action-draft-chXX.md`
3. `planning/dialogue-ledger-chXX.md`（如有）
4. 当前 `正文.md`、上一章末尾与必要 `memory/` 事实

## MUST
- 场景包缺少目标、阻力、不可逆选择或立即后果。
- 关键 beat 无法说明如何导致下一 beat。
- 正文关键事件、动机、规则或谜团没有动作稿/信息账本来源。
- 重点信息没有来源、知情者或行动后果。
- 关键对白不改变计划、权力、认知或关系。
- 新生造术语超出场景包第 5 节术语预算，或术语以解释而非身体/动作落地。

## 输出
写入 `reviews/chXX-causal-editor.md`：最多 6 条 MUST/MAY，含位置、证据、断裂的因果/信息责任、应回退层级（场景包/动作稿/对白账本/正文）、修订意图；附 verdict: pass / needs_revision。

## 边界
不生成新正文；不把文采偏好当作因果问题。
"""


def _agent_line_editor_md() -> str:
    return """# Line Editor

## 角色
行文编辑。在 causal-editor 通过后执行；只审读，不重写正文。

## 审稿维度
1. 对白归属：称呼、动作、位置、物件或明确反应是否足够。
2. 对白行动性：是否只为解释设定、复述信息或整齐排比而存在。
3. 重复簇：相邻段是否近义重复且未改变局势。
4. 解释性旁白：叙述者是否替读者总结情绪、主题或认知。
5. 节奏：呼吸段是否具备人物功能；句长是否有方差——全短或全长的均匀段都是机械节奏。

## 输出
写入 `reviews/chXX-line-editor.md`：最多 6 条 MUST/MAY，含位置、原文证据、读者效果、修订意图；附 verdict: pass / needs_revision。MUST 仅用于归属不明、重复造成信息停滞或解释取代关键行动。

## 边界
不擅自统一文风，不以禁词命中替代上下文判断，不生成新正文。
"""


def _agent_orchestrator_md() -> str:
    return f"""# Orchestrator

## 角色
章节流程编排者。维护进度、门禁证据、暂停和回退；不写正文、不审稿、不自行改写记忆事实。

## 状态机
状态记录在 `planning/chapter-state/chXX.md`：
`{_STATE_CHAIN}`

- `blocked` 只用于需要人工选择、事实冲突、正文覆盖风险或外部发布。必须记录 `blocked_from`、原因、所需决定、恢复状态和恢复证据；恢复后回到原状态或更早状态，并重跑后续门禁。
- `ready` 只表示流程材料已齐备（含 blind_read 通过、chapter-editor verdict 为 ready_for_editor_decision），不等于用户批准。

## 门禁与回退
- 表面质检失败 → `drafted`，修正文。
- 叙事门禁或 causal-editor MUST → `scene_packaged` 或 `action_drafted`。
- line-editor MUST → `drafted`。
- consistency-guard MUST → 由问题定位；不得静默篡改既成事实。
- blind-reader 重建失败 → `drafted`（渲染不足）或 `scene_packaged`（场景本身缺物）。
- chapter-editor verdict=needs_revision → 按维度回退：因果类 → `scene_packaged`/`action_drafted`；行文类 → `drafted`。

## 规则
- 一次只编排一个章节或场景，不批量写后续章节。
- writer 仅加载当前场景、近场连续、相关人物/承诺和必要规则；长篇全量材料留给跨章审计。
- 每次只推进一个状态，并写入证据、结果和下一步。
- 审稿结论必须落盘到 `reviews/chXX-<role>.md`，证据表只存指针与 verdict。
"""


# Mapping of relative path -> (template factory, factory args)
# Paths are relative to books/<slug>/.
TEMPLATE_FILES: dict[str, tuple[Any, tuple[str, ...]]] = {
    ".gitignore": (_dot_gitignore, ()),
    "CLAUDE.md": (_claude_md, ("slug", "title", "genre", "timestamp")),
    "README.md": (_readme_md, ("slug", "title", "genre", "timestamp")),
    "memory/past.md": (_memory_past_md, ()),
    "memory/worldbuilding.md": (_memory_worldbuilding_md, ()),
    "memory/voice-bible.md": (_memory_voice_bible_md, ("title", "genre")),
    "memory/future/00-index.md": (_memory_future_index_md, ()),
    "planning/story-engine.md": (_planning_story_engine_md, ()),
    "planning/research-boundaries.md": (_planning_research_boundaries_md, ()),
    "planning/scene-package-template.md": (_planning_scene_package_template_md, ()),
    "planning/action-draft-template.md": (_planning_action_draft_template_md, ()),
    "planning/dialogue-ledger-template.md": (_planning_dialogue_ledger_template_md, ()),
    "planning/chapter-state-template.md": (_planning_chapter_state_template_md, ()),
    "reviews/review-template.md": (_reviews_review_template_md, ()),
    "tools/quality_check.py": (lambda: QUALITY_CHECK_PY, ()),
    "tools/narrative_gate.py": (lambda: NARRATIVE_GATE_PY, ()),
    ".claude/agents/context-collector.md": (_agent_context_collector_md, ()),
    ".claude/agents/consistency-guard.md": (_agent_consistency_guard_md, ()),
    ".claude/agents/chapter-editor.md": (_agent_chapter_editor_md, ()),
    ".claude/agents/blind-reader.md": (_agent_blind_reader_md, ()),
    ".claude/agents/causal-editor.md": (_agent_causal_editor_md, ()),
    ".claude/agents/line-editor.md": (_agent_line_editor_md, ()),
    ".claude/agents/orchestrator.md": (_agent_orchestrator_md, ()),
}

# Directories that should exist; files under them are created via TEMPLATE_FILES.
REQUIRED_DIRECTORIES = [
    "chapters",
    "memory/entities",
    "memory/future",
    "memory/context-cache",
    "planning/events",
    "planning/chapter-state",
    "reviews/archive",
    "patches",
    ".snapshots",
    "tools",
    ".claude/agents",
]

# Files that `sync-tools` may refresh in existing books (managed, never
# hand-edited). Everything else is only created when missing.
SYNCABLE_FILES: tuple[str, ...] = (
    "tools/quality_check.py",
    "tools/narrative_gate.py",
    ".claude/agents/context-collector.md",
    ".claude/agents/consistency-guard.md",
    ".claude/agents/chapter-editor.md",
    ".claude/agents/blind-reader.md",
    ".claude/agents/causal-editor.md",
    ".claude/agents/line-editor.md",
    ".claude/agents/orchestrator.md",
    "planning/scene-package-template.md",
    "planning/action-draft-template.md",
    "planning/dialogue-ledger-template.md",
    "planning/chapter-state-template.md",
    "reviews/review-template.md",
)


def render_templates(slug: str, title: str, genre: str) -> dict[str, str]:
    """Return a mapping of relative path -> rendered content."""
    timestamp = datetime.now(timezone.utc).isoformat()
    rendered: dict[str, str] = {}
    for rel_path, (factory, arg_names) in TEMPLATE_FILES.items():
        args: list[str] = []
        for name in arg_names:
            if name == "slug":
                args.append(slug)
            elif name == "title":
                args.append(title)
            elif name == "genre":
                args.append(genre)
            elif name == "timestamp":
                args.append(timestamp)
            else:
                args.append("")
        rendered[rel_path] = factory(*args)
    return rendered


def init_book_project(root: Path, slug: str, title: str, genre: str) -> dict[str, Any]:
    """Create the recommended `books/<slug>/` layout without overwriting user files.

    Returns metadata about created directories and files.
    """
    if not slug or not slug.replace("-", "").replace("_", "").isalnum():
        raise ProjectTemplateError(
            f"Invalid book slug: {slug!r}. Use alphanumeric, dash, or underscore."
        )
    if not title or not title.strip():
        raise ProjectTemplateError("Book title cannot be empty.")
    if not genre or not genre.strip():
        raise ProjectTemplateError("Book genre cannot be empty.")

    book_dir = Path(root) / "books" / slug
    created_dirs: list[str] = []
    created_files: list[str] = []
    skipped_files: list[str] = []

    for rel_dir in REQUIRED_DIRECTORIES:
        target = book_dir / rel_dir
        target.mkdir(parents=True, exist_ok=True)
        created_dirs.append(rel_dir)

    templates = render_templates(slug, title.strip(), genre.strip())
    for rel_path, content in templates.items():
        target = book_dir / rel_path
        if target.exists():
            skipped_files.append(rel_path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created_files.append(rel_path)

    return {
        "book_dir": str(book_dir),
        "created_directories": created_dirs,
        "created_files": created_files,
        "skipped_files": skipped_files,
    }
