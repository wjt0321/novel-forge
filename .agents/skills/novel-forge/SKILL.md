---
name: novel-forge
description: Use when creating, planning, drafting, reviewing, auditing, repairing, or exporting a Novel Forge fiction project.
---

# Novel Forge

Novel Forge 是可审计的中文长篇生产链；文学目标是：**这篇小说像人写的吗？**

## 选择入口

- **自动生产唯一入口**：默认使用当前宿主原生的独立 Roles / Teams / Task Agent / Session；
  Lead 按本 Skill 调度、等待、回收产物，原生角色可用时不得因命令 Backend 缺失而停止。
- 控制面写入只经 adapter；不得自行创建正文、规划、审稿或 ready Git 恢复点。
  新书先由确定性控制面通过 `init-novel-project` 初始化，再创建 Writer 规划会话。
  `tools/novel-workflow.py start` 是可选 headless 入口；
  `NOVEL_FORGE_HARNESS_COMMAND` 只用于可选 headless。
- 高权限只属于无模型推理的确定性控制面；Lead 只调度，三个创作角色只交付各自产物。
  必须使用宿主官方 wait / join 等到角色终态；创建成功、已接单、进度消息或文件暂时稳定都不算完成。
  保存宿主返回的真实 task/agent ID；禁止用角色名作 TaskOutput ID、固定 sleep 或
  文件轮询。每角色默认等待 30 分钟，working/progress 时不得提前 stop。
  Blind Reader 正式记录后才能启动 Chapter Editor；退役 session 的晚到结果无效。
  无法创建、隔离或等待真实独立角色时停止，只说明“本章未开始”。
  `degraded_exploration` 只有用户明确要求探索稿时才允许。
- 模型偏好可按角色配置或继承父会话，但不绑定厂商；证据只认终态 `resolvedModel`。
- 创作 Lead/角色不得创建、修改、修复、包装、安装或配置 Harness / SessionBackend；
  不得自行设置命令桥，不得向用户提供部署或配置 Harness 的选项。
- 仅搭建空项目才用 `books/<slug>/`；SQLite 审批或导出用 `library/<slug>/`。
  不直改 SQLite、`library/**/revisions/` 或不可变 `evidence/`。

Adapter 从仓库根运行，`--root` 用绝对路径；变更操作须 `--confirm <operation>`。

## Books v4.8

默认状态链只有八态：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

`ready` 不是作者批准或发布许可。

`SessionBackend` 厂商无关；角色判断由真实会话返回，Lead 禁止代填。

### 通用执行合同

Formal 前读取 `harness-contract`。原生角色或可选 headless Harness 都输出
`novel-forge-runtime/v1` 累计快照；每次响应后运行 `session-audit`，
`continue_allowed=false` 即停机，无标准快照不能 formal。
命令桥仅接受仓库外入口并固定哈希；入口替换或 `control_plane_mutation` 立即停止。

### 隔离 Writer Capsule

Formal writer 不进入 `books/<slug>/`。控制面按 guardian-contract 在仓库外建 capsule-only 工作区；
writer 只见合同、`handoff.md`、`formal-writer/v1` 的 `instructions.md` 和
`draft/正文.md`。runtime 经 `record-capsule-runtime` 外置，导入由 Guardian 核验。
额外文件、路径逃逸、保护输入变化或证明不实均为 `compromised`。无变化 Patch 记为
`no_content_change`，不创建 Generation 或刷新审稿。
`run_writer=launched` 后必须用真实 operation handle 等待官方 `completed`，再检查
正文与 runtime；`accepted`、`progress` 或文件稳定无效。超时保留失败回执并换新
Session/Capsule，晚到旧稿不得覆盖重试稿。
协议不绑厂商；ACP 和完整 transcript 不是 formal 依赖；无法隔离时停止。

### 章节序列与新会话

正式生产一次只做一章，执行单位是**一章一个原生 writer session**。
sequence 返回 launch directive：

