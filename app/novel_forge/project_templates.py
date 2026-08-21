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

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .book_git import initialize_book_git
from .guardian_contract import guardian_contract
from .models import SLUG_RE
from .planning_spec import (
    CHAPTER_HANDOFF_SECTION,
    CHAPTER_STATES,
    EVIDENCE_DIRECTORIES,
    HUMAN_NARRATIVE_POLICIES,
    LITERARY_MICRO_RULES_VERSION,
    MAX_DRAFT_MUTATIONS_PER_CHAPTER,
    MECHANISM_CLAUSES,
    MIN_FORMAL_CJK,
    REVIEW_ROLES,
    genre_preset,
    render_literary_micro_rules,
)
from .style_corpus import render_ai_tells_brief, render_positive_genes_brief
from .session_audit import harness_contract
from .writer_prompt import (
    FORMAL_WRITER_PROMPT_ID,
    MAX_FORMAL_WRITER_PROMPT_CHARS,
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
- 工作流版本: v5.4（正文优先 Lean 原生工作流）

## 唯一目标与入口
- 小说正文是唯一主产品。规划、表、证据、状态和 Git 都是附属记录，不能因遥测
  未知或技术字段缺失要求重写有效正文。
- Writer 只修改 `.novel-forge/diff/chNN/writer/draft/正文.md`；双审通过后由 Python
  晋升到 `books/{slug}/chapters/eXX/ch-XX/正文.md`，不建 `正文-v2.md`。
- 创作任务禁止先探索仓库实现。首个写操作必须是
  `python tools/novel-workflow.py ... start`，随后只执行
  `next-action → 宿主官方终态 → complete-role`。

## 角色边界
- Python 状态机决定下一步并自动计算哈希、stale、证据绑定、状态和 Git。
- 宿主只负责创建或复用独立 Session、等待官方终态、让角色写当前书 diff 区内动作
  指定的单一产物；
  Lead 无需填写技术表单或拼装宿主 session ID。
- 首个 Lean Writer 动作直接写 Capsule 内 `draft/正文.md`；Python 在后台准备最小
  规划材料。两个审稿角色只写动作的 `result_file`。
- Blind Reader 只读当前正文；Chapter Editor 再读场景包、必要 Canon 和 Blind 结果。
- Lead 不写正文、不审稿、不填 Runtime、Guardian、Generation、token、请求数或 Git。
- 不得创建或注册宿主专用 Agent 类型，不得写项目或用户级 `.claude/agents`。
- working/progress 时继续等待；创建成功、idle/available 或文件出现都不算完成。
- 无法创建真实独立角色时停止，只说明“本章未开始”，不得单会话模拟三角色。
- `NOVEL_FORGE_HARNESS_COMMAND` 仅是可选 headless 入口；不得在创作中配置 Harness。
- 默认 `lean_native`；未知遥测保持 null，不阻断正文和双审。只有明确使用
  `--strict-audit` 时才启用完整技术信封与全仓快照。

## 闭环
1. Python 直接签发 Writer 的正文动作；Writer 可在写作过程中做必要规划或最多 5 次
   题材、事实边界、重名检索，但不回传规划表。正式章至少 {MIN_FORMAL_CJK} CJK。
2. Python 跑表面门并冻结 `控制面冻结稿.md`；双审前正文仍留在 diff 区，不创建 Generation。
3. 新 Blind Reader Session 只读暂存正文；通过后才创建新 Chapter Editor Session。
4. 两审通过后 Python 晋升正文，再建立 Generation、Guardian、Review、状态和本地 Git。
5. 有 MUST 时直接签发 Writer 的 patch 动作，优先复用当前宿主 Writer 会话，只集中修一次 MUST，
   然后全文重新双审。
6. 第二版仍有 MUST 时停止自动回炉并让用户选择，不无限循环。
7. 有效正文已产生后，技术附属记录失败必须优先原地补记；禁止无理由重写正文。

## 文学目标
- 人物在压力中主动选择并付出私人代价；身体、物件、位置和关系持续改变行动。
- 允许误判、迟疑、沉默、不对称对白、延迟反应和未解释余波。
- 禁止把规划、审稿、因果清单或主题翻译成说明段；禁止职业证明循环、机械三连、
  连续否定翻转、解释性修补和用户硬锚漂移。
- Blind Reader 只有 `human_likeness=convincing` 且
  `reader_desire=continue` 才能 pass。
- {mechanism}

## 连续性与不可绕过
- `memory/canon/**/*.md` 是连续性权威源；新事实先进入 candidate。
- handoff 只含相关 Canon、开放承诺、上一章末段、Voice exemplar 和当前场景目标。
- 不得复制其他书的正文、记忆、审稿或样本。
{policy_lines}

- `正文.md` 不得出现提示词、Agent 身份、哈希、Generation、状态、Guardian 或 Git。
- Generation、Runtime、Guardian Receipt 和 Review History 创建后不可覆盖；正文改变
  必须新建 Generation 和两份 Review，旧记录变 stale。
- 本书 Git 位于 `.local-book-git/{slug}.git`，不得配置 remote；ready 不代表作者批准。
"""


def _readme_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    return f"""# 《{title}》

- 类型: {genre}
- 创建时间: {timestamp}
- 默认工作流: v5.4；完整编排说明见 `.agents/skills/novel-forge/SKILL.md`。

## 如何阅读
打开最新正文：

```
books/{slug}/chapters/eXX/ch-XX/正文.md
```

## 目录
- `chapters/` — 正文唯一入口
- `memory/` — 人物、历史、世界设定、voice-bible
- `memory/canon/` — Markdown 权威记忆；`memory/candidates/` — 待审增量
- `.novel-forge/` — 可重建 SQLite 索引、manifest 与章节 diff 暂存区（不入版本库）
- `planning/` — 故事发动机、研究边界、场景包、章节状态
- `evaluation/harness-contract.json` — 任意 Agent/Harness 的机器可读运行协议
- `evaluation/guardian-contract.json` — strict audit 的仓库外隔离协议；日常 Lean 不要求
- `evaluation/` — 评测宪法、实验与证据输入模板
- `evidence/` — 不可变创作证据与脱敏 runtime audit
- `.local-guardian/{slug}/` — 主仓库忽略的签名 Guardian key、授权、runtime sidecar 与权威回执
- `reviews/` — 审稿记录（每个角色一份，含 verdict）
- `patches/` — 局部修订 patch
- `.snapshots/` — 临时快照

## 默认工作流
Writer 在 diff 区写正文 → 表面检查 → blind-reader → chapter-editor → 有 MUST 则
Writer 修改同一暂存正文 → 全文双审 → Python 晋升并 ready。规划只在 Writer 写作
过程中进行，不单独交付或卡住正文。哈希、状态、stale、Guardian、Runtime 和 Git
由 Python 自动处理。

单次序列默认 1 章，最多 4 章。即使用户要求连续写 4 章，正文也必须由 4 个互不
复用的原生 writer session 顺序完成；上一章完整 `ready` 前不得启动下一章。
日常使用一次只做一章；Guardian 把简短用户意图与固定边界编译为
`{FORMAL_WRITER_PROMPT_ID}` 的 `instructions.md`，无需把完整 Skill 反复塞入模型上下文。
第三个不同正文版本必须先经 `authorize-regeneration` 取得签名控制面授权；公开
`evidence/guardian-receipts/` 副本不能脱离 `.local-guardian/{slug}/` 权威账本单独通过。

## 本地 Git
本书的 Git 元数据位于主仓库 `.local-book-git/{slug}.git`，不得配置 remote。
generation 绑定后保留 draft 提交，进入 ready 后保留 ready 提交。Git 只用于本地
diff、恢复和实验回放，不代表作者批准。用 `book-git-status` 查看状态。

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
6. 正式编排优先用 `begin-chapter-sequence` 生成
   `memory/context-cache/chXX-handoff.md`；它在记忆包之外只加入 Voice exemplar、
   上一章末段和当前 scene package。

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
  "salience": "medium",
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
    positive_genes = render_positive_genes_brief()
    ai_tells = render_ai_tells_brief()
    return f"""# Voice Bible — 《{title}》

> 本书的声音宪法。硬禁令只保留机器可检测的少数几条；其余全部是正面引导：
> 给方向与示范，不给填空表。每章起草前必读；修改本文件属于书级决策，需记录原因。
> 本文件描述叙事功能，不提供可反复套用的名词、动作、章末物件或句法配方。

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

### 对白边界（按读者效果判断）
- 高压对白必须让人物相对位置、身体受力或权力变化持续可感；只有对白退化为整齐
  问答记录、使现场退出时才是 MUST。纯对白本身不是错误，禁止按固定句数机械插动作。
- 只有读者无法判断谁在对谁说、回应关系因此断裂时，归属问题才是 MUST；不按固定
  轮数强加说话人标签。

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
- **机锋合法**：长在人物处境上的反讽、自嘲、俏皮话是人味资产；但必须来自当前
  人物和处境，不得把范文里的机锋移植成全书口头禅。

## 写前仪式：角色独白
动笔前以主角第一人称写 300-500 字独白（不进入正文，不留档）。问自己：此刻他/她最不想想的是什么？让他/她去想到那个。

## 风格基因库（正例参照）
> 取自对知名作品的公开技法分析，只学叙事功能、不抄任何措辞。与本书声音冲突的
> 基因直接忽略；采纳的基因写进上方对应小节，而不是每次写作时重读全表。

{positive_genes}

## AI 味对照清单（反例禁则）
> 密度才是破绽：单次出现不算罪，同类模式反复出现才构成机器味。审稿 advisory
> 会抽样提示其中可机检的条目（emotion-label / connective-tic 等），其余靠
> 起草与复审时人工对照。

{ai_tells}

## exemplar_notes
> 第 2 章起必填（narrative_gate 会检查本节）：从本书已写章节中选一个短段，
> 只说明它代表的叙事距离、信息释放和节奏功能。不得把范文里的具体名词、标志动作、
> 章末物件或句法骨架迁移到新章。
> 声音指纹由审稿阶段直接从文件计算，不把句长、段落、对白占比等数字粘贴到这里，
> 更不得把诊断值交给 Writer 当作生成目标。

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


def _evaluation_literary_micro_rules_md() -> str:
    return (
        "# 文学微规则\n\n"
        f"- version: {LITERARY_MICRO_RULES_VERSION}\n\n"
        "> 由脱敏样本提炼，只传递可执行判断，不向日常会话注入原文样本、"
        "数值风格目标或长篇反例。\n\n"
        "## Writer\n\n"
        f"{render_literary_micro_rules('writer')}\n\n"
        "## Blind Reader\n\n"
        f"{render_literary_micro_rules('blind-reader')}\n\n"
        "## Chapter Editor\n\n"
        f"{render_literary_micro_rules('chapter-editor')}\n"
    )


def _evaluation_generation_template_md() -> str:
    return """# Generation Evidence

> provider、model、外层 Agent/harness 与上下文清单必须按实际运行填写。
> 来源不明或元数据与真实运行不一致的样本不得进入跨模型比较。
> token、请求、正文写改与审稿调用只填写本 generation 的增量；不得把整场会话
> 累计值复制到每个 generation。未知保持 null。正式 Harness 应先读取
> `evaluation/harness-contract.json`，把原生遥测规范化为
> `novel-forge-runtime/v1`；正式稿还必须运行 `record-session-audit`，外部审计
> 优先于本文件自报字段。
> Lean Agent 正文必须从当前书 diff Capsule 经 Python 晋升，并存在匹配当前正文与
> `run_id` 的干净 Guardian 回执；strict audit 才要求仓库外 writer capsule。
> writer 不得直接写 `chapters/` 或书内控制面。
> 第三个及后续不同正文 SHA-256 需要 author/human_delegate 明确授权，并额外填写
> `"human_regeneration_authorized": true` 与 `"human_decision_reference": "<决定引用>"`；
> 前两代或未授权记录不得填写这两个字段。

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "generation.ch01.unique-id",
  "kind": "generation",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "agent",
  "source_paths": [
    "chapters/e01/ch-01/正文.md"
  ],
  "summary": "本章当前正文的生成来源。",
  "chapter": 1,
  "draft_mode": "formal",
  "writer_type": "agent",
  "provider": "provider-name",
  "model": "model-name",
  "content_path": "chapters/e01/ch-01/正文.md",
  "content_sha256": "替换为正文文件的64位sha256",
  "prompt_template_id": "__FORMAL_WRITER_PROMPT_ID__",
  "prompt_sha256": "替换为instructions.md的64位sha256",
  "elapsed_seconds": null,
  "input_tokens": null,
  "output_tokens": null,
  "total_tokens": null,
  "cached_input_tokens": null,
  "request_count": null,
  "draft_write_count": null,
  "draft_edit_count": null,
  "review_call_count": null,
  "metrics_source": "unknown",
  "pause_count": null,
  "interaction_count": null,
  "review_round": 0,
  "parent_generation_id": null,
  "generation_stage": "raw",
  "provenance_confidence": "unknown",
  "run_id": "unknown",
  "agent_harness": "unknown",
  "reasoning_effort": "unknown",
  "sandbox_profile": "unknown",
  "tool_capabilities": [],
  "tool_failures": []
}
```
""".replace("__FORMAL_WRITER_PROMPT_ID__", FORMAL_WRITER_PROMPT_ID)


def _evaluation_harness_contract_json() -> str:
    return (
        json.dumps(
            harness_contract(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _evaluation_guardian_contract_json() -> str:
    return (
        json.dumps(
            guardian_contract(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _evaluation_degraded_run_template_md() -> str:
    return """# Degraded Exploration Run

> 仅用于 Shell、adapter、子代理或其他关键工具不可用时。
> 必须如实记录缺失能力和失败，不得把本记录升级为 formal 完成证据；
> `degraded_exploration` 不得进入 ready 或 benchmark_eligible。

<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "generation.ch01.degraded.unique-id",
  "kind": "generation",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "authority": "agent",
  "source_paths": ["chapters/e01/ch-01/正文.md"],
  "summary": "工具受限条件下完成的探索正文。",
  "chapter": 1,
  "draft_mode": "degraded_exploration",
  "writer_type": "agent",
  "provider": "provider-name",
  "model": "model-name",
  "content_path": "chapters/e01/ch-01/正文.md",
  "content_sha256": "替换为正文文件的64位sha256",
  "metrics_source": "unknown",
  "review_round": 0,
  "generation_stage": "raw",
  "provenance_confidence": "unknown",
  "run_id": "unknown",
  "agent_harness": "harness-name",
  "reasoning_effort": "unknown",
  "sandbox_profile": "no_shell",
  "tool_capabilities": ["read_file", "write_file"],
  "tool_failures": ["shell: 记录真实错误或限制"]
}
```

