# 精简文学闭环（v3.8）

## 起点

Novel Forge 的最终问题不是“流程是否走完”，而是：

> 这篇小说像是人类写的吗？

v3.7 已能拦截 Markdown 污染并限制三代回炉，但 2026-07-18 的五章 ACP
实验表明，流程本身仍会放大上下文、工具调用和同源自审：

- 5 章正文共约 2.53 万 CJK。
- 真实总 token 42,938,274，其中缓存输入 42,432,000。
- 199 次请求，缓存输入约占总 token 的 98.82%。
- 30 份同源角色审稿共约 15.8 万字节，仍未发现正文中的 `ch01`/`ch05`、
  `正文.md` 和工作流复盘。
- ch03-ch05 分别形成约 15、15、16 个正文文件状态，表现为“先短写，再反复补到
  5000”，而不是一次完整起草。

完整实验数据见
`docs/examples/agent-demo-v38-claude-minimax-acp-audit.md`。

## 设计判断

文学价值不能由正则、模型评分或状态机保证。系统能保证的是：

1. 高置信机械破绽先被廉价拦截。
2. writer 得到足够但有限的材料，不被审计协议挤出人物和场景。
3. “像人写的”由真正 prose-only 的盲读问题直接表达。
4. 审稿与返工有明确预算，避免同一模型用更多文字证明自己正确。
5. 运行成本和上下文增长成为可见证据，而不是事后猜测。

## 八态链

v3.8 将 books/ 默认状态从 14 态压缩为 8 态：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

删除的不是质量责任，而是重复的执行检查点：

- `action_drafted` / `dialogue_planned`：动作稿和对白账本改为按风险生成。
- `causal_reviewed` / `line_reviewed` / `texture_reviewed` /
  `consistency_checked`：四类责任合并进 chapter-editor 的一次综合审稿。

旧专业角色名仍可被 `record-review` 接受，以兼容旧书和困难章节，但新项目不默认生成
这些 Agent 文件，且它们不再是 ready 前置。

## 一页写作契约

正式章写前只保留两份高价值输入：

1. **最小写作包**：交付事实、人物认知、相关承诺、上一章末段、必要规则和短
   exemplar；不设计本章情节。
2. **一页式 scene package**：只设计目标、阻力、选择、代价、替代解释、beat
   因果、责任归属、常识反证和余波；不复制大段事实。

动作稿仅在三方以上动作依赖、专业操作或不可逆物理过程时使用。对白账本仅在对白承担
关键事实转移或责任变化时使用。两者都是辅助材料，不新增状态。

`关键对白意图` 与 `专业判断审计` 不再预填豁免。没有相关风险时仍须写具体“无需”
理由，避免模型把模板默认文字误当作已经做过判断。

ch02+ 的本章开头短引允许在 `scene_packaged` 阶段写
`deferred_until_drafted`，但必须在 formal gate 前回填为正文开头 20% 内的真实短引。
这消除了“正文还没写，场景包却要求逐字引用正文”的顺序悖论。

## 两角色文学门

### Blind Reader

只读当前正文，回答空间、身体、行动约束、情绪轨迹、对白动态和可记忆画面，并填写：

`human_likeness: convincing | uncertain | synthetic`

只有 `convincing` 能与 `verdict=pass` 同时成立。盲读报告引用未来章节会被拒绝；审稿
日期晚于当前 UTC 日期也会被拒绝。

结构校验还要求盲读报告实际填写空间、身体、行动约束、情绪轨迹、对白动态和三个
可记忆画面。系统只验证责任被覆盖，不对答案的文学价值打分。

### Chapter Editor

先只读正文完成事件链、人物选择、代价和停止点重建，再读取一页式 scene package、
当前记忆包和上一章末段。它一次承担：

- 因果与有限认知；
- 人物及世界的独立目标；
- 对白和信息流；
- 句子肌理；
- 跨章连续性。

`record-review` 要求五项维度逐项填写；仅有 verdict、一个短引和空 Findings 表的
chapter-editor 报告不能进入 ready。

只有出现具体、无法可靠合并判断的专业风险时，才调用一个 specialist。默认每章审稿
调用从 6 次降为 2 次；五章初审从 30 次降为 10 次。

## 机器文学风险

新增 blocking `workflow-meta-leak`，拦截正文中的高置信生产语言：

- `ch05` / `ch-05`
- `正文.md`
- `scene-package` / `chapter-state`
- generation / review_round
- SHA-256
- surface_checked / ready_eligible / open_must

`voice_signature.analyze_serial_style()` 增加跨章 advisory：

- `sentence-length-collapse`：后续章节句长均值相对首章显著下降。
- `cross-chapter-repetition`：同一完整句跨章精确复用至少三次。

两项同时出现时 `human_likeness_risk=true`。该信号不自动判定文学失败，而是要求
blind-reader 和 chapter-editor 对原文给出判断。

## 返工与成本

自动 generation 上限从 3 个不同正文 SHA 降为 2 个：

1. 初稿：一次完整 Write。
2. 合并两角色 finding 后的一次集中 patch。

第二份正文仍有新 MUST 时进入人工决定；第三份正文需要 author/human_delegate 明确
授权。MAY 不触发回炉。

generation evidence 新增：

- `cached_input_tokens`
- `request_count`
- `draft_write_count`
- `draft_edit_count`
- `review_call_count`

默认 advisory 预算：

| 指标 | 每章上限 |
|---|---:|
| cached input tokens | 2,000,000 |
| requests | 30 |
| draft writes + edits | 3 |
| review calls | 3 |

每份 generation 记录本次运行的增量，不重复复制整场会话累计值。
`evidence-status.runtime_budget` 按章聚合，并返回
`unassessed | partial | within_budget | exceeded`。未知指标不再伪装成预算内；
超限不否定已写正文，但编排器应停止自动准备下一章，先结束增长中的会话、压缩上下文
或请求人工决定。

## 迁移与完整性

`sync-tools` 只迁移带 v3.7 生成标记的 `CLAUDE.md` / `README.md`，无版本标记的手写
宪法保持不动。旧状态映射如下：

- `action_drafted` / `dialogue_planned` → `scene_packaged`
- `causal_reviewed` / `line_reviewed` / `texture_reviewed` /
  `consistency_checked` → `surface_checked`

旧专业 Agent 文件可以留作历史兼容，但 v3.8 宪法不再默认调用它们。

进入 `ready` 前，八态证据表必须没有空值或 `-`，并提供本次 ready 决定的 evidence
指针。系统不会先写出 ready、再由 project-status 宣布它非法。

## Skill 减重

Canonical Skill 从 16,283 字符、276 行缩至约 4,500 字符、140 行以内。它只保留：

- books/library 路由；
- 八步闭环；
- 两角色文学门；
- token 边界；
- 事实、证据和作者批准边界；
- 常用 adapter op。

文学教材、历史里程碑和完整字段解释不再每次随 Skill 注入。机械约束进入代码，重型
参考留在 docs 和具体模板中。

## 不保证什么

v3.8 不能数学保证一章具有文学价值，也不能保证任何模型真正“像人”。它提供的是更
可信的失败发现方式：少让模型证明流程，多让独立读者面对正文；少把 token 花在缓存
与自审，多把推理预算留给人物选择、语言和后果。
