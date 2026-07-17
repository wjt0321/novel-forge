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
    EVIDENCE_DIRECTORIES,
    HUMAN_NARRATIVE_POLICIES,
    MECHANISM_CLAUSES,
    REVIEW_ROLES,
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


def _human_narrative_policy_lines() -> str:
    return "\n".join(
        f"- `{policy_id}`: {description}"
        for policy_id, description in HUMAN_NARRATIVE_POLICIES.items()
    )


def _claude_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    mechanism = MECHANISM_CLAUSES[genre_preset(genre)]
    policy_lines = _human_narrative_policy_lines()
    return f"""# 小说宪法：《{title}》

## 基本信息
- slug: `{slug}`
- 标题: 《{title}》
- 类型: {genre}
- 创建时间: {timestamp}
- **工作流版本**: v3.4（质量链 + Markdown 权威记忆 + 有限认知与因果归属）

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
3. `memory-status` 必须为 `clean`；随后用 `build-memory-context` 生成并读取本章记忆包
4. `memory/worldbuilding.md` — 世界规则
5. `planning/scene-package-chXX.md` — 目标、阻力、beat 因果链与信息账本
6. `planning/action-draft-chXX.md` — 动作版因果底稿
7. `planning/dialogue-ledger-chXX.md` — 关键对白账本（如有）
8. 上一条 `chapters/eXX/ch-XX/正文.md` 的最后 20%
9. `planning/research-boundaries.md` — 事实红线

## 严格边界
- 禁止自动批量生成多章。
- 禁止在未读 `memory/`（含 voice-bible）和 `planning/story-engine.md` 的情况下写正文。
- 禁止在记忆索引非 `clean` 或未生成本章 `memory/context-cache/chXX-memory.md` 时写正文。
- `memory/canon/**/*.md` 是权威记忆；`.novel-forge/index.sqlite3` 是可删除缓存。Agent 不得直接编辑 SQLite。
- 正文产生的新事实、事件、认知变化与承诺必须先提交到 `memory/candidates/`；只有显式晋升后才可进入 Canon。
- {mechanism}
- 禁止 `——`、`……`、`不是X而是Y`、结论性旁白升华。
- 正式章节不少于 5000 个 CJK 汉字；更短的只能标为实验片段。字数是底线不是目标：靠复述与注水凑字数的章同样不合格（见信息预算与 line-editor 重复簇审查）。
- 起草前完成本章场景包和动作稿；存在关键对白时完成对白账本。认知账本必须区分观察事实、人物假设、替代解释与可推翻证据；因果归属账本必须写清谁提出条件、谁知情、谁承担后果。
- 专业能力只能通过可执行判断体现：写清证据、未证前提、执行条件、成本与风险；不得用术语、履历回忆或微表情解码替人物证明聪明。
- 正文润色不得新增动作稿外的关键事件、设定、人物动机或长线谜团。
- 起草前按 voice-bible 的写前仪式写一段角色独白（不进入正文），并用 exemplar_notes 的范文段落校准本章目标声音。
- 每章写完后必须运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md` 与 `python tools/narrative_gate.py chapters/eXX/ch-XX/正文.md planning/scene-package-chXX.md`。
- 审稿必须落盘：每个审稿角色的结论写入 `reviews/chXX-<role>.md`（格式见 `reviews/review-template.md`），chapter-state 证据表只存文件指针与 verdict。
- 修订优先局部 patch；因果或信息失败时回到场景包/动作稿，结构失败才重写场景。
- patch 命名：`patches/ch-{{章节号}}-{{功能}}.md`；只记录局部修订意图、位置、替换范围和验证结果，不替换整章正文。应用后重跑质检、相关编辑和一致性检查。
- `tools/*.py` 是仓库规则的薄壳，不要手工编辑；由 `sync-tools` 统一刷新。
- 本模板默认包含 v3 编排资产；所有状态、记忆、审稿和上下文材料只留在本书目录内，严禁复制其他书的正文、`memory/`、`reviews/`、`context-cache/` 或已填写 `chXX` 实例。

## 人类叙事证据边界
`evaluation/constitution.md` 定义本书的评测宪法；`evidence/` 保存不可变的生成、分支、盲评、偏好、跨章审计与规则决策记录。它们证明过程，不认证文学价值。

{policy_lines}

- 开始章节前用 `set-draft-mode` 明确 `formal` 或 `exploration`；模式写入 chapter-state，命令行参数不能临时覆盖。
- 正式稿必须先记录并绑定 generation evidence；正文或规划变化后，旧审稿自动失效。
- 用 `evidence-status` 检查当前章的生成证据与五章检查点；用 `record-evidence` 提交 UTF-8 Markdown 证据文件。
- 分支实验的候选正文放在 `evaluation/experiments/<experiment-id>/candidates/`，不得写进正式正文目录；选择后仅胜者可进入下一步。
- 第 5、10、15……章进入 `ready` 前必须有当前 checkpoint arc audit，且 `open_must=0`；卷终另做 `scope=volume` 审计。

## 角色团队（按子代理职责分派，定义见 `.claude/agents/`）
- `context-collector`: 写前收集最小上下文，输出到 `memory/context-cache/`。
- `orchestrator`: 维护章节状态、门禁证据与回退决策，不写正文。
- `causal-editor`: 审场景因果、信息账本、术语预算与人物行动后果。
- `line-editor`: 审对白归属、对白行动性、重复簇、解释性旁白。
- `texture-editor`: 审句子工艺——分句堆叠、排比、比喻密度、解释腔、句长方差、套话。
- `consistency-guard`: 写后检查实体、时间线、未回收承诺，输出报告。
- `blind-reader`: 只读正文，重建空间/身体/行动/情绪轨迹/对话动态与可记忆画面。
- `chapter-editor`: 宏观五维审稿（轻量 Editorial Memo），输出 verdict。
"""