## 恢复正式流程
- [ ] 外层 Harness 已建立标准项目结构。
- [ ] 已补齐 formal 场景包、记忆上下文与 generation 证据。
- [ ] 已重新运行全部正式门禁和审稿；没有沿用降级运行的 pass。
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


def _dot_gitignore() -> str:
    return """# Per-book ignore rules for books/<slug>/
.snapshots/
memory/context-cache/
.novel-forge/
__pycache__/
*.pyc
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
- previous_chapter_sha256: <review-binding previous_chapter_sha256；ch01 填 not_applicable>
- planning_sha256: <review-binding planning_sha256>
- draft_mode: <formal|exploration|degraded_exploration>
- generation_id: <generation evidence id or unrecorded>
- evidence_quote: <关键审稿必须逐字存在于当前正文>
- previous_chapter_quote: <ch02+ consistency/chapter-editor 必填；ch01 填 not_applicable>
- reviewer_type: <human|agent|model>
- reviewer_id: <stable reviewer/session id>
- review_session_id: <真实审稿会话 id；blind-reader pass 必须不同于 writer run_id>
- provider: <provider or not_applicable>
- model: <model or not_applicable>
- context_scope: <prose_only|simulated_blind|full_review_context>
- independence_note: <同源评审时必填；角色名不同不等于独立>
- human_likeness: <blind-reader 填 convincing|uncertain|synthetic；其他角色填 not_applicable>
- reader_desire: <blind-reader 填 continue|conditional|stop；其他角色填 not_applicable>
- emotional_residue: <blind-reader 写读后仍残留的关系、情绪或代价；其他角色填 not_applicable>
- next_chapter_pull: <blind-reader 写让人自愿追读的具体问题；其他角色填 not_applicable>

## Prose-only Reconstruction（blind-reader 必填）
- reconstruction_space:
- reconstruction_body:
- reconstruction_constraints:
- reconstruction_emotion:
- reconstruction_dialogue:
- memorable_image_1:
- memorable_image_2:
- memorable_image_3:

## Editorial Dimensions（chapter-editor 必填）
- editorial_causality:
- editorial_agency:
- editorial_dialogue:
- editorial_texture:
- editorial_continuity:

## Findings
| # | 级别 (MUST/MAY) | 位置 | 原文证据 | 读者效果 | 修订意图 | 状态 (open/closed) |
|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |

## 复审记录
- 复审人 / 日期 / 关闭的 finding 编号
"""


