---
name: novel-forge
description: "当需要创建、策划、起草、修订、审阅、质检、审计或导出 Novel Forge 小说项目时使用。"
whenToUse: 当用户要求创建小说项目、撰写或修改章节正文、运行质量门禁、记录审稿、推进章节状态机或导出小说时使用
metadata:
  version: "2.9"
  entrypoint: "app.novel_forge.skill_adapter"
---

# Novel Forge 小说创作

本 Skill 用于管理 Novel Forge 小说资产。不得直接改 SQLite 数据库或不可变 revision 文件。

## 路径与工作目录

- **不要硬编码盘符或绝对根路径。** 一律从当前工作目录、调用参数，或项目根的相对结构推导路径。
- 调用 adapter 时，`--root` 必须传入**仓库根目录的绝对路径**；不要传 `.`。从项目根启动时，可先由 shell 解析当前绝对路径：

```cmd
set "NOVEL_FORGE_ROOT=%CD%" && set PYTHONPATH=%NOVEL_FORGE_ROOT% && python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" <operation> ...
```

- `books/<slug>/` 是新项目的文件前台；`library/<slug>/` 是 legacy 审计工作流。
- 不得静默混用两套工作流。需要两者共用时，先在项目说明中声明哪一处是正文唯一来源。

## 选择工作流

- **新建项目、在写作 Agent 项目内写作：** 默认 `books/<slug>/`。它自带完整质量门（lint、narrative_gate、五个审稿角色、盲读者、宏观编辑），不需要数据库。
- **需要 SQLite 审计、不可变 revision 历史、Canon 事实库或 Pandoc 导出：** 使用 `library/<slug>/` adapter 工作流。
- **两者都要：** 以 `books/<slug>/` 为正文唯一来源，写定后用 `write-revision` 把定稿提交进 `library/` 审计；不要反向流动。

## 新项目工作流：`books/<slug>/`

用户明确要求创建后，在仓库根目录执行（`--root` 使用绝对路径）：

```cmd
set "NOVEL_FORGE_ROOT=%CD%" && set PYTHONPATH=%NOVEL_FORGE_ROOT% && python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" --confirm init-novel-project init-novel-project <slug> --title "<书名>" --genre "<类型>"
```

genre 决定 voice-bible 预设（都市现实 / 幻想修真 / 末世科幻 / 通用），请如实填写。

生成的核心文件：

- `CLAUDE.md`：本书宪法与进度
- `chapters/eXX/ch-XX/正文.md`：章节唯一正文
- `memory/`：既成事实、实体、世界规则、未来规划与 **voice-bible.md（本书声音宪法）**
- `planning/`：故事发动机、研究边界、场景包、动作稿、对白账本、章节状态
- `evaluation/`：评测宪法、实验设计与证据输入模板
- `evidence/`：不可变创作证据（生成、分支、盲评、偏好、跨章审计、规则决定）
- `reviews/`：审稿记录（每个角色一份，含 verdict）与 `review-template.md`
- `.claude/agents/`：八个审稿/编排角色定义（见下）
- `tools/quality_check.py` 与 `tools/narrative_gate.py`：**仓库规则的薄壳**，不要手工编辑；用 `sync-tools` 统一刷新

### 文字质感层（去 AI 味的核心）

禁令只能去掉最粗糙的破绽，人味来自正面引导。每本书的 `memory/voice-bible.md` 是文字质感的唯一载体。**起草与审稿前，先读两份解剖文档：`docs/examples/human-flavor-anatomy.md`（正面技法）与 `docs/examples/ai-flavor-antipatterns.md`（反面模式）**——它们是从试验品中固化的证据，每条都标了由哪道门拦截。