def _readme_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    return f"""# 《{title}》

- 类型: {genre}
- 创建时间: {timestamp}
- 默认工作流: v3.4；完整编排说明见 `.agents/skills/novel-forge/SKILL.md`。

## 如何阅读
打开最新正文：

```
books/{slug}/chapters/eXX/ch-XX/正文.md
```

## 目录
- `chapters/` — 正文唯一入口
- `memory/` — 人物、历史、世界设定、voice-bible
- `memory/canon/` — Markdown 权威记忆；`memory/candidates/` — 待审增量
- `.novel-forge/` — 可重建 SQLite 索引与 manifest（不入版本库）
- `planning/` — 故事发动机、研究边界、场景包、章节状态
- `evaluation/` — 评测宪法、实验与证据输入模板
- `evidence/` — 不可变创作证据：生成、分支、盲评、偏好、跨章审计、规则决定
- `reviews/` — 审稿记录（每个角色一份，含 verdict）
- `patches/` — 局部修订 patch
- `.snapshots/` — 临时快照

## 默认工作流
1. 用 `set-draft-mode` 选择 `formal` 或 `exploration`；探索稿永远不能进入 `ready`。
2. `context-collector` 检查 `memory-status`，生成本章 `build-memory-context`，再收集最小上下文并建立章节状态。
3. 正式稿填写含决策摩擦、可证伪假设、因果归属、专业判断审计与场景余波的 `scene-package`、`action-draft`；有关键对白时填写 `dialogue-ledger`。
4. 按 `CLAUDE.md` 宪法与 `memory/voice-bible.md` 起草 `正文.md`，记录 generation evidence 并绑定当前章。
5. 运行 `quality_check.py` 和 `narrative_gate.py`；需要比较方案时做单胜者分支实验与盲评，禁止把候选静默拼接。
6. 依次交六个审稿角色审阅，记录真实 reviewer/provider/model/context；由 `orchestrator` 推进相邻状态。
7. `consistency-guard` 将新事实整理为 candidate；经明确晋升后重建索引。每五章做 checkpoint audit，卷终另做 volume audit。

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


def _memory_guide_md() -> str:
    return """# 长篇记忆内核

## 权威源与缓存
- `memory/canon/**/*.md` 是已批准事实的长期权威源。
- `memory/candidates/chXX/*.md` 是待审增量，不会自动进入 Canon。
- `.novel-forge/index.sqlite3` 与 `memory/context-cache/` 都是可删除缓存。
- 禁止直接编辑 SQLite；修改 Markdown 后运行 `rebuild-memory-index`。

## 五类记录
- `entity`：人物、地点、组织、物件及别名。
- `fact`：带 `valid_from` / `valid_to` 的状态事实。
- `event`：已经发生的事件、参与者与地点。
- `knowledge`：某角色知道、怀疑或误信什么。
- `promise`：伏笔、悬念、债务与回收窗口。

## 工作协议
1. 从 `memory/memory-record-template.md` 复制候选记录到本书外的临时文件并填写。
2. 用 `record-memory-candidate` 校验并存入候选区。
3. 人工或编排 Agent 审核后，用 `promote-memory-candidate` 晋升。
4. 状态变化必须填写 `supersedes`；例如死亡事实取代存活事实，旧事实有效期会闭合。
5. 起草前运行 `memory-status`；仅在 `clean` 时生成 `build-memory-context`。

所有记录必须引用本书内真实存在的 `source_path`，并提供可定位的短证据。正文或 Canon 改动都会使索引变为 stale，必须重建后才能生成上下文包。
"""


def _memory_record_template_md() -> str:
    return """# 记忆候选：替换本标题

> 复制本文件到书外临时位置后填写；不要把模板本身当作 Canon。
> kind 可为 entity / fact / event / knowledge / promise，并按 MEMORY.md 补齐该类字段。

<!-- novel-forge-memory:v1 -->
```json
{
  "chapter": 1,
  "evidence": "可定位的短证据",
  "id": "fact.example.state.ch01",
  "kind": "fact",
  "object": "当前状态",
  "predicate": "state",
  "schema_version": 1,
  "source_path": "chapters/e01/ch-01/正文.md",
  "status": "candidate",
  "subject": "entity.example",
  "summary": "供上下文包使用的一句话摘要。",
  "supersedes": null,
  "tier": "hard",
  "valid_from": 1,
  "valid_to": null
}
```

## 人工说明
- 为什么这条记录值得进入长篇记忆：__________
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

## 语域地图（叙述者在场度，每章起草前对照）

人味来自"换挡"，AI 味来自全程一档。叙述者在场度分四档：
- **0 = 隐形摄像机**：只有人事在现场，读者忘记叙述者（场景行动、对峙对白、情感峰值）。
- **1 = 贴身跟随**：轻微引导不插话（过渡、赶路、呼吸段）。
- **2 = 讲者现身**：有人领着讲（开场切入、背景交代、插叙导航）。
- **3 = 讲者抒情**：叙述者直接点评感慨（默认禁用；除非全书定调就是说书人体）。

| 文本功能 | 建议在场度 | 本书示例（第 2 章起填） |
|---|---|---|
| 开场切入 | 2：句 1 讲者定位时空，句 2 跟上目标与压力 | ________ |
| 场景行动/程序 | 0：术语零解释，判断全部落身体 | ________ |
| 对峙/对白 | 0：叙述退到归属与反应拍 | ________ |
| 回忆/插叙 | 1-2：物件能完成过渡就用 1，跨得远才用讲者导航 | ________ |
| 过渡/赶路 | 1 | ________ |
| 情感峰值 | 0：情绪全部落到身体，不命名 | ________ |
| 收束/章末 | 1-2：允许经营最后一个画面，不许点评主题 | ________ |

