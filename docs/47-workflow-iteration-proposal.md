# 47. 迭代提案与实施记录：46 复盘卡点修复与代码审查意见

日期：2026-08-02

状态：**已实施（P0/P1/P2 全部完成，701 个测试全绿）；下节供 48 号迭代评估**

范围：46 号复盘卡点已按"47 号迭代"完成实施（authorize-revision 官方命令、lean 授权、决策选项可达性、冻结稿改名、引文模糊校验），并在实施后由独立子代理对全部改动做了一次隔离上下文审查。本文记录审查发现、已修复项与下一轮迭代意见。

## 46 复盘实施回顾（已完成）

- **K1/K2/K7**：`authorize-revision <slug> --reference <依据>` 官方命令记录 author 决策并恢复一次集中修订 + 完整双审；`retry` 在 lean 下通过 `authorize_regeneration(require_body_history=False)` 走出 receipts 死锁；决策选项由 Python 按可达性生成；`next-action` 返回 `user_decision` 卡；`complete-role` 在决策期被拒。
- **K3**：冻结稿改名 `控制面冻结稿.md`；Writer 动作携带 `read_only_project_files`；控制面变异失败消息给出唯一允许写入路径。
- **K4**：`_quote_matches` 模糊引文校验（精确 → 规范化 → 前缀+容差 → 失败定位）。
- **K5/K8**：审稿提示词引导一致性 MUST 标 `scope=local` 走局部 Patch；决策消息携带修订轮次与"将再跑一轮 Writer + 完整双审"提示。

## 子代理审查发现与已修复项

独立审查共发现 7 类问题，全部修复并有回归测试（696 个测试全绿后新增 7 个回归用例，全量重跑通过）：

| # | 问题 | 严重度 | 修复 |
|---|---|---|---|
| F1 | `local_patch_hard_gate_failed` 决策下 `authorize-revision` 把旧局部 Patch 指令当 MUST，真实阻塞 lint 发现丢失 | 高 | 决策点把 `surface_findings` 写入 relay state 的 `must_findings` |
| F2 | `_quote_matches` 前缀容差恒真比较，引文尾部完全不校验 | 中 | 改为窗口内逐字差异计数 ≤ 15 |
| F3 | `retry` 重新生成不清理 `must_findings`/`patch_round`，技术恢复把"重新生成"误路由为陈旧 MUST 的 patch | 中 | 重新生成分支显式清理两个字段 |
| F4 | `decision_message` 未写入 relay state，`next-action`/`status` 显示兜底文案且两处不一致 | 低 | 决策分支写 `decision_message`；`_decision_message` 统一生成（含轮次提示） |
| F5 | `patch_round` 硬编码为 1，轮次计数不递增 | 低 | 两处 lean 修订入口改为递增 |
| F6 | 非修订类决策（hard_budget/high-risk/calibration）的 B 选项变为可执行的未记账旁路，官方命令不在选项中 | 低 | `_decision_options` 按决策种类生成专属选项（E/F/G） |
| F7 | README/docs 遗留 `初稿.md` 旧名 | 低 | 全部替换为 `控制面冻结稿.md` |

**审查结论**：无无限循环缺陷。所有机器驱动循环均有界（surface patch 3 轮、技术重试 `max_technical_retries`、补交修复按 action_id 计数）；authorize-revision 每轮都回到人工决策，不是自动回炉。`user_decision` 新 kind 在所有 `next_action` 调用点（complete_minimal 前置守卫、complete_role 按 phase 分发、恢复路径）都有 phase 门控，不会被误当角色动作。

## 下一轮（48 号）迭代意见

### P1：双审并行化（46 号 K6，正式评估）

Blind Reader 与 Chapter Editor 当前串行（Editor 依赖 Blind 结果）。并行化可把每轮双审时间减半，但需要：

- 状态机改造：`awaiting_blind_reader` 与 `awaiting_chapter_editor` 合并为可并行阶段，动作卡同时签发两个角色；
- Editor 无 Blind 结果时的语义定义（独立审稿 vs 保留依赖）；
- 恢复矩阵同步更新（Editor 运输失败时 Blind 已完成的组合态）；
- `_complete_staged_review` 的合流逻辑（两个结果都到齐才进入 MUST 合并）。

建议独立评估后决定；若实施，测试面约为本次迭代的两倍。

### P2：引文校验性能

`_quote_matches` 失败路径的最长公共前缀扫描是 O(n×m)（正文 1 万字 × 引文长度），每轮审稿失败都要全扫。可优化为：先只扫描 probe（前 20 字）附近窗口，命中即止；或对规范化正文做一次索引（KMP/`find` 分段）。

### P2：决策文案覆盖一致性

`decision_message` 已写入 `literary_revision_required` 与 `local_patch_hard_gate_failed` 两类决策；`native_role_failed`、`surface_revision_required`、`hard_budget_reached`、`exploration_only` 仍走兜底文案。下一轮可统一：所有进入 `decision_required` 的分支都写 `decision_message`，使 `next-action` 卡与 `status` 永远一致。

### P3：strict_audit 模式的续修入口

`authorize_revision` 走 `_request_staged_literary_patch`（lean 动作）；strict 模式由 legacy orchestrator 的 `retry`（已支持 `require_body_history=False`）兜底，但 strict 下没有与 `authorize-revision` 对称的官方命令。审计/基准场景若需要，可为 strict 模式补对应入口。

### P3：选项字母规划

决策选项现覆盖 A–G（保留/重生成/停止/续修/预算/高风险/校准）。若未来新增决策种类，选项字母与文案集中在 `_decision_options`，避免各分支自造文案。

## 不做的事（明确记录）

- 不实现实体-归属共现启发式一致性检测器（46 号 K5 建议）：系统只验证流程与可定位证据，不认证文学价值；启发式误报风险高于收益。位置/归属矛盾由审稿 instructions 引导标 `scope=local` 走既有局部 Patch 路径。
- 不把 `authorize-revision` 扩展为无限重试：每轮续修后仍进入人工决策，保留作者最终决定权。