- **节奏管方差，不管长短**：一段之内句长要有可感的起伏。全短的均匀段是碎，全长的均匀段是糊。lint 的 `sentence-rhythm` 规则按句长变异系数检测。
- **比喻有配额**：每章 ≤3 个；删弱比喻，找准确的词。lint 的 `simile-density` 规则（≥3/千字）预警。
- **锚定物象**：每章 3-5 个实物（可操作、可磨损、有价格或来历），登记在场景包 3b 节；可记忆画面骑在物件上，不骑在形容词上。
- **角色语言指纹是症状，不是标签**：每个主要角色的语言习惯来自其经历；紧张时句子怎么变、永远不说哪种话。
- **范文锚定（exemplar_notes）**：第 2 章起，从本书已写章节选一段最代表目标声音的正文贴入 voice-bible，起草前校准。narrative_gate 会检查。
- **声音指纹**：把范文段落的可量化风格指标（句长均值/方差、对白占比、比喻密度、分句复杂度等）一并贴上——在仓库根运行 `PYTHONPATH=. python -m app.novel_forge.voice_signature <章节文件>` 生成。"像不像这本书"由此变成可测量的距离：起草时对齐它，texture-editor 用它做漂移检查（`--vs` 对比）。
- **语域配比**：人味不是单一语域，是按文本功能换挡。voice-bible 的语域地图给出叙述者在场度分档（0 隐形摄像机 / 1 贴身跟随 / 2 讲者现身 / 3 讲者抒情），场景包 beat 表逐拍声明，起草按拍换挡。默认起草语域是"把正在发生的事讲给一个具体的人听"（开场与插叙尤其），不是"写一章小说"；收束段允许经营最后一个画面，但不许点评主题。
- **写前独白**：动笔前以主角第一人称写 300-500 字独白（不进入正文），找到他/她此刻最不想想的事。
- **术语预算**：每章新生造术语 0-2 条，登记在场景包第 5 节；每条必须落到身体接触、相对位置、可操作物或受阻动作，不得以解释性旁白落地。lint 的 `term-density` 规则做密度预警。

### 人类叙事证据 v3.6

“像人写的”不是允许事实错误，也不是在句面随机撒噪声。工作流把它拆成五个可分别观察的层：

1. **事实秩序**：Canon、来源证据、时间线和人物知识边界必须稳定。
2. **因果秩序**：每场都有欲望冲突、拒绝、误读、不能说出口的话、选择与被接受的代价。
3. **有限认知**：人物只能凭其已知信息行动，允许合理误判，但不允许作者替人物全知。
4. **表达不均匀**：节奏、语域、细节密度和句法随场景功能变化；方差来自压力与选择，不来自随机缺陷。
5. **作者偏好**：以盲评、单胜者分支和偏好证据积累；偏好不能覆盖事实与因果。

以下策略 ID 是项目宪法、Agent 角色和证据层共同使用的稳定边界：

- `no-deliberate-defects`：不得用故意错别字、事实错误、随机病句或机械噪声伪造人类感。
- `single-winner-branch`：分支实验必须选择一个胜者并记录其代价，不得静默拼接全部候选。
- `model-score-not-approval`：模型评分、门禁通过和 ready 状态都不是作者批准或发布许可。
- `aesthetic-does-not-override-facts`：审美偏好不能覆盖 Canon、事实证据、因果责任或人物已知边界。
- `exploration-not-ready`：探索稿可跳过正式材料门，但不得进入 ready 或冒充正式章节。
- `role-name-not-independence`：角色名不同不构成独立审稿；必须记录 reviewer/provider/model/context。
- `world-not-protagonist-proof`：世界不得只为证明主角正确而排列线索；重要推断必须保留替代解释和可推翻条件。
- `expertise-must-be-executable`：专业判断必须写清证据、未证前提、执行条件、成本与风险，不能只靠术语证明人物聪明。

每章开始前必须用 `set-draft-mode` 持久化模式：

