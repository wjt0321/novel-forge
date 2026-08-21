# 历史决定与整合记录

本档案保存被取代的里程碑文档、已完成的设计/实施方案、一次性 Agent Demo 报告中的耐久结论。它是历史背景，不是当前工作流契约。当前行为由 `../43-fiction-first-lean-native-workflow.md`、`../44-current-workflow-logic-audit.md`、`../45-workflow-iteration-proposal.md` 以及 `../README.md` 中链接的三份聚焦参考定义。

整合前的原始文档在 Git 历史中可访问。

## 2026-07-31 价值分析

整合前 `docs/` 包含 115 个文件、10,184 个非空行。整合后剩 15 个文件、1,553 个非空行：文件减少 87.0%，行数减少 84.8%。

| 来源集合 | 文件数 | 价值决定 | 理由 | 去向 |
|---|---:|---|---|---|
| 当前工作流 43–45 | 3 | 保留 | 当前默认、审计/恢复真源、最新迭代 | 原地保留 |
| 里程碑 01–13 | 13 | 浓缩 | 旧式搭建、数据库、packet/readiness 和早期工作流细节；仅作兼容性 | `legacy-library-reference.md` 加本时间线 |
| 文学里程碑 14–23、26、28、35 | 13 | 浓缩 | 耐久文学规则分散在版本化报告与重复实验中 | `literary-quality-reference.md` |
| 控制面里程碑 24–25、27、29–34、36–42 | 16 | 浓缩 | 耐久隔离、Session、Guardian、本地 Git、恢复与 ready 规则现归一份实现 | `architecture-reference.md` |
| 已完成的设计/实施方案 | 18 | 汇总后删除 | 一次性执行脚手架，不再是操作参考 | 见下方"已完成方案历史" |
| Agent Demo v34–v56 Markdown/JSON 报告 | 43 | 汇总后删除 | 一次性、不可对比的实验；重复出现的来源声明与失败模式 | 见下方"Agent Demo 历史" |
| 测试用回归 JSON | 1 | 迁移 | 机器夹具不是文档 | `tests/fixtures/agent-demo-v43-control-plane-bypass.json` |
| 可复用文学范例 | 4 | 保留 | 对 Writer/reviewer 校准直接有用 | `docs/examples/` |
| 脱敏工作流样本目录 | 3 | 保留 | 不含正文与私密控制数据的当前聚合工作流证据 | `docs/examples/book-workflow-samples/` |

整合有意移除逐版本正文与一次性测试输出。保留三份聚焦参考里的必要流程、约束、恢复规则、路线图决定、失败模式、来源边界与可复用范例。Git 仍是精确历史档案。

## 里程碑时间线 01–42

