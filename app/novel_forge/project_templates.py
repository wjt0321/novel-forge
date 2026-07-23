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
from .planning_spec import (
    CHAPTER_STATES,
    EVIDENCE_DIRECTORIES,
    HUMAN_NARRATIVE_POLICIES,
    LITERARY_MICRO_RULES_VERSION,
    MECHANISM_CLAUSES,
    REVIEW_ROLES,
    genre_preset,
    render_literary_micro_rules,
)
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
- 工作流版本: v5.2（完成信封补交、封存 Review Capsule 与按角色恢复）

## 唯一正文与事实源
- 正文只写入 `books/{slug}/chapters/eXX/ch-XX/正文.md`；不建 `正文-v2.md`。
- `memory/canon/**/*.md` 是连续性权威源，SQLite 只是缓存；新事实先进入 candidate。
- 严禁复制其他书的正文、记忆、审稿或已填写模板。
- `evidence/` 证明过程，不代表作者批准；`ready` 也不代表发布许可。

## 自动生产唯一入口
- 创作任务禁止先探索仓库实现。首个写操作必须是
  `python tools/novel-workflow.py ... start`；没有命令 Backend 时自动进入原生会话
  Relay，随后只循环 `next-action → 宿主官方终态 → complete-role`。
- Python 状态机决定下一步；宿主只负责创建、等待和回传。Lead 不写角色产物、
  evidence、状态或 ready，也不从缺失结果中补造完成态。
- Lead 使用动作的 `completion_template`；格式错只补交同一终态，不重跑角色。
- Writer 只接收 Writer Capsule；审稿只接收 `review_capsule.path`，Lead 不搬正文。
- 创作角色对项目仓库零写入：规划和审稿只返回结构化结果，Writer 只写仓库外
  capsule 的 `draft/正文.md`。新增项目产物会被清理并换新会话。
- ACP 只用于事后取证和根因调查，不创建生产会话，不参与 Guardian、ready 或 Git。
- 新书先由确定性控制面通过 `init-novel-project` 初始化；创作角色不得直接写
  `books/`，不得自行创建正文、规划、审稿或 ready Git 恢复点。
- `NOVEL_FORGE_HARNESS_COMMAND` 只启用可选 headless 命令 Backend，不是用户选项。
- 高权限只属于无模型推理的确定性控制面；Lead 和三个角色无权改规则或代做彼此产物。
- 必须使用宿主官方 wait / join 等到角色终态；创建成功、已接单、进度消息或文件暂时稳定都不算完成。
- 创建后保存宿主返回的真实 `operation_handle.kind/value`；句柄 kind 决定宿主的
  wait/join/result 通道。禁止把 agent ID 猜成 task ID、把角色名当作 TaskOutput ID、
  固定 sleep 或以文件出现猜测完成。每个创作角色默认至少等待 30 分钟；仍在
  working/progress 就继续等待。`idle_notification` 或 available 不是角色产物；
  completed 还必须返回绑定 role、session_id、session_instance_id 的 `role_result`。
- Writer、Blind Reader、Chapter Editor 与 Patch Writer 分别计算技术重试次数；
  有效 Generation 后的审稿运输故障只从未完成的审稿角色恢复，不重新生成正文。
- 模型配置只是选择意图；证据只记录宿主终态返回的 `resolvedModel`。Writer 角色在
  Claude Code 模板中使用 `model: inherit`，表示继承当前父会话模型，不绑定具体厂商。
- Claude Code 创建角色时必须使用项目已定义的 `novel-forge-writer`、
  `novel-forge-blind-reader`、`novel-forge-chapter-editor`，不得退回
  general-purpose 后仍宣称使用了项目角色。
- 无法创建或等待真实独立角色时停止，只说明“本章未开始”。
- 创作任务中的 Lead 和角色不得创建、修改、修复、包装、安装或配置 Harness
  / SessionBackend；headless 缺失时不得自行设置命令桥或要求用户部署。
- `degraded_exploration` 只有用户明确要求探索稿时才允许；不得因工具受限自行降级，
  也不得把探索稿称为完成。
