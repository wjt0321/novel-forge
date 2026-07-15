# Novel Forge Skill Interface

## 用途

本 Skill 用于驱动 `D:\s-black-novel`（Novel Forge）的受限 JSON adapter，完成自主研究 → 故事发动机 → 场景计划 → 分场起草 → 独立审稿 → 迭代修订的受控循环。**不得直接操作 SQLite 或 `library/` 下的 revision 文件。**

## 硬边界

- 禁止直接修改 `data/novel-forge.db` 或 `library/<slug>/manuscript/revisions/` 下的任何文件。
- 禁止让写作 Agent 自审自放行；独立编辑身份固定为 `independent_reader_editor`。
- 禁止模仿在世作家风格；只使用文学技法卡，记录“技法”而非仿写。
- 正文（>=5000 中文汉字）必须通过 `write-revision` 提交；禁止伪造人类最终批准。
- 自动验收通过结果只能是 `autonomous_acceptance_complete`，不是文学/市场保证，也不是最终发布许可。
- 自主循环最多 3 轮；到上限仍未通过必须输出 `failed_needs_human`。

## 调用入口

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root <ABSOLUTE_ROOT> <operation> ...
```

`--root` 必须是绝对路径。所有 stdout 为 JSON；traceback 只应出现在未预期错误时。

## 常用命令

### 只读/诊断（无需 `--confirm`）

```bash
status <slug>
status <slug> <chapter-number>
check-acceptance <slug> <chapter-number> [--max-rounds 3]
list-research <slug>
get-story-engine <slug>
get-chapter-plan <slug> <number>
list-promises <slug>
list-iterations <slug> <number>
```

### 变更操作（必须 `--confirm <operation>`）

```bash
add-research-entry <slug> --url URL --retrieved-at ISO --source-type official|academic|news|other --confidence A|B|C --claim "..." --allowed-use plot_support|background_only|fiction_seed --fiction-boundary "..." [--verification-state collected|verified|unresolved] [--verification-ref ID] [--unresolved] [--notes]

update-research-entry <slug> <entry_id> [--verification-state collected|verified|unresolved] [--verification-ref ID]

set-story-engine <slug> --secret "..." --desire "..." --alternative-actions a1 a2 ... --irreversible-choice "..." --immediate-cost "..." --thematic-pressure "..."

set-chapter-plan <slug> <number> --plan-file ABS.json [--status draft|approved_for_writing]

update-promise <slug> <promise_id> --status advanced|resolved|abandoned --scene-ref REF [--note]

record-iteration <slug> <number> --writer-role ROLE --editor-verdict revision_required|ready_for_human_editor_decision --blocking-issues-file ABS.json --revision-targets t1 t2 ... --word-count N [--status running|completed|failed]

git-checkpoint <slug> --message "..."
```

### 第二～五里程碑与质量链重构（P0–P4）相关命令

- `init-workspace <slug>` / `refresh-workspace <slug>`：生成/刷新 `<root>/work/<slug>/` 人类可读目录入口（README/CURRENT/manuscript 镜像等）。
- `write-revision-patch <slug> <number> --patch-file ABS.json`：对当前 revision 做精确定位替换，生成新 revision；不直接修改 library。

参见 `docs/04-operations-and-backup.md`、`docs/11-autonomous-research-writing-chain.md`、`docs/12-quality-chain-reconstruction.md`。

## 输入文件规范

- `--plan-file`：JSON 数组，每个元素为 scene object，必须含 `scene_ref`、`goal`、`obstacle`、`choice`、`cost`、`ending_change`，可选 `promises`。
- `--blocking-issues-file`：JSON 数组，每个元素必须含 `location`、`evidence`、`effect`、`revision_intent`。
- `--patch-file`：JSON 数组，每个元素必须含 `location`、`evidence`（唯一匹配）、`replacement`、`reason`。
- 所有外部输入文件必须：绝对路径、有效 UTF-8（允许 BOM）、不在 `<root>/library/` 内。

## JSON 输出契约

成功：

```json
{"ok": true, "operation": "...", "state_changed": true|false, "data": {...}}
```

可预期业务失败：

```json
{"ok": false, "error": {"code": "confirmation_required|business_error|invalid_arguments|invalid_root", "message": "..."}}
```

**data 中不会包含正文全文、Voice Bible 全文、Scene Contract 全文、Editorial Memo 全文或写作包全文。** `list-research` 返回研究条目字段，但 Skill 不应把这些原始 claim 直接粘贴到公开输出。

## 推荐自主循环

1. **研究**：`add-research-entry` 建立 Research Ledger；B/C 级 `plot_support` 必须绑定一条 `verified` A 级 `plot_support` 佐证，否则不得作为唯一关键情节支点。
2. **故事发动机**：`set-story-engine` 定义 secret / desire / irreversible choice / cost / thematic pressure。
3. **章节计划**：`set-chapter-plan` 创建 4–6 场景的 plan；记录 `promises`。
4. **写作包**：`build-drafting-packet` 生成外部 Markdown 上下文包给写作 Agent；不修改 library。
5. **起草**：外部 Agent 按包写场景，输出独立 Markdown，再用 `write-revision` 提交。
6. **审稿**：`lint`、`add-reader-review`、`submit-editorial-memo`。
7. **迭代**：如未通过，`record-iteration` 记录本轮 verdict、blocking issues、revision targets；`writer_role` 不得为 `independent_reader_editor`。
8. **局部修订**：对定位明确的校对/语言问题，可用 `write-revision-patch` 生成新 revision；仍需重新 lint/review/memo。
9. **验收**：`check-acceptance`；通过则 `autonomous_acceptance_complete`，否则继续修订或 3 轮后 `failed_needs_human`。
10. **检查点**：每轮/每场后 `git-checkpoint`，只 stage `library/<slug>/` 与 `docs/<slug>/`。
11. **目录入口**：用 `init-workspace` / `refresh-workspace` 维护 `<root>/work/<slug>/` 的人类可读索引。

## 已知限制

- `check-acceptance` 只检查流程覆盖度与可验证语言/校对层，不评判文学性。
- P1 lint 是表面模式匹配，可能误报，不能替代人工校对。
- 不实现真实 LLM 调用或联网抓取；Skill 需自行调度外部模型。
- 不实现删除；所有历史保留审计。

## 参考文档

- `docs/11-autonomous-research-writing-chain.md`
- `docs/04-operations-and-backup.md`
- `docs/07-database-migration.md`
- `docs/12-quality-chain-reconstruction.md`