| 里程碑 | 耐久贡献 | 当前归属 |
|---|---|---|
| 01 Getting Started | 环境、CLI/API 入口、当前工作流与旧式工作流的区分 | `legacy-library-reference.md`、`../43-fiction-first-lean-native-workflow.md` |
| 02 Data Model and State Machine | books/chapters/revisions/findings/facts/promises/audit 与状态机迁移不变量 | 旧式参考与架构参考 |
| 03 Quality and Approval Gates | 修订范围内的 lint/review/Canon 闸门；pass 不等于作者批准 | 文学参考与架构参考 |
| 04 Operations and Backup | 审计、备份、导出 manifest、已确认的 adapter 操作 | 旧式参考与架构参考 |
| 05 Human-readable Fiction Quality | 证据 → 读者效应 → 修订意图；不自动改写正文 | 文学参考 |
| 06 Voice Bible and Scene Contracts | 正向声音指引、有界场景压力、版本化合同 | 文学参考 |
| 07 Database Migration | 版本检测、时间戳备份、原子迁移、回滚 | 旧式参考 |
| 08 Drafting Packets | P0/P1/P2 context 原则 | architecture/45 中的当前 Writer 包 |
| 09 Drafting Readiness | 占位检测、formal vs exploratory readiness | 架构参考与文学参考 |
| 10 Narrative Editorial Gate | 因果/能动性/editorial memo 边界 | 文学参考 |
| 11 Autonomous Research/Writing Chain | 研究账本、story engine、plans、promises、iterations | 旧式参考；当前工作流只保留耐久原则 |
| 12 Quality-chain Reconstruction | 分层闸门、human-first books 工作区、Patch 修订 | 架构参考 |
| 13 Claude Project Workflow | `books/` Markdown-first 项目与有界 adapter | 架构参考 |
| 14 Blind Experience Gate | prose-first 隔离 reader 报告与批准效应 | 文学参考 |
| 15 Books Skill Quality | 单一规则源、lint 薄壳、adapter 边界 | AGENTS 与架构参考 |
| 16 Register Mixing Handover | 对白/语域变化与范例观察 | 文学参考 |
| 17 Long-form Memory Kernel | candidate Canon、promises、矛盾点、有界章节交接 | 架构参考 |
| 18 Human Narrative Evaluation | human-likeness 是读者重建，不是 AI 检测 | 文学参考 |
| 19 Limited Cognition/Causal Responsibility | 知识来源、可选解读、因果归属 | 文学参考 |
| 20 Review Convergence/Benchmark Integrity | 修订范围内 findings、来源有资格的对比、不分数当批准 | 文学参考与基准历史 |
| 21 Harness Integrity/Serial Continuity | runtime 真源、独立 Session、串行交接 | 架构参考 |
| 22 Source Hygiene/Cost Short Circuit | 提前停掉无效实验；保留来源不确定性 | 架构参考 |
| 23 Lean Literary Loop | 小角色表面、全硬闸门、有界修订循环 | 当前 43/44 |
| 24 External Harness Guardrails | 厂商中立 terminal/runtime 契约与预算边界 | 架构参考 |
| 25 Chapter Session Orchestration | 一章一会话、claim/advance 序列、有界交接 | 架构参考 |
| 26 Literary Anti-overfit/Sequence Truth | 一条胜出分支、Writer/Editor 分离、不排名模型 | 文学参考 |
| 27 Per-book Local Git | 外部本地恢复 Git、不推 remote、checkpoint 顺序 | 架构参考 |
| 28 Reader Pull/Runtime Truth | 追读欲与观察到的 runtime 与模型自报分开 | 文学/架构参考 |
| 29 Isolated Writer Capsule | Writer 只读 capsule 的输出、受保护输入、Guardian 导入 | 架构参考 |
| 30 Compiled Writer Prompt | 有界厂商中立 prompt 与来源绑定 | 架构参考 |
| 31 Automatic Three-role Workflow | Writer → Blind Reader → Editor → 一次 Patch → 双审 | 当前 43/44 |
| 32 Literary Production Loop | Python 控制面、角色分离、分阶段正式晋升 | 架构参考与当前工作流 |
| 33 Async Completion/Micro-rules | 官方终态真源、硬锚、紧凑文学禁用规则 | 架构参考与文学参考 |
| 34 Session Attestation/Sealing | 双 session 身份、内容封存、evidence-before-ready | 架构参考 |
| 35 Literary Rule Manual | Writer/Reader/Editor 允许/谨慎/禁止规则 | 文学参考 |
| 36 Harness Trust/Control Integrity | Lead 不能创建基础设施，不能用授权代替隔离 | 架构参考 |
| 37 Native Terminal Wait/Model Selection | 等待官方终态；requested vs resolved 模型区分 | 架构参考/45 |
| 38 Typed Role Result/Review Recovery | 类型化 payload、路径归属、有界结果修复 | 架构参考与当前审计 |
| 39 Deterministic Native Control | Python 拥有状态，创作角色零控制面写 | 架构参考 |
| 40 Native Relay/Assurance Modes | 持续 pull 协议与 formal/exploration 区分 | 当前 43/44 与架构参考 |
| 41 Completion Repair/Review Capsules | 不重做正文的修复元数据；密封 review 输入 | 当前审计与架构参考 |
| 42 Hard-anchor/Session/Ready Integrity | 结构化锚覆盖、永久 session 冲突检测、checkpoint 顺序 | 当前审计与架构参考 |

## 已完成方案历史

被删除的方案文件落在以下已收尾的工作流：