- `formal`：正式章；执行 5000 CJK、场景包、书级材料、generation evidence、六角色审稿和检查点审计。
- `exploration`：探索片段；允许快速试声、试场景或试分支，但 `ready_eligible=false`，不能用命令行参数临时伪装成正式稿。
- `degraded_exploration`：Shell、adapter、子代理或关键工具不可用时的降级探索；必须用 `evaluation/degraded-run-template.md` 如实记录 `sandbox_profile`、`tool_capabilities` 与 `tool_failures`。它不能进入 `ready`、`benchmark_eligible` 或静默升级为 formal。

正式场景包必须填写“决策问题”“规划反证与常识检查”和“场景余波”。决策问题五项中至少两项必须真实成立；“立章”只调整信息密度与语域，不能把拒绝、误读、不可说的话和代价全部豁免。场景余波记录身体、物件、关系、认知/误信和未偿债务，使本章后果能被后续章节继续读取。

第 2 章起，正式场景包还必须填写 `0b. 章际交接`：上一章正文路径与 SHA-256、上一章结尾和本章开头的逐字短引、两章交界的时间/地点/动作，以及 `same_day_continuous` / `cross_day` / `flashback` / `parallel` 转场类型。上一章短引必须位于章末 20%，本章短引必须位于章首 20%；同日连续场景不得出现未解释的时间倒退。

正式场景包还必须处理三类语义责任：

- **认知与可证伪假设**：把“观察事实 / 人物假设 / 替代解释 / 置信度 / 可推翻证据 / 当前状态”分开。没有关键推断时必须给出具体豁免理由。
- **因果归属账本**：记录会改变行动条件的动作或约定由谁提出/执行、作用于谁、谁当场知情、谁承担后果。它用于阻止“明明是主角提出三日期限，后文却说成对方选择”的责任漂移。
- **专业判断审计**：金融、医疗、法律、刑侦、工程、历史制度与职业手艺等判断只要推动关键行动，就登记证据、未证前提、执行条件、成本/风险和证伪方式；没有专业判断时明确说明。
- **规划反证与常识检查**：逐项核对时间/日历算术、物理动作机制、人物知识来源、不可逆性反证和场景停止点。没有具体日期或装置时可以写“无需：<具体原因>”，但不得留空。该门只证明做过反证，不自动认证答案正确。

“让人物不再永远比世界正确”不是让人物故意犯蠢。它要求世界和其他人物保有独立目标；聪明人物可以形成高质量假设并据此下注，但旁白不得把微表情、沉默或单一迹象写成唯一答案。至少有一部分重要判断应保持未决、被修正，或以代价验证。

需要比较写法时，把候选放在 `evaluation/experiments/<experiment-id>/candidates/`，使用匿名标签做具体问题盲评，再记录 branch evidence。只能选一个胜者；其他候选的价值以“被放弃的代价”保存，不能把所有优点静默拼接成折中稿。

generation、review、planning 和正文用 SHA-256 指纹绑定。同章同正文 SHA-256 只算一个 generation；换 evidence ID、阶段或 review_round 不得制造新轮次。第四个及后续不同正文版本只有在 `author` / `human_delegate` 提交 `human_regeneration_authorized=true` 和非空 `human_decision_reference` 时才可写入；这不代表作者批准正文。正文、场景材料、模式或 generation 改变后，旧审稿变 stale，必须重读修订后的完整正文。第 2 章起，consistency-guard 与 chapter-editor 的 `previous_chapter_sha256` 进入来源指纹；上一章变化只使这两个跨章角色 stale，不强迫其他四个角色无关重审。blind-reader、consistency-guard 与 chapter-editor 必须提供逐字存在于正文的 `evidence_quote`；后两者从第 2 章起还必须提供 `previous_chapter_quote`。blind-reader 必须 `context_scope=prose_only`；causal-editor 与 chapter-editor 必须先只读正文完成 prose-only reconstruction，再打开规划比较 planning delta。审稿与生成使用相同 provider/model 时必须披露，且即使换角色名也不自动算独立。`project-status` 与 `ready` 会重新运行完整审稿校验，直接写权威 review 文件不能绕过 `record-review`。

