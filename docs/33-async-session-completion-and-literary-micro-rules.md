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

`NovelWorkflowOrchestrator` 在 `run_writer` 返回后不立即导入，而是等待两个外部产物：

1. Capsule 内唯一正文 `draft/正文.md`；
2. Capsule 外由 Harness 生成的 runtime sidecar。

两个文件必须存在、非空，并在连续采样中保持大小和修改时间稳定。默认最多等待
30 分钟；宿主可以在构造 Orchestrator 时调整等待、轮询和稳定采样参数。

等待超时不产生“干净降级”：

1. 仍调用原 Guardian 导入；
2. 保留缺失 sidecar、缺失正文或其他原因形成的不可变失败回执；
3. 当前 Session 由 Guardian/Sequence 失效；
4. 创建新的 Writer Session 和新的 Capsule；
5. 最多自动重试 2 次；
6. 旧会话即使之后写完，也只能留在已废弃 Capsule，不能覆盖新会话正文。

编排器不解析产品 transcript，也不绑定 Claude、DeepSeek、Codex、Kimi 或其他宿主。
它只等待厂商无关的文件完成条件。

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
从同一常量编译，避免模板、提示词和文档形成平行规则。

## 成本

本改造不增加模型调用：

- 异步等待是本地文件轮询，不占模型上下文；
- 硬锚合同只有六项用户输入；
- 微规则按角色注入，不加载原文样本库；
- 仍为一次规划、一次初稿、每轮两次审稿，必要时一次集中 Patch；
- 第三版仍需用户明确选择重新生成。

## 证据样本

本里程碑的脱敏证据与处置见：

- `docs/examples/agent-demo-v49-async-writer-bypass-and-partial-humanity.md`
- `docs/examples/agent-demo-v49-async-writer-bypass-and-partial-humanity.json`

系统仍不认证文学价值、作者批准或发布许可。
