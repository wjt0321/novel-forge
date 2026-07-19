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

## Books v3.8

默认状态链只有八态：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

`ready` 只是材料齐备，不是作者批准或发布许可。

### 每章闭环

1. `project-status` + `evidence-status`，确认上一章无 blocking 且 runtime budget
   未超限；再用 `set-draft-mode` 固定 `formal | exploration | degraded_exploration`。
2. formal 先跑 `memory-status`；`stale` 时执行 `rebuild-memory-index`，仅在
   `clean` 时运行 `build-memory-context`。工具受限必须降级并记录真实失败。
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
   本章开头短引在 `scene_packaged` 可写 `deferred_until_drafted`；完成后推进
   `scene_packaged`，起草后回填真实短引，formal gate 前不得保留 deferred 标记。
5. 一名 writer 一次写完整章。正式章不少于 5000 CJK；不要边查字数边连续补写。
   `正文.md` 除标题外只含叙事文本，不得出现 Markdown 粗体、提示词、Agent 身份、
   `ch05`、`正文.md`、generation evidence/id、SHA-256、surface_checked、ready
   等生产元数据。
6. 记录并绑定 generation evidence，再运行 `run-gates`，成功推进
   `surface_checked`。任何 blocking 立即短路，不启动审稿、不准备下一章。
7. 默认只运行两角色：blind-reader 与 chapter-editor。两者分别落盘并经
   `record-review` 校验；不得暂停询问“是否开始审核”。
8. 合并两份 finding，只允许一次有范围的集中 patch。第二份不同正文 SHA-256
   后若仍有新 MUST，进入 `human_decision_required`；不得自动生成第三份。
   ch05/ch10/... 还需当前 checkpoint arc audit，`open_must=0`。进入 ready 前，
   八态证据表不得保留 `-`/空值，并给出当前 ready 决定的 evidence 指针。

## 文学门

机器 lint 只拦高置信破绽，并报告跨章精确复读、句长塌缩等风险；它不认证文学价值。

### Blind Reader

只读当前正文，禁止读取 planning、memory、其他章节或未来信息。重建空间、身体、
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

审稿必须绑定当前 chapter/planning/generation SHA、真实 reviewer/provider/model/context。
blind-reader 使用 `context_scope=prose_only`；ch02+ chapter-editor 还绑定
`previous_chapter_sha256` 和逐字 `previous_chapter_quote`。同模型换角色名不算独立。

## Token 边界

- 每章使用独立写作会话；只传最小交接包，不携带前章工具日志和审稿全文。
- 正文默认 standard/medium。Max/长思考只用于用户明确的推理基准，或真正困难的
  写前反证/因果裁决；结论压缩进 scene package，不另建反证报告。Max/长思考不用于
  目录、模板、状态、证据和默认审稿。
- 正文目标：一次完整 Write，最多一次集中 Edit。
- 默认审稿调用：2；专业加审后建议不超过 3。
- generation 如实记录 `cached_input_tokens`、`request_count`、
  `draft_write_count`、`draft_edit_count`、`review_call_count`、
  `tool_capabilities` 与 `tool_failures`。未知保持 null/unknown，不估算精确数字。
- 每份 generation 的运行指标只填本次增量，不把会话累计总数重复复制到多份记录。
  `evidence-status` 按章累计，状态为 `unassessed | partial | within_budget | exceeded`；
  超限时停止自动准备下一章，先压缩会话和上下文。

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

常用只读 op：`project-status`、`run-gates`、`evidence-status`、`memory-status`。
常用变更 op：`set-draft-mode`、`record-evidence`、`record-review`、
`advance-state`、`sync-tools`、memory candidate/promotion。

`sync-tools` 会受控迁移带 v3.7 生成标记的 `CLAUDE.md`/`README.md`，并把旧状态
映射到八态链；没有版本标记的手写项目宪法保持不动。旧专业 Agent 文件可保留为历史
兼容资产，但不再属于默认闭环。

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
