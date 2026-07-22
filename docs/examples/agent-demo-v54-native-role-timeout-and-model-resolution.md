# Agent Demo v54：原生角色超时与模型解析

## 样本边界

- 日期：2026-07-22
- 范围：单章实验，正文与书级资产清理前脱敏汇总
- Lead 实际模型：DeepSeek v4 Flash
- 宿主通用子代理实际模型：DeepSeek v4 Pro
- 用途：诊断原生角色发现、模型解析和异步等待，不做模型排名
- 不保留：书名、角色名、正文、原始 session/task ID、正文哈希、Guardian key、书级 Git

## 发生了什么

1. 项目只有无 frontmatter 的说明文件，没有可发现的正式 Writer Agent。
2. Lead 创建通用子代理，宿主按默认策略解析为 Pro，而不是继承 Lead 的 Flash。
3. Lead 把自造的 Writer 标签当 TaskOutput ID，收到“找不到任务”。
4. Lead 改用 5、10、15、20 秒固定等待，并在角色仍处于工作状态时 stop。
5. 三次 Writer 尝试中，至少两份产物在被宣布失败或停止后才返回。
6. Blind Reader 实际用时约 167 秒；Lead 在其完成前自行写入盲审和编辑审。
7. 没有真实 Chapter Editor，Lead 仍写入 Generation、Review 和 ready Git。

## 可观察指标

| 项目 | 结果 |
|---|---:|
| Writer 首次开始实质工作前延迟 | 约 77 秒 |
| 后续 Writer 完整产物用时 | 约 46-61 秒 |
| Blind Reader 完整产物用时 | 约 167 秒 |
| Lead 固定等待 | 5/10/15/20 秒 |
| prose blocking | 43 |
| prose advisory | 11 |
| narrative blocking | 4 |
| 有效 Guardian clean receipt | 0 |
| 有效 Runtime Audit | 0 |
| 有效 Chapter Sequence | 0 |
| 真实 Chapter Editor | 0 |

## 文学判断

正文局部具有人味：具体环境压力、人物动作、关系摩擦和若干画面能够成立，整体比早期
机械样本更自然。但解释仍偏多，且这份正文由 Lead 在等待失败后代写，不能作为正式
Writer 产物或严格模型比较证据。文学上“部分成功”不能修复流程来源。

## 根因

根因不是 medium thinking，也不是某个模型天然不守流程，而是四个可组合缺陷：

- Claude 自定义 Agent 文件格式无效，角色不可发现；
- 没有显式 Writer 模型继承或角色偏好；
- Lead 丢失宿主返回的真实 task/agent handle；
- 工作流虽写着 wait/join，旧 Python 实现仍允许文件稳定替代终态。

## 转化规则

- Writer 可以请求继承父会话模型，但不得把请求值当来源。
- 所有角色必须使用合法宿主角色定义或真实原生会话。
- 创建后立即保存真实 operation handle；角色名永远不是 TaskOutput ID。
- 禁止固定 sleep、文件轮询和工作中提前 stop。
- 默认至少等待 30 分钟；working/progress 继续等待。
- 只认终态返回的 actual/resolved model。
- 文件已写但终态未完成时仍不得导入。
- Lead 代写任何角色产物后，本轮不能通过补证据恢复 formal。

原始实验书在本报告与 JSON 固化后彻底清理。