`ready` 与 `benchmark_eligible` 分离。同源审稿在来源如实披露时仍可完成本地生产链，但只有当前 blind-reader 与 chapter-editor 均通过且与 generation 异源时，才具备跨模型比较资格。`project-status` 同时返回 `review_confidence` 和 `workflow_integrity`，主动暴露缺失 state、正文停在 planned、generation 未记录/过期、review 过期/非法、嵌套重复审稿文件与占位证据。`reviews/chXX-<role>.md` 是审稿唯一权威路径；`reviews/chXX/<role>.md` 一类副本会取消 benchmark 资格，但不会被自动删除。

generation evidence 可记录 `run_id`、`agent_harness`、`reasoning_effort`、`sandbox_profile`、`tool_capabilities`、`tool_failures`、`elapsed_seconds`、input/output/total tokens、`metrics_source`、暂停/交互次数、`review_round`、父 generation、`generation_stage` 和 `provenance_confidence`。未知值必须保持 null/unknown/空数组，不得编造精确成本。`user_attested` 只能由 author 或 human_delegate authority 记录；Agent 不得自称获得了用户证明。

第 5、10、15……章进入 `ready` 前必须存在 `scope=checkpoint` 且 `open_must=0` 的 arc audit。`source_paths` 必须覆盖范围内每一章，`source_sha256` 必须逐项匹配；任一来源变化都会令审计 stale。卷终另做 `scope=volume` 审计；两者语义不同，不能用五章检查点冒充卷级收束。

### 长篇 v3.7 编排

每个新项目默认具备以下资产；所有状态、记忆和审稿结果必须保留在**各自** `books/<slug>/` 内，不得放到 `books/` 顶层共享：

- `.claude/agents/orchestrator.md`：单章状态机、门禁证据与回退决策；不写正文。
- `planning/chapter-state/chXX.md`：记录章节状态、最小上下文预算、阻断项与下一步；证据表只存文件指针与 verdict。
- `planning/scene-package-chXX.md`、`action-draft-chXX.md`、`dialogue-ledger-chXX.md`：分别承载场景因果（含认知、因果归属与专业审计）、动作底稿和关键对白意图。
- 审稿角色：`causal-editor`（因果、认知责任、归属与专业可执行性）、`line-editor`（对白归属与行动性、重复簇、能力证明循环、解释性旁白）、`texture-editor`（句子工艺：分句堆叠、排比、比喻、解释腔、句长方差、套话）、`consistency-guard`（实体/时间线/承诺/知识边界/责任归属）、`blind-reader`（只读正文重建画面）、`chapter-editor`（宏观五维，输出 verdict）。均不直接改写正文。
- 以上角色按职责分派给你可用的子代理机制；`.claude/agents/` 是职责定义的存放处，不绑定特定 harness。

状态链：

`planned → context_collected → scene_packaged → action_drafted → dialogue_planned → drafted → surface_checked → causal_reviewed → line_reviewed → texture_reviewed → consistency_checked → blind_read → editorial_reviewed → ready`

向前迁移只能逐个相邻状态推进；允许明确回退到更早材料层。`record-review` 只记录证据，不自动推进状态。`surface_checked` 会重跑机器 lint；存在 blocking 时不得推进，也不得启动任何审稿角色。失败必须回退到对应材料层，而不是直接用措辞润色掩盖结构问题。`ready` 仅允许正式稿进入，并要求当前 generation、正式门禁、六个审稿角色全部有效：causal/line/texture/consistency/blind 为 pass，chapter-editor 为 ready_for_editor_decision；检查点章节还要求 arc audit。`project-status` 会复核旧 `ready` 章节的当前门禁，规则升级后失效的旧状态会进入 workflow integrity blocker。**复审协议：任何角色复审时必须重读修订后的完整正文与 patch 记录，而不是仅核对原 finding 是否被删除**——"删过了"不等于"剩下的没问题"。

