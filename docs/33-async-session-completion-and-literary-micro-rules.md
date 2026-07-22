# 异步会话完成协议与文学微规则

## 问题

真实宿主不一定在 `run_writer` 返回时已经完成正文。Claude Code Teams、外部 Agent
平台或自定义 Harness 都可能先返回“子会话已启动”，然后让原生会话继续异步写作。
旧编排器把函数返回误当成会话完成，立刻尝试记录 runtime 和导入 Capsule，随后可能：

- 因正文或 runtime 尚未出现而生成 compromised 回执；
- Lead 不愿继续等待，转而在主会话代写、补证据或假装完成；
- 在已失效 Session 或旧 Capsule 上继续修改；
- 晚到的旧稿与新会话重试发生竞争；
- 规划、审稿摘要和 Git 提交显示 ready，底层有效状态仍是 planned 或 awaiting_session。

这不是某个模型或产品的专属问题，而是 Backend 缺少“启动”和“完成”的语义分离。

## Writer 完成协议

`NovelWorkflowOrchestrator` 在 `run_writer` 返回后不立即导入。Backend 必须返回
真实带类型 operation handle 与规范化状态：

1. `launched`：只表示已启动，编排器使用同一 handle 调用宿主官方 wait/join；
2. `completed`：官方终态完成，之后才检查 Capsule 正文与外置 runtime sidecar；
3. `failed` / `timed_out`：保留失败记录并废弃当前 Session/Capsule。

角色名、团队成员名或 Lead 自造标签都不能代替 operation handle。`accepted`、
`progress`、文件出现、文件大小稳定和固定 `sleep` 都不构成完成证据。默认终态等待
上限仍为 30 分钟；角色仍在 working/progress 时继续等待。

v4.9 进一步要求句柄包含 `kind/value`，宿主按 kind 选择 Task Output、background
output、mailbox、artifact 或其他官方通道。`idle_notification`、idle、available
都不等于产物；completed 必须同时返回角色绑定的 `role_result`。Writer 的 payload
只包含 capsule 内相对路径 `draft/正文.md`，宿主绝对路径由控制面掌握。

等待超时不产生“干净降级”：

1. 仍调用原 Guardian 导入；
2. 保留缺失 sidecar、缺失正文或其他原因形成的不可变失败回执；
3. 当前 Session 由 Guardian/Sequence 失效；
4. 创建新的 Writer Session 和新的 Capsule；
5. 最多自动重试 2 次；
6. 旧会话即使之后写完，也只能留在已废弃 Capsule，不能覆盖新会话正文。

编排器不解析完整产品 transcript，也不绑定 Claude、DeepSeek、Codex、Kimi 或其他
宿主。它只要求 Backend 把宿主官方生命周期规范化为同一终态语义，并在完成后返回
实际 resolved model。

## Writer 职责边界

旧 handoff 的停止规则错误地要求 Writer 同时完成正文、证据、审稿和 ready。它与
Guardian Contract 的“Writer 只能写 `draft/正文.md`”直接冲突，也会诱导 Lead 在
等待期间越权补做其他角色。

新规则明确：

- Writer 只完成本章正文；
- Generation、Runtime、Guardian Receipt、Review、状态与 Git 由编排器处理；
- Blind Reader 和 Chapter Editor 必须使用各自新的原生会话；
- Writer 不等待审稿、不代审、不推进 ready；
- Lead 只调度和呈现人话状态，不代写、代审或修订。

## 用户硬锚合同

用户六项输入由 Orchestrator 原样编译为 `0a. 用户硬锚合同`：

- 书名；
- 题材；
- 主角；
- 世界观；
- 本章核心冲突；
- 本章结尾钩子。

合同由系统注入 Scene Package，不接受规划会话改写。Writer 在有界 Story Brief 中看到
合同；Chapter Editor 还会收到独立的 `story_contract` 上下文。合同优先于规划解释，
Editor 必须核对时间方向、金额或数量、物件位置、人物知识来源、核心冲突和章末钩子。

这可以阻止“规划先漂移，正文照着漂移，Editor 再拿漂移后的规划证明正文正确”的闭环
自证。

## 文学微规则

脱敏样本不直接注入日常上下文。`planning_spec.py` 只保留三角色的短规则：

- Writer：主动选择进入动作、关系和代价；专业性落在材料、工具、身体和风险；允许
  误判、迟疑和不完整表达；禁止把规划、替代解释和主题翻译成说明段。
- Blind Reader：先判断人物欲望、关系摩擦和选择余波，再判断谜题与专业性；识别整齐
  问答、通用冷静能人、职业证明、规划清单和漂亮结论。
- Chapter Editor：硬锚优先；核对时序、空间、物件、知识边界和选择代价；识别控制面
  翻译、模式饱和与修补接缝；每轮全文重读并一次列全 MUST。

新书会生成 `evaluation/literary-micro-rules.md` 供审计；Writer handoff 和两份审稿任务
从同一常量编译，避免模板、提示词和文档形成平行规则。当前短版已升级为
`literary-micro-rules/v3`，完整解释见 `docs/35-literary-rule-manual.md`。

## 成本

本改造不增加模型调用：

- 异步等待使用宿主官方 wait/join，不增加模型调用，也不占创作上下文；
- 硬锚合同只有六项用户输入；
- 微规则按角色注入，不加载原文样本库；
- 仍为一次规划、一次初稿、每轮两次审稿，必要时一次集中 Patch；
- 第三版仍需用户明确选择重新生成。

## 证据样本

本里程碑的脱敏证据与处置见：

- `docs/examples/agent-demo-v49-async-writer-bypass-and-partial-humanity.md`
- `docs/examples/agent-demo-v49-async-writer-bypass-and-partial-humanity.json`

系统仍不认证文学价值、作者批准或发布许可。
