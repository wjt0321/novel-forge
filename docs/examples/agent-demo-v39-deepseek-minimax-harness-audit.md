# DeepSeek/Reasonix 与 MiniMax/pi 五章 Harness 审计

## 实验边界

- 审计日期：2026-07-19
- 同一份五章提示词、同一固定故事种子：《回水》
- DeepSeek 运行于 Reasonix AutoResearch
- MiniMax M3 high thinking 运行于 MiniMax Code，其 session 元数据显示
  `runtime=pi-agent`、`agentName=mavis`

本样本比较“模型 + Agent/Harness”的整套系统。它不能单独证明 DeepSeek 或 MiniMax
模型本体的优劣。长期证据只保留聚合指标、日志哈希、章节长度、门禁结果和缺陷计数，
不保存正文、prompt、思考链或工具返回。

这两个具名产品只用于验证通用规则。v3.9 的正式接口是厂商无关的
`novel-forge-runtime/v1`；任何其他 Agent/Harness 只要输出相同累计快照，就接受完全
相同的预算、来源、停机和会话隔离判定。

## 运行成本

| 指标 | DeepSeek + Reasonix | MiniMax M3 + pi-agent |
|---|---:|---:|
| 运行时长 | 2,003.072 秒 | 5,566.222 秒 |
| 请求数 | 239 | 592 |
| 工具调用 | 306 | 589 |
| 工具失败 | 14 | 34 |
| 总 token | 日志未提供 | 107,612,220 |
| cached-input | 日志未提供 | 106,769,514 |
| 最大单请求上下文 | 日志未提供 | 375,300 |
| 上下文重置 | 日志未提供 | 1 |

MiniMax 的新增输入 612,193、输出 222,935，缓存输入占总 token 约 99.22%。主要消耗
来自同一增长会话反复携带上下文，而不是五章正文输出本身。

## v3.9 止损回放

formal v3.9 要求每章独立 writer session，标准快照的 `scope.chapter_count` 只能为 1；
单章硬预算是 30 请求、2,000,000 cached-input tokens、单请求上下文 120,000。

这两份旧日志都把五章放在一个会话中，无法可靠还原每章边界。为避免伪造精确断点，
下面仍按五章总预算 150 请求、10,000,000 cached-input tokens 做保守兼容回放。新的
formal Harness 会在会话启动时先因“多章同会话”被拒绝，实际止损早于下列数字。

- Reasonix 会在第 151 次请求、累计工作时长约 1,142.477 秒时停止；原运行继续到
  239 次请求和 2,003.072 秒。
- MiniMax/pi 会更早在第 128 次请求、约 524.915 秒时触发 cached-input 上限；
  当时累计缓存输入 10,051,016。原运行继续到 592 次请求、106,769,514 缓存输入和
  5,566.222 秒。

因此 v3.9 不是“建议少用 token”，而是给外层 Harness 返回
`continue_allowed=false`。写作 Agent 无权用审美、进度或自审结论覆盖。

## 来源真实性

两套项目的 generation evidence 都未绑定真实 session id，并与外部日志存在差异。

Reasonix 差异字段：

- run id / generation binding
- provider
- Harness 名称
- 工具失败

MiniMax/pi 差异字段：

- run id / generation binding
- provider/model
- Harness 名称
- reasoning effort
- 工具失败

MiniMax 日志记录 34 次失败，generation 却声明空失败；日志明确是 high thinking，
generation 却记录 standard。v3.9 会在 ready 前拒绝这类来源冲突。

## 正文完成度

| 章 | DeepSeek CJK | DeepSeek v3.9 gate | MiniMax CJK | MiniMax v3.9 gate |
|---|---:|---|---:|---|
| ch01 | 5,193 | 可进入审稿 | 5,770 | 可进入审稿 |
| ch02 | 6,015 | 可进入审稿 | 5,125 | 可进入审稿 |
| ch03 | 4,980 | narrative blocking | 5,398 | 损坏对白 blocking |
| ch04 | 3,139 | quality + narrative blocking | 5,316 | 继承损坏对白 blocking |
| ch05 | 2,792 | quality + narrative blocking | 5,303 | 三项文学结构 blocking |

Reasonix 的主要问题是没有完成五章 formal 交付：后 3 章不足或缺少正式材料。其跨章
精确复用只有 3 个句子，未达到硬阻断阈值。

MiniMax 的机械流程完成度更高，但文学表面从第三章开始损坏：

- 句长均值 `19.0 → 13.2 → 12.2 → 11.6 → 11.7`
- 105 个跨章精确复用句
- 691 / 2,034 个句子实例属于跨章逐字复用，覆盖率 34.0%
- 1 个至少 60 CJK 的长段落跨章逐字复制
- 第三章检测到 10 处对白内部嵌套说话人标签

旧 gate 报告全部 quality blocking=0，说明这些问题原本不在硬门内。v3.9 会分别以
`serial-duplicate-coverage`、`cross-chapter-paragraph-copy` 和
`malformed-dialogue-structure` 阻断。

## 回到起点

“这篇小说像是人类写的吗？”

DeepSeek/Reasonix 的前两章更接近可读的人类叙事，但整套运行没有完成承诺的五章正式
交付。MiniMax/pi 完成了五章和大量流程材料，却在长会话中把动作、句子和段落变成
可复制模板，并由同一来源的审稿继续放行。

所以答案不能由“是否 ready”“写了多少字”或“模型自评通过”决定。v3.9 的作用是先
排除失控成本、虚假来源、伪盲审和机械损坏，再把剩下真正需要文学判断的部分交还给
独立读者与作者。

## 样本处置

完成最终回放与全量验证后，两个 `books/` 实验项目和两份原始 JSON 会话导出已于
2026-07-19 清理。仓库只保留本文件及同名 JSON 中的聚合指标、来源哈希、阈值、缺陷
计数和结论，不保留实验正文、prompt、思考链、消息正文或工具返回。