正式模式的审核批次是已声明流程，不得在门禁后暂停询问“是否开始审核”。六角色先各自落盘，orchestrator 再去重同源 finding、合并回退层级并只形成一次集中 patch。第一份 generation 是初稿，第二份是合并 patch，第三份是终审版本；第三份完成后若仍有新 MUST，必须进入 `human_decision_required`，不得自动生成第四份。MAY 不触发整章回炉。

自动回炉预算按**不同正文 SHA-256**计算，不按 evidence 文件数量计算。原始正文起草默认使用 standard/medium 推理；Max/长思考优先用于写前反证、章际交接、因果责任和审稿 findings 合并，或用户明确声明的推理强度基准实验。即使正文使用 Max，也不得把 Max 自动复制到六个同源审稿角色；不用于重复生成模板、目录或同一正文的多份自证材料。

即使模型支持超长上下文，writer 也应只加载去除模板格式的最小摘要、当前场景、近场连续、相关人物/承诺及必要世界规则，保留剩余上下文用于推理和审稿；全书材料只用于季末或跨章审计。上一章存在 source-hygiene blocking 时不得准备下一章，避免格式污染跨章自我复制。

- **情感弧：** 场景包的可选情感弧记录开场、不可逆选择和章末残余状态；正文应用身体、注意力与选择呈现变化，不直接替角色命名情绪。
- **跨章一致性：** `consistency-guard` 必读 `memory/future/00-index.md`，对承诺标记兑现、保持未回收、延后或"偏离：X"。
- **patch：** 使用 `patches/ch-{章节号}-{功能}.md`，仅记录局部修订；应用后重跑 `quality_check.py`、`narrative_gate.py` 和受影响编辑审稿。

### 单章 v3.7 流程

1. **调研：** 写手自行检索与主题有关的现实素材，保留来源链接；区分已核验事实与虚构内容。不得仿写在世作家，只能使用可说明的文学技法。
2. **故事发动机：** 在 `planning/` 写清主角欲望、阻力、对手/世界的独立目标、主角可能错误的模型、不可逆选择、即时成本和一个尚未解答的承诺。正式稿不得使用空故事发动机。
3. **定模式：** 用 `set-draft-mode` 选择正式、探索或降级探索；工具受限时先记录真实失败，不得自行猜造完整目录并宣称 formal 完成。
4. **填材料：** 正式稿的 `memory/worldbuilding.md` 与 `planning/research-boundaries.md` 必须填写或显式标注"无需"；voice-bible 填好语言指纹与感官调色板。空模板会被 narrative_gate 拦下。
5. **场景包：** 填写 `scene-package-chXX.md`，明确边界、目标、阻力、至少两项真实决策摩擦、认知/可证伪假设、规划反证五项、在场者状态、beat 因果链、因果归属、信息预算、专业判断审计与场景余波；第 2 章起补齐 `0b. 章际交接`。
6. **动作与对白：** 写 `action-draft-chXX.md`；场景包声明有关键对白时必须写 `dialogue-ledger-chXX.md`。正文润色不得新增动作稿外的关键事件、设定、动机或谜团。
7. **上下文：** `context-collector` 只读必要记忆、规划、研究边界、voice-bible、当前场景材料和上一章结尾；不得写正文。
8. **起草与取证：** 一名写手只写一章，从正在发生的行动开始；`正文.md` 除章节标题外只写纯叙事文本，禁止 `**粗体**`、`__强调__` 等 Markdown 粗体/强调语法，不得模仿规划模板标签。按语域声明换挡起草，不批量生成后续章节。专业能力优先通过提问、下注、操作和后果显形，不反复用履历/原理解释证明人物聪明。写后按真实运行记录 provider、model、run_id、Agent harness、推理强度、沙箱、工具能力/失败、上下文来源和可得的耗时/token/暂停/轮次，生成证据绑定当前章；来源不实的样本不得进入模型比较。
9. **门禁与实验：** 运行 quality/narrative gate，并成功推进到 `surface_checked`；任一工具级 blocking 立即短路，不运行审稿、不准备下一章。只有存在真实分歧时才做分支实验，匿名盲评后保留单一胜者。
10. **批量审稿：** `surface_checked` 成功后自动运行一批六角色审稿；不再询问是否开始。结论分别落盘并记录真实 reviewer/provider/model/context，causal/chapter editor 先做 prose-only reconstruction。
11. **收敛修订：** orchestrator 去重 findings 后只做一次集中 patch，再做一次全文终审。第三份 generation 后仍出现新 MUST 时停止并请求人工决定，不自动回炉。
12. **跨章审计：** 每五章检查承诺、人物状态、因果债务与读者问题；卷终单独审计。
13. **如实交付：** 门禁通过不等于文学保证、市场保证、作者批准或发布许可。