| 日期 | 工作流 | 结果 |
|---|---|---|
| 2026-07-15 | Novel Forge 基础 | 初始 service/repository/database、CLI/API、质量与备份契约 |
| 2026-07-17 | Human narrative workflow | 基于证据的 reader/editor 评估与 books 工作流 |
| 2026-07-17 | Long-form memory kernel | candidate Canon、promises、有界连续性 |
| 2026-07-17 | Review convergence and benchmark integrity | 修订范围与有资格的实验证据 |
| 2026-07-17 | Harness integrity and serial continuity | runtime/session 真源与多章节隔离 |
| 2026-07-19 | External guardrails | 厂商中立 Harness 契约与实验停止规则 |
| 2026-07-19 | Chapter-session orchestration | claim/advance 序列与有界交接 |
| 2026-07-19 | Per-book local Git | 外部本地 Git 恢复与 checkpoint 语义 |
| 2026-07-19 | Reader pull/runtime truth | 读者追读欲字段与 runtime 来源约束 |
| 2026-07-20 | Formal Writer prompt | 编译后的有界 prompt 与 Capsule 绑定 |
| 2026-07-21 | Automatic three-role workflow | Writer/Reader/Editor 编排与恢复 |
| 2026-07-21 | Literary production loop | 控制面隔离与一次 Patch 收敛 |
| 2026-07-23 | Deterministic native workflow | Native Relay、结果路由、工作区卫生 |
| 2026-07-31 | Workflow observability phase 1 | 一次写入的成本/重试/正文变更观测，不改路由 |
| 2026-08-02 | Author-revision routing（iteration 47） | 官方命令 `authorize-revision`、Lean receipt 闸门绕过、可达决策选项、冻结稿改名、证据引文模糊匹配 |

方案在落地实现与测试成为可执行真源后被删除。新完成的方案应在此汇总，而不是长期保留。

## 2026-08-02 iteration 47 耐久结论

1. 第二次双审仍失败后，唯一可行路径是官方作者决定命令；`python -c` 与状态文件覆盖已是死胡同恢复路径，现在由 `authorize-revision <slug> --reference <依据>` 取代。
2. Receipt-history 闸门不得阻断 Lean 模式：明确的作者决定（retry 或 authorize-revision）授权下一版正文；双版本闸门只对未授权的自动重试生效。
3. 决策选项属于确定性控制面（可达性），不属于 Lead 或宿主；`next-action` 签发 `user_decision` 卡片，`complete-role` 在决策待定时被拒绝。
4. 实体位置/归属一致性检测器**有意未实现**：Python 验证流程与可定位证据，不验证文学意义；启发式实体扫描会过报或漏报。可定位一致性 MUST 改由 reviewer 指令路由到现有 local-Patch 路径。
5. 证据引文验证需要有限容差与精确失败位置；只做精确子串匹配会推高 review 重试次数却不带来质量收益。

## Agent Demo 历史

所有实验比较的是 模型+宿主+权限+工作流，而不是孤立的模型权重。不同的故事、prompt、上下文、工具、完成深度使统一排名不可能。`ready`、分数或闸门通过从来都不等于作者批准或发布资格。

