# 47. 迭代提案与实施记录：46 复盘卡点修复与代码审查意见

日期：2026-08-02

状态：**全部实施完成（P0/P1/P2 + 文末下一轮意见 P1--P3，703 个测试全绿）；下一轮迭代意见见文末**

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

## 下一轮迭代意见（2026-08-02 已全部实施）

### P1：双审并行化（已实施）

Blind Reader 与 Chapter Editor 并行签发（`awaiting_double_review` 阶段 + 两张角色卡 + `pending/completed/issued` 队列），可并行委派、完成顺序不限，Editor 在无 Blind 结论时独立审稿（`blind_review` 降级为可选输入）。恢复路径按 `failed_review_role` 重排失败角色。strict_audit 保持串行。

### P2：引文校验性能（已实施）

`_quote_matches` 失败定位改为按引文种子（20/8/4/2/1 字）`find` 定位再算最长匹配，避免全文 O(n×m) 扫描。

### P2：决策文案覆盖一致性（已实施）

所有进入 `decision_required` 的分支（native_role_failed、surface_revision_required、hard_budget_reached、exploration_only、high_risk、续修类）都写 `decision_message`；`next-action` 卡与 `status` 共用 `_decision_message` 生成，文案一致。

### P3：strict_audit 模式的续修入口（已实施）

`orchestrator.authorize_revision` 提供 strict 模式对称入口（校验决策种类、记录 author 决策、`require_body_history=False` 续修）；`relay.authorize_revision` 在 strict 下转调。

### P3：选项字母规划（已满足）

决策选项 A–G 全部集中在 `_decision_options`；后续新增种类在此扩展，不散落各分支。

## 附加修复（实施中由用户指出）

- **正文保留**：`draft/正文.md` 在晋升前永不清除。`_reset_writer_capsule_dir` 只清理可再生成辅助文件；guardian `prepare_writer_capsule` 允许 capsule 只保留既有正文；技术重试/重新生成不再丢正文。
- 角色卡哈希（`role_card_sha256`）与动作 ID 一致性校验，控制面自管路径（state.json、native-relay、authorizations、session-completions、workflow-observations）排除快照对比但不放行篡改。

## 不做的事（明确记录）

- 不实现实体-归属共现启发式一致性检测器（46 号 K5 建议）：系统只验证流程与可定位证据，不认证文学价值；启发式误报风险高于收益。位置/归属矛盾由审稿 instructions 引导标 `scope=local` 走既有局部 Patch 路径。
- 不把 `authorize-revision` 扩展为无限重试：每轮续修后仍进入人工决策，保留作者最终决定权。

## 2026-08-02 第二轮审查修复（独立子代理实测复现）

1. **H1**：recover 跨角色重写主卡导致另一角色完成校验误报控制面篡改、恢复路由错误角色。修复：并行 recover/repair 不写主卡（write_primary=False）；主卡保留快照检测；其他角色的 review capsule 管理路径视为合法变化。
2. **H2**：`failed_review_role` 残留导致后续 recover 重签错误角色。修复：recover 消费后立即清除。
3. **M1**：乱序完成时队列头 fallback 错绑角色。修复：fallback 改为"最后领取（issued 末尾）的未完成角色"；`issued_review_roles` 保持领取顺序（不再排序）。
4. **M2**：并行角色结果文件缺失 = 死胡同。修复：complete_minimal 并行阶段结果缺失自动走 recover 重签该角色。
5. **L2**：repair 计数键用主卡导致漂移。修复：并行时用被修复角色卡的真实 action_id。
6. 审查结论：**无无限循环缺陷**（所有自动重试被 `max_technical_retries` 与用户决策严格有界）。
