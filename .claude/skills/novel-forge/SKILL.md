---
name: novel-forge
description: Use when creating, planning, drafting, reviewing, auditing, repairing, or exporting a Novel Forge fiction project.
---

# Novel Forge

Novel Forge 是可审计的中文长篇生产链；文学目标是：**这篇小说像人写的吗？**

## 选择入口

- 新写作项目：`books/<slug>/`，正文唯一入口为
  `chapters/eXX/ch-XX/正文.md`。
- 需要 SQLite revision、审批或导出：`library/<slug>/`。
- 两者并用时，以 `books/` 为正文源，定稿后单向提交到 `library/`。
- 不直接编辑任何 SQLite、`library/**/revisions/` 或不可变 `evidence/`。

Adapter 从仓库根运行，`--root` 必须是绝对路径；变更操作必须
`--confirm <operation>`。先用 `--help` 查看参数，不在 Skill 中复制全部 CLI。

## Books v4.4

默认状态链只有八态：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

`ready` 只是材料齐备，不是作者批准或发布许可。

### 通用 Harness Contract

开始 formal 写作前，任何 Agent/Harness 都先读取本书
`evaluation/harness-contract.json`，或调用只读 op `harness-contract`。核心协议与
模型厂商、Agent 产品、Shell 类型无关：Harness 把自己的原生遥测规范化为
`novel-forge-runtime/v1` 累计快照；系统只认标准字段，不要求识别产品名称。

每次模型响应后更新快照并在下一请求前运行 `session-audit`；
`budget.continue_allowed=false` 就停机。无标准快照只能 exploration/degraded_exploration。

### 隔离 Writer Capsule

Formal Agent writer 不直接进入 `books/<slug>/`。外部 Harness 先读取
`evaluation/guardian-contract.json` 或调用 `guardian-contract`，在仓库外创建
capsule，并把 writer 文件系统限制为 capsule-only。writer 只见合同、`handoff.md`
和可写的 `draft/正文.md`；runtime 快照由 Harness 在 capsule 外生成，并经
`record-capsule-runtime` 写入外置 Guardian sidecar。`ingest-writer-capsule`
本地核对文件、哈希、session、预算与证明后原子导入正文。
额外文件、路径逃逸、保护输入变化或证明不实均为 `compromised`，session 失效。
协议不绑定厂商；ACP 和完整 transcript 不是 formal 依赖。无法落实隔离时只能
`degraded_exploration`。

### 章节序列与新会话

正式生产的执行单位不是“一次写几章”，而是**一章一个原生 writer session**。
系统用 `planning/chapter-sequences/<sequence-id>.json` 返回 launch directive：

1. 用户要求 1 章：运行 `begin-chapter-sequence --chapter-count 1`。
2. 用户要求连续多章：同一编排器可自动顺序执行，但单次序列最多 4 章；五章及以上
   必须拆分，禁止用一个 writer session 连写。
3. Harness 按 launch directive 创建新的原生 writer session，并用
   `claim-chapter-session` 绑定真实 session ID。角色名、子 Agent 名和编排器 ID
   都不能代替原生 writer session ID。随后运行 `prepare-writer-capsule`，让该
   session 只进入仓库外 capsule。
4. writer 只处理当前一章；上一章完整 `ready` 后必须结束其 writer session。
   编排器再运行
   `advance-chapter-sequence`，只有返回 `launch_next_session=true` 时才顺序创建
   下一章的新 session。
5. 同一 session ID 不得用于另一章或另一书；generation `run_id` 必须等于 claim
   的 session ID。上一章未完整 `ready` 时不得签发下一章。

交接包写入 `memory/context-cache/chXX-handoff.md`，只含相关 Canon/认知与承诺、
上一章末段及 SHA-256、Voice exemplar 和 scene package；禁止续传旧会话或整书。

### 每书本地 Git

每书 Git 元数据在 `.local-book-git/<slug>.git`，不得配置 remote；用
`book-git-status` 查元数据。generation/ready 自动形成 `chapter: chNN draft` /
`chapter: chNN ready`，每五章打本地 checkpoint。Git 只管恢复，不代表批准。
彻底删除实验书时必须同时清除工作区与外置 gitdir。

### 每章闭环

1. 用 `begin-chapter-sequence` 创建 1-4 章序列，读取当前章 launch directive，
   创建新的原生 writer session 后立即 `claim-chapter-session`。再用
   `set-draft-mode` 固定 `formal | exploration | degraded_exploration`，并运行
   `prepare-writer-capsule` 创建仓库外隔离工作区。
2. 编排操作会核对/重建派生记忆索引并生成有界 `chXX-handoff.md`；单章诊断仍可
   运行 `memory-status` / `rebuild-memory-index` / `build-memory-context`。
   工具受限必须降级并记录真实失败。