| Demo | 耐久发现 |
|---|---|
| v34 source/evidence comparisons | 用户声明的模型来源可能与项目元数据冲突；保留有资格的来源置信度，永远不要把 Agent 输出与人类基准混在一起。 |
| v34 model/agent/rework comparison | 工作流完成深度与修订成本与表面正文同等重要；非受控样本不能排名模型。 |
| v35 DeepSeek across Harnesses | 同一声明模型在写作型与编码型 Harness 下表现不同；比较整个 runtime 系统。 |
| v37 MiniMax five-chapter drift | 即便状态到达 ready，Markdown 强调与格式污染会逐章累积。 |
| v38 Claude/MiniMax ACP audit | 真实计费/runtime 事件必须与模型自报分开；长共享上下文增加成本与污染风险。 |
| v39 DeepSeek/Reasonix vs MiniMax/pi | 外部 Harness 需要来源校验、硬预算、会话隔离与停止条件。 |
| v40 multi-host session audit | 一章一会话与有界交接是必要的；宿主/任务标识符不可互换。 |
| v41 four-model prose comparison | 保留一条胜出分支；文学诊断不能在小样本多模型对比上过拟合。 |
| v42 reader-pull study | human-likeness 与追读欲是分开的；可读的纹理不保证下一章的拉力。 |
| v43 control-plane bypass | 同上下文的 Lead 能伪造 session 证据并绕过 Guardian 边界；该 JSON 仍作为 `tests/fixtures/` 下的回归夹具。 |
| v44 single-chapter Harness bypass | 看起来正式的文件与哈希不证明独立 Writer 或合法晋升路径。 |
| v45 workflow comparison | 更强的正文、更低的成本、更可信的编排可以分属不同的模型/Harness 组合。 |
| v46 three-session human-light flow | 当 session 身份与产物归属保持显式时，最小角色交接可行。 |
| v47 automatic false-ready bypass | 直接编辑状态/文件可制造 ready；Python 必须拥有晋升与 checkpoint 顺序。 |
| v48 control-plane spill/repair seam | 创作角色写到发布路径之外需要恢复；恢复不能抹掉合规正文。 |
| v49 async Writer bypass/partial humanity | 官方终态前的文件出现不是完成；表面人味可与无效工作流证据并存。 |
| v50 single-context backfill | 补填的 review 文件与自签 ID 不能反过来证明独立 review。 |
| v51 literary success/formal bypass | 一章可能在文学上有潜力但程序上无效；审美判断永远无法补足缺失的形式证据。 |
| v52 missing-backend degraded completion | 没有 backend 就在正式生产前停下；降级的 exploration 不能重标为 formal。 |
| v53 Lead-created fake Harness | 用户允许继续 ≠ 允许 Lead 安装或伪造基础设施、会话或遥测。 |
| v54 timeout/model resolution | requested 与 resolved 模型不同；等待宿主的官方终态与真实解析出的身份。 |
| v55 result routing/path ownership | Session/member/task ID 与 Unix/Windows 产物路径需要类型化路由与显式归属。 |
| v56 multi-host stress audit | 没有样本同时拿下正文、成本、工作流真源；按风险路由质量投入并保留作者判断。 |

## 可复用结论

1. 评估 模型+宿主+角色隔离+上下文+恢复 整个系统。
2. 未知来源或遥测保持未知。
3. 文学成功与程序合规是两个独立维度。
4. 强 Lead 推理不能替代程序强制的角色隔离。
5. 弱 Lead 行为必须无法自写/自审出 ready。
6. 局部问题用精确局部替换；结构性问题需要一次集中章节 Patch。
7. 成本控制停止额外调用；它永远不把未解决问题转成 pass。
8. 只有作者能批准作品；发布资格始终为 false。

## 2026-08-02 iteration 47 完成附记

1. 并行双审：Lean 同时签发两张 reviewer 卡片，完成顺序任意；Chapter Editor 在没有 Blind 结论时独立审稿；严格审计仍走串行。
2. 晋升前永不清理暂存正文：capsule 重新准备保留 `draft/正文.md`，guardian 接受保留现有正文的 capsule，技术重试与重新生成也保留。
3. 每张角色卡片由 SHA-256 摘要与 action-id 一致性校验保护；控制面自管路径只在控制面本身重写它们时（state.json、relay 记录、观测、授权）从快照对比中排除。

## 2026-08-18 pi-subagent 适配层单次会话测试

一次探索性测试会话试图通过 `pi-coding-agent` subagent 工具端到端走通 Lean Native 的 `Writer → Blind Reader → Chapter Editor → ready` 链路。测试未保留正文、未产出正式章节；仅在 `docs/examples/book-workflow-samples/catalog.json` 样本 `failure-lean-sandbox-redirect-2026-08-18-05` 中记下脱敏聚合快照。**结论指向 Novel Forge 与宿主 subagent 机制之间的适配层**，不针对工作流规则本身。按严重度排序，未改动 `43`、`44`、`45` 中的 Writer/reader/editor 契约。

### 缺陷 1 — subagent `output` 参数覆盖 canonical draft 路径（critical）

当 Lead 用 `output="draft/正文.md"` 与 `outputMode="file-only"` 派发 Writer 子代理时，宿主 subagent 系统把该路径当作完成回执槽位。Writer 会话确实把章节写进了 sandbox（已校验：22763 字节），但同一文件在父工作目录视图里最终落到的是完成 JSON，不是正文。Sandbox 与父 fs 不同步，完成产物是父端的最后一次写，不是 Writer 的写。