### books/ 的 adapter 操作

以下 op 让编排器以 JSON 驱动 books/ 工作流（只读 op 免 confirm；变更 op 强制 `--confirm <operation>`；永不返回正文全文）：

- `project-status <slug> [章节号]`：进度、正文与 state 并集、审稿 verdict、`workflow_integrity`、`review_confidence` 与 `benchmark_eligible` 汇总。
- `set-draft-mode <slug> <章节号> --mode <formal|exploration|degraded_exploration>`：持久化章节模式；变更会使旧审稿绑定失效。
- `run-gates <slug> <章节号> [--mode <formal|exploration|degraded_exploration>]`：按已持久化模式运行门禁；`--mode` 只做一致性断言，不能覆盖状态。
- `evidence-status <slug> [章节号]`：查看证据计数、generation 绑定和五章检查点状态。
- `record-evidence <slug> --file <证据文件绝对路径>`：校验并不可变记录 Markdown 证据；generation 证据会绑定对应章节。
- `record-review <slug> <章节号> --role <角色> --file <审稿文件绝对路径>`：校验审稿结构（角色、verdict、章号一致）并存入 `reviews/`，回写 chapter-state 证据表。
- `advance-state <slug> <章节号> --to <状态> [--evidence <指针>] [--next-action <说明>]`：向前只允许相邻迁移；进入 `ready` 强制重跑正式门禁、校验 generation、六角色当前审稿与检查点 audit。
- `sync-tools <slug> [--dry-run]`：用当前模板刷新该书的 tools、agent 定义与 planning 模板（voice-bible 只在缺失时创建，永不覆盖手写内容）。
- `memory-status <slug>`：比对 Canon Markdown、正文证据哈希、manifest 与 SQLite，返回 `missing / stale / clean`；只读。
- `record-memory-candidate <slug> --file <绝对 Markdown 路径>`：校验并记录候选记忆，不进入 Canon。
- `promote-memory-candidate <slug> <candidate-id>`：检查冲突、显式接续旧状态、晋升 Canon 并重建索引。
- `rebuild-memory-index <slug>`：从 `memory/canon/**/*.md` 原子重建本书 SQLite 索引。
- `build-memory-context <slug> <章节号>`：仅在索引 `clean` 时生成分层章节记忆包。
- `git-checkpoint <slug> --message "..."`：对 books/ 项目同样可用（见 Git 一节）。

### 长篇记忆 v1.1

`books/<slug>/memory/canon/**/*.md` 是本书连续性的长期权威源；`books/<slug>/.novel-forge/index.sqlite3` 只是按书生成、可随时删除的 SQLite 检索缓存，不属于 legacy `data/novel-forge.db`，也不增加第三方依赖。

