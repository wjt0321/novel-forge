# 46. 《敛骨人》第一章生产卡点复盘与迭代建议

日期：2026-08-02

状态：**复盘记录；P0/P1/P2 卡点已于 2026-08-02 实施并修复（见 `47-workflow-iteration-proposal.md`）**

范围：本次以默认 `lean_native` 工作流生产《敛骨人》（slug: `liangu`）第一章，最终因"1 个多小时未完成一章"由作者中止并删除该书。本文只记录实际遇到的控制面与流程卡点，不评价文学质量；所有现象均来自本次会话真实发生的事件。

## 背景

- 书籍：《敛骨人》，都市灵异·悬疑·逆袭，第一章《数到九》。
- 过程：`start → Writer(初稿) → Blind Reader(第一轮 MUST) → Chapter Editor(确认 MUST) → Writer(v2 修订) → Blind Reader(第二轮 MUST) → Chapter Editor(确认 MUST) → decision_required → 用户选择"再修一次" → 控制面不可行 → 用户豁免 state.json phase 字段 → python -c 调用 `_request_staged_literary_patch` 恢复修订流程 → Writer(v3 修订，成功回传) → 第三轮 Blind Reader 未执行即中止。
- 总耗时：约 1 小时 20 分，第一章仍未 ready。

## 卡点清单

### K1. decision_required 的三个选项全部不可行（核心死锁）

**现象**：第二版仍有 MUST 时进入 `decision_required`，用户看到 A/B/C 三个选项：

- A（保留草稿）：只保留当前草稿，不晋升 ready —— 用户的目标是"修完晋升"；
- B（重新生成 = retry）：CLI 执行 `retry` → `GuardianError`：第三版需要 `human_regeneration_authorized` 签名，而 guardian 检查 `len(prior_body_sha256) < 2`（依赖 receipts，lean 模式不写 receipt，当前 0 个）→ **永远失败**；
- C（停止任务）。

**根因**：两条设计规则自相矛盾：

1. 规则"第二版仍有 MUST 时停止自动回炉，让用户选择"（宪法闭环第 6 条、SKILL 停止点）；
2. 规则"第三个不同正文版本必须 `authorize-regeneration`，且以 receipts ≥ 2 为门槛"。

lean 模式不写 receipt，导致规则 2 的门槛永远无法满足 → 规则 1 给出的所有出路中"继续修"这条必然失败。**decision_required 没有提供任何一条通往"修复后晋升"的可行路径。**

**影响**：流程死锁；用户被迫做越权操作（豁免状态文件）绕过控制面，或用 python -c 直接调用内部函数恢复流程。

**建议**：
- `decision_required` 增加 D 选项："作者授权一次集中修订后重新双审"（语义 = 有 MUST 的续修，不是无限 retry，不触发 regeneration 门槛）；
- lean 模式在"作者明确授权"时直接允许第三版，`authorize-regeneration` 的 receipt 门槛仅适用于无 author 签名的自动重试；
- 或者：在 author 授权时写入轻量 receipt（lean receipt，不含遥测），使门槛可满足且语义一致。

### K2. 授权机制语义与"再修一次"用户预期不符

**现象**：AskUserQuestion 给出"再修一次（推荐）"选项且用户选择后，控制面立即报告不可行，用户被迫重新选择，白费一轮交互。

**根因**：UI 选项（继续修）与状态机实际能力（第三版必须授权且授权必然失败）不一致；选项未按当前状态机可达性渲染。

**建议**：决策选项由 Python 按当前状态机可达性生成（`next-action` 的决策分支直接列出可行动作），Lead/宿主只渲染、不发明选项。

### K3. Writer 写错文件触发 control_plane_mutation

**现象**：第三轮 Writer 把修订写到 `diff/ch01/初稿.md`（控制面冻结稿）而不是 `diff/ch01/writer/draft/正文.md` → `complete-role` 失败（`failure_reason=control_plane_mutation`），冻结稿被自动恢复、目标文件被清理。换新会话明确"初稿.md 只读、只写 draft/正文.md"后才成功。

**根因**：
- `初稿.md` 文件名语义误导：它是"冻结的正式稿"，名字却像"草稿"，Writer 模型自然认为修订目标是它；
- 动作卡没有显式标注"哪些文件只读、唯一可写文件是哪个"；
- 失败信息只报 `control_plane_mutation`，没有指出"应写 writer/draft/正文.md"。

**建议**：
- 冻结稿改名（如 `控制面冻结稿.md`），或动作卡明确列出"只读文件：初稿.md；唯一可写：writer/draft/正文.md"；
- `_verify_workspace` 失败时在错误消息中给出应写目标路径，减少盲目重试。

### K4. Blind Reader 引文逐字校验过严，反复失败

**现象**：两轮双审共 4 个审稿会话，多处因 `evidence_quote` 未逐字匹配 prose 原文被拒，需换新会话重试；最严重的一次一个角色失败两次。

**根因**：逐字校验对长句（含引号、标点、双引号嵌套）要求模型精确复现完整句段，模型倾向于改写或截断；失败后错误信息不明确，Lead 只能猜着重试。

**建议**：
- 校验降级：去除空白/标点后比对，或"前缀 20 字 + 长度容差"模糊匹配；
- 失败时返回第一个不匹配字符的位置与期望/实际片段；
- 审稿 instructions 提供"从 prose.md 复制"的机械性引导（角色打开文件后直接复制，不凭记忆写引文）。

### K5. 两轮 MUST 均为"物件位置/归属矛盾"，本可更早拦截

**现象**：第一轮 MUST：蛋糕归属矛盾（三处给弟弟、三处给小念自己）；第二轮 MUST：七号柜位置矛盾（"化妆间开柜" vs "太平间冷柜"，两处"钟"字封条同柜）。均需整章双审重跑 + Writer 整章集中修订。

**根因**：这类"同一物件在多处的位置/归属不一致"是确定性可检测的低级矛盾，却走完全量双审 + 整章修订的重型通道。

**建议**：
- 双审前加轻量一致性核对脚本：抽取关键实体（柜号、封条、蛋糕、日期）在全文的语境分类，冲突即拦截并要求 Writer 局部修复；
- 或允许此类一致性 MUST 走局部 Patch（`replacements.json` 精确替换 + 硬门重跑），而不是整章修订。45 号迭代已引入局部 Patch，本次因 MUST 需跨多段全局协调而不可用，但位置矛盾实际可定位。

### K6. 修订后必须"全文重新双审"，成本线性放大

**现象**：每轮修订后 Blind Reader + Chapter Editor 各全文重读一遍；三轮 Writer + 两轮双审 = 约 8 个角色会话的全文级阅读，总耗时超 1 小时。

**根因**：SKILL 规定"有 MUST 时集中修一次，然后全文重新双审"——对全局一致性 MUST 合理，但无风险分级：局部 MUST 也按全文双审处理。

**建议**：
- 双审并行：Blind Reader 与 Chapter Editor 当前串行（Editor 依赖 Blind 结果）；对一致性核对类 MUST 可并行；
- 按 MUST 类型分级：`local`（可定位）→ 局部 Patch + 硬门；`structural`（全局）→ 整章修订 + 全文双审。仅 structural 才走全文双审。

### K7. 官方 CLI 没有"授权修复后继续"命令

**现象**：恢复流程只能通过 python -c 调用内部函数 `_request_staged_literary_patch` 或用户豁免 state.json，两条路都绕过官方命令面。

**根因**：CLI 缺少 `authorize-revision` / `revise <slug>` 类命令；第三版以上的续修没有官方入口。

**建议**：提供 `authorize-revision <slug>` 命令（记录 author 决策、写入轻量证据、签发 Writer patch 动作），消灭所有越权绕过路径。

### K8. 角色会话单次耗时过长，总时长不可预期

**现象**：单次 Writer 会话可达 30 分钟级以上，往返累计 1 小时 20 分；用户视角是"1 个多小时还没做完一章"。

**根因**：整章生成/修订天然耗时；叠加 K6 的全文重读与 K4 的重试放大。

**建议**：
- Lead 每轮角色开始前向用户报告预估轮数与累计时间；
- 超时/轮次上限触发"停止 / 换策略"提示（45 号已提硬预算，落地到具体阈值：如 3 轮双审未过即停止并给决策，而不是继续第四轮）。

## 本次未遇到但需注意

- 新题材复用检测：用户要求"避开现有 books 题材"，本次由人工重新选材完成；可考虑 `start` 时提示已有书的题材标签。
- 数据残留：`data/novel-forge.db` 无 liangu 记录（已确认）；书籍状态均落在书内 `.novel-forge/index.sqlite3` 与 `.local-guardian/<slug>/`，删书目录即干净。

## 迭代建议汇总

| # | 建议 | 对应卡点 | 优先级 |
|---|------|----------|--------|
| 1 | `decision_required` 增加"作者授权续修"选项，第三版不再依赖 receipts 门槛 | K1/K2 | P0 |
| 2 | 决策选项由 Python 按状态机可达性生成，Lead 不发明选项 | K2 | P0 |
| 3 | CLI 增加 `authorize-revision` 官方命令，消灭 python -c 绕过 | K7 | P0 |
| 4 | 冻结稿改名 / 动作卡显式标注只读与唯一可写路径 / 失败信息给出目标路径 | K3 | P1 |
| 5 | 引文校验模糊化 + 明确失败位置，审稿 instructions 引导复制 | K4 | P1 |
| 6 | 双审前加确定性一致性核对（实体-位置-归属），MUST 分级：local 走局部 Patch | K5 | P1 |
| 7 | 双审并行化；仅 structural MUST 走全文双审 | K6 | P2 |
| 8 | 每轮角色预估轮数与累计时间对用户可见，超阈值即停并给决策 | K8 | P2 |

## 结论

本次运行暴露的核心问题不是文学质量门（两轮 MUST 都真实存在、双审有效），而是**控制面在"第二版仍有 MUST"之后的路由是死路**：选项 B 必然失败、没有续修命令、只有越权绕过。45 号迭代收缩了流程复杂度，但第三版及以上路径的授权语义未与 lean 模式对齐。47 号迭代提案应优先解决 K1/K2/K7（死锁与官方入口），其次 K4/K5（失败率与成本），K6/K8 为体验优化。
