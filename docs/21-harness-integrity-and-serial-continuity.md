# Harness 完整性与连续章节交接

## 目标

v3.6 处理两类此前未被清楚表达的运行事实：

1. 写作 Agent 可能无法使用 Shell、adapter 或子代理，但仍能完成有价值的探索正文。
2. 工程型 Agent 可能完整填写流程资产，却通过重复证据、错误来源或同源自审制造虚假的完成度。

本里程碑不认证模型身份，也不认证文学价值。它只让运行来源、正文版本和跨章交接更可审计。

## 运行身份

generation evidence 增加：

- `run_id`
- `agent_harness`
- `reasoning_effort`
- `sandbox_profile`
- `tool_capabilities`
- `tool_failures`

未知值保持 unknown 或空数组。Agent authority 不得自行声明 `user_attested`；用户证明必须由 author 或 human_delegate authority 承担。

## 语义 Generation

同一章、同一正文 SHA-256 只代表一个正文版本。重复 evidence 文件不能制造新的 generation，也不能消耗自动回炉预算。

- record-evidence 拒绝同章同正文哈希的重复 generation。
- evidence-status 同时报告原始 record 数和不同正文版本数。
- 历史重复记录会出现在 duplicate group 中，但预算只按不同正文版本计数。
- 第四个及后续不同正文版本在写入前即被拒绝，除非记录由 `author` / `human_delegate` 提交，且包含 `human_regeneration_authorized=true` 与非空 `human_decision_reference`。授权只放行该次不可变记录，不代表作者批准正文。

## 降级探索

新增 `degraded_exploration` 模式，用于 Shell、adapter 或子代理不可用的运行。

- 可以保留正文、最小场景意图和 degraded run report。
- 不要求 formal 场景材料齐全。
- 不能进入 ready、benchmark_eligible 或作者批准状态。
- 正常环境恢复后，必须通过显式导入、补材料和重新取证进入 formal，不得静默升级。

项目应由外层 Harness 预先初始化。写作 Agent 不应在工具失败后自行猜测完整目录和证据格式。

## 章际交接

第 2 章起，场景包必须包含 `0b. 章际交接`：

- 上一章路径与 SHA-256
- 上一章结尾原文短引
- 本章开场原文短引
- 上一章结束与本章开始的时间、地点、动作
- 时间关系：同日连续、跨日、倒叙或并行

门禁验证哈希和短引真实存在；上一章短引必须位于正文末尾 20%，本章短引必须位于正文开头 20%。对同日连续场景，能解析的时点必须保持非递减；“上一章傍晚结束、下一章同日下午三点开始”会被阻断。

## 连续性审稿

第 2 章起：

- consistency-guard 与 chapter-editor 的绑定包含上一章正文 SHA-256。
- 两个角色都必须提供当前章与上一章的可核验证据短引。
- 上一章修改后，本章相关审稿自动 stale。
- causal-editor、line-editor、texture-editor 与 blind-reader 不绑定上一章哈希，避免无关全文重审。
- `project-status` 与 `ready` 会重新运行和 `record-review` 相同的结构、来源、引文与 generation 校验；直接写入 `reviews/chXX-<role>.md` 不能绕过门禁。
- ch05 仍需 checkpoint arc audit，且其 source hash 覆盖 ch01-ch05。

## 五章测试验收

下一轮连续五章实验重点观察：

1. ch02-ch05 是否都有真实章际交接。
2. 前章修改是否使后章连续性审稿 stale。
3. generation 是否按不同正文版本计数。
4. Max 或长思考是否用于反证，而不是复制流程资产。
5. ch05 checkpoint 是否捕捉承诺、人物状态和时间线债务。
6. 同源审稿是否仍被清楚标记为 single_origin。

`ready`、`benchmark_eligible`、作者批准与发布许可继续保持分离。