1. 新 Writer 先交付本章规划；再运行 `begin-chapter-sequence --chapter-count 1`。
2. 连续多章仍逐章换 Writer；单次序列最多 4 章，五章及以上拆分。
3. Lead 等待原生 Writer，控制面用 `claim-chapter-session` 绑定真实 session ID；
   后续章按 directive 新建会话。角色名或编排器 ID 不能代替原生 session ID；
   Backend 还须返回唯一 `session_instance_id`。随后创建 capsule。
4. Writer 只写本章正文，输出后停止角色工作；证据、审稿、状态、ready 与 Git 由
   控制面和独立角色处理，Lead 不得代做。上一章完整 `ready` 后再运行
   `advance-chapter-sequence`，只有返回 `launch_next_session=true` 时才顺序创建
   下一章的新 session。
5. session 不得跨章或跨书；generation `run_id` 必须等于 claim ID。三角色完成凭证
   绑定当前章、Generation、正文和角色产物，只由 Orchestrator 写；缺一不能 ready。

交接包只含硬锚、相关 Canon/承诺、上一章末段、Voice exemplar 和 Writer Story Brief；
不续传旧会话。完整 Scene Package 是 Chapter Editor 控制面，决策审计不进 Writer。

### 每书本地 Git

每书 Git 元数据在 `.local-book-git/<slug>.git`，不得配置 remote；用
`book-git-status` 查元数据。generation/ready 自动形成 `chapter: chNN draft` /
`chapter: chNN ready`，每五章打本地 checkpoint。Git 只管恢复，不代表批准。
彻底删除实验书时同时清除工作区、外置 gitdir、外置 Guardian 和临时 Capsule。

### 每章闭环

1. 新 Writer 先交付规划；用 `begin-chapter-sequence` 创建 1-4 章序列并立即
   `claim-chapter-session`。后续章按 launch directive 新建 Writer。再用
   `set-draft-mode` 固定 `formal | exploration | degraded_exploration`，并运行
   `prepare-writer-capsule` 创建仓库外隔离工作区。
2. 编排操作会核对/重建派生记忆索引并生成有界 `chXX-handoff.md`；单章诊断仍可
   运行 `memory-status` / `rebuild-memory-index` / `build-memory-context`。
   工具受限时记录真实失败并停止 formal；仅用户预先要求探索稿时才降级。
3. context collector 只交付一页最小写作包：目标/阻力/选择/代价、相关
   Canon 与人物认知、最多三条承诺、上一章末段、必要规则和一个短 exemplar。
   不加载全书 Canon、旧审稿全文、模板或无关章节；引用既有 exemplar。
4. 填一页式 `scene-package-chXX.md`。它必须包含人物摩擦、替代解释、
   beat 因果、责任归属、常识反证和余波；写作包交付事实，scene package 设计选择，
   重复字段只引用不扩写。只有三方以上动作依赖、专业操作/不可逆物理过程，或对白
   承担关键事实转移时，才建动作稿/对白账本。
   关键对白意图与专业判断不得留空；没有时写具体“无需”理由。
   ch02+ 的 `0b. 章际交接` 绑定上一章路径、SHA-256、末段短引及时间/地点/动作；
   还要写明上一章末明确决定、本章是否推翻该决定；若推翻，必须引用本章前 40%
   出现的触发事件原文，不能用事后解释替代桥接。
    本章开头短引在 `scene_packaged` 可写 `deferred_until_drafted`；完成后推进
    `scene_packaged`，起草后回填真实短引，formal gate 前不得保留 deferred 标记。
    Orchestrator 会把书名、题材、主角、世界观、本章核心冲突和章末钩子原样注入
    `0a. 用户硬锚合同`；规划不得改写，Writer 与 Chapter Editor 都以该合同优先。