- Canon 分为 `entities / facts / events / knowledge / promises` 五类。记录是普通 Markdown，机器字段放在唯一的 `novel-forge-memory:v1` fenced JSON 块中，块外人工说明必须保留。
- 新事实只能先进入 `memory/candidates/chXX/`。Agent 不得直接把正文推断写入 Canon；显式晋升是作者批准边界。
- `fact` 使用 `valid_from / valid_to` 表达有效期。人物死亡、受伤、持有物变化等状态变化必须用 `supersedes` 指向旧事实，禁止用同一 `(subject, predicate)` 的重叠有效期静默覆盖。
- 每条记录必须引用本书内存在的 `source_path` 和可定位证据。Canon 或其正文证据被改动后，`memory-status` 必须变为 `stale`，重建前不得生成写作上下文。
- 记录可填写 `salience: high / medium / low`，旧记录默认为 medium；上下文包在同一层级内优先输出高显著性记录。单章 candidate 文件或 Canon 记录任一超过 15 条时，`memory-status` 返回 `memory_volume_high` advisory；不得因此自动删除、合并或拒绝事实。
- 起草前固定顺序：`memory-status` → 必要时 `rebuild-memory-index` → `build-memory-context` → context-collector 压缩为最小上下文。writer 不加载全书 Canon。
- 写后由 consistency-guard 提取事实、事件、知识变化和承诺 candidate；晋升后再重建索引。未晋升候选不能作为后续章节事实。
- `.novel-forge/` 与 `memory/context-cache/` 都是衍生物；删除后不丢长期信息。禁止直接编辑 SQLite。

记录格式与各 kind 必填字段见本书 `memory/MEMORY.md` 和 `memory/memory-record-template.md`。

### 写作规则分级

**L1 工具阻断（quality_check.py blocking，机器可检）：**

- 禁止 `——`、`……`。
- 禁止在 `正文.md` 使用 `**粗体**`、`__强调__` 等 Markdown 强调标记；渲染后不显眼也仍属源码污染。
- 禁止 `不是X，而是Y / 不是X，是Y` 式否定翻转。

**L2 编辑门禁（narrative_gate + 审稿角色，结构性问题）：**

- 禁止背景卸货、清单式对话、说话人不明、重复段落与先下结论的主题升华。
- 避免"同一名词反复出现 → 连续下判断 → 补技术解释"的机械观察链。专业信息必须服务于人物此刻的选择、误判或行动。
- 禁止“观察 → 原理解释/履历背书 → 正确判断 → 他人惊讶”的能力证明循环支配场景；让能力落实为可失败的选择与后果。
- 可观察事实不得被旁白直接升级为唯一心理解释。重要判断必须有替代解释、置信度和可推翻条件；微表情、停顿、衣着与口音只能支持假设，不能自动证明动机。
- 世界与配角拥有独立目标，不能只负责提供线索、验证主角和惊叹主角。主角判断正确时，对方仍可因自身利益作出不利行动。
- 专业判断必须可执行：交代可观察证据、未证前提、权限/本金/工具/时间等条件、成本和风险。缺任一关键条件的术语结论不能作为情节支点。
- 因果归属必须稳定：谁提出条件、谁执行、谁知情、谁承担后果，正文与场景包不得漂移。
- 人物性呼吸段若声明“不新增情节信息”，就不得偷偷加入线索、推断或设定；它只能改变身体、关系、价值暴露或对既有事物的感受。
- 场景包与正文中的数字与术语必须落到身体接触、相对位置、可操作物与受阻动作中，不得用面积、尺寸、参数替代画面。
- **禁止跨段重复同一信息结论。** 后文只有在信息出现新证据、造成新后果、被角色误解/反驳，或推动新的选择时才能回收；回收必须写出新增变化，不能只换词复述。
- **禁止无归属的排比式对白。** 连续两句以上对话必须让读者无需猜测即可判断说话者；对白的每一次交锋至少应改变人物关系、行动条件或当下风险，否则删减或改为叙述。
- 新生造术语遵守场景包第 5 节的术语预算（0-2 条，落到身体/动作）。

