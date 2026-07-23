# v5.2 硬锚、会话与 ready 完整性加固

## 问题

压力测试暴露出三个彼此独立的缺口：

1. Chapter Editor 可以只返回泛化的五维编辑判断，没有逐项证明用户给出的主角、
   世界观、核心冲突与章末钩子已被正文交付。
2. Relay 只比较当前 Writer 与已成功审稿的 session ID。失败、退役、章节序列历史中的
   Session，或复用旧 `session_instance_id` 的角色，仍可能换一个角色名再次进入流程。
3. ready Git checkpoint 建立后，编排器才写 `phase=complete`，导致恢复点创建完毕后
   工作树立刻重新变脏，但用户仍会看到章节完成。

## 修复

### 结构化硬锚核验

Chapter Editor 的正式结果必须包含 `hard_anchor_coverage`，逐项覆盖：

- `protagonist`
- `world`
- `conflict`
- `ending_hook`

每项都记录 `status`、当前正文逐字证据和普通读者实际能重建出的内容。身份、亲缘、
方向、数量、物件归属或行动目标与用户合同冲突时标记 `conflicted`；正文未交付时标记
`missing`。两种状态都必须伴随开放 MUST。只有世界设定中明确留给后续章节的部分可以
使用 `deferred_by_scene_boundary`。

Relay 和命令 Backend 只负责校验结构、证据是否来自当前正文以及阻断状态是否有 MUST；
文学与语义判断仍由独立 Chapter Editor 会话完成，Lead 不代审。

### 会话身份永久熔断

控制状态记录每个创作角色的 `session_id` 与 `session_instance_id`，包括完成、失败和
退役状态。新 Planning、Blind Reader、Chapter Editor 或 Patch Writer 完成结果必须同时
避开：

- 当前 Writer 身份；
- 已完成审稿身份；
- 失败或退役角色身份；
- 章节序列中已经使用的 Writer session；
- 任一历史 `session_instance_id`。

完成信封字段可补交仍沿用同一官方终态；一旦进入实质失败恢复，该身份即不可重试。

### ready 恢复点顺序

章节序列 effective 状态确认 complete 后，编排器先保存
`planning/workflow/active.json` 的 `phase=complete`，再创建每书
`chapter: chNN ready` checkpoint。checkpoint 返回成功还不够，随后必须复核：

- 有真实 commit hash；
- 每书 Git 没有 remote；
- 每书工作树为 clean。

任一条件失败都不能向用户显示章节完成。

## 回归覆盖

新增测试覆盖硬锚缺失却无 MUST、复用章节序列 Writer 身份、失败审稿身份原地重试，
以及 ready checkpoint 后工作树保持 clean。跨章夹具也必须持续交付同一用户硬锚，
不能用换主角的无效正文伪装成正常续章。