> 本表是指南针不是检查表。每个 beat 整齐划一地换挡，是另一种机械味。
> **悬念合法化**：开场可以给悬念，但信息差必须由人物认知范围内的手段产生（物件、迟疑、推断），不得靠讲者越权（如"他还不知道……"式 dramatic irony、全镇视角转述）制造——悬念强度与视角纪律是两个独立的轴，不能为前者牺牲后者。

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
- **机锋合法**：长在人物处境上的反讽、自嘲、俏皮话（"想要当败家子，也无从下手"）是人味高光，尽管用；但以不冲淡当下张力为界。

## 写前仪式：角色独白
动笔前以主角第一人称写 300-500 字独白（不进入正文，不留档）。问自己：此刻他/她最不想想的是什么？让他/她去想到那个。

## exemplar_notes
> 第 2 章起必填（narrative_gate 会检查本节）：从本书已写章节中选一段最能代表目标声音的正文贴在此处，注明选自哪章、为什么它是标杆。起草前用它校准方向——校准感觉，不抄句子。
> 贴完范文段落后，把它的**声音指纹**一并贴上（在仓库根运行 `PYTHONPATH=. python -m app.novel_forge.voice_signature <章节文件>`）。指纹把"像不像本书"变成可测量的距离：起草时对齐它，texture-editor 用它做漂移检查。

________________
"""


def _planning_story_engine_md() -> str:
    return """# 故事发动机

## 核心秘密
- 主角或世界隐藏什么？__________

## 欲望
- 主角想要什么？__________

## 对抗中的独立意志
- 谁或什么不为主角服务，并拥有自己的目标？__________
- 即使主角判断完全正确，对方仍会怎样行动？__________

## 主角的错误模型
- 主角目前坚信、但可能错误的判断：__________
- 什么证据能推翻它？__________

## 替代行动与不兼容欲望
- 主角本可以做但未做的选择：__________
- 主角不能同时保住的两样东西：__________

## 不可逆选择
- 一旦作出便改变后续的选择：__________

## 即时代价
- 选择立刻失去 / 暴露 / 伤害什么？__________

## 未解承诺
- 读者继续阅读时等待回答的具体问题：__________

## 主题压力
- 贯穿全篇的追问或张力：__________
"""


def _evaluation_constitution_md() -> str:
    return """# 人类化小说评测宪法

> 本文件规定工作流能判什么、只能记录什么，以及什么必须留给作者决定。
> 通过任何自动门禁都不等于文学价值、市场价值、可读性或作者批准。

## 五层责任

1. **事实秩序**：人物生死、时间、地点、持有物、知识边界不得自相矛盾；由 Canon 与一致性门负责。
2. **因果秩序**：欲望、阻力、选择、代价与场景余波必须可以追溯；由规划和因果审稿负责。
3. **人物认知的有限性**：允许误解、遗漏、偏见、自欺与错误归因，但它们必须属于人物，而不是系统遗忘事实。
4. **表达的不均匀**：允许跳过、停顿、粗粝、沉默与语域换挡，只要它们承担人物或叙事功能。
5. **作者偏好**：喜欢什么、拒绝什么、愿意承担什么审美风险，只能由明确的作者决定或授权评审记录。

## 不得伪造的人味

- 不得故意加入错别字、病句、事实错误或随机瑕疵来冒充人类写作。
- 不得把禁词替换、随机句长、口癖注入或表面粗糙当成人味。
- 不得静默拼接全部候选；分支实验必须选择一个方案并保留被放弃的代价。
- 不得仿写在世作者；只能使用可说明、可迁移的文学技法。

## 证据边界

- 模型评分不是作者批准，也不是文学价值认证。
- 事实检查可以阻断；审美判断只能给证据、偏好、分歧与风险。
- 同一模型换一个角色名不自动构成独立评审；必须记录 reviewer/provider/model/context。
- 世界不能只为证明主角聪明而存在；重要判断必须保留替代解释、置信程度和可推翻条件。
- 专业术语不能替代专业正确性；关键判断必须能说明执行条件、成本、风险和失败方式。
- 任何规则都必须先作为实验假设，经跨章节或跨作品证据支持后才能升级；无效规则应降级或退休。
"""


def _evaluation_case_template_md() -> str:
    return """# 功能型评测案例

- case_id:
- 文本功能：开场 / 行动压力 / 对白权力 / 关系闲笔 / 信息隐瞒 / 失败余波 / 章末换题
- 来源与授权边界：
- 不保存原文时的分析指针：

## 可观察证据
- 人物当下目标：
- 选择或拒绝：
- 细节怎样改变行动：
- 潜台词或认知限制：
- 读者记住的画面：

## 反例边界
- 表面相似但功能不同的情况：
- 不应机械提炼成的禁令：
"""


def _evaluation_experiment_template_md() -> str:
    return """# 单变量实验

- experiment_id:
- 假设：
- 唯一变量：
- 固定条件：人物 / 场景包 / 模型 / 上下文 / 字数范围
- 候选标签：A / B / C
- 盲评人或模型来源：

## 盲评问题
- 人物最想得到什么？
- 人物隐瞒或拒绝承认什么？
- 关系发生了什么变化？
- 记住哪三个具体画面？
- 下一章真正想知道什么？

## 结果
- 单一胜者：
- 放弃的优点与代价：
- 是否生成偏好记录：
- 是否支持规则升级：否 / 继续验证 / 是（附跨项目证据）
"""


def _evaluation_rule_registry_md() -> str:
    return """# 规则注册表