3. context collector 只交付一页最小写作包：目标/阻力/选择/代价、相关
   Canon 与人物认知、最多三条承诺、上一章末段、必要规则和一个短 exemplar。
   不加载全书 Canon、旧审稿全文、模板说明或无关章节；直接引用既有 exemplar，
   不另建声音分析报告。完成后推进 `context_collected`。
4. 填一页式 `scene-package-chXX.md`。它必须包含人物摩擦、替代解释、
   beat 因果、责任归属、常识反证和余波；写作包交付事实，scene package 设计选择，
   重复字段只引用不扩写。只有三方以上动作依赖、专业操作/不可逆物理过程，或对白
   承担关键事实转移时，才建动作稿/对白账本。
   关键对白意图与专业判断不得保留空模板；没有时写具体“无需”理由。
   ch02+ 的 `0b. 章际交接` 绑定上一章路径、SHA-256、末段短引及时间/地点/动作；
   还要写明上一章末明确决定、本章是否推翻该决定；若推翻，必须引用本章前 40%
   出现的触发事件原文，不能用事后解释替代桥接。
   本章开头短引在 `scene_packaged` 可写 `deferred_until_drafted`；完成后推进
   `scene_packaged`，起草后回填真实短引，formal gate 前不得保留 deferred 标记。
5. 一名 writer 在 capsule 内一次写完整章。正式章不少于 5000 CJK；不要边查字数
   边连续补写。writer 只写 `draft/正文.md`；Harness 先经
   `record-capsule-runtime` 写入外置 runtime，再运行 `ingest-writer-capsule`，
   取得干净 Guardian 回执。集中 patch 使用预置当前正文的新 capsule；第三个潜在
   正文版本必须先经 `authorize-regeneration` 获得绑定前两版哈希的签名授权。
   writer 只接收叙事距离、信息释放和节奏功能，不接收句长、对白率、比喻密度等
   数值风格指标，也不得复制 Voice exemplar 的具体名词、标志动作、收尾物件或句法。
   `正文.md` 除标题外只含叙事文本，不得出现 Markdown 粗体、提示词、Agent 身份、
   `ch05`、`正文.md`、generation evidence/id、SHA-256、surface_checked、ready
   等生产元数据。
6. Guardian 导入成功后记录并绑定 generation evidence；运行期间持续审计标准累计
   快照，结束时经
   `record-session-audit` 固化脱敏运行证据。之后运行 `run-gates` 并推进
   `surface_checked`。runtime、来源、质量、叙事或文学结构任一 blocking 都立即
   短路，不启动审稿、不准备下一章。
7. 默认只运行两角色：blind-reader 与 chapter-editor。blind-reader 必须在不同于
   writer `run_id` 的会话中只读正文，并记录真实 `review_session_id`；同一写作会话
   只能填写 `context_scope=simulated_blind` 与 `needs_revision`，不能 pass。
   pass 还必须给出 `reader_desire=continue`、`emotional_residue` 与
   `next_chapter_pull`，证明一个真人会自愿追读，而不是只证明画面可重建。
   两者分别落盘并经 `record-review` 校验；不得暂停询问“是否开始审核”。
   无法创建独立审稿会话时返回 `review_session_required`，不得改成开放式提问。
8. 合并两份 finding，只允许一次有范围的集中 patch。第二份不同正文 SHA-256
   后若仍有新 MUST，进入 `human_decision_required`；不得自动生成第三份。
   ch05/ch10/... 还需当前 checkpoint arc audit，`open_must=0`。进入 ready 前，
   八态证据表不得保留 `-`/空值，并给出当前 ready 决定的 evidence 指针；formal
   Agent generation 还必须有匹配正文与 `run_id` 的干净 Guardian 回执。本章
   ready 后结束 writer session，由编排器执行 `advance-chapter-sequence`。

## 文学门

机器门只拦高置信破绽。极端跨章逐字复用覆盖、长段跨章复制和嵌套说话人标签属于
blocking；句长塌缩和低量精确复读仍是 advisory。`pattern-saturation` 标记单章内
句首、短分句或整句被当成固定手势反复调用；`voice-anchor-surface-copy` 标记后续章
对 Voice exemplar 表层八字片段的重复挪用。这两项默认只提醒编辑器，不自动改稿，
也不把声音指纹变成 writer 的数值目标。中文叙事行混入 ASCII 逗号或直引号同样只做
advisory。机器不认证文学价值。

### Blind Reader

运行在不同于 writer `run_id` 的独立会话，只读当前正文，禁止读取 planning、memory、
其他章节或未来信息。重建空间、身体、
行动约束、情绪轨迹、对白动态和至少三个可记忆画面。必须填写：

`human_likeness: convincing | uncertain | synthetic`

只有 `convincing` 可配合 `verdict: pass`。清单化节奏、模板物件循环、解释性结论、
未来章节知识或工作流语言都应判为 `uncertain/synthetic + needs_revision`。
还必须填写 `reader_desire: continue | conditional | stop`、
`emotional_residue` 与 `next_chapter_pull`。只有 `continue` 可配合 pass；
还须填写五项重建与三个可记忆画面；`record-review` 拒绝空壳盲评。

