# 章节独立会话编排（v4.0）

## 为什么改为一章一会话

五章连续写作实验显示，长 writer session 到后段会同时积累三类债务：

1. 语言惯性：固定动作、物件、短句和感官证明反复承担相同功能；
2. 上下文惯性：旧工具输出、审稿记录和失败尝试持续进入缓存；
3. 流程惯性：越到后面越容易跳过证据、审稿或门禁，甚至写错项目路径。

v4.0 把原生 writer session 变成真正的章节边界。每章重新获得第一次落笔的新鲜度，
作品身份则由外部状态延续。要保留的是这本书的声音，而不是上一轮模型刚形成的口头禅。

## 两层状态

章节正文仍使用既有八态链：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

其上新增轻量章节序列：

`awaiting_session → running → awaiting_session ... → complete`

序列记录位于：

`books/<slug>/planning/chapter-sequences/<sequence-id>.json`

它是可更新的编排状态，不是不可变文学证据。generation、runtime audit、review 和
章节状态仍按原有权威路径保存。

## 操作协议

### 开始序列

```powershell
PYTHONPATH=. python -m app.novel_forge.skill_adapter `
  --root D:\s-black-novel `
  --confirm begin-chapter-sequence `
  begin-chapter-sequence <slug> `
  --start-chapter 1 `
  --chapter-count 3 `
  --sequence-id run-001
```

`chapter-count` 默认 1，最大 4。五章及以上必须拆成多个序列。命令只签发第一章，
不会提前创建后续章 writer。

### 绑定真实会话

外部 Harness 读取返回的 launch directive，创建新的原生 writer session，然后：

```powershell
PYTHONPATH=. python -m app.novel_forge.skill_adapter `
  --root D:\s-black-novel `
  --confirm claim-chapter-session `
  claim-chapter-session <slug> run-001 `
  --session-id <native-session-id>
```

session ID 在整个 `books/` 工作区内不得复用。generation `run_id` 必须等于这个
claim 值，角色名、子 Agent 名和编排器 ID 都不能替代它。

### 完成本章并签发下一章

writer 完成本章、runtime audit、两角色审稿和八态推进后，章节必须处于当前有效的
`ready`。随后编排器运行：

```powershell
PYTHONPATH=. python -m app.novel_forge.skill_adapter `
  --root D:\s-black-novel `
  --confirm advance-chapter-sequence `
  advance-chapter-sequence <slug> run-001 `
  --session-id <native-session-id>
```

系统重新验证 generation、runtime、formal gates、review 和 workflow integrity。
只有全部成立时，才结束当前 writer session，并为下一章生成 launch directive。
外部 Harness 看到 `launch_next_session=true` 后创建新的原生 session；不能续用当前
session，也不能并发提前写下一章。

## 有界交接包

每章交接包位于：

`memory/context-cache/chXX-handoff.md`

它只允许包含：

- 当前章唯一 scope 与停止规则；
- 与当前章有关的 Canon、人物知识和开放承诺；
- 上一章正文路径、SHA-256 与末段；
- Voice Bible 中的短 exemplar；
- 当前章 scene package。

明确禁止：

- 旧 writer session 的消息历史；
- 旧工具参数、结果与错误堆栈；
- 旧审稿全文；
- 整本正文或全部 Canon；
- 其他书的任何资产。

默认字符上限：

| 组成 | 上限 |
|---|---:|
| 记忆上下文 | 12,000 |
| 当前 scene package | 8,000 |
| 上一章末段 | 1,600 |
| Voice exemplar | 1,200 |
| 交接包总计 | 28,000 |

这些是字符级的前置约束，用于让新 session 从小而完整的工作集开始。运行期仍由
`session-audit` 执行 token 硬停：每章最多 30 请求、2,000,000 cached-input
tokens、单请求上下文 120,000 tokens。2,000,000 是异常止损线，不是目标额度。

## 单章与多章请求

- “写 1 章”：创建一章序列；本章 ready 后序列 complete。下次用户继续时，可从
  下一章创建新序列，上一章状态和交接信息仍在仓库中。
- “写 3 章”：创建三章序列；每章分别 claim、ready、结束和重新开 session，严格
  顺序执行。
- “写 5 章”：拒绝单序列执行。拆成不超过四章的序列，并在序列边界重新确认长期
  规划、开放承诺和作者方向。

因此，一章一会话不会把长篇变成拼接短篇。长会话依赖模型记得；章节化生产依赖系统
证明它没有忘。