> 规则生命周期：experimental → advisory → blocking；也可降级为 retired。
> 单篇 demo 的修复经验不能直接成为通用硬门。

| rule_id | 假设 | 生命周期 | 支持作品/类型/模型 | 反例 | 最近决定证据 |
|---|---|---|---|---|---|
|  |  | experimental |  |  |  |
"""


def _evaluation_generation_template_md() -> str:
    return """# Generation Evidence

> provider、model、外层 Agent/harness 与上下文清单必须按实际运行填写。
> 来源不明或元数据与真实运行不一致的样本不得进入跨模型比较。

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "generation.ch01.unique-id",
  "kind": "generation",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "agent",
  "source_paths": [
    "chapters/e01/ch-01/正文.md",
    "chapters/e01/ch-02/正文.md",
    "chapters/e01/ch-03/正文.md",
    "chapters/e01/ch-04/正文.md",
    "chapters/e01/ch-05/正文.md"
  ],
  "summary": "本章当前正文的生成来源。",
  "chapter": 1,
  "draft_mode": "formal",
  "writer_type": "agent",
  "provider": "provider-name",
  "model": "model-name",
  "content_path": "chapters/e01/ch-01/正文.md",
  "content_sha256": "替换为正文文件的64位sha256"
}
```
"""


def _evaluation_branch_template_md() -> str:
    return """# Branch Decision Evidence

> 候选正文放在 `evaluation/experiments/<experiment-id>/candidates/<label>.md`。
> winner 只能有一个；综合稿必须先成为新的匿名候选。

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "branch.experiment.unique-id",
  "kind": "branch",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "agent",
  "source_paths": ["evaluation/experiments/opening/candidates/A.md"],
  "summary": "关键节点受控分支的单一选择。",
  "chapter": 1,
  "experiment_id": "opening",
  "candidates": ["A", "B"],
  "winner": "B",
  "selection_mode": "single_winner",
  "evaluation_ids": ["evaluation.experiment.unique-id"],
  "discarded_tradeoffs": {
    "A": "记录放弃 A 时同时放弃的有效品质。"
  }
}
```
"""


def _evaluation_blind_template_md() -> str:
    return """# Blind Evaluation Evidence

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "evaluation.experiment.unique-id",
  "kind": "evaluation",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "human_reviewer",
  "source_paths": ["evaluation/experiments/opening/candidates/A.md"],
  "summary": "匿名候选的具体读者重建结果。",
  "chapter": 1,
  "experiment_id": "opening",
  "candidate_labels": ["A", "B"],
  "blinded": true,
  "preferred_label": "B",
  "reviewer_type": "human",
  "reviewer_id": "reader-session-id",
  "provider": "not_applicable",
  "model": "not_applicable",
  "context_scope": "candidate_prose_only",
  "questions": {
    "desire": "人物最想得到什么？",
    "concealment": "人物隐瞒或拒绝承认什么？",
    "relationship_change": "关系发生了什么变化？",
    "memorable_images": ["画面一", "画面二", "画面三"],
    "next_question": "下一章真正想知道什么？"
  }
}
```
"""


def _evaluation_preference_template_md() -> str:
    return """# Author Preference Evidence

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "preference.unique-id",
  "kind": "preference",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "author",
  "source_paths": ["evidence/evaluations/evaluation.experiment.unique-id.md"],
  "summary": "作者对本次候选的选择理由。",
  "chapter": 1,
  "branch_id": "branch.experiment.unique-id",
  "evaluation_ids": ["evaluation.experiment.unique-id"],
  "selected_id": "B",
  "rejected_ids": ["A"],
  "accepted_qualities": ["保留的具体品质"],
  "rejected_qualities": ["拒绝的具体品质"],
  "decision_authority": "author"
}
```
"""


def _evaluation_arc_audit_template_md() -> str:
    return """# Arc Audit Evidence

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "arc.checkpoint.01-05",
  "kind": "arc_audit",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "human_delegate",
  "source_paths": ["chapters/e01/ch-01/正文.md"],
  "summary": "五章检查点或卷终审计。",
  "scope": "checkpoint",
  "start_chapter": 1,
  "end_chapter": 5,
  "volume_id": null,
  "verdict": "continue",
  "open_must": 0,
  "source_sha256": {
    "chapters/e01/ch-01/正文.md": "替换为来源文件的64位sha256",
    "chapters/e01/ch-02/正文.md": "替换为来源文件的64位sha256",
    "chapters/e01/ch-03/正文.md": "替换为来源文件的64位sha256",
    "chapters/e01/ch-04/正文.md": "替换为来源文件的64位sha256",
    "chapters/e01/ch-05/正文.md": "替换为来源文件的64位sha256"
  }
}
```

JSON 块外逐项记录：承诺、人物弧、关系债务、母题复现、节奏、矛盾与遗弃线索。
"""


def _evaluation_rule_decision_template_md() -> str:
    return """# Rule Decision Evidence

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "rule.unique-id",
  "kind": "rule_decision",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "human_delegate",
  "source_paths": ["evaluation/experiment-template.md"],
  "summary": "规则升级、降级或退休的证据决定。",
  "rule_id": "rule-id",
  "hypothesis": "可证伪的规则假设。",
  "lifecycle": "experimental",
  "tested_works": ["work-a"],
  "tested_genres": ["genre-a"],
  "tested_models": ["model-a"],
  "intervention_type": "planning_prompt",
  "retirement_reason": null
}
```
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
4. 运行 `memory-status`；非 `clean` 时先请求 `rebuild-memory-index`，不得带病起草。
5. 运行 `build-memory-context <slug> <X>`，读取生成的 `memory/context-cache/chXX-memory.md`。
6. 读 `memory/worldbuilding.md`、上一章最后 20% 与当前场景材料。
7. 将生成包压缩为本章 **最小上下文摘要**，不得自行补全缺失事实。
8. 从场景包提取认知账本与因果归属账本；摘要中必须区分“Canon 事实 / 人物已知 / 人物猜测 / 未决替代解释”。

