# 外置 Harness 护栏（v3.9）

v3.8 已经把默认工作流从六审和多轮回炉压缩为八态、两审、最多一次集中 patch。
2026-07-19 的两组不同模型与 Harness 对照实验说明：仅靠 Skill 内的自然语言约束仍
不够。写作 Agent 可以自报错误的模型、思考强度、工具失败和 token，也可以在同一个
增长会话里反复读取、编辑和自审，最后把形式材料全部标成 ready。

v3.9 的方案 B 不针对任何一家模型或 Agent 产品。它定义一个机器可读、厂商无关的
Harness Contract，把四类责任移到写作 Agent 外部：

1. Harness 会话统计；
2. 继续或停止的 token 决定；
3. generation 来源真实性；
4. blind-reader 是否真的与 writer 会话隔离。

## 通用契约

任何 Agent/Harness 开始 formal 写作前，都必须读取本书：

```text
books/<slug>/evaluation/harness-contract.json
```

也可以直接调用：

```powershell
$env:PYTHONPATH='.'
python -m app.novel_forge.skill_adapter `
  --root D:\s-black-novel `
  harness-contract
```

契约要求 Harness 把自己的原生遥测规范化为
`schema=novel-forge-runtime/v1` 的累计会话快照。核心字段包括：

- `session_id` 与本次覆盖的 `scope.chapter_count`；
- Harness 名称/版本、provider/model、reasoning effort；
- 累计请求数、输入/输出/缓存/总 token；
- 最大单请求上下文、上下文重置次数；
- 工具调用总数、失败数、按工具计数；
- 已运行秒数。

标准快照允许额外字段，但审计器会忽略它们。prompt、正文、思考链、工具参数、工具
返回和审稿正文都不进入 runtime audit。

## 生命周期

契约不是“完成后填一次表”。formal Harness 必须：

1. 写作前读取契约；
2. 每次模型响应后更新累计快照；
3. 在发起下一次模型请求前运行 `session-audit`；
4. 若 `budget.continue_allowed=false`，在下一次请求前停机；
5. 运行结束后用 `record-session-audit` 固化最终脱敏审计；
6. 另开独立会话运行 prose-only blind-reader。

无法输出标准快照、无法执行中途停机或无法隔离盲审的 Harness，不会被识别为“不支持
的产品”，但只能进入 `exploration` / `degraded_exploration`，不能 formal ready。

## 兼容导入

`app/novel_forge/session_audit.py` 的架构入口是标准快照。同时保留少量已经验证的原生
日志解析器，方便旧 Harness 迁移：

- 一类嵌套消息导出：从 session 与 message usage/tool calls 提取统计；
- 一类 item stream 导出：从 assistant/tool/phase 项提取统计。

这些解析器只是兼容层，不是支持边界。新的或未知的 Harness 无需等待项目增加专用
解析器，只要直接输出 `novel-forge-runtime/v1` 即可。

输出只包含：

- session id、Harness、provider/model、reasoning effort；
- 请求数、输入/输出/缓存/总 token；
- 最大单请求上下文、上下文重置次数；
- 工具调用总数、失败数、按工具计数；
- 来源日志 SHA-256；
- 外部预算结论与 generation 元数据差异。

输出明确排除 prompt、正文、思考链、消息内容和工具返回。

## 审计入口

对标准快照或兼容日志做只读预检：

```powershell
$env:PYTHONPATH='.'
python -m app.novel_forge.skill_adapter `
  --root D:\s-black-novel `
  session-audit <slug> --file <绝对会话JSON路径>
```

固化脱敏审计：

```powershell
$env:PYTHONPATH='.'
python -m app.novel_forge.skill_adapter `
  --root D:\s-black-novel `
  --confirm record-session-audit `
  record-session-audit <slug> --file <绝对会话JSON路径>
```

记录写入 `books/<slug>/evidence/runtime-audits/<session-id>.json`。同一 session id
不得覆盖；记录不含会话正文，因此可以作为 ready 复核来源。

## 外部硬预算

formal 标准快照固定 `scope.chapter_count=1`，因为协议要求每章独立写作会话。若标准
快照自报多章范围，审计会直接拒绝，不能靠放大范围提高预算。只有回放旧兼容日志时，
因为日志缺少该字段，才按当前项目已有正文章数聚合：

| 指标 | 每章上限 | 五章上限 |
|---|---:|---:|
| 请求数 | 30 | 150 |
| cached-input tokens | 2,000,000 | 10,000,000 |
| 单请求上下文 | 120,000 | 120,000 |

任一可观测指标超限：

```json
{
  "status": "exceeded",
  "continue_allowed": false
}
```

Harness 必须把 `continue_allowed=false` 当成停止信号，并在下一次模型请求前执行。
它不是审美判断，不允许 chapter-editor、writer 或角色提示词自行豁免。

## 来源校验

runtime audit 将真实观测与 generation evidence 对比：

- `run_id` 对 session id；
- provider/model；
- `agent_harness`；
- reasoning effort；
- 日志存在工具失败但 generation 声明空数组。

外部无法观测的字段保持 `unknown`，不会制造假差异；已观测字段不一致则 formal ready
失败。这样“模型自己填写自己是谁”不再是来源真相。

## 盲审隔离

关键 review 新增：

```text
review_session_id: <真实审稿会话 id>
```

model/agent blind-reader pass 同时要求：

- `context_scope=prose_only`；
- generation 有真实 `run_id`；
- `review_session_id != generation.run_id`；
- `human_likeness=convincing`。

同一写作会话可以做诊断，但只能填写：

```text
context_scope=simulated_blind
verdict=needs_revision
```

角色名、提示词或 Markdown 元数据不再能证明独立。

## 文学结构硬门

v3.9 不把“文学好坏”交给正则，但将三种机械可证的稿件损坏升级为 blocking：

- `serial-duplicate-coverage`：跨章逐字复用句覆盖至少 20 个句子实例，且达到全文
  句子实例的 20%；
- `cross-chapter-paragraph-copy`：至少 60 CJK 的完整段落跨章逐字复制；
- `malformed-dialogue-structure`：对白内部重复嵌套相同说话人标签，累计至少 2 处。

句长塌缩、低量精确复读仍为 advisory，由 blind-reader 与 chapter-editor 判断是否是
有意复沓。blocking 会进入 `surface_checked`、`run-gates.ready_eligible`、ready
复核和 `project-status.workflow_integrity`，同源编辑不能自行放行。

## 实验止损效果

在 2026-07-19 的两个保留样本上回放通用规则。由于旧运行把五章放在同一会话中，下面
是按五章总预算计算的保守兼容回放；新的 formal contract 会更早拒绝这种多章会话：

- MiniMax/pi-agent 首先在第 128 次请求、约 524.915 秒触发五章
  10,000,000 cached-input 上限；原运行最终达到 592 请求、107,612,220 tokens、
  约 5,566.222 秒。
- Reasonix 在第 151 次请求、累计工作时长约 1,142.477 秒触发五章 150 请求上限；
  原运行最终达到 239 请求、约 2,003.072 秒。

具名样本只证明通用协议能拦截两种不同失控方式，不构成产品专用优化。这不是保证模型
一定写得像人。它保证系统不会让一个已经失控的 Harness 继续用更多 token 证明自己
正确，也不会让同一个会话同时充当 writer、blind-reader 和最终裁判。
