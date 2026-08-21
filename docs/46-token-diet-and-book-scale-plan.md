# 46. Token 精简与全书尺度质量路线图

> 创建：2026-08-21。本文档是**压缩上下文后重新开始的执行入口**。
> 背景：docs/44 记录了 2026-08-21 的三轮已完成工作（代码审查修复、遗留项收尾、
> 风格语料库 style-corpus/v1）。本文档只写**接下来要做的事**。

## 0. 新会话必读

- `AGENTS.md`（全部规则继续适用；`publication_eligibility` 恒 False）
- `docs/43-fiction-first-lean-native-workflow.md`（日常流程唯一默认路径）
- `docs/44-current-workflow-logic-audit.md` 末尾三个 2026-08-21 小节（近期变更）
- 改状态机/门禁/提示词/recovery 必须补回归测试；先定向测试再全量；
  从根目录 `PYTHONPATH='.'; python -m pytest tests -q`

## Part A：Token 精简（实测数据驱动）

### 实测基线（2026-08-21）

| 消耗点 | 现值 | 说明 |
|---|---|---|
| 交接包总预算 | **28,000 字符/章** | `MAX_HANDOFF_TOTAL_CHARS`，最大单点开销 |
| ├ 场景包 | 8,000 | `MAX_HANDOFF_SCENE_PACKAGE_CHARS` |
| ├ Canon/记忆 | 12,000 | `MAX_HANDOFF_MEMORY_CHARS` |
| ├ 上章尾部 | 1,600 | |
| └ 声音范文 | 1,200 | |
| strict 规划动作卡 | 内嵌 story-engine + voice-bible **全文** | `workflow.py::_planning_context` 直接 read_text 整个文件；voice-bible 现 5,138 字符 |
| 审稿 canon 摘要 | 12,000 字符 | `native_relay.py` `canon_context_digest(max_chars=12000)` |
| voice-bible 模板 | 5,138 字符 | 其中语料两节约 2,200（style-corpus 渲染 1500+1200 截断后） |
| Writer 固定提示词 | 702（draft）/ 382+指令（patch） | 已经很紧，**不动** |
| 审稿固定提示词 | 933–1,160 | 已经很紧 |
| Writer P0/P1/P2 包 | 1500/850/450 CJK | 已经很紧 |

### A1. 交接包预算分级收紧（优先级最高，纯减法）

- `planning_spec.py` 是唯一单源。建议目标：total 28k→**14k**，memory 12k→**6k**，
  scene 8k→**5k**；tail/exemplar 不动。
- 进阶（可选）：按 `chapter_risk` 分档——喘息章/过渡章用更低预算，
  volume_start/major_turn 用足额。加 `HANDOFF_BUDGETS_BY_RISK` dict。
- 回归：现有 handoff 相关测试逐个核对截断断言；新增预算常量单源测试
  （防止有人再复制数字）。

### A2. strict 规划卡去内嵌全文

- `_planning_context`（workflow.py:1231）把 story-engine.md 与 voice-bible.md
  **整文件**塞进动作卡。改为：
  - story-engine：只嵌「核心秘密/欲望/阻力/代价」四节的 `extract_markdown_sections`
    结果（复用 literary_texture 或 book_gates.section 的既有工具）；
  - voice-bible：只嵌 `narrative_distance`、`focalization`、`硬禁令`、
    `角色语言指纹` 四节 + 语料两节的**书内采纳子集**（见 A3）；
  - 卡上同时保留文件路径（角色确需全文时由宿主按路径读，走 allowed reads）。
- lean 路径不受影响（已是文件引用制）。

### A3. 语料两节的常驻成本

- 现状：正例基因 1,055 + 反例清单 1,066 字符随模板进入每本书的 voice-bible，
  进而进入规划上下文。
- 推荐方案：voice-bible 里两节改为**「本书采纳的基因」勾选表**（空表 + 指引），
  全量语料移到独立生成文件 `memory/style-reference.md`（init 时生成一次，
  作者/编辑按需读，不进常规上下文）。
- 备选（更省事）：直接调低渲染预算 `render_positive_genes_brief(900)` /
  `render_ai_tells_brief(700)`。效果打折但改动最小。
- 注意：无论哪种，`tests/test_style_corpus.py::test_voice_bible_template_embeds_both_corpus_sections`
  要同步改；且不得破坏 exemplar_notes 的下划线回填锚（教训见 docs/44 2026-08-21（三））。

### A4. 审稿 canon 摘要降额试验

- 12,000 → **6,000** 先行试运行一本书，对比 Chapter Editor 结论质量
  （用 cost-summary 与审稿 MUST 数量做前后对照），无明显退化再固化。