## 输出格式
- 场景目标（1 句）
- 必须出现的物件/动作（最多 3 个）
- 不能违反的设定红线（最多 3 条）
- 上一条未回收的张力（最多 2 条）
- 本章关键假设、替代解释与可推翻证据（最多 2 条）
- 关键条件的提出者、知情者与后果承担者（最多 2 条）
- 本章节奏与感官要点（从 voice-bible 摘 1-2 条）
- 禁止在正文中出现的内容（如机制解释、结论升华）

## 边界
- 不生成正文。
- 不修改 `chapters/`。
- 不直接修改 `memory/canon/` 或 `.novel-forge/index.sqlite3`。
- 发现缺失或新事实时只提交 memory candidate，未经晋升不得当作 Canon。
- `aesthetic-does-not-override-facts`: 审美目标不得让摘要越过 Canon、证据或人物已知边界。
- 不调用外部搜索。
"""


def _agent_consistency_guard_md() -> str:
    return """# Consistency Guard

## 角色
写后检查员，不写正文。

## 任务
在完成一段正文后，读：
1. 刚写的 `chapters/eXX/ch-XX/正文.md`
2. 本章生成的 `memory/context-cache/chXX-memory.md`
3. `memory/worldbuilding.md`
4. 上一章结尾与当前章相关实体的 Canon 记录
5. Canon 中未回收承诺及计划兑现窗口
6. `planning/scene-package-chXX.md` 的认知账本与因果归属账本

## 检查清单
- [ ] 实体名称与已记录一致
- [ ] 角色认知不超过其已知信息
- [ ] 正文没有把人物假设、怀疑或专业判断静默升级成 Canon 事实
- [ ] 重要条件的提出者、执行者、知情者与后果承担者和因果归属账本一致
- [ ] 已标记“未决/误判”的假设没有被后文旁白提前认证为正确
- [ ] 时间线无矛盾
- [ ] 已埋承诺有回收或明确未回收
- [ ] 本章内容与 `memory/future/00-index.md` 中的承诺及兑现窗口对齐；偏离时明确标记“偏离：X”并说明处理方式
- [ ] 无现代语汇/网络用语出现在非现代背景
- [ ] 无突兀背景卸货句
- [ ] 正文产生的新事实、事件、知识变化与承诺已整理为 candidate；未批准项未写入 Canon

## 输出
报告写入 `reviews/chXX-consistency-guard.md`（格式见 `reviews/review-template.md`）：
- 问题（最多 3 条）
- 位置（场景/行）
- 建议修订方向
- 承诺状态：兑现 / 保持未回收 / 延后 / **偏离：X**
- verdict: pass / needs_revision

## 复审协议
复审时必须重读修订后的**完整正文**与对应 patch 记录，确认修改没有产生新的不一致，而不是仅核对原 finding 是否被删除。

## 边界
- 不生成新正文。
- 不修改 `chapters/`、`memory/canon/` 与 SQLite；只可提交候选记录供晋升。
- `aesthetic-does-not-override-facts`: 文学效果不能成为静默改写既成事实的理由。
- `world-not-protagonist-proof`: 世界不能通过巧合、微表情或旁白持续为主角的判断背书。
"""


def _dot_gitignore() -> str:
    return """# Per-book ignore rules for books/<slug>/
.snapshots/
memory/context-cache/
.novel-forge/
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
2. **人物能动性**：关键转折由人物的主动选择驱动，还是被环境或旁白推着走？人物是否可能判断错误并为选择承担代价？
3. **细节选择**：留下的细节是否都服务于此刻的目标、误判或行动？有无解释性赘余？
4. **因果链**：章内每个关键 beat 如何造成下一 beat？条件由谁提出、谁知道、谁承担后果？有无靠巧合或情绪硬转？
5. **prose 观察**：一处具体行文判断（节奏、归属、重复、感官落地），引用原文。

## 输出（写入 `reviews/chXX-chapter-editor.md`）
- 五维逐条：位置、原文证据、读者效果、修订意图。
- MUST 总数 ≤ 6；存在未关闭 MUST 时不得给出通过 verdict。
- 纯抽象赞扬（“写得好”“画面感强”而无原文证据）判为无效审稿，必须重写。
- verdict: `ready_for_editor_decision` / `needs_revision`

## 复审协议
复审时必须重读修订后的**完整正文**与对应 patch 记录，确认修改没有产生新的宏观问题，而不是仅核对原 finding 是否被删除。

## 边界
- 不生成新正文。
- 不判断文学价值或市场潜力。
- `model-score-not-approval`: verdict 只是流程证据，不是作者批准或发布许可。
- `role-name-not-independence`: 必须如实记录 reviewer/provider/model/context；换角色名不算独立审稿。
- `world-not-protagonist-proof`: 若所有关键观察都立即证明主角正确，必须检查世界是否已退化为能力展示装置。
- `expertise-must-be-executable`: 专业结论缺执行条件、成本或风险时，不得因“听起来专业”而放行。
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

## 复审协议
复审时必须重读修订后的**完整正文**（依然只读正文，不读规划材料）与对应 patch 记录，确认修改没有产生新的画面缺口，而不是仅核对原 finding 是否被删除。