5. 一名 writer 只读 instructions、handoff 与 patch 时预置正文，在 capsule 内处理一章。
   正式章不少于 5000 CJK；不要边查字数
   边连续补写。writer 只写 `draft/正文.md`；确定性控制面先经
   `record-capsule-runtime` 写入外置 runtime，再运行 `ingest-writer-capsule`，
   取得干净 Guardian 回执。集中 patch 使用预置当前正文的新 capsule；第三个潜在
   正文版本必须先经 `authorize-regeneration` 获得绑定前两版哈希的签名授权。
   无变化 Patch 保留失败回执，不产生新 Generation。
   writer 只接收叙事距离、信息释放和节奏功能，不接收句长、对白率、比喻密度等
   数值风格指标，也不得复制 Voice exemplar 的具体名词、标志动作、收尾物件或句法。
   规划是后台故事义务；正文允许误判、遗漏和延迟反应。
   `正文.md` 除标题外只含叙事文本，不得出现 Markdown 粗体、提示词、Agent 身份、
   `ch05`、`正文.md`、generation evidence/id、SHA-256、surface_checked、ready
   等生产元数据。
6. Guardian 导入成功后记录并绑定 generation evidence；其中
   `prompt_template_id`/`prompt_sha256` 必须匹配签名回执。运行期间持续审计标准累计
   快照，结束时经
   `record-session-audit` 固化脱敏运行证据。之后运行 `run-gates` 并推进
   `surface_checked`。runtime、来源、质量、叙事或文学结构任一 blocking 都立即
   短路，不启动审稿、不准备下一章。
7. 默认只运行两角色：blind-reader 与 chapter-editor。blind-reader 必须在不同于
   writer `run_id` 的会话中只读正文，并记录真实 `review_session_id`；同一写作会话
   只能填写 `context_scope=simulated_blind` 与 `needs_revision`，不能 pass。
   pass 还必须给出 `reader_desire=continue`、`emotional_residue` 与
   `next_chapter_pull`，证明一个真人会自愿追读，而不是只证明画面可重建。
   两者分别落盘并经 `record-review` 校验；逐项判断必须来自审稿会话，编排器不得
   代填。三角色须有不同 `session_instance_id` 和外置完成凭证。不得暂停询问审核。
    无法创建独立审稿会话时返回 `review_session_required`，不得改成开放式提问。
    Chapter Editor 额外读取独立 `story_contract`，必须先核对时间方向、金额或数量、
    物件位置、人物知识来源、核心冲突与章末钩子；Scene Package 不能覆盖用户硬锚。
8. 两份 finding 合并为一次 Patch，义务含位置、原文证据、读者效果和修订意图，
   禁止解释性修补。第二版仍有 MUST 时退役 Patch Writer 并等待选择；用户明确重新
   生成后，才为新 session 签发第三版授权并全文双审。
   ch05/ch10/... 还需当前 checkpoint arc audit，`open_must=0`。进入 ready 前，
   八态证据表不得保留 `-`/空值，并给出当前 ready 决定的 evidence 指针；formal
   Agent generation 还必须有匹配正文与 `run_id` 的干净 Guardian 回执。本章
   ready 前由 Sequence 见证当前 Writer、Generation 与正文；随后确认 effective 一致
   再建 ready Git 恢复点，失败即回退。

## 文学门

机器门只拦高置信破绽。极端逐字复用、长段复制和嵌套说话人标签为 blocking；
句长塌缩、低量复读、ASCII 标点为 advisory。`pattern-saturation` 查固定手势复用；
`voice-anchor-surface-copy` 查 exemplar 表层复制。只提醒编辑器，不生成数值目标。
机器不认证文学价值。

`literary-micro-rules/v3` 是短规则唯一来源；日常不加载样本全文。三角色按“可以写、
慎写、允许、绝对禁止”判断主动选择、私人代价、物理状态、知识来源、机械精确、
完美证据链和控制面泄漏；完整解释见 `docs/35-literary-rule-manual.md`。

### Blind Reader