### Chapter Editor

先只读正文重建事件链、选择、代价和停止点，再读 scene package、记忆包和上一章
末段，完成五项审查。仅有具体专业风险时按需调用一个
`causal-editor | line-editor | texture-editor | consistency-guard`；专业角色是兼容工具，
不是默认六审。
通过报告必须逐项填写因果、人物能动性、对白信息流、句子肌理和连续性；
`record-review` 会拒绝只有 verdict 的空壳综合审稿。

审稿必须绑定当前 chapter/planning/generation SHA、真实 reviewer/provider/model/context
与 `review_session_id`。blind-reader pass 使用 `context_scope=prose_only` 且
`review_session_id != generation.run_id`；ch02+ chapter-editor 还绑定
`previous_chapter_sha256` 和逐字 `previous_chapter_quote`。同模型换角色名不算独立。

## Token 边界与外置 Guardian

- 每章独立会话，只传有界 handoff；Guardian 的哈希、预算、回执都在本地执行，
  不回灌 ACP、完整 transcript、旧工具结果或验证器源码。
- `session-audit` 只认 `novel-forge-runtime/v1`。每章上限：30 请求、2,000,000
  cached-input tokens、单请求 120,000 context tokens；超限即停止。
- 正文默认 standard/medium，即标准或中等推理。Max/长思考只处理具名难题，
  结论压入 scene package；不用于整章、模板、状态、证据或默认审稿。
- 正文一次 Write、最多一次集中 Edit；默认两角色，专业加审后建议总调用不超过 3。
- generation 如实记录 `run_id`、provider/model/Harness、reasoning effort、
  token/request、draft/review 计数、`tool_capabilities` 与 `tool_failures`。
  指标只填本次增量；未知保持 null/unknown。
- formal ready 需要匹配 `run_id` 且未超限的外部审计；一章 runtime audit 只能绑定当前 generation，
  同一 writer `run_id` 不得跨章复用，计数缺失或超限均阻断。

## 事实与记忆

`memory/canon/**/*.md` 是长期权威源；`.novel-forge/index.sqlite3` 可重建且不得直改。
新事实、事件、知识变化和承诺只能先进入 candidate，经显式晋升后才成为 Canon。
事实、人物认知、人物假设与替代解释必须分开。审美偏好不能覆盖事实和因果责任。

## 稳定策略

稳定策略：`no-deliberate-defects`、`single-winner-branch`、
`model-score-not-approval`、`aesthetic-does-not-override-facts`、
`exploration-not-ready`、`role-name-not-independence`、
`world-not-protagonist-proof`、`expertise-must-be-executable`。含义以机器合同和
项目模板为准；核心是不伪造缺陷、不拼接胜者、不把模型结论当批准、不让审美覆盖事实。

## 证据与 Git

常用只读 op：`harness-contract`、`guardian-contract`、`chapter-sequence-status`、`project-status`、
`run-gates`、`evidence-status`、`memory-status`、`session-audit`、
`book-git-status`。
常用变更 op：`set-draft-mode`、`record-evidence`、`record-review`、
`record-session-audit`、`advance-state`、`begin-chapter-sequence`、
`claim-chapter-session`、`prepare-writer-capsule`、`ingest-writer-capsule`、
`record-capsule-runtime`、`authorize-regeneration`、`invalidate-chapter-session`、
`advance-chapter-sequence`、`sync-tools`、
`init-book-git`、`book-git-checkpoint`、`restore-book-git`、memory candidate/promotion。

`sync-tools` 会受控迁移带 v3.7/v3.8/v3.9/v4.0/v4.1/v4.2/v4.3 生成标记的
`CLAUDE.md`/`README.md`，补齐 v4.4 隔离 capsule、读者追读、运行真相、每书本地 Git 与章节序列，
并把旧状态映射到八态链；没有版本标记的手写项目宪法保持
不动。旧专业 Agent 文件可保留为历史兼容资产，但不再属于默认闭环。

同章同正文 SHA-256 只能算一个 generation。`harness_exposed` 必须有真实 `run_id`、
`agent_harness`、`metrics_source=harness_reported`、工具能力与失败。Agent 不得自称
`user_attested`。

未经用户明确要求，不得 commit、push 或执行 `git-checkpoint`。

## Legacy

`library/` 的状态机、lint、Reader Review、Blind Experience、Editorial Memo、
approval 与 export 均通过 adapter/service 执行。不得用 `--allow-below-minimum`
绕过正式小说 5000 CJK 门槛。

## 汇报

只汇报正文路径、CJK、机器门禁、blind-reader 的 `human_likeness` / `reader_desire`、
chapter-editor verdict、剩余文学/事实风险、runtime budget 和 Git 是否发生。
