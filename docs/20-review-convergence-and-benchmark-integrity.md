# 审稿收敛与基准完整性（v3.5）

## 目标

v3.5 解决三类在 v3.4 完整质量链之后仍然出现的问题：

1. 规划材料自身带有日历、动作机制、知识来源或“伪不可逆”错误，后续同源审稿继续继承。
2. 六个角色增加了检查覆盖面，却可能全部来自同一 provider/model，不能形成独立模型证据。
3. 全文复审没有返工预算，局部 finding 可触发多轮回炉，耗时与 token 持续增长。

本里程碑仍不认证文学价值。`ready`、`benchmark_eligible`、模型评分和门禁通过都不是
作者批准或发布许可。

## 规划反证门

正式 scene package 新增必填节 `1e. 规划反证与常识检查`：

- 时间/日历算术：日期、星期、时长、期限和先后是否互相成立。
- 物理动作机制：电话、门锁、车辆、工具、支付与伤势按什么顺序才可执行。
- 人物知识来源：角色的判断来自观察、告知、Canon 记忆还是仍为假设。
- 不可逆性反证：选择能否轻易归还、撤销、拒绝履行或逃避责任。
- 场景停止点：哪个动作或关系变化发生后立即停，哪些解释留到下一场。

门禁只验证每项有可审计答案，不宣称答案一定正确。需要现实核验的内容仍由研究边界、
一致性审稿或人工事实检查负责。

## 审稿反锚定

`causal-editor` 与 `chapter-editor` 必须先只读正文，保存 prose-only reconstruction，
再打开规划材料比较 planning delta。规划中写了目标、选择或因果链，不再被视为正文
已经交付这些内容的证据。

blind-reader 继续保持 `context_scope=prose_only`。review 元数据解析允许简单 Markdown
粗体或括号说明，但会规范为精确 verdict；`needs_revision` 不会因格式清洗变成通过。

## Ready 与基准资格

`ready` 仍允许单机离线工作流使用同源审稿，只要来源被如实披露、审稿与当前正文绑定、
全部正式门禁满足。`project-status` 另行输出：

- `review_confidence`: `unassessed / single_origin / mixed_origin / independent`
- `benchmark_eligible`: 只有当前 blind-reader=`pass`、chapter-editor=
  `ready_for_editor_decision`，且两者均与 generation 异源时为 `true`

因此“可进入作者决定”与“可用于跨模型比较”不再混为一谈。

## 回炉预算

正式模式默认自动跑完预先声明的一批审核，不在“是否开始审核”处再次向用户暂停：

1. 第一份 generation：初稿。
2. 六角色一次批量审稿；orchestrator 对同源 finding 去重并裁决唯一回退层级。
3. 第二份 generation：一次合并 patch 后的修订稿。
4. 一次完整终审；必要时允许第三份 generation 作为终审版本。
5. 第三份 generation 后若再出现新 MUST，进入 `human_decision_required`，不得自动生成第四份。

MAY 不触发整章回炉。局部问题优先局部 patch；只有因果或结构材料失效时才回退到规划层。
历史 generation 仍可不可变记录，系统只在状态中报告 `budget_exhausted` /
`budget_exceeded`，不删除实验数据。

## Generation 运行指标

generation evidence 新增可选字段：

- `elapsed_seconds`
- `input_tokens` / `output_tokens` / `total_tokens`
- `metrics_source`: `harness_reported / user_observed / unknown`
- `pause_count` / `interaction_count`
- `review_round`
- `parent_generation_id`
- `generation_stage`: `raw / revised / final`
- `provenance_confidence`: `harness_exposed / mixed_attestation / user_attested / unknown`

未知字段保持 null/unknown，禁止估算成精确值。`evidence-status` 返回 generation 数量、
阶段摘要、自动预算和下一份 generation 是否需要人工决定。

## 状态完整性

`project-status` 从正文文件和 chapter-state 文件的并集发现章节，输出
`workflow_integrity`。当前可见问题包括：

- `missing_chapter_state`
- `content_present_while_planned`
- `generation_unrecorded` / `generation_stale`
- `invalid_review_verdict` / `stale_review`
- `placeholder_state_evidence`
- `budget_exhausted` / `budget_exceeded`

状态报告不返回正文全文，也不自动修改任何创作资产。

## 记忆显著性

记忆 Markdown 增加可选 `salience: high / medium / low`，旧记录缺失时默认为 medium。
可重建索引升级为 v2，并在同一上下文分层内优先输出高显著性记录。

`memory-status` 统计每章 candidate 文件与 Canon 记录数量；任一侧超过 15 条时给出
`memory_volume_high` advisory。该警报用于阻止把每个动作都原子化成长期事实，不会
自动删除、合并或拒绝晋升。

## 实验来源

本次规则来自 2026-07-17 的三份 Agent demo：

- MiniMax-M2.7 + Claude Code：约 3 分钟，快速完成但未进入正式审稿链。
- MiniMax-M3 + Claude Code：十多分钟，中途询问是否开始审核。
- 用户确认的 Kimi K3 + Kimi Code：约 50 分钟、四份 generation、约三轮审核回炉。

完整指纹、优缺点、来源边界和运行观察见
`docs/examples/agent-demo-v34-model-agent-comparison.md` 与同名 JSON。