## 边界
- 不重写正文。
- 不评价文学价值。
- `model-score-not-approval`: pass 只表示本轮盲读可重建，不是作者批准。
- `role-name-not-independence`: 记录真实 reviewer/provider/model；只换提示词或角色名不算独立。
- 只报告一件事：仅凭正文，读者能不能看见。
"""


def _reviews_review_template_md() -> str:
    roles = "|".join(REVIEW_ROLES)
    return f"""# Review — chXX / <role>

- chapter: chXX
- role: <{roles}>
- verdict: <pass|needs_revision|ready_for_editor_decision>
- date: YYYY-MM-DD
- source_fingerprint: <review-binding source_fingerprint>
- chapter_sha256: <review-binding chapter_sha256>
- planning_sha256: <review-binding planning_sha256>
- draft_mode: <formal|exploration>
- generation_id: <generation evidence id or unrecorded>
- reviewer_type: <human|agent|model>
- reviewer_id: <stable reviewer/session id>
- provider: <provider or not_applicable>
- model: <model or not_applicable>
- context_scope: <prose_only|full_review_context>
- independence_note: <同源评审时必填；角色名不同不等于独立>

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
- 章型（交锋 / 立章 / 过场 / 收束）：
> 章型只调整信息密度、对白配比与叙述者在场度，不豁免人物摩擦。立章可以没有终局式不可逆选择，但决策问题至少要有两项真实成立；过场以呼吸段为主体；收束允许经营画面。
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

## 1c. 决策问题
> 五项中至少两项必须真实成立；“立章”不能把本节全部写成“无”。

- **不能同时得到的两样东西：**
- **角色拒绝承认什么：**
- **角色误读了谁或什么：**
- **哪句话不能说出口：**
- **最终接受的具体代价：**

## 1d. 认知与可证伪假设
> 只登记会推动关键行动的推断。观察事实不等于解释；替代解释不能是敷衍同义句。
> 若本章确实没有依赖推断推动的关键行动，写“无需：<具体原因>”。

| 观察事实 | 人物当前假设 | 替代解释 | 置信度（低/中/高） | 可推翻证据 | 本章状态（未决/证实/推翻/误判） |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 2. 在场者状态
> “不肯说/尚不知道”列必须填写真秘密；没有秘密的人物不必列表。

| 人物 | 表面目标 | 不肯说/尚不知道 | 对他人的判断 | 此场结束后的变化 |
|---|---|---|---|---|
|  |  |  |  |  |

## 3. Beat 因果链
> “语域”列填叙述者在场度（0 隐形摄像机 / 1 贴身跟随 / 2 讲者现身），对照 voice-bible 语域地图；不写默认 0。

| # | 触发 | 人物行动/决定 | 阻力或反应 | 局势变化 | 进入下一 beat 的原因 | 语域 |
|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |

## 3b. 锚定物象（3-5 个）
> 本章依赖的实物：必须可操作、可磨损、有价格或来历；可记忆画面应骑在这些物件上，而非骑在形容词上。

| 物象 | 它承载的压力/关系 | 首次出现 beat |
|---|---|---|
|  |  |  |

## 3c. 因果归属账本
> 至少一条。记录会改变行动条件、关系或后续责任的关键动作/条件，防止“谁提出三日期限”一类归属漂移。

| 动作/条件 | 提出或执行者 | 对象 | 当场知情者 | 来源 beat | 后果承担者 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 4. 信息账本
| 信息 | 来源/证据 | 谁得到它 | 当场造成的决定 | 后续兑现 | 状态 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 5. 信息预算
- 主冲突（1 条）：
- 关系/权力变化（1 条）：
- 关键对白：是 / 否
- 新世界规则（0-1 条）：
- 长线伏笔（0-1 条）：
- 新生造术语（0-2 条，每条注明如何落到身体/动作而非解释）：
- 延后信息：

## 5b. 专业判断审计
> 医疗、金融、法律、刑侦、工程、历史制度、手艺等专业判断只要推动关键行动，就必须登记。
> 若本章没有依赖专业判断推动的关键行动，写“无需：<具体原因>”。

| 判断/主张 | 可观察证据 | 未证前提 | 可执行条件 | 成本/风险 | 失败或证伪方式 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 6. 人物性呼吸段（可选）
- 放置在 beat # 之后：
- 人物功能（回避/拖延/误读/身体失控/关系余温/价值暴露）：
- 具体可见物或动作：
- 它不能新增的情节信息：
- 它实际改变的身体/关系/价值：

## 7. 场景余波
- **身体：** 伤、累、冷、饥饿、睡眠或动作能力留下什么变化？
- **物件：** 什么被获得、失去、损坏、转交或留下痕迹？
- **关系：** 信任、权力、距离或债务发生什么变化？
- **认知/误信：** 谁知道、怀疑或仍然误信什么？
- **未偿债务/承诺：** 哪个后果必须在后续章节继续存在？
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
- draft_mode: formal
- generation_id: unrecorded
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


