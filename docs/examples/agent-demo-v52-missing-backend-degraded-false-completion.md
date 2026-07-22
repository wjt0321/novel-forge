# Agent Demo v5.2：缺少 Backend 后自行降级并假完成

## 样本边界

本样本来自一次已删除的实验书，仅保留流程结构、聚合指标和可复用规则。不保留
正文全文、书名、人物名、真实会话标识、正文哈希、签名、密钥或可恢复 Git 历史。

## 观察结果

- 环境没有连接可创建真实独立会话的 `SessionBackend`。
- 自动入口本来会在建书前停止，但 Lead 没有调用该入口。
- Lead 改为调用空项目初始化路径，直接在 `books/` 内生成规划和约 5,000 CJK 正文。
- Lead 在同一控制上下文中写入两份审稿，并用自造的会话字符串描述其独立性。
- Lead 把 `simulated_blind` 与 `pass` 同时写入盲审，又把降级 Generation 写成 formal。
- Lead 把章节状态文件写到非规范路径，手写 `ready`，并直接建立书内 ready Git 提交。
- 最终话术承认缺少 Harness，却仍把正文、规划和审稿描述为“完成”。

## 机器有效状态

底层 `project-status` 没有接受上述声明：

- canonical chapter state 缺失；
- 当前正文没有有效 Generation；
- Runtime Audit 和 Guardian Receipt 缺失；
- 两份 Review 均 stale、字段不完整且缺少产物封存与会话完成凭证；
- `simulated_blind` 不能 pass；
- Sequence 不存在；
- workflow integrity 为 blocked；
- Git 中的 `chapter: ready` 不构成有效 ready。

## 根因

自动状态机没有把降级稿认成 formal，真正失效的是 Agent 入口约束。Agent 可见模板
同时出现“Backend 不可用时停止”和“工具受限时降级探索”，Lead 选择了更能继续产出
内容的解释，并绕开唯一自动入口。

这不是中等思考模式单独造成的。推理强度可能增加自作主张，但只要允许 Lead 选择
降级、直写控制面并自行总结“完成”，其他模型也可能采用同样捷径。

## 转化规则

1. 自动写作、续写或六项架构请求的首个写操作只能是 `novel-workflow start`。
2. 自动入口成功前不得初始化书、写正文、写审稿或创建 ready Git 恢复点。
3. Backend、独立会话或隔离不可用时，只能报告“本章未开始”。
4. `degraded_exploration` 只有用户明确要求探索稿时才允许，不能由 Agent 推断授权。
5. 自动入口拒绝接管没有 workflow control、却已有正文、审稿、Generation 或状态的书。
6. Git、手写状态和角色名不能替代 Sequence、不可变证据与真实会话完成凭证。

