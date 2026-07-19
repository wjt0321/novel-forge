---
name: novel-forge
description: Use when creating, planning, drafting, reviewing, auditing, repairing, or exporting a Novel Forge fiction project.
---

# Novel Forge

Novel Forge 是可审计的中文长篇生产链，不是自动写书机。文学目标始终回到一个问题：
**这篇小说像是人类写的吗？**

## 选择入口

- 新写作项目：`books/<slug>/`，正文唯一入口为
  `chapters/eXX/ch-XX/正文.md`。
- 需要 SQLite revision、审批或导出：`library/<slug>/`。
- 两者并用时，以 `books/` 为正文源，定稿后单向提交到 `library/`。
- 不直接编辑任何 SQLite、`library/**/revisions/` 或不可变 `evidence/`。

Adapter 从仓库根运行，`--root` 必须是绝对路径；变更操作必须
`--confirm <operation>`。先用 `--help` 查看参数，不在 Skill 中复制全部 CLI。

## Books v4.1

默认状态链只有八态：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

`ready` 只是材料齐备，不是作者批准或发布许可。

### 通用 Harness Contract

开始 formal 写作前，任何 Agent/Harness 都先读取本书
`evaluation/harness-contract.json`，或调用只读 op `harness-contract`。核心协议与
模型厂商、Agent 产品、Shell 类型无关：Harness 把自己的原生遥测规范化为
`novel-forge-runtime/v1` 累计快照；系统只认标准字段，不要求识别产品名称。

每次模型响应后更新一次累计快照，并在发起下一次模型请求前运行 `session-audit`。
只要 `budget.continue_allowed=false` 就立即停机；writer、editor 或角色提示词都无权
豁免。无法输出标准快照的运行只能进入 exploration/degraded_exploration，不能 ready。

### 章节序列与新会话

正式生产的执行单位不是“一次写几章”，而是**一章一个原生 writer session**。
Novel Forge 不直接调用任何厂商创建会话，而是维护
`planning/chapter-sequences/<sequence-id>.json`，向外部 Harness 返回机器可读
launch directive：

1. 用户要求 1 章：运行 `begin-chapter-sequence --chapter-count 1`。
2. 用户要求连续多章：同一编排器可自动顺序执行，但单次序列最多 4 章；五章及以上
   必须拆分，禁止用一个 writer session 连写。
3. Harness 按 launch directive 创建新的原生 writer session，并用
   `claim-chapter-session` 绑定真实 session ID。角色名、子 Agent 名和编排器 ID
   都不能代替原生 writer session ID。
4. writer 只处理当前一章；上一章完整 `ready` 后必须结束其 writer session。
   编排器再运行
   `advance-chapter-sequence`，只有返回 `launch_next_session=true` 时才顺序创建
   下一章的新 session。
5. 同一 session ID 不得用于另一章或另一书；generation `run_id` 必须等于 claim
   的 session ID。上一章未完整 `ready` 时不得签发下一章。

章节交接包固定写入 `memory/context-cache/chXX-handoff.md`，只含相关 Canon/人物
认知与开放承诺、上一章末段及 SHA-256、Voice exemplar 和当前 scene package。
不得续传旧会话消息、旧工具输出、旧审稿全文、整本正文或其他书资产。

### 每章闭环

1. 用 `begin-chapter-sequence` 创建 1-4 章序列，读取当前章 launch directive，
   创建新的原生 writer session 后立即 `claim-chapter-session`。再用
   `set-draft-mode` 固定 `formal | exploration | degraded_exploration`。
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
5. 一名 writer 一次写完整章。正式章不少于 5000 CJK；不要边查字数边连续补写。
   writer 只接收叙事距离、信息释放和节奏功能，不接收句长、对白率、比喻密度等
   数值风格指标，也不得复制 Voice exemplar 的具体名词、标志动作、收尾物件或句法。
   `正文.md` 除标题外只含叙事文本，不得出现 Markdown 粗体、提示词、Agent 身份、
   `ch05`、`正文.md`、generation evidence/id、SHA-256、surface_checked、ready
   等生产元数据。
6. 记录并绑定 generation evidence；运行期间持续审计标准累计快照，结束时经
   `record-session-audit` 固化脱敏运行证据。之后运行 `run-gates` 并推进
   `surface_checked`。runtime、来源、质量、叙事或文学结构任一 blocking 都立即
   短路，不启动审稿、不准备下一章。
7. 默认只运行两角色：blind-reader 与 chapter-editor。blind-reader 必须在不同于
   writer `run_id` 的会话中只读正文，并记录真实 `review_session_id`；同一写作会话
   只能填写 `context_scope=simulated_blind` 与 `needs_revision`，不能 pass。
   两者分别落盘并经 `record-review` 校验；不得暂停询问“是否开始审核”。
8. 合并两份 finding，只允许一次有范围的集中 patch。第二份不同正文 SHA-256
   后若仍有新 MUST，进入 `human_decision_required`；不得自动生成第三份。
   ch05/ch10/... 还需当前 checkpoint arc audit，`open_must=0`。进入 ready 前，
   八态证据表不得保留 `-`/空值，并给出当前 ready 决定的 evidence 指针。本章
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
通过报告还必须填写空间、身体、行动约束、情绪、对白五项重建与三个可记忆画面；
`record-review` 会拒绝空壳盲评。