运行在不同于 writer `run_id` 的独立会话，只读当前正文，禁止读取 planning、memory、
其他章节或未来信息。重建空间、身体、
行动约束、情绪轨迹、对白动态和至少三个可记忆画面。必须填写：

`human_likeness: convincing | uncertain | synthetic`

只有 `convincing` 可配合 `verdict: pass`。清单化节奏、模板物件循环、解释性结论、
未来章节知识或工作流语言都应判为 `uncertain/synthetic + needs_revision`。还查
替代解释枚举、职业证明、整齐问答和 Patch 接缝；谜题成立不等于真人愿意追读。
还必须填写 `reader_desire: continue | conditional | stop`、
`emotional_residue` 与 `next_chapter_pull`。只有 `continue` 可配合 pass；
还须填写五项重建与三个可记忆画面；`record-review` 拒绝空壳盲评。

### Chapter Editor

先只读正文重建事件链、选择、代价和停止点，再读 scene package、记忆包和上一章末段。
仅有具体专业风险时按需调用一个
`causal-editor | line-editor | texture-editor | consistency-guard`；专业角色是兼容工具，
不是默认六审。
每轮重审因果、能动性、对白、肌理和连续性，并查控制面泄漏与解释性 Patch。

审稿必须绑定当前 chapter/planning/generation SHA、真实 reviewer/provider/model/context
与 `review_session_id`。blind-reader pass 使用 `context_scope=prose_only` 且
`review_session_id != generation.run_id`；ch02+ chapter-editor 还绑定
`previous_chapter_sha256` 和逐字 `previous_chapter_quote`。同模型换角色名不算独立。

## Token 边界与外置 Guardian

- 每章独立会话，只传短提示词与有界 handoff；不回灌 transcript、旧工具结果或验证器源码。
- `session-audit` 只认 `novel-forge-runtime/v1`。每章上限：30 请求、2,000,000
  cached-input tokens、单请求 120,000 context tokens；超限即停止。
- 正文默认 standard/medium，即标准或中等推理。Max/长思考只处理具名难题，
  结论压入 scene package；不用于整章、模板、状态、证据或默认审稿。
- 正文一次 Write、最多一次集中 Edit；默认两角色，专业加审后建议总调用不超过 3。
- 第三版必须等待用户明确选择；MAY/advisory 不生成。
- generation 如实记录 `run_id`、provider/model/host、reasoning effort、
  token/request、draft/review 计数、`tool_capabilities` 与 `tool_failures`。
  指标只填本次增量；未知保持 null/unknown。
- formal ready 需要匹配 `run_id` 且未超限的外部审计；一章 runtime audit 只能绑定当前 generation，
  同一 writer `run_id` 不得跨章复用，计数缺失或超限均阻断。
- Generation、Runtime Audit、Review History 不可重封；completion 精确绑定当前产物。
  Agent 不得自称 human；新正文必须新建 Generation 和两份 Review。

## 事实与记忆

`memory/canon/**/*.md` 是权威源且不得直改；新信息先作 candidate，晋升后才进入
Canon。事实与认知分开。

策略：`no-deliberate-defects`、`single-winner-branch`、`model-score-not-approval`、
`aesthetic-does-not-override-facts`、`exploration-not-ready`、
`role-name-not-independence`、`world-not-protagonist-proof`、
`expertise-must-be-executable`。

## 证据与 Git

只读：`project-status`、`run-gates`、`evidence-status`、`memory-status`、
`chapter-sequence-status`、`session-audit`、`book-git-status`。变更参数查 `--help`。

`sync-tools` 只迁移带版本标记的生成文件到 v4.8；手写项目宪法不动，旧专业 Agent
仅作兼容资产。

同章同正文 SHA-256 只能算一个 generation。`harness_exposed` 必须有真实 `run_id`、
`agent_harness`、`metrics_source=harness_reported`、工具能力与失败。Agent 不得自称
`user_attested`。

未经用户明确要求，不得 commit、push 或执行 `git-checkpoint`。