- Writer 规划阶段可做最多 5 次题材、事实边界和重名检索；不得借此阅读工作流源码。
- 默认 `formal_native` 使用外置 Capsule、零项目写入、全仓快照和 Guardian；
  宿主有真实 OS 沙箱时透明升级为 `formal_sandboxed`，不询问用户 A/B。

## 本地版本历史
- 本书使用独立本地 Git；工作区内 `.git` 只指向主仓库忽略的
  `.local-book-git/{slug}.git`，不得配置 remote 或上传。
- generation 绑定后自动提交 `chapter: chNN draft`；进入 ready 后自动提交
  `chapter: chNN ready`；第 5/10/15... 章创建本地 checkpoint tag。
- Git 只负责 diff 与恢复，不替代 evidence、ready、作者批准或发布决定。
- 用 `book-git-status` 检查 head、dirty 与 remote_count；adapter 仍显式传入
  Novel Forge 主仓库的绝对 `--root`。

## 每章状态链与执行闭环
`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

1. Orchestrator 先读 `evaluation/harness-contract.json` 与
   `evaluation/guardian-contract.json`。用户要求写 1 章时运行
   `begin-chapter-sequence --chapter-count 1`；要求连续写多章时，
   仍由同一编排器按顺序执行，但单次最多 4 章，五章及以上必须拆分。用
   `set-draft-mode` 固定 formal/exploration。起草前确认 `memory-status=clean`，
   并运行 `build-memory-context` 生成当前章有界上下文。
2. 每章都用 launch directive 创建新的原生 writer session，并立即用
   `claim-chapter-session` 绑定真实 session id。不得把编排器 session、角色名或
   上一章 session 冒充新会话。
3. Orchestrator 运行 `prepare-writer-capsule`，把当前章有界 handoff 放进仓库外
   capsule。默认 `formal_native` 只向 writer 交付 Capsule 输入并用全仓前后快照
   验证零项目写入；宿主有真实沙箱时透明升级为 `formal_sandboxed` capsule-only。
   writer 只能读取 `instructions.md` 与 `handoff.md`，只能输出 `draft/正文.md`，
   不得接收本书控制面、evidence、sequence、校验器源码或其他章节。`instructions.md` 由 Guardian 按
   `{FORMAL_WRITER_PROMPT_ID}` 编译，不回灌完整 Skill。handoff 中只放过滤后的
   Writer Story Brief；完整 Scene Package 的决策问题、替代解释、可证伪假设、因果
   归属和专业判断审计只供 Chapter Editor 使用。确定性控制面或可选 headless Harness 在 capsule 外生成标准
   累计 runtime，并用 `record-capsule-runtime` 写入 Guardian sidecar；writer 不得写 runtime。
4. 一次只做一章，writer 一次写完整章；正式章 ≥5000 CJK。规划与疑难因果核验可用 high；正文默认
   standard/medium；默认审稿也用 standard/medium。Max/长思考只处理被明确命名的
   困难问题，不用于整章自由生成。规划是后台故事义务，不得在正文中逐项证明；
   人物允许误判、遗漏、自欺和延迟反应。对白按回应关系、身体位置和权力变化判断，
   不按固定句数机械插动作。
5. Writer 结束后运行 `ingest-writer-capsule`。额外脚本、路径逃逸、保护输入变化、
   runtime 缺失或 session 不一致会把回执标成 `compromised`，当前 session 自动
   失效，必须 claim 新会话。一次集中 patch 必须使用新 capsule，它会预置当前正文；
   第三个潜在正文版本必须先用 `authorize-regeneration` 记录绑定当前章节、
   session 与前两份正文哈希的签名人类授权，再把 authorization ID 交给新 capsule。
6. 记录 generation；`run_id`、provider/model/Harness/思考强度、工具失败、
   `prompt_template_id` 与 `prompt_sha256` 必须来自真实 capsule/回执，并经
   `record-evidence` 落盘。初稿后只允许一次集中 patch，即最多两份不同正文 SHA-256。
7. 每次模型响应后更新累计快照并运行 `session-audit`；若
   `budget.continue_allowed=false`，必须在下一次模型请求前停止。结束时再经
   `record-session-audit` 固化脱敏审计。预算超限、来源不一致、逐字复用覆盖过高、
   长段复制、损坏对白、Markdown 粗体、工作流标记、`——`、`……` 等任一 blocking
   都立即短路。
8. 默认只做两角色审稿：blind-reader 必须在不同于 writer `run_id` 的独立会话中
   只读正文并给 `human_likeness`、`reader_desire` 与追读证据；同会话只能标记
   `simulated_blind` 且不能 pass。
   blind-reader 还要识别控制面泄漏、整齐问答、职业证明与修补接缝。
   chapter-editor 每轮重新完成因果、人物、行文、肌理和连续性五项审查。专业角色仅在
   明确风险下按需调用。审稿终态缺少正式结果通道、`role_result` 或角色绑定时，
   废弃该 session 并新开同角色 session，最多自动重试两次；Blind 已正式记录后
   Editor 故障只重试 Editor。
9. 上一章完整 ready（当前有效状态为 `ready`）后结束 writer session，并由编排器运行
   `advance-chapter-sequence`。返回 `launch_next_session=true` 时才创建下一章的
   新 session；否则停止。第五章做 checkpoint audit，并用 `evidence-status`
   核对证据闭环。

## 文学目标
- 问题不是“表格填完了吗”，而是：人物是否在压力中选择，世界是否有独立意志，细节是否改变行动，声音是否在章际保持活性。
- blind-reader 必须回答 `human_likeness: convincing|uncertain|synthetic` 与
  `reader_desire: continue|conditional|stop`；只有 convincing + continue 可通过，
  并必须说明读后残留的关系/情绪压力与下一章追读问题。
- 机器只拦高置信结构破绽：极端跨章逐字复用、长段复制、损坏对白；句长塌缩、
  Voice 范文表层复制和章内模式饱和仍只报告风险，不认证文学价值。
- Writer 不接收句长、段落长度、对白占比等数字目标；这些统计只由审稿阶段诊断，
  不得当作生成配额或文学达标线。
- {mechanism}

## 不可绕过
{policy_lines}

- 只有用户明确要求探索稿时才能使用 `degraded_exploration`，记录真实
  `tool_failures`，不得伪装 formal 或称为完成。
- `正文.md` 不得出现提示词、Agent 身份、章节工作流编号、SHA-256、generation evidence/id、surface_checked 或 ready 等生产元数据。
- 不得暂停询问“是否开始审核”；formal 门禁通过后自动创建独立审稿会话并完成两角色审核。无法创建新会话时返回 `review_session_required`，不得改成开放式提问。只有事实冲突、覆盖风险、作者取舍或第二份 generation 后仍有 MUST 才暂停。
"""


def _readme_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    return f"""# 《{title}》

- 类型: {genre}
- 创建时间: {timestamp}
- 默认工作流: v5.2；完整编排说明见 `.agents/skills/novel-forge/SKILL.md`。

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
- `evaluation/harness-contract.json` — 任意 Agent/Harness 的机器可读运行协议
- `evaluation/guardian-contract.json` — 仓库外隔离 writer capsule 协议
- `evaluation/` — 评测宪法、实验与证据输入模板
- `evidence/` — 不可变创作证据与脱敏 runtime audit
- `.local-guardian/{slug}/` — 主仓库忽略的签名 Guardian key、授权、runtime sidecar 与权威回执
- `reviews/` — 审稿记录（每个角色一份，含 verdict）
- `patches/` — 局部修订 patch
- `.snapshots/` — 临时快照

## 默认工作流
章节序列签发 → 新 writer session claim → 编译短提示词 → 仓库外隔离 capsule → 一次完整初稿 →
Guardian 导入回执 → 机器门禁 → blind-reader → chapter-editor → 至多一次集中 patch → ready →
结束本章 session → 顺序签发下一章。

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
> 正式 Agent 正文还必须经仓库外 writer capsule 导入，并存在匹配当前正文与
> `run_id` 的干净 Guardian 回执；writer 不得直接写 `books/` 控制面。
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


def _agent_context_collector_md() -> str:
    return """---
name: novel-forge-context-collector
description: "Collect one bounded chapter context packet without drafting prose."
---

# Context Collector

只收集，不写正文。输出一页以内的写作包：

1. 目标、阻力、选择、即时成本各一句。
2. 当前章直接相关的 Canon/人物已知/人物猜测，合计不超过 8 条。
3. 上一章末段只保留连续动作和一个短引，不加载整章。
4. 相关承诺最多 3 条，世界规则最多 3 条。
5. voice bible 只摘本章距离、节奏和一个 exemplar 短段。
6. 列出未加载材料及原因。

正式序列由 `begin-chapter-sequence` 自动核对/重建派生索引并生成
`chXX-handoff.md`；单章诊断仍可直接运行 `memory-status` /
`build-memory-context`。
不得读取全书审稿史、全部 Canon、其他章节规划或模板说明。上一章有
source-hygiene blocking 时停止。事实缺口只记 candidate，不自行补全。
"""


def _agent_writer_md() -> str:
    return """---
name: novel-forge-writer
description: "Draft exactly one Novel Forge chapter inside an assigned isolated capsule."
model: inherit
---

# Writer

你是本章唯一 Writer。`model: inherit` 只表示继承宿主当前父会话的模型选择，不绑定
任何厂商或模型名称；宿主实际返回的 `resolvedModel` 才是正式来源真相。

1. 只读取分配给你的 capsule 内 `capsule.json`、`guardian-contract.json`、
   `instructions.md` 与 `handoff.md`。
2. 只写 `draft/正文.md`，不得创建脚本、runtime、回执、审稿、状态或 Git 记录。
   完成时只通过宿主正式结果通道返回 capsule 内相对路径 `draft/正文.md`，不得猜测、
   拼接或回报宿主绝对路径。
3. 只完成一章；正文达到 `instructions.md` 的完整章节目标后停止。
4. 不读取完整 Skill、验证器、其他章节、旧会话、旧审稿或 `books/` 控制面。
5. 有 MUST 时仍是新的 Patch Writer 会话，只处理合并后的 MUST，不顺手处理 MAY。
6. 无法遵守 capsule-only 边界时返回失败，不得降级为主会话直写。
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
7. 第 2 章起核对 `0b. 章际交接`，并用 review-binding 的上一章正文 SHA-256 锁定来源

## 检查清单
- [ ] 实体名称与已记录一致
- [ ] 角色认知不超过其已知信息
- [ ] 正文没有把人物假设、怀疑或专业判断静默升级成 Canon 事实
- [ ] 重要条件的提出者、执行者、知情者与后果承担者和因果归属账本一致
- [ ] 已标记“未决/误判”的假设没有被后文旁白提前认证为正确
- [ ] 时间线无矛盾
- [ ] 上一章结尾短引、本章开头短引、时间/地点/动作与转场类型彼此一致
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
- `evidence_quote` 必须逐字存在于本章正文；第 2 章起 `previous_chapter_quote` 必须逐字存在于上一章正文

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
    return """---
name: novel-forge-chapter-editor
description: "Run the final independent chapter-level editorial review after Blind Reader."
---

# Chapter Editor

最后一个默认审稿环节，只审读，不重写正文。

1. 先只读正文，重建事件链、人物选择、代价、停止点和三个画面。
2. 再读一页式 scene package、当前记忆包和上一章末段；不读旧专业审稿。
3. 每轮都完整完成五项检查，不得只核对上一轮 finding：因果与有限认知、
   人物和世界的独立目标、对白与信息流、
   句子肌理及跨章连续性。
4. 机器报告出现句长塌缩、章内模式饱和、Voice 范文表层复制或低量跨章复读时，
   结合原文判断它是有意复沓还是模板化填充；极端逐字复用覆盖、长段复制和损坏对白
   属于上游 blocking，不得由本角色豁免。
5. 第 2 章起核对上一章末明确决定；若本章行动反转，必须能在正文前段找到新的触发，
   不能让 scene package 用解释替正文补桥。
6. 只有发现具体专业风险时，才请求一个 specialist review；不得默认扩成六审。
7. 检查编辑控制面是否泄漏进正文：人物不得逐项背诵替代解释、反证或因果审计。
8. 检查人物可替换性、对白是否退化为整齐记录，以及局部 patch 是否形成集中解释段。
   不得按固定台词句数或固定动作间隔判错。

通过宿主正式结果通道返回结构化报告，不直接写 `reviews/`。每条 MUST/MAY 都要有
原文证据和读者效果；
MUST 最多 5 条。第 2 章起填写 `previous_chapter_quote`。verdict 只能是
`ready_for_editor_decision` / `needs_revision`。复审必须重读完整修订稿。
报告必须逐项填写 `editorial_causality`、`editorial_agency`、
`editorial_dialogue`、`editorial_texture`、`editorial_continuity`；
空字段不能通过 record-review。
`ready_for_editor_decision` 不是作者批准。
"""


def _agent_blind_reader_md() -> str:
    return """---
name: novel-forge-blind-reader
description: "Blind-read only the current prose in a fresh isolated review session."
---

# Blind Reader

## 角色
盲读者。必须运行在不同于 writer `run_id` 的独立会话，只读当前章的
`正文.md`——严禁读取 `planning/`、`memory/`、voice-bible、其他章节或任何规划材料。
用"规划知识"填补正文未渲染的画面，正是本环节要抓的作弊。同一写作会话若只能自检，
必须填写 `context_scope=simulated_blind` 并给 `needs_revision`，不能冒充 pass。

## 任务
仅凭正文重建以下六项：
1. **空间**：场景布局、出入口、人物相对位置。
2. **身体**：谁的身体处于什么状态（伤、累、冷、汗），身体与环境的接触点。
3. **行动约束**：此刻什么动作做不到，为什么（时间、钱、伤、规则）。
4. **情绪轨迹**：开场到章末情绪如何移动，由什么具体事件推动。
5. **对话动态**：每个话轮谁说、对谁说、想要什么。
6. **可记忆画面**：至少 3 个，每个必须附原文引用（≤2 句）。

## 输出
通过宿主正式结果通道返回结构化报告，不直接写 `reviews/`。
- 六项重建结果逐项给出；任何一项重建失败即 MUST，注明卡在哪个位置、正文缺什么信息。
- 每条结论必须有原文证据；禁止抽象赞扬。
- `human_likeness: convincing | uncertain | synthetic`。只有 `convincing`
  可以配合 verdict=pass；若节奏像清单、物件循环像模板配额、叙述知道未来章节、
  正文带工作流语言、人物逐项列完替代解释、高压对白退化为整齐问答记录，或局部
  修订留下明显接缝，必须结合读者效果给 uncertain/synthetic 与 needs_revision。
- `reader_desire: continue | conditional | stop`。只有 `continue` 可以配合
  verdict=pass；必须填写 `emotional_residue` 与 `next_chapter_pull`，回答一个真人
  是否会自愿继续读，而不是正文是否“符合模板”。
- 报告必须填写 `reconstruction_space`、`reconstruction_body`、
  `reconstruction_constraints`、`reconstruction_emotion`、
  `reconstruction_dialogue` 与三个 `memorable_image_N`；空字段不能通过
  record-review。
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
    return """# Scene Package — 第XX章「标题」

> 一页式写作契约。只写会改变正文的内容，不写文学说明书。

## 0. 边界
- 开始动作 / 停止动作：
- 承接压力 / 本章不解决：

## 0b. 章际交接（ch02+）
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


def _agent_texture_editor_md() -> str:
    return """# Texture Editor

## 角色
文字肌理编辑。只管句子与分句的工艺，不管结构、因果与设定。在 line-editor 通过后执行；只审读，不重写正文。

## 审稿维度（仅此六项，逐项给证据）
1. **分句堆叠**：逗号串起的均匀微短分句。病不在多，在于连续动作没有主次，
   每个分句都像同样重量的打点。
2. **排比铺陈**：叙述者为显文采的机械三连。先问"这串排比是谁的"——民俗、童谣、人物的仪式性复沓、对白里的排比，合法；叙述者逞才的，才算病。
3. **比喻**：检查它是否改变理解、行动或人物关系；只装饰气氛的弱比喻应删。
4. **解释腔**：叙述者替读者总结情绪/规矩/主题（含动作中段背规矩条文）。注意区分"百科式设定宣讲"与"有声音、贴处境的讲者陈述"——后者在立章与插叙中合法。
5. **句长方差**：句内与段内是否有呼吸；均匀短句与均匀长句都报警，但不追求
   某个数值。
6. **套话与悬浮词**：冷光闪烁、空气凝固、时光荏苒类；没有落到具体物象的抽象词。
7. **语域适配**：对照 `memory/voice-bible.md` 的语域地图（0 隐形摄像机 / 1 贴身 / 2 讲者现身 / 3 讲者抒情），判断每段的叙述者在场度是否匹配其功能——开场切入是否够快、行动是否隐形、插叙是否有讲者导航或物件过渡、收束是否收在画面而非点评。场景包 beat 表有语域声明时，逐拍对照；场景包声明章型（交锋/立章/过场/收束）时，按章型校准（立章放宽对白占比与信息密度预期）。

另：**机锋是合法资产**。长在人物处境上的反讽、自嘲和俏皮话不得仅因偏离
中性文风而被删除；只有打断当前张力时才 MAY。

## 声音指纹漂移（有 exemplar 时必做）
运行 `voice_signature` 比较本章与本书 exemplar。统计只用于定位需要回读的段落，
不设文学达标数值，不要求 Writer 把正文调到某个句长、段落或对白比例。重点判断：
本章是否仍有相同的叙事距离与信息释放方式，同时避免复制范文的具体名词、标志动作、
章末物件和句法骨架。单项漂移默认 MAY；只有原文已形成可定位的机械读感时才提 MUST。

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
1. 第一遍先只读正文，独立重建 beat 因果、知识来源、动作机制、不可逆条件与停止点。
2. 保存重建结果后，再读 `planning/scene-package-chXX.md`、`planning/action-draft-chXX.md` 与 `planning/dialogue-ledger-chXX.md`（如有）。
3. 最后读取上一章末尾与必要 `memory/` 事实，核对连续性边界。

## 反锚定协议
- 必须先只读正文；不得因为场景包写了“不可逆”就认定正文选择已经不可逆。
- 报告先列“prose-only reconstruction”，再列“planning delta”。正文缺失与规划错误分开归责。
- 特别复核规划反证五项：时间/日历、动作机制、知识来源、不可逆性与场景停止点。

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
    return f"""---
name: novel-forge-orchestrator
description: "Coordinate the deterministic Novel Forge three-role workflow without authoring role artifacts."
---

# Orchestrator

维护状态和证据，不写正文。状态链：
`{_STATE_CHAIN}`

## 自动生产唯一入口
- 创作任务禁止先探索仓库实现。首个写操作必须是
  `python tools/novel-workflow.py ... start`；没有命令 Backend 时自动进入原生会话
  Relay，随后只循环 `next-action → 宿主官方终态 → complete-role`。
- Python 状态机决定下一步；宿主只负责创建、等待和回传。创作角色对项目仓库零写入，
  ACP 只用于事后取证，不参与生产控制。
- Lead 必须从动作的 `completion_template` 填写真实终态；格式错误只补交同一终态，
  不得重跑角色。Writer 只接收 Writer Capsule，审稿角色只接收
  `review_capsule.path`，Lead 不搬运正文。
- 新书先由确定性控制面通过 `init-novel-project` 初始化；创作角色不得直接写
  `books/`，不得自行创建正文、规划、审稿或 ready Git 恢复点。
- `NOVEL_FORGE_HARNESS_COMMAND` 只启用可选 headless 命令 Backend，不是用户选项。
- 高权限只属于无模型推理的确定性控制面；Lead 和三个角色无权改规则或代做彼此产物。
- 必须使用宿主官方 wait / join 等到角色终态；创建成功、已接单、进度消息或文件暂时稳定都不算完成。
- 创建角色后立即保存宿主返回的真实 `operation_handle.kind/value`。句柄 kind
  决定调用 Task Output、background output、mailbox 或其他宿主官方结果通道；
  禁止把 agent ID 猜成 task ID、把角色名当作 TaskOutput ID，或凭自造名称查询。
- 禁止固定 sleep、短轮询或以文件出现猜测完成。Writer、Blind Reader 和 Chapter
  Editor 每个角色默认至少等待 30 分钟；角色仍处于 working/progress 时继续等待，
  不得为节省 Lead 时间提前 stop。只有官方 failed/cancelled/timed_out 终态或用户明确
  停止才退役角色。
- `idle_notification`、idle 或 available 只表示角色可接收新消息，不是报告已送达。
  completed 必须同时取得 `novel-forge-role-result/v1` 的 `role_result`，且 role
  与当前角色一致，并绑定 session_id、session_instance_id 和原 operation handle；
  完成信封错误先原地补交；实质结果无效时才废弃该 session 并新开同角色 session。
  Writer、Blind Reader、Chapter Editor 与 Patch Writer 各自最多自动重试两次，
  互不占用预算。
- 请求模型、角色 frontmatter 和环境默认值都只是选择意图。正式记录必须使用宿主终态
  返回的 `resolvedModel`；若实际模型与请求不同，如实记录实际值，不得把偏好写成来源。
- 无法创建或等待真实独立角色时停止，只说明“本章未开始”。
- 创作任务中的 Lead 和角色不得创建、修改、修复、包装、安装或配置 Harness
  / SessionBackend；headless 缺失时不得自行设置命令桥或要求用户部署。
- `degraded_exploration` 只有用户明确要求探索稿时才允许；不得因工具受限自行降级，
  也不得把探索稿称为完成。
- Writer 规划阶段可做最多 5 次题材、事实边界和重名检索；不得借此阅读工作流源码。
- 默认 `formal_native` 使用外置 Capsule、零项目写入、全仓快照和 Guardian；
  宿主有真实 OS 沙箱时透明升级为 `formal_sandboxed`，不询问用户 A/B。

## 默认闭环
1. 启动时读取 `evaluation/harness-contract.json` 与
   `evaluation/guardian-contract.json`；原生遥测必须规范化为
   `novel-forge-runtime/v1`。
2. 用户要 1 章时运行 `begin-chapter-sequence --chapter-count 1`；用户要连续多章
   时按请求建立序列，但最多 4 章，五章及以上必须拆分。起草前确认
   `memory-status=clean`，并运行 `build-memory-context`。
3. 每次 launch directive 只允许当前一章。Lead 创建并等待新的原生 writer session，
   Claude Code 使用 `novel-forge-writer`；其他宿主使用语义等价的 Writer role。
   控制面立即 `claim-chapter-session`，再运行 `prepare-writer-capsule`，
   默认只交付仓库外 Capsule 并用全仓快照验证零项目写入；宿主有真实文件系统沙箱时
   透明升级为 capsule-only。
4. Guardian 按 `{FORMAL_WRITER_PROMPT_ID}` 编译短小的 `instructions.md`。Writer 只读
   capsule 内的 `instructions.md` 与 `handoff.md`，只写 `draft/正文.md`；确定性控制面
   在 capsule 外生成 runtime 与隔离证明，并用 `record-capsule-runtime` 写入外置
   Guardian sidecar。Writer 不接收完整 Skill、句长、段落长度、对白占比等数字目标，
   也不得照抄 Voice exemplar 的具体名词、动作、收束物件或句法骨架。handoff 只含
   过滤后的 Story Brief；完整 Scene Package 的决策审计只供 Chapter Editor 使用。
   Writer 的正式 `role_result` 只返回 capsule 内相对路径 `draft/正文.md`；宿主绝对
   路径由确定性控制面掌握，不要求角色发现或回报。
5. Writer 结束后运行 `ingest-writer-capsule`。额外脚本、路径逃逸、保护输入变化、
   隔离证明缺失或 session 不一致会把回执标成 `compromised`，当前 session 自动
   失效，必须 claim 新会话。一次集中 patch 使用预置当前正文的新 capsule；第三个
   潜在正文版本必须先由 `authorize-regeneration` 记录绑定当前章节、session 与
   前两份正文哈希的 author/human_delegate 签名授权，再引用其 authorization ID。
6. generation 绑定真实 writer `run_id`、`prompt_template_id` 与 `prompt_sha256`。
   每次模型响应后对累计快照运行 `session-audit`；返回
   `continue_allowed=false` 时在下一次请求前停机。
7. 结束时运行 `record-session-audit`；宿主观测优先于 Agent 自报。runtime、来源、
   质量、叙事或文学结构 gate 有 blocking 立即短路。
8. 在不同会话自动运行 blind-reader，再运行 chapter-editor；Claude Code 分别使用
   `novel-forge-blind-reader` 与 `novel-forge-chapter-editor`。Blind Reader 正式记录后才能启动 Chapter Editor。
   不得暂停询问是否开始审核。
   Python 为两角色分别封存仓库外 Review Capsule；动作不携带正文全文，Lead 只传
   Capsule 路径。Capsule 绑定当前正文及全部允许输入，篡改后自动换新审稿会话并
   从当前正式正文重新封存。
   无法创建独立审稿会话时返回机器状态 `review_session_required`，不得向用户抛出
   “要不要审核”一类开放式问题。blind-reader 检查控制面泄漏、整齐问答、职业证明和
   修补接缝；chapter-editor 每轮完整重审五项文学维度。两者只通过宿主正式结果通道
   返回结构化报告；控制面验证并落盘。结果丢失时只换新当前角色，不由 Lead 代填。
9. 同源 findings 合并成一个局部 patch，义务必须绑定位置、原文证据、读者效果和
   修订意图，不得直接增加解释段。第二份不同正文 SHA-256（第二份 generation）后
   仍有 MUST，退役 Patch Writer 并进入 `human_decision_required`；用户明确选择
   重新生成后才签发第三版授权。
10. 上一章完整 `ready` 后结束该 writer session，运行
   `advance-chapter-sequence`。只有返回 `launch_next_session=true` 才能按顺序
   创建下一章的新 session；不得提前并发起草。

## 成本边界
- 每章独立会话；跨章只传有界 handoff，不携带旧会话消息、旧工具输出和审稿全文。
- 一次只做一章；简短用户意图由 Guardian 编译成不超过 {MAX_FORMAL_WRITER_PROMPT_CHARS} 字符的正式提示词，
  不重复注入完整 Skill。
- Guardian 清单、哈希、预算和回执校验在本地执行，不占模型上下文；ACP 或完整
  transcript 不是 formal 依赖，也不得为审计而回灌给 writer。
- 2,000,000 cached-input tokens 是每章硬停止上限，不是应当吃满的目标。
- 正文一次完整 Write，最多一次集中 Edit；禁止边查 CJK 边连续补写。
- 规划和疑难因果核验可用 high；正文与默认审稿使用 standard/medium。
- Max 只处理被明确命名的困难问题，不用于整章自由生成、模板、状态或证据。
- 默认两角色；专业编辑只有 chapter-editor 指出具体风险时才调用一个。
- MAY 和 advisory 不触发额外生成；第三版必须等待用户明确选择。

## 回退
- 机器 blocking 或行文问题 → `drafted`。
- 因果/人物选择失效 → `scene_packaged`。
- Canon 冲突、覆盖风险、作者取舍或预算耗尽 → `blocked`。
- 用户明确要求探索稿且工具受限 → `degraded_exploration`，如实记录失败；
  自动生产请求不得走此回退。

## 不可绕过
{policy_lines}

- Formal writer 不得看到或修改 `books/` 控制面、验证器源码、evidence、状态文件或
  其他章节；宿主无法落实 capsule-only 文件系统时，自动生产必须停止。
- compromised capsule 必须废弃当前 session；不得在同一 session 中删除违规文件后
  重新导入，也不得由 writer 自己填写隔离证明或 Guardian 回执。
- 公开 `evidence/guardian-receipts/` 副本不能单独证明通过；必须匹配
  `.local-guardian/<slug>/` 的签名权威账本与 imported 控制记录。
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
    ".claude/agents/context-collector.md": (_agent_context_collector_md, ()),
    ".claude/agents/writer.md": (_agent_writer_md, ()),
    ".claude/agents/chapter-editor.md": (_agent_chapter_editor_md, ()),
    ".claude/agents/blind-reader.md": (_agent_blind_reader_md, ()),
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
    ".claude/agents",
]

# Files that `sync-tools` may refresh in existing books (managed, never
# hand-edited). Everything else is only created when missing.
SYNCABLE_FILES: tuple[str, ...] = (
    "tools/quality_check.py",
    "tools/narrative_gate.py",
    ".claude/agents/context-collector.md",
    ".claude/agents/writer.md",
    ".claude/agents/chapter-editor.md",
    ".claude/agents/blind-reader.md",
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

    local_git = initialize_book_git(root, slug, title.strip())
    return {
        "book_dir": str(book_dir),
        "created_directories": created_dirs,
        "created_files": created_files,
        "skipped_files": skipped_files,
        "local_git": local_git,
    }