### Chapter Editor

先只读正文重建事件链、选择、代价和停止点，再读取一页式 scene package、
当前记忆包及上一章末段。一次完成因果与有限认知、人物/世界独立目标、对白信息流、
句子肌理和连续性五项审查。仅当出现具体专业风险时，按需调用一个
`causal-editor | line-editor | texture-editor | consistency-guard`；专业角色是兼容工具，
不是默认六审。
通过报告必须逐项填写因果、人物能动性、对白信息流、句子肌理和连续性；
`record-review` 会拒绝只有 verdict 的空壳综合审稿。

审稿必须绑定当前 chapter/planning/generation SHA、真实 reviewer/provider/model/context
与 `review_session_id`。blind-reader pass 使用 `context_scope=prose_only` 且
`review_session_id != generation.run_id`；ch02+ chapter-editor 还绑定
`previous_chapter_sha256` 和逐字 `previous_chapter_quote`。同模型换角色名不算独立。

## Token 边界与外置 Guardian

- 每章使用独立写作会话；只传有界 `chXX-handoff.md`，不携带前章会话、工具日志和
  审稿全文。长篇连续性由外部状态证明，不依赖模型在长会话中“记得”。
- 运行预算由 `session-audit` 读取 `novel-forge-runtime/v1` 累计快照，不信任
  generation 自报。未知 Harness 只需实现该格式；内置产品日志解析仅是兼容导入器。
  默认硬上限为每章 30 个请求、2,000,000 cached-input tokens，单次请求上下文
  120,000 tokens；任一超限即 `continue_allowed=false`，停止自动准备下一章。
  2,000,000 是止损上限，不是目标；新 session 应从有界交接包开始，不能继承旧章
  的整包 cached context。
- 正文默认 standard/medium。Max/长思考只用于用户明确的推理基准，或真正困难的
  写前反证/因果裁决；规划与困难因果检查可用高推理，正文起草与默认审稿使用
  标准或中等推理。Max 必须绑定一个具名难题，结论压缩进 scene package，不得让
  整章自由生成长期处于 Max。Max/长思考不用于目录、模板、状态、证据和默认审稿。
- 正文目标：一次完整 Write，最多一次集中 Edit。
- 默认审稿调用：2；专业加审后建议不超过 3。
- generation 如实记录 `run_id`、provider/model、`agent_harness`、reasoning effort、
  `cached_input_tokens`、`request_count`、
  `draft_write_count`、`draft_edit_count`、`review_call_count`、
  `tool_capabilities` 与 `tool_failures`。未知保持 null/unknown，不估算精确数字。
- 每份 generation 的运行指标只填本次增量，不把会话累计总数重复复制到多份记录。
  `evidence-status` 按章累计，状态为 `unassessed | partial | within_budget | exceeded`；
  但 formal ready 还必须存在匹配 `run_id`、来源一致且未超限的 runtime audit。

## 事实与记忆

`memory/canon/**/*.md` 是长期权威源；`.novel-forge/index.sqlite3` 可重建且不得直改。
新事实、事件、知识变化和承诺只能先进入 candidate，经显式晋升后才成为 Canon。
事实、人物认知、人物假设与替代解释必须分开。审美偏好不能覆盖事实和因果责任。

## 稳定策略

- `no-deliberate-defects`: 不用错字、事实错误、随机病句伪造人味。
- `single-winner-branch`: 分支只保留一个胜者，不静默拼接候选。
- `model-score-not-approval`: 模型评分、gate 与 ready 都不是作者批准。
- `aesthetic-does-not-override-facts`: 审美不覆盖 Canon、证据、认知与责任。
- `exploration-not-ready`: 探索稿和降级稿不能进入 ready。
- `role-name-not-independence`: 角色名不同不代表独立审稿。
- `world-not-protagonist-proof`: 世界和配角不得只负责证明主角正确。
- `expertise-must-be-executable`: 专业判断必须有证据、条件、成本与风险。

## 证据与 Git

常用只读 op：`harness-contract`、`chapter-sequence-status`、`project-status`、
`run-gates`、`evidence-status`、`memory-status`、`session-audit`。
常用变更 op：`set-draft-mode`、`record-evidence`、`record-review`、
`record-session-audit`、`advance-state`、`begin-chapter-sequence`、
`claim-chapter-session`、`advance-chapter-sequence`、`sync-tools`、
memory candidate/promotion。

`sync-tools` 会受控迁移带 v3.7/v3.8/v3.9/v4.0 生成标记的
`CLAUDE.md`/`README.md`，补齐 v4.1 文学防过拟合与章节序列目录，并把旧状态映射到
八态链；没有版本标记的手写项目宪法保持
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

只汇报正文路径、CJK、机器门禁、blind-reader 的 `human_likeness`、
chapter-editor verdict、剩余文学/事实风险、runtime budget 和 Git 是否发生。