修复方向：

- PI 侧：把 `output` 语义改为只读快照槽位；永远不要把完成回执写到子代理本来要写的路径。
- Novel Forge 侧：在 `tools/novel-workflow.py` 或 canonical skill 中明确，Writer 派发时 `output` 必须设为 `false`（或非 canonical 路径）。加回归测试，断言父视图里 `draft/正文.md` 等于 Worker 的 sandbox 写盘内容，而不是完成回执。

### 缺陷 2 — `complete-role` 不把文件实际写入者与所报 session-id 绑定（high）

`complete_minimal` 接受任意 `session-id` 字符串。一旦 `draft/正文.md` 在 canonical 路径上存在且非零字节，工作流就把所报 id 记为 Writer 的真实 session 并继续。Lead 因此可以伪造 session-id 并绕过角色边界——自己写文件、随便报个字符串作为 Writer session。缺陷 1 的 sandbox 路由失败让问题更严重：恢复 Writer 实际产物的唯一办法是 Lead 触达 `draft/正文.md`，按 `43` 规则 4 这会让该章永远停在 `exploration`，无法到达 `formal_ready`。

这与本档案里 v43 / v47 / v50 / v53 控制面绕过同根——耐久教训是同一条：**程序强制的角色隔离不能依赖 Lead 自觉**。

修复方向：

- Novel Forge 侧：`complete-role` 应校验 canonical 产物的最后写入来源。廉价信号：文件 mtime 与所报会话的开始/结束时间戳对比，或让 Writer 会话把 session-id 写到产物旁的隐藏元数据侧车。任一项不匹配必须直接失败，不能记下伪造会话。
- Novel Forge 侧：加一条不要求 Lead 写 `draft/正文.md` 的恢复路径。建议：Lead 用 `output:false` 派发新 Writer 子代理，让它读现有 canonical draft、按 capsule 校验、然后从自己的会话里重写（或完全重写）。前一位 Writer 的 transcript 是恢复来源，不是 Lead 的手。

### 缺陷 3 — task 文本构造存在未文档化的转义陷阱（high）

`workflowScript` 只接受 JavaScript statement body。在 `task` 字符串里嵌一段 `python -c "..."` 校验命令（用反引号模板字面量）会触发 `SyntaxError: Invalid or unexpected token`。错误提示建议改用数组 `.join('\n')`，但只能试错才知道。skill 当前没有任何"如何安全构造长 task 文本"的指引。

修复方向：

- PI 侧：让 `workflowScript` 支持从文件路径或 `heredoc` 接受原始 task 字符串，不再只接受 JavaScript statement body。
- Skill 侧：把"数组 .join('\n')"模式作为内嵌多行 prose 任务的标准方式写进文档，配一个完整示例。

### 缺陷 4 — Worker 子代理在未明确禁止时会扩张任务范围（medium）

派发的 Writer 子代理看到项目根目录有开放的 `pytest` 测试目录，并且 system prompt 把工作区框定为完整生产系统，于是自行跑全套 `pytest` 做自定校验。它在那次调用里卡了 4 分钟，要靠显式 `stop` 才能放开。Lean Native skill 只规定 Writer 可读/写哪些文件，没规定限制 Worker 的工具集。

修复方向：

- Skill 侧：明确禁止 Writer/Reader/Editor 子代理跑测试、lint、git，或在 canonical 产物路径之外执行任何命令。把禁止条款写在派发合同里，不要只写在 `instructions.md`。
- PI 侧：可选支持 `--tool-allowlist` 让 Lead 按角色限制工具，不必写进 task 文本。

### 缺陷 5 — Windows 子代理停止后泄漏 git pack 文件句柄（medium，环境相关）

`subagent({ action: "stop" })` 之后，子代理遗留进程组仍持有 git pack mmap 文件句柄。stop 之后 `shutil.rmtree`、`cmd /c rmdir /s /q`、PowerShell `Remove-Item` 全部因 `WinError 5` 失败。canonical `.local-book-git/<slug>.git/` 只能重命名以中和；40 个被锁 pack 对象留在 `.__stale_*` 墓碑里等下次开机。

