---
name: novel-forge
description: Use when creating, planning, drafting, reviewing, auditing, repairing, or exporting a Novel Forge fiction project.
---

# Novel Forge

Novel Forge 是可审计的中文长篇生产链；文学目标是：**这篇小说像人写的吗？**

## 创作任务快速路径

创作时**不要探索仓库实现**，不读 `app/`、`tests/`、`docs/`、Git 历史或旧实验书。
首个写操作只能是：

```bash
python tools/novel-workflow.py --root <绝对仓库根> start <slug> \
  --title ... --genre ... --protagonist ... --world ... --conflict ... --hook ...
```

1. 运行 `next-action <slug>` 取得 Python 签发的有界动作。
2. 按动作创建或复用真实原生 Session；不得由 Lead 扮演角色。
3. Writer 只接收 Writer Capsule；审稿角色只接收 `review_capsule.path`，Lead
   禁止读取、复制、粘贴或重组 Capsule 内正文。
4. 等待宿主官方终态后，以动作自带的 `completion_template` 为唯一 JSON 骨架，
   只填真实终态、typed operation handle、Session、模型、`role_result` 和遥测，再运行
   `complete-role <slug> --from-file <临时JSON>`。
5. 重复到 Python 返回完成、决策或停止；不得自行推进状态、证据或 Git。

Writer 规划可做题材常识、重名与事实边界检索，默认最多 5 次；不得借此读源码。
正文和两个审稿角色不做开放式仓库探索。

## 选择入口

- **自动生产唯一入口**：`tools/novel-workflow.py start`。没有命令 Backend 时自动进入
  原生会话 Relay；宿主原生 Roles / Teams / Task Agent / Session 负责上下文隔离。
- Python 状态机决定下一步；宿主只负责创建、等待和回传，不写证据、状态或 ready。
  completed 必须绑定 role、session_id、session_instance_id、typed operation handle、
  结果通道和 `role_result`。必须使用宿主官方 wait / join 等到角色终态；
  创建成功、已接单、进度消息或文件暂时稳定都不算完成，`idle/available` 与晚到结果无效。
- 创作角色对项目仓库零写入：规划和审稿只回传结构化结果；Writer 只写仓库外
  capsule 的 `draft/正文.md`；异常产物或 `control_plane_mutation` 会废弃会话。
- 高权限只属于无模型推理的确定性控制面；新书先由确定性控制面通过 `init-novel-project` 初始化。
  不得自行创建正文、规划、审稿或 ready Git 恢复点；
  Blind Reader 正式记录后才能启动 Chapter Editor。宿主无法创建或等待真实独立
  Session 时只说明“本章未开始”；`degraded_exploration` 只有用户明确要求探索稿时才允许。
- ACP 只用于事后取证；模型偏好不绑定厂商，证据只认终态 `resolvedModel`。
  `NOVEL_FORGE_HARNESS_COMMAND` 只启用可选 headless 命令 Backend。
- 创作 Lead/角色不得创建、修改、修复、包装、安装或配置 Harness / SessionBackend；
  不得自行设置命令桥，不得向用户提供部署或配置 Harness 的选项。

## Books v5.2

默认状态链只有八态：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

`ready` 不是作者批准或发布许可；角色判断由真实会话返回，Lead 禁止代填。

### 隔离 Writer Capsule

Formal writer 不进入 `books/<slug>/`。默认 `formal_native` 使用仓库外 Capsule、
角色零项目写入和执行前后全仓快照；宿主具备真实文件系统沙箱时可透明升级为
`formal_sandboxed`。这不是用户 A/B 选择。writer
只见 `guardian-contract`、`handoff.md`、`formal-writer/v1` 的 `instructions.md` 和
`draft/正文.md`。runtime 经 `record-capsule-runtime` 外置，导入由 Guardian 核验。
额外文件、路径逃逸、保护输入变化或证明不实均为 `compromised`。无变化 Patch 记为
`no_content_change`，不创建 Generation 或刷新审稿。
`run_writer=launched` 后必须按 `operation_handle.kind` 用原句柄等待官方
`completed`，并取得 writer `role_result`；其中只允许返回 capsule 内相对路径
`draft/正文.md`，不得让 Writer 猜宿主绝对路径。`accepted`、`progress`、
`idle/available` 或文件稳定无效。完成信封或 Runtime Snapshot 装配错误时保留同一
Session/Capsule/正文，按模板补交同一终态，Lead 不得重跑 Writer。真实完整性或终态
失败才废弃 Session/Capsule，晚到旧稿不得覆盖重试稿。
协议不绑厂商；ACP 和完整 transcript 不是 formal 依赖；无法创建独立上下文或取得
官方终态时停止。

### 章节序列与新会话

正式一次只做一章，一章一个新 writer session；序列最多 4 章。用
`claim-chapter-session` 绑定 `session_instance_id` 对应的真实 session，角色名不能
代替会话。上一章完整 `ready` 后才运行 `advance-chapter-sequence`。交接只含硬锚、
相关 Canon、上一章末段与 Writer Story Brief；完整 Scene Package 是 Chapter Editor 控制面。

### 每书本地 Git

每书 Git 在 `.local-book-git/<slug>.git`，不得配置 remote；`book-git-status`
可查。自动建 `chapter: chNN draft` / `chapter: chNN ready`。删除实验书时同时清除
工作区、外置 gitdir、外置 Guardian 和临时 Capsule。

### 每章闭环

