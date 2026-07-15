# 11 - 自主研究写作链（Autonomous Research-to-Fiction Chain）

## 目标

第六里程碑为 Novel Forge 增加可审计的**自主研究 → 故事发动机 → 场景计划 → 分场起草 → 独立审稿 → 迭代修订**链路。它不改变底层 revision/审批状态机，而是给 Skill 提供受限、可追踪的上下文与验收入口。

核心约束：

- 不自动调用 LLM 写正文；所有正文仍由人类或外部写作 Agent 通过 `write-revision` 提交。
- 不承诺文学质量或市场表现；自动验收通过 `autonomous_acceptance_complete` 只意味着“流程覆盖度达标，可进入可选人类审阅或正常 export 流程”，不是最终发布许可，也不保证文学价值。
- 研究事实必须有可复核来源；B/C 级 `plot_support` 必须绑定一条 `verified` A 级 `plot_support` 佐证，否则不能作为关键情节支点。
- 正式短篇硬门槛：**5000 个中文汉字（CJK Han）以上**，且至少 **4–6 个场景**。
- 自主循环最多 **3 轮**；仍未通过则标记 `failed_needs_human`，不得伪造通过。

## 数据模型

### Research Ledger（按书隔离）

`research_entries` 记录每条研究声明：

- `url`：来源地址
- `retrieved_at`：检索时间
- `source_type`：`official` / `academic` / `news` / `other`
- `confidence`：`A` / `B` / `C`
- `claim`：事实陈述
- `allowed_use`：`plot_support` / `background_only` / `fiction_seed`
- `fiction_boundary`：事实与虚构的边界说明
- `unresolved`：是否未解决
- `verification_state`：`collected` / `verified` / `unresolved`
- `verification_ref`：指向同书 A 级 `verified` `plot_support` 条目的 ID，用于 B/C 级声明的佐证

`allowed_use=plot_support` 且 `unresolved=true` 会阻止 `check-acceptance` 通过。
B/C 级 `plot_support` 若无 `verification_ref` 指向 verified A 级 `plot_support`，同样阻止通过。

### Story Engine（书级）

`story_engines` 记录核心叙事张力：

- `secret`：主角或世界的核心秘密
- `desire`：主角欲望
- `alternative_actions`：至少一个替代行动
- `irreversible_choice`：不可逆选择
- `immediate_cost`：即时代价
- `thematic_pressure`：主题压力

### Chapter Plan（章级）

`chapter_plans` 存储 4–6 个场景的 JSON：

- `scene_ref`：场景引用
- `goal`：场景目标
- `obstacle`：阻力
- `choice`：选择
- `cost`：代价
- `ending_change`：结尾变化
- `promises`：可选，本场景埋下的叙事承诺

### Promise Ledger（书级）

`promise_ledger` 追踪叙事承诺生命周期：

- `planted` → `advanced` / `resolved` / `abandoned`
- 每个承诺必须带 `promise_text` 与 `planted_scene_ref`

### Iteration Runs（章级）

`iteration_runs` 记录每一轮“写 → 独立编辑 → 修订目标”：

- `round_number`：自动递增
- `writer_role`：写手身份
- `editor_role`：固定为 `independent_reader_editor`，不得冒充真人
- `editor_verdict`：`revision_required` / `ready_for_human_editor_decision`
- `blocking_issues`：JSON 数组，每项含 `location` / `evidence` / `effect` / `revision_intent`
- `revision_targets`：修订目标列表
- `word_count`：本轮正文字数（CJK Han 计数）
- `status`：`running` / `completed` / `failed`

## 自动验收门 `check-acceptance`

覆盖检查：

1. 存在 chapter plan 且 4–6 场景
2. 当前 revision 存在
3. 当前 revision 正文 >= 5000 个 CJK Han
4. 无未解决的 `plot_support` 研究
5. 所有 promise 已 `resolved` 或 `abandoned`
6. 当前 revision 有 active editorial memo，verdict 为 `ready_for_editor_decision`，且无 blocking issues
7. 当前 revision 无 blocking lint、无未关闭 S1/S2 review finding / reader review
8. 迭代轮次 < `max_rounds`

结果：

- 全部通过 → `autonomous_acceptance_complete`
- 未通过但轮次未超限 → `revision_required`
- 达到最大轮次仍未通过 → `failed_needs_human`

## Skill Adapter 命令

所有命令通过受限 JSON adapter 访问，禁止直接操作 SQLite 或 revision 文件。

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root D:\my-novel <operation> ...
```

只读/诊断：

- `list-research <slug>`
- `get-story-engine <slug>`
- `get-chapter-plan <slug> <number>`
- `list-promises <slug>`
- `list-iterations <slug> <number>`
- `check-acceptance <slug> <number> [--max-rounds N]`

变更操作（均需 `--confirm <operation>`）：

- `add-research-entry <slug> --url ... --retrieved-at ... --source-type ... --confidence ... --claim ... --allowed-use ... --fiction-boundary ... [--verification-state collected|verified|unresolved] [--verification-ref ID] [--unresolved] [--notes]`
- `update-research-entry <slug> <entry_id> [--verification-state ...] [--verification-ref ID]`
- `set-story-engine <slug> --secret ... --desire ... --alternative-actions a1 a2 ... --irreversible-choice ... --immediate-cost ... --thematic-pressure ...`
- `set-chapter-plan <slug> <number> --plan-file ABS.json [--status draft|approved_for_writing]`
- `update-promise <slug> <promise_id> --status advanced|resolved|abandoned --scene-ref ... [--note ...]`
- `record-iteration <slug> <number> --writer-role ... --editor-verdict ... --blocking-issues-file ABS.json --revision-targets t1 t2 ... --word-count N [--status running|completed|failed]`
- `git-checkpoint <slug> --message "..."`

`--plan-file` 与 `--blocking-issues-file` 必须是绝对路径、有效 UTF-8、且不得位于 `<root>/library/` 内。

## CLI 等价命令

```bash
python -m novel_forge.cli add-research-entry my-novel --url ... --claim ...
python -m novel_forge.cli set-story-engine my-novel --secret ... --desire ...
python -m novel_forge.cli set-chapter-plan my-novel 1 --plan-file plan.json
python -m novel_forge.cli check-acceptance my-novel 1
python -m novel_forge.cli git-checkpoint my-novel --message "draft scene 1"
```

## Git 检查点

`git-checkpoint` 只 stage `library/<slug>/` 与存在的 `docs/<slug>/`，不触碰 `data/`、全局 `docs/` 或外部产物。它用于在 Skill 自主循环中给每场/每轮留下可追踪的 diff，而不是替代人类提交。

## 限制

- 不自动写正文；写作 Agent 仍需生成独立 Markdown 并通过 `write-revision` 提交。
- 不自动判断文学性；`autonomous_acceptance_complete` 只是流程覆盖度门槛。
- 不联网抓取；`add-research-entry` 需要调用方提供来源 URL 与检索时间。
- 循环上限 3 轮，到上限必须显式 FAILED/NEEDS_HUMAN。