def _planning_scene_package_template_md() -> str:
    return f"""# Scene Package — 第XX章「标题」

> 一页式写作契约。只写会改变正文的内容，不写文学说明书。

## 0. 边界
- 开始动作 / 停止动作：
- 承接压力 / 本章不解决：

## {CHAPTER_HANDOFF_SECTION}（ch02+）
> “本章开头原文”可在起草后回填，但必须在 formal gate 前成为真实短引。
> 转场类型：same_day_continuous / cross_day / flashback / parallel。
> 若本章推翻上一章末的明确决定，必须引用当前正文前 40% 内真实出现的触发事件。
- 上一章正文路径：
- 上一章正文 SHA-256：
- 上一章结尾原文：
- 本章开头原文：
- 上一章结束时间：
- 本章开始时间：
- 上一章结束地点：
- 本章开始地点：
- 上一章结束动作：
- 本章开始动作：
- 转场类型：
- 上一章末明确决定：
- 本章是否推翻该决定：是 / 否 / 不适用
- 若推翻，触发事件原文：未推翻时写“无需：未推翻上一章决定”

## 1. 场景压力
- 视角角色要什么：
- 对手/世界独立要什么：
- 选择与即时成本：
- 章末未解除压力：

## 1c. 决策问题
- 不能同时得到的两样东西：
- 角色拒绝承认什么：
- 角色误读了谁或什么：
- 哪句话不能说出口：
- 最终接受的具体代价：

## 1d. 认知与可证伪假设
| 观察 | 当前假设 | 替代解释 | 置信度 | 可推翻证据 | 状态 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 1e. 规划反证与常识检查
- 时间/日历算术：
- 物理动作机制：
- 人物知识来源：
- 不可逆性反证：
- 场景停止点：

## 2. 在场者状态
| 人物 | 此刻目标 | 隐瞒/未知 | 本场变化 |
|---|---|---|---|
|  |  |  |  |

## 3. Beat 因果链
| # | 触发 | 行动/决定 | 阻力/反应 | 结果与下一步 | 语域 |
|---|---|---|---|---|---|
| 1 |  |  |  |  |  |
| 2 |  |  |  |  |  |

## 3c. 因果归属账本
| 动作/条件 | 提出/执行者 | 知情者 | 后果承担者 |
|---|---|---|---|
|  |  |  |  |

## 4. 信息账本
- 本章唯一新信息 / 来源 / 导致的选择：

## 5. 信息预算
- 锚定物象（3-5）：
- 关键对白意图（没有则写无需）：
- 新规则/伏笔/术语（各 0-1）：
- 延后信息：

## 5b. 专业判断审计
- 判断/主张（无则写“无需：具体原因”）：

## 6. 人物性呼吸段
- 私人欲望（任务之外仍想保住什么）：
- 关系摩擦（对方不会配合什么）：
- 感知偏差（视角人物先注意什么、容易漏掉什么）：

## 7. 场景余波
- 身体 / 物件 / 关系 / 认知误信 / 未偿承诺：
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
    "evaluation/literary-micro-rules.md": (
        _evaluation_literary_micro_rules_md,
        (),
    ),
    "evaluation/generation-template.md": (_evaluation_generation_template_md, ()),
    "evaluation/harness-contract.json": (
        _evaluation_harness_contract_json,
        (),
    ),
    "evaluation/guardian-contract.json": (
        _evaluation_guardian_contract_json,
        (),
    ),
    "evaluation/degraded-run-template.md": (
        _evaluation_degraded_run_template_md,
        (),
    ),
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
    "planning/chapter-sequences",
    "planning/guardian-sessions",
    "evaluation/cases",
    "evaluation/experiments",
    "evidence/runtime-audits",
    "evidence/guardian-receipts",
    "reviews/archive",
    *(f"evidence/{directory}" for directory in EVIDENCE_DIRECTORIES.values()),
    "patches",
    ".snapshots",
    "tools",
]

# Files that `sync-tools` may refresh in existing books (managed, never
# hand-edited). Everything else is only created when missing.
SYNCABLE_FILES: tuple[str, ...] = (
    "tools/quality_check.py",
    "tools/narrative_gate.py",
    "planning/scene-package-template.md",
    "planning/action-draft-template.md",
    "planning/dialogue-ledger-template.md",
    "planning/chapter-state-template.md",
    "reviews/review-template.md",
    "memory/MEMORY.md",
    "memory/memory-record-template.md",
    "evaluation/case-template.md",
    "evaluation/experiment-template.md",
    "evaluation/literary-micro-rules.md",
    "evaluation/generation-template.md",
    "evaluation/harness-contract.json",
    "evaluation/guardian-contract.json",
    "evaluation/degraded-run-template.md",
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
    if not slug or not SLUG_RE.fullmatch(slug):
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

    local_git = initialize_book_git(root, slug, title.strip())
    return {
        "book_dir": str(book_dir),
        "created_directories": created_dirs,
        "created_files": created_files,
        "skipped_files": skipped_files,
        "local_git": local_git,
    }