### A5. 规则文本去重审计（清理类，放最后）

- 同一思想多处复述：`LITERARY_MICRO_RULES` / `HUMAN_NARRATIVE_POLICIES` /
  `MECHANISM_CLAUSES` / voice-bible 各节 / `review_prompt` 边界文案 /
  `writer_prompt.literary_boundary`。
- 目标：每个角色一份单一渲染源，重叠段落只在一处定义、他处引用编号。
- 做法：先写映射表（哪段文字出现在哪些文件），再逐条合并；全程快照测试
  锁定渲染输出，防漂移。

## Part B：全书尺度三特性

### B1. 跨章重复检测（最先做；与 book_memory 索引最顺路）

- 问题：AI 味在成书尺度最大破绽是跨章自我重复（同一比喻/情绪节拍/句式骨架
  在 ch10 与 ch40 重现），单章审稿不可见。
- 设计：
  - 新模块 `app/novel_forge/book_repeat.py`（或并入 literary_texture，倾向独立）；
  - 对 `chapters/e*/ch-*/正文.md` 晋升正文建指纹：CJK 2-6 gram 集合 +
    比喻句抽取（复用 lint._SIMILE_RE）+ 章末句签名；
  - 新章暂存正文在双审前比对已晋升章节，命中输出 advisory 样本
    （哪一章哪个片段重复），进 Chapter Editor `machine_diagnostics` 抽样；
  - 白名单：人物名、voice-bible 登记的口头禅/母题（合法复现）。
- 接入点：`run_gates` literary 部分 or native_relay 双审前预检（二选一，
  倾向前者——门禁单源）；**advisory only**，不构成 blocking。
- 测试：两章共享比喻句 → 检出并指认章节；仅人名重合 → 不报。

### B2. 人物弧线账本（体量最大，放后）

- 问题：有 per-chapter 私人欲望，无跨章变化追踪；文学性核心是“人被经历改变”。
- 设计（仿 canon 的 Markdown 单源 + candidate/promotion 两段式）：
  - 位置 `books/<slug>/planning/arcs/<character>.md`；
  - 每条弧线：信念起点 → 动摇事件(章) → 代价 → 改变(章) → 当前位置；
  - scene package 模板 ch02+ 增加「弧线位置」字段（本章该人物处于哪一格），
    `check_scene_package` 增加对应非阻塞检查；
  - Chapter Editor 通过后 Python 提示弧线 candidate 更新，作者 promotion
    （复用 book_memory 的 candidate/promotion 机制与索引）。
- 测试：账本解析/晋升/索引重建；scene package 缺弧线位置的提示。

### B3. 声音锚定策略（成本低见效快）

- 问题：范文自举自上一章，全书可一起温水煮青蛙式漂移而检测永远通过。
- 设计：
  - voice-bible `exemplar_notes` 支持「锚定章」标记行（如 `anchor: ch03,ch07`）；
  - `voice_signature` 对比对象从“上一章”改为“锚定章集合”（无标记时退回现状）；
  - 每 10 章或 `approve-high-risk` 时提醒作者复核锚（进 decision 卡提示文案即可）；
  - 冷启动：`memory/voice-seed.md`（作者手写 300-500 字），ch01 前作为初始锚。
- 测试：有 anchor 标记时 drift 对比目标变化；seed 存在时 ch01 使用 seed。

## Part C：执行顺序与护栏

```
A1 交接包预算收紧 ──► A2 规划卡去内嵌 ──► B1 跨章重复检测 ──► B3 声音锚定 ──► B2 弧线账本 ──► A4 canon 降额试验 ──► A5 规则文本去重
```

- 每步：定向测试 → 全量 `pytest tests -q` → 行为变化记入 docs/44 日期小节。
- 预算数值改动必须留在 planning_spec 单源；禁止任何模板/工具复制数字。
- `writer_prompt` 总预算（1200）与 P0/P1/P2 不在本轮范围内动；若要动，
  必须先做作者小样校准（approve-writer-model 同等级别的显式决策）。
- 完成一批后更新本文件的 checklist 并考虑归档耐久结论到 docs/archive/history.md。

### Checklist

- [ ] A1 交接包预算收紧（+风险分档可选）
- [ ] A2 strict 规划卡去内嵌全文
- [ ] A3 语料两节常驻成本优化（推荐拆 style-reference.md）
- [ ] B1 跨章重复检测（book_repeat.py + 门禁接入 + 白名单）
- [ ] B3 声音锚定策略（anchor 标记 + voice-seed 冷启动）
- [ ] B2 人物弧线账本（arcs/*.md + scene package 字段 + promotion）
- [ ] A4 canon 摘要 12k→6k 试验
- [ ] A5 规则文本去重审计