def _agent_texture_editor_md() -> str:
    return """# Texture Editor

## 角色
文字肌理编辑。只管句子与分句的工艺，不管结构、因果与设定。在 line-editor 通过后执行；只审读，不重写正文。

## 审稿维度（仅此六项，逐项给证据）
1. **分句堆叠**：逗号串起的均匀微短分句（如"弯腰，笑，说了好一阵"式的动作碎片连排）。**病不在"多"，在"匀"**：长短错落、有主有次的连排是中文活水（《剑来》分句复杂度 5.22）；2-4 字均匀碎片才是打点。
2. **排比铺陈**：叙述者为显文采的机械三连。先问"这串排比是谁的"——民俗、童谣、人物的仪式性复沓、对白里的排比，合法；叙述者逞才的，才算病。
3. **比喻**：每章 ≤3 个且必须承担功能；删装饰性比喻。
4. **解释腔**：叙述者替读者总结情绪/规矩/主题（含动作中段背规矩条文）。注意区分"百科式设定宣讲"与"有声音、贴处境的讲者陈述"——后者在立章与插叙中合法。
5. **句长方差**：句内与段内句长是否有呼吸；均匀短句与均匀长句都报警。方差方向不限（拾骨人 CV≈0.6 与《剑来》CV≈0.9 都是人声）。
6. **套话与悬浮词**：冷光闪烁、空气凝固、时光荏苒类；没有落到具体物象的抽象词。
7. **语域适配**：对照 `memory/voice-bible.md` 的语域地图（0 隐形摄像机 / 1 贴身 / 2 讲者现身 / 3 讲者抒情），判断每段的叙述者在场度是否匹配其功能——开场切入是否够快、行动是否隐形、插叙是否有讲者导航或物件过渡、收束是否收在画面而非点评。场景包 beat 表有语域声明时，逐拍对照；场景包声明章型（交锋/立章/过场/收束）时，按章型校准（立章放宽对白占比与信息密度预期）。

另：**机锋是合法资产**——长在人物处境上的反讽、自嘲、俏皮话（如"想要当败家子，也无从下手"）是人味高光，不得当问题提；只有当它打断场景张力时才 MAY。

## 声音指纹漂移（有 exemplar 时必做）
若 `memory/voice-bible.md` 的 exemplar_notes 已贴范文段落，运行
`PYTHONPATH=. python -m app.novel_forge.voice_signature <本章正文> --vs <范文文件>`
（范文无独立文件时，把范文段落临时存成文件再跑）。任何一项 metric 漂移超出容差即 MAY；句长方差、对白占比、分句复杂度三项同时漂移即 MUST。

## 章型指纹基准（校准参照，非达标线）
| 章型 | 人类基准 | 句长均值 | 句长CV | 对白占比 | 问句率 | 比喻密度 | 分句复杂度 |
|---|---|---|---|---|---|---|---|
| 立章（绵长型） | 剑来 ch01 | 43.8 | 0.90 | 0.09 | 0.06 | 1.3‰ | 5.2 |
| 过场+交锋 | 剑来 ch02 | 44.8 | 0.67 | 0.07 | 0.14 | 1.1‰ | 5.1 |
| 交锋（冷硬型） | 拾骨人 ch01 | 17.5 | 0.59 | 0.21 | 0.10 | 0.6‰ | 2.8 |
| 机器反例 | 星墟 DS | 12.4 | 0.58 | 0.09 | 0.008 | 3.5‰ | 1.4 |

用法：章型决定配比，指纹对齐本书 exemplar，不跨书对标。两个警惕信号（实证）：全章**问句率≈0**（没有人物用问句推进，DS 0.008 vs 人类 0.06–0.14）；**比喻密度 ≥3‰**（装饰性比喻是机器糠）。各项全扁（句长短、分句匀、无问句、比喻多）同时出现时，即使单条都不越界也按 MUST 提。

## 输出
写入 `reviews/chXX-texture-editor.md`：最多 8 条 MUST/MAY，每条含位置、原文证据、读者效果、修订意图；附 verdict: pass / needs_revision。MUST 用于：排比/堆叠造成的机械节奏、解释替代呈现、硬禁令违例。

## 复审协议
复审时必须重读修订后的**完整正文**与对应 patch 记录，确认修改没有产生新的肌理问题，而不是仅核对原 finding 是否被删除。

## 边界
不评价结构、因果、人物动机与设定；不生成新正文。
- `no-deliberate-defects`: 不得建议故意加入错字、病句或随机噪声来制造人味。
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
- 场景包缺少目标、阻力、人物摩擦或立即后果；“立章”不能把决策问题全部豁免。
- 关键 beat 无法说明如何导致下一 beat。
- 正文关键事件、动机、规则或谜团没有动作稿/信息账本来源。
- 重点信息没有来源、知情者或行动后果。
- 正文把观察直接写成唯一解释，认知账本却没有替代解释、置信度或可推翻证据。
- 条件的提出者、执行者、知情者或后果承担者与因果归属账本不一致。
- 人物的重要判断全部被世界立即验证，没有误判风险、未决状态或独立于主角的对抗意志。
- 专业判断缺少证据、未证前提、执行条件、成本或风险，却被正文当成能力证明。
- 关键对白不改变计划、权力、认知或关系。
- 新生造术语超出场景包第 5 节术语预算，或术语以解释而非身体/动作落地。

## 输出
写入 `reviews/chXX-causal-editor.md`：最多 6 条 MUST/MAY，含位置、证据、断裂的因果/信息责任、应回退层级（场景包/动作稿/对白账本/正文）、修订意图；附 verdict: pass / needs_revision。

## 复审协议
复审时必须重读修订后的**完整正文**与对应 patch 记录，确认修改没有产生新的因果断裂，而不是仅核对原 finding 是否被删除。

## 边界
不生成新正文；不把文采偏好当作因果问题。
- `single-winner-branch`: 对分支实验只评因果代价；必须保留单一胜者，不得建议拼接全部候选。
- `aesthetic-does-not-override-facts`: 审美偏好不得压过事实、人物认知与因果责任。
- `world-not-protagonist-proof`: 不得把“主角持续正确”误判为人物能动性；世界和其他人物必须保有独立意志。
- `expertise-must-be-executable`: 听起来专业不等于可执行，缺条件与风险的专业结论必须退回规划层。
"""


