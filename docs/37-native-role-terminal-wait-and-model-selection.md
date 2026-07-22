# 原生角色终态等待与模型选择

## 事故

一次单章实验中，Lead 使用轻量模型，宿主创建的通用子代理却自动落到另一种更重的
模型。项目生成的 `.claude/agents/` 文件没有合法 frontmatter，也没有正式 Writer
角色，因此宿主无法发现项目角色配置。随后 Lead 又把角色名当作任务 ID 查询，查询
失败后改用 5、10、15、20 秒固定等待，并在角色仍工作时提前停止。

Writer 实际需要约一分钟才开始交付，Blind Reader 需要接近三分钟。多个晚到产物在
Lead 宣布失败后继续返回；Lead 已经越权代写正文、盲审、编辑审和 ready 记录。最终
小说局部可读，但正式链路不成立。

## 模型选择

Novel Forge 继续保持厂商无关：

- `RoleExecutionPreference` 只表达 `preferred_model` 或
  `inherit_parent_model`；
- 偏好不等于来源，不能写入 Generation 冒充实际模型；
- 角色终态返回的 resolved model 才是正式来源；
- 宿主自动回退到其他模型时，如实记录实际值；
- 工作流不硬编码 DeepSeek、Claude、Codex、Kimi 或任何产品组合。

Claude Code 的生成模板现在包含可发现的四个自定义 Agent。Writer 使用
`model: inherit`，因此当前 Lead 由用户选择某个模型时，Writer 可以继承同一模型；
Blind Reader 与 Chapter Editor 不写死模型，继续使用宿主默认或用户级角色配置。
这满足“Writer 使用适合作文的模型、审稿使用另一模型”的需要，同时不把组合写进
通用协议。

## 终态协议

`run_writer` 返回 `SessionRunState`：

- `operation_id`：宿主返回的真实 task/agent handle；
- `status`：`launched | completed | failed | timed_out`；
- `resolved_model`：宿主确认的实际模型，可为空但不得猜测。

`launched` 必须进入 `wait_for_completion`。编排器默认等待 1800 秒，只认相同
operation ID 的 `completed`。以下情况一律不能导入：

- 用角色名、自造标签或旧 task ID 查询；
- created、accepted、progress 或 working；
- 固定 `sleep` 后文件看似稳定；
- 角色已被 stop，但晚到文件仍出现；
- completion 返回了不同 operation ID。

超时或终态失败会创建不可变 compromised 回执、废弃 Session 与 Capsule，并使用新
Session/Capsule 自动重试。晚到旧稿没有重新获得导入资格。

## Claude 角色模板

新书生成：

- `.claude/agents/writer.md`
- `.claude/agents/blind-reader.md`
- `.claude/agents/chapter-editor.md`
- `.claude/agents/orchestrator.md`

四个文件都有合法 YAML frontmatter。Orchestrator 明确要求保存真实 handle，禁止
固定 sleep、文件轮询和工作中提前 stop；正式来源使用 `resolvedModel`。这些是 Claude
适配层，不改变 Skill 的通用边界。其他编程工具只需把自己的 Roles/Teams/Task 生命周期
映射为同一状态与模型来源语义。

## 成本

本改造不增加写作或审稿调用。等待发生在宿主控制面；Writer 继承模型也不增加上下文。
失败只在真实终态超时后重试，避免过去因为 Lead 过早判断失败而并发启动多个 Writer，
反而减少浪费。

## 证据

脱敏事故样本见：

- `docs/examples/agent-demo-v54-native-role-timeout-and-model-resolution.md`
- `docs/examples/agent-demo-v54-native-role-timeout-and-model-resolution.json`

样本只用于工作流诊断，不认证文学价值、作者批准或模型排名。