1. 新 Writer 先交付规划；用 `begin-chapter-sequence` 创建 1-4 章序列并立即
   `claim-chapter-session`。后续章按 launch directive 新建 Writer。再用
   `set-draft-mode` 固定 `formal | exploration | degraded_exploration`，并运行
   `prepare-writer-capsule` 创建仓库外隔离工作区。
2. 编排器核对记忆并生成有界 `chXX-handoff.md`；诊断用 `memory-status` /
   `rebuild-memory-index` / `build-memory-context`。工具失败即停止 formal。
3. context collector 只交付一页最小写作包：目标/阻力/选择/代价、相关
   Canon 与人物认知、最多三条承诺、上一章末段、必要规则和一个短 exemplar。
   不加载全书 Canon、旧审稿全文、模板或无关章节；引用既有 exemplar。
4. 一页式 `scene-package-chXX.md` 包含人物摩擦、替代解释、beat 因果、责任归属、
   常识反证和余波；重复字段只引用。关键对白意图与专业判断不得留空。
   ch02+ 的 `0b. 章际交接` 绑定上一章路径、SHA-256、末段短引及时间/地点/动作；
   还要写明上一章末明确决定、本章是否推翻该决定；若推翻，必须引用本章前 40%
   出现的触发事件原文，不能用事后解释替代桥接。
    本章开头短引在 `scene_packaged` 可写 `deferred_until_drafted`；完成后推进
    `scene_packaged`，起草后回填真实短引，formal gate 前不得保留 deferred 标记。
    Orchestrator 将六项输入原样注入 `0a. 用户硬锚合同`，规划不得改写。
5. 一名 writer 只读 instructions、handoff 与 patch 时预置正文，在 capsule 内处理一章。
   正式章不少于 5000 CJK；不要边查字数
   边连续补写。writer 只写 `draft/正文.md`；确定性控制面先经
   `record-capsule-runtime` 写入外置 runtime，再运行 `ingest-writer-capsule`，
   取得干净 Guardian 回执。集中 patch 使用预置当前正文的新 capsule；第三个潜在
   正文版本必须先经 `authorize-regeneration` 获得绑定前两版哈希的签名授权。
   无变化 Patch 保留失败回执，不产生新 Generation。
   writer 只接收叙事功能，不接收句长、对白率等数值风格指标；规划是后台故事义务，
   正文允许误判、遗漏和延迟反应。
   `正文.md` 除标题外只含叙事文本，不得出现 Markdown 粗体、提示词、Agent 身份、
   `ch05`、`正文.md`、generation evidence/id、SHA-256、surface_checked、ready
   等生产元数据。
6. Guardian 导入成功后记录并绑定 generation evidence；其中
   `prompt_template_id`/`prompt_sha256` 必须匹配签名回执。运行期间持续审计标准累计
   快照，结束时经
   `record-session-audit` 固化脱敏证据，再运行 `run-gates` 推进
   `surface_checked`；任一 blocking 都短路。
7. 默认只运行两角色：blind-reader 与 chapter-editor。blind-reader 必须在不同于
   writer `run_id` 的会话中只读正文，并记录真实 `review_session_id`；同一写作会话
   只能填写 `context_scope=simulated_blind` 与 `needs_revision`，不能 pass。
   pass 还必须给出 `reader_desire=continue`、`emotional_residue` 与
   `next_chapter_pull`，证明一个真人会自愿追读，而不是只证明画面可重建。
   两者分别落盘并经 `record-review` 校验；逐项判断必须来自审稿会话，编排器不得
   代填。三角色须有不同 `session_instance_id` 和外置完成凭证。不得暂停询问审核。
    Python 分别封存 Review Capsule：Blind 只含当前正文，Editor 加场景包、硬锚、
    必要 Canon、Blind Review 和机器诊断；动作不含正文，Lead 只传路径。manifest
    绑定当前正文，篡改后换新审稿 Session 并重新封存。
    审稿 completed 但完成信封缺字段时先按 `completion_template` 补交同一终态；
    实质结果失败才换同角色 session，最多两次。四个创作阶段分别计数；Blind 成功后
    Editor 从零开始。有效 Generation 的 `retry` 继续审稿，不重写正文。耗尽后才显示
    A/B/C。无法创建独立审稿会话时返回
    `review_session_required`，不得改成开放式提问。
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

`literary-micro-rules/v4` 是短规则唯一来源；日常不加载样本全文。三角色按“可以写、
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

`memory/canon/**/*.md` 不得直改；新信息先作 candidate，晋升后进入 Canon。
策略 ID：`no-deliberate-defects`、`single-winner-branch`、`model-score-not-approval`、
`aesthetic-does-not-override-facts`、`exploration-not-ready`、
`role-name-not-independence`、`world-not-protagonist-proof`、`expertise-must-be-executable`。

## 证据与 Git

只读：`project-status`、`run-gates`、`evidence-status`、`memory-status`、
`chapter-sequence-status`、`session-audit`、`book-git-status`。变更参数查 `--help`。

`sync-tools` 只迁移带版本标记的生成文件到 v5.2；手写项目宪法不动，旧专业 Agent
仅作兼容资产。

同章同正文 SHA-256 只能算一个 generation。`harness_exposed` 必须有真实 `run_id`、
`agent_harness`、`metrics_source=harness_reported`、工具能力与失败。Agent 不得自称
`user_attested`。

未经用户明确要求，不得 commit、push 或执行 `git-checkpoint`。