def _agent_line_editor_md() -> str:
    return """# Line Editor

## 角色
行文编辑，管对白与信息流。在 causal-editor 通过后执行；句子工艺（分句、比喻、句长）归 texture-editor，不在本角色重复审。只审读，不重写正文。

## 审稿维度
1. 对白归属：称呼、动作、位置、物件或明确反应是否足够。
2. 对白行动性：是否只为解释设定、复述信息或整齐排比而存在。
3. 重复簇：相邻段是否近义重复且未改变局势。
4. 解释性旁白：叙述者是否替读者总结情绪、主题或认知（句子级的解释腔由 texture-editor 复核）。
5. 能力证明循环：是否反复出现“观察 → 原理解释/履历背书 → 正确判断 → 他人惊讶”。
6. 呼吸段：是否具备标注的人物功能；若场景包声明“不新增信息”，正文是否仍偷偷加入线索、推断或设定。

## 输出
写入 `reviews/chXX-line-editor.md`：最多 6 条 MUST/MAY，含位置、原文证据、读者效果、修订意图；附 verdict: pass / needs_revision。MUST 用于归属不明、重复造成信息停滞、解释取代关键行动或能力证明循环支配整场。

## 复审协议
复审时必须重读修订后的**完整正文**与对应 patch 记录，确认修改没有产生新的行文问题，而不是仅核对原 finding 是否被删除。

## 边界
不擅自统一文风，不以禁词命中替代上下文判断，不生成新正文。
- `world-not-protagonist-proof`: 删除解释时保留人物的观察与选择，不替人物补一个新的确定答案。
- `expertise-must-be-executable`: 优先让专业能力通过提问、下注、操作和后果显形，不保留重复的履历背书。
"""


def _agent_orchestrator_md() -> str:
    policy_lines = _human_narrative_policy_lines()
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
- texture-editor MUST → `drafted`。
- consistency-guard MUST → 由问题定位；不得静默篡改既成事实。
- blind-reader 重建失败 → `drafted`（渲染不足）或 `scene_packaged`（场景本身缺物）。
- chapter-editor verdict=needs_revision → 按维度回退：因果类 → `scene_packaged`/`action_drafted`；行文类 → `drafted`。

## 规则
- 一次只编排一个章节或场景，不批量写后续章节。
- writer 仅加载当前场景、近场连续、相关人物/承诺和必要规则；长篇全量材料留给跨章审计。
- 每次只推进一个状态，并写入证据、结果和下一步。
- 审稿结论必须落盘到 `reviews/chXX-<role>.md`，证据表只存指针与 verdict。
- 开始起草前持久化 `formal` / `exploration` 模式；探索稿不得推进到 `ready`。
- 正式稿绑定 generation evidence 后再审稿；正文、规划、模式或 generation 变化会使旧审稿失效。
- 分支实验只允许一个胜者；每五章检查 checkpoint arc audit，卷终另做 volume audit。

## 不可绕过的策略
{policy_lines}
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
    "memory/MEMORY.md": (_memory_guide_md, ()),
    "memory/memory-record-template.md": (_memory_record_template_md, ()),
    "planning/story-engine.md": (_planning_story_engine_md, ()),
    "planning/research-boundaries.md": (_planning_research_boundaries_md, ()),
    "evaluation/constitution.md": (_evaluation_constitution_md, ()),
    "evaluation/case-template.md": (_evaluation_case_template_md, ()),
    "evaluation/experiment-template.md": (_evaluation_experiment_template_md, ()),
    "evaluation/rule-registry.md": (_evaluation_rule_registry_md, ()),
    "evaluation/generation-template.md": (_evaluation_generation_template_md, ()),
    "evaluation/branch-decision-template.md": (_evaluation_branch_template_md, ()),
    "evaluation/blind-evaluation-template.md": (_evaluation_blind_template_md, ()),
    "evaluation/preference-template.md": (_evaluation_preference_template_md, ()),
    "evaluation/arc-audit-template.md": (_evaluation_arc_audit_template_md, ()),
    "evaluation/rule-decision-template.md": (
        _evaluation_rule_decision_template_md,
        (),
    ),
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
    ".claude/agents/texture-editor.md": (_agent_texture_editor_md, ()),
    ".claude/agents/orchestrator.md": (_agent_orchestrator_md, ()),
}

# Directories that should exist; files under them are created via TEMPLATE_FILES.
REQUIRED_DIRECTORIES = [
    "chapters",
    "memory/entities",
    "memory/future",
    "memory/context-cache",
    "memory/candidates",
    "memory/canon/entities",
    "memory/canon/facts",
    "memory/canon/events",
    "memory/canon/knowledge",
    "memory/canon/promises",
    ".novel-forge",
    "planning/events",
    "planning/chapter-state",
    "evaluation/cases",
    "evaluation/experiments",
    "reviews/archive",
    *(f"evidence/{directory}" for directory in EVIDENCE_DIRECTORIES.values()),
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
    ".claude/agents/texture-editor.md",
    ".claude/agents/orchestrator.md",
    "planning/scene-package-template.md",
    "planning/action-draft-template.md",
    "planning/dialogue-ledger-template.md",
    "planning/chapter-state-template.md",
    "reviews/review-template.md",
    "memory/MEMORY.md",
    "memory/memory-record-template.md",
    "evaluation/case-template.md",
    "evaluation/experiment-template.md",
    "evaluation/generation-template.md",
    "evaluation/branch-decision-template.md",
    "evaluation/blind-evaluation-template.md",
    "evaluation/preference-template.md",
    "evaluation/arc-audit-template.md",
    "evaluation/rule-decision-template.md",
)

# Author/project policy assets are created in old books when missing, but an
# existing file is never overwritten by sync-tools.
CREATE_ONLY_FILES: tuple[str, ...] = (
    "evaluation/constitution.md",
    "evaluation/rule-registry.md",
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