**L3 工艺引导（voice-bible 正面引导，不强制但默认遵循）：**

- 避免整齐对仗的短句堆叠；句长、信息密度与叙述距离随紧张程度变化（节奏方差）。
- 情绪用生理变化 + 决定 + 行动延迟呈现；不用"他意识到/他终于明白"式导语。
- 替代感叹号与套话：删掉它们，找到那个准确的词或物象。

**通用纪律：**

- 正式短篇章节必须不少于 **5000 个 CJK 汉字**；更短的文本只能标为实验片段。字数是底线不是目标：靠复述与注水凑字数的章同样不合格。
- 写手必须区分现实事实和虚构。可见线索不能直接证明未核验的历史、技术或制度性结论。
- `正文.md` 中不得出现提示词、工作流标记、研究笔记或 Agent 身份。
- 未经用户明确指示，不得覆盖既有章节；历史由 Git 保存，不新增 `正文-v2.md` 等并行正文。
- 未经用户明确批准，不得宣称"已批准"。

## Legacy 审计工作流：`library/<slug>/`

仅在确实需要审计状态、不可变 revision、Canon 或导出时使用：

```cmd
set "NOVEL_FORGE_ROOT=%CD%" && set PYTHONPATH=%NOVEL_FORGE_ROOT% && python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" <operation> ...
```

- 查看状态：`status <slug> [章节号]`
- 创建：`--confirm init-book init-book <slug> --title "..."`；再执行 `--confirm create-chapter create-chapter <slug> <章节号> --title "..."`
- 写 revision：`--confirm write-revision write-revision <slug> <章节号> --from-file <绝对草稿路径>`
- 精确局部修订：`--confirm write-revision-patch write-revision-patch <slug> <章节号> --patch-file <绝对 JSON 路径>`
- 质量门：`lint <slug> <章节号>`、`review <slug> <章节号>`

`approve-chapter` 的六个硬性前置条件（全部绑定当前 revision，新 revision 不继承旧状态）：

1. 存在当前 revision；
2. 无 blocking lint（`em-dash`、`ellipsis`、`not-is-flip`）；
3. 无未关闭 S1/S2 review finding（四维：structure / character / narrative / continuity）；
4. 无未关闭 S1/S2 Reader Review；
5. 有通过的 Blind Experience Review（盲读者仅凭正文重建空间、身体、行动约束、情绪轨迹、对话动态与至少三个有原文证据的可记忆画面；经 `build-blind-reader-packet` / `submit-blind-experience-review` 提交）；
6. 有 `ready_for_editor_decision` 且无 blocking issue 的 Editorial Memo（五维审稿，`prose_observation` 必须含可定位证据，纯抽象赞扬会被拒绝；经 `submit-editorial-memo` 提交）。

严禁直接修改 `data/novel-forge.db` 或 `library/<slug>/manuscript/revisions/`。正式小说不得使用 `--allow-below-minimum`。

## Git

Git 是 `books/` 与 `library/` 项目共同的历史层。检查点只经 adapter 执行：

```cmd
python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" --confirm git-checkpoint git-checkpoint <slug> --message "<说明>"
```

`git-checkpoint` 只 stage 当前书的目录（`books/<slug>/` 或 `library/<slug>/`，加 `docs/<slug>/` 如存在）；`data/` 永不入库；索引非空时拒绝执行。未经用户明确要求，不得 commit、push 或同步至 Gitea/GitHub。

## 完成汇报

只汇报：

- 项目路径与正文唯一入口
- CJK 汉字数和质检结果
- 独立编辑的 MUST/MAY 摘要与 verdict（含 blind-reader、chapter-editor）
- 尚存的事实或文学风险
- 是否发生 Git 操作
- 使用 v3 时的当前章节状态机位置与任何 blocking / advisory