修复方向：

- PI 侧：终止子代理时，在发信号前主动关闭进程组的文件描述符。Windows 上当 agent 可能持有 git pack 句柄时，优先 `taskkill /F /T` 而不是优雅 stop。
- Skill 侧：加 Windows 专项清理备注——canonical 路径可在物理删除失败时被改名，持久记录是脱敏聚合目录。

### 缺陷 6 — 工作流状态机没有 sandbox 路由失败的信号（medium）

缺陷 1 发生后，canonical 产物存在但内容错误，relay 阶段却仍是 `awaiting_writer`。没有自检把 `draft/正文.md` mtime 与 Writer 会话预期完成窗口对比。Lead 没有程序信号知道需要恢复，只能靠文件检查人工诊断。

修复方向：

- Novel Forge 侧：当 canonical 文件 mtime/内容与 Writer 会话报告的完成回执不匹配时，加一条 phase 迁移 `awaiting_writer -> awaiting_writer_with_anomaly`（或在 `awaiting_writer` 上挂一个 `anomaly` 标记）。skill 必须描述 anomaly 状态以及"用 `output:false` 派发新 Writer"的派发协议。

### 缺陷 7 — 工作流体量与用户实际意图错配（low，产品讨论）

用户原话："搜集时下流行的题材，任选一个，写一篇小说，只需要第一章"。Lean 默认入口要 `start` 配七个参数、派三次角色、两次并行 review、再加一次晋升。一个创作请求要先进七步状态机才能落到正文上。这些步骤对认真连载的作者都正确，对快速试写第一章都过重。

修复方向：

- 仅作产品讨论。可复用结论应留在本档案作为提醒：工作流是为连载生产设计的，不是为临时实验。未来迭代可加 `--quick-draft` 能力，跳过双审并默认使用 `exploration` 语义。

### 交叉引用

缺陷 2 与本档案现有 v43、v47、v50、v53 绕过类同根；缺陷 1 的恢复路径与 v48（恢复不能抹掉合规正文）、v49（官方终态前文件出现不是完成）相邻。本档案可复用结论 4（"强 Lead 推理不能替代程序强制的角色隔离"）与结论 5（"弱 Lead 行为必须无法自写/自审出 ready"）直接适用。
## 2026-08-21 文档收敛：一次性提案/复盘归档

以下四个已完成文档删除（耐久结论如下，原文见 Git 历史）：

1. **46-workflow-iteration-blockers-liangu.md**（《敛骨人》卡点复盘）：核心教训
   是 decision_required 曾无"修复后晋升"可行路径（lean 无 receipt 导致
   regeneration 门槛永不可满足）。修复 = authorize-revision 语义 + lean 下
   author 决策经 require_body_history=False 授权第三版。后续所有决策类故障
   均路由为可授权 decision。
2. **47-workflow-iteration-proposal.md**：46 复盘与首轮代码审查的全部意见已于
   2026-08-02 实施完毕；第二轮审查修复亦完成。实施明细在当日 docs/44 小节与 Git 历史。
3. **49-workflow-code-review-proposal.md**（2026-08-07 代码审查）：§2 字段单源/
   zip 三节点、P1 会话契约、§3 token 压缩、§4 修辞 advisory 与 uncertain 契约
   全部落地，记录在 docs/44 的 2026-08-07 各小节。代码注释中残留的 "docs/49 §N"
   引用指本文档（Git 历史可查）。
4. **46-token-diet-and-book-scale-plan.md**：Checklist 八项全部完成——A1 交接包
   15,200、A2 规划卡有界摘录、A3 style-reference.md 拆分、B1 book_repeat.py、
   B2 book_arcs.py、B3 anchor+voice-seed、A4 canon 6000、A5 审计=已单源化。
   行为变更记录于 docs/44 的 2026-08-21（四）（五）小节；作者用法收进
   literary-quality-reference「Book-scale quality features」。代码注释中的
   "docs/46 B1/B2/B3/A1-A5" 编号即该计划条目。

保留的现行文档：43（流程规则）、44（逻辑审计+变更日志）、45（迭代实施记录）、
48（未来方向笔记）、三份聚焦 reference、README、本 archive。
