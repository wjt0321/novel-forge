# 15 - books/ 工作流 Skill 化与文字质量层

## 背景

v3（docs/13）落地后，三本试验品暴露出六个系统性缺口：

1. **规则双源分叉**：`app/novel_forge/lint.py` 有 12+ 条规则，而每本书的 `tools/quality_check.py` 是 7 条规则的冻结副本，命名不一致（`not-is-flip` vs `negation-flip`），且永远不会同步到旧书。同一本书过两套工具会得出不同质检结论。
2. **books/ 在 skill 层裸奔**：skill_adapter 只有 `init-novel-project` 一个 op 服务 books/；状态机、审稿、门禁全靠手工读写文件。
3. **最强的两扇门没进 books/**：盲读者重建与宏观五维审稿只存在于 legacy 工作流；SKILL.md 全文未提 Blind Experience Gate 与 Editorial Memo。
4. **去 AI 味只有禁令没有正面引导**：voice-bible 不在模板里；节奏指导与 LLM 碎句倾向同向叠加；术语密度无人管。
5. **模板工程债**：genre 参数形同虚设；narrative_gate 硬编码小节标题；`worldbuilding.md`/`research-boundaries.md` 空模板也能标 `ready`。
6. **审稿不落盘**：审稿结论只存在于子代理上下文，不可审计，无法形成学习回路。

本里程碑的决策：采用**"少禁令、多示范、给直觉方向"**路线——硬禁令保持机器可检测的少数几条，其余全部转为 voice-bible 正面引导、范文锚定与症状化角色指纹。5000 CJK 下限保留（用户硬性要求），灌水问题由信息预算与重复簇审查解决。

## 改动总览

### 规则单源化（消灭分叉）

- 新增 `app/novel_forge/planning_spec.py`：场景包必填小节、章节状态链、审稿角色、verdict 集合、genre 预设的唯一来源。
- 新增 `app/novel_forge/book_gates.py`：narrative gate 的规范实现（场景包校验 + 书级材料校验）。
- 每本书的 `tools/quality_check.py` / `tools/narrative_gate.py` 改为**薄壳**：定位仓库根（支持 `NOVEL_FORGE_ROOT` 环境变量覆盖）后委托 `app.novel_forge.lint` / `app.novel_forge.book_gates`。规则从此单源，新书旧书一致。
- `sync-tools <slug> [--dry-run]`：用当前模板刷新存量书的薄壳、agent 定义与 planning 模板；voice-bible 只在缺失时创建，永不覆盖手写内容。

### lint 新规则（advisory，不阻断）

- `sentence-rhythm`：段内句长**变异系数**过低报警。管方差不管长短——全短的均匀段是碎，全长的均匀段是糊；对白密集段豁免。
- `term-density`：高频生造术语（道脉/残剑/九斩类后缀构词）密度预警。核/法/压/纹/墟/骸等常用字结尾刻意排除，都市文不误报。
- `python -m app.novel_forge.lint <file>`：lint 直接可用，不必经薄壳。

### 文字质感层进模板

- 新增 `memory/voice-bible.md` 模板：narrative_distance、focalization、节奏蓝图、sentence_rhythm（方差导向）、角色语言指纹（症状化）、感官调色板、术语纪律、emotional_restraint、3 条硬禁令、正面引导、写前独白仪式、exemplar_notes 范文锚定槽。
- **genre 参数真正生效**：按 genre 选择感官调色板预设（都市现实 / 幻想修真 / 末世科幻 / 通用），"禁止解释机制"条款按题材改写（金手指/穿越/灾难成因）。
- 场景包第 5 节新增**新生造术语预算（0-2 条）**；"在场者状态"表注明"不肯说/尚不知道列必须填写真秘密"。

### v3.1 状态机与审稿落盘

状态链扩展为：

`planned → context_collected → scene_packaged → action_drafted → dialogue_planned → drafted → surface_checked → causal_reviewed → line_reviewed → texture_reviewed → consistency_checked → blind_read → editorial_reviewed → ready`

- 新角色 `blind-reader`：只读正文，严禁读规划材料；重建空间/身体/行动约束/情绪轨迹/对话动态 + ≥3 个带原文引用的可记忆画面；失败即 MUST。
- 新角色 `texture-editor`（v3.1.1 增补）：文字肌理专审，只管句子与分句工艺——分句堆叠、排比、比喻密度、解释腔、句长方差、套话。设立原因：句号级机器规则测不到逗号级 AI 味，而这类问题又会在多维度审稿角色的注意力预算里漏网（实测教训，见 docs/15 后记）。`ready` 强制要求其 verdict=pass。
- `chapter-editor` 升级为轻量 Editorial Memo：五维（叙事必要性/人物能动性/细节选择/因果链/prose 观察），每条必须附可定位原文证据，纯抽象赞扬判无效；输出 `ready_for_editor_decision / needs_revision`。
- 审稿必须落盘到 `reviews/chXX-<role>.md`（模板 `reviews/review-template.md`）；chapter-state 证据表只存指针与 verdict。
- 复审协议：任何角色复审时必须重读修订后的完整正文与 patch 记录，不得仅核对原 finding 是否被删除——"删过了"不等于"剩下的没问题"（修订残留实测教训）。
- narrative_gate 新增书级材料门：`worldbuilding.md` 与 `research-boundaries.md` 必须填写或显式标注"无需"；voice-bible 缺失对 ch01 为 advisory、ch02 起为 blocking；exemplar_notes 自 ch02 起必填。
- 进入 `ready` 强制校验：blind-reader verdict=pass 且 chapter-editor verdict=ready_for_editor_decision。

### books/ 的 adapter 操作（JSON-only，永不返回正文）

- `project-status <slug> [章节号]`：进度、状态机位置、审稿 verdict 汇总。
- `run-gates <slug> <章节号>`：quality + narrative 门禁结果。
- `record-review <slug> <章节号> --role --file`（变更）：校验角色/verdict/章号一致后落盘并回写证据表。
- `advance-state <slug> <章节号> --to <状态>`（变更）：状态链迁移，ready 强制校验审稿证据。
- `sync-tools <slug> [--dry-run]`（变更；dry-run 免 confirm）。
- `git-checkpoint` 扩展支持 `books/<slug>/`（原仅 `library/<slug>/`）。
- 人类 CLI 补 `init-novel-project`。

## 已知边界

- 存量书的历史章节按新门禁重跑可能报 blocking（统一规则的预期效果：此前漏检，不是回归）。是否回修订文由用户决定；本里程碑不改写任何既有正文。
- voice-bible 骨架需要逐书填写（语言指纹、感官调色板、exemplar）；这是写作输入，不由工具代笔。
- 5000 CJK 下限未改；若未来要支持更短的连载章节，需用户另行拍板改为"信息预算 + 密度审查"模式。

## 验证

- `pytest tests/ -q`：318 例全绿（含新增 26 例：lint 新规则、模板 genre 分支、book_project 业务层、adapter 契约、CLI）。
- 五本存量书曾执行 `sync-tools`：薄壳工具与 `python -m app.novel_forge.lint` 结论一致（分叉闭合）。

## 后记：试验品清理与证据固化（2026-07-17）

五本试验品（shenhao-cashback 为 Kimi 所写，star-ruin-sword、wasteland-echo、chuanyue-xiuxian-test、穿越问道为 DeepSeek 所写）完成对照使命后已由用户授权清理（Git 历史可恢复）。清理前完成了正反两面取证：

- `docs/examples/human-flavor-anatomy.md`：Kimi 章的人味技法解剖（细节即社会关系、对白是权力动作、潜台词来自秘密、情绪身体化、呼吸段有人物功能、数字服务于选择、节奏方差、章末问题换代）。
- `docs/examples/ai-flavor-antipatterns.md`：DeepSeek 章的八种反模式（均匀碎句、术语堆叠、数值监控、机械观察链、感官轰炸开篇、比喻过密、危机中背景卸货、对白真空），每种标明了由哪道门拦截。
- 基于实测校准新增 lint `simile-density`（Kimi 1.6/千字 vs DeepSeek 3.5/千字，阈值 3.0）；实测否决了"感知动词密度"规则（两阵营无差异，不立项）。
- 场景包模板新增 3b「锚定物象」字段（3-5 个可操作、可磨损、有价格或来历的实物）。
- `books/` 目录现为空库，新书全部由 `init-novel-project` 生成。

## 后记 2：texture-editor 增补（2026-07-17，v3.1.1）

《拾骨人》ch01 全流程试写暴露：人工读者在 ready 章节中抓到两处逗号级 AI 味（"弯腰，笑，说了好一阵"式打点堆叠、"行里的规矩，拾骨不见天"式动作中段背条文），全部句号级机器规则与五个多维度审稿角色均未拦截。根因有二：

1. **机器规则的盲区在分句级**：句长方差、机械三连等检测都以句号切分；"他输密码，六个数字，按得很慢"与"弯腰，笑，说了好一阵"表面指标几乎一致，正则无法可靠区分——这类判断需要语义理解，只能交给审稿角色。
2. **多维度角色的注意力预算**：每个角色背 5-6 个维度，结构性大鱼吃光预算，肌理小鱼漏网。

处置：新增专职 `texture-editor`（六维度聚焦句子工艺），钉入 `ready` 硬条件（`READY_REQUIRED_REVIEWS`）；line-editor 职责收窄为对白与信息流；增补复审协议（复审必须重读完整正文而非仅验证删除，防"修订残留"）；反模式文档补第 9 条（逗号级动作堆叠，含真实漏网原文）。增补后 texture-editor 首轮实战即独立抓回上述两处并挖出第三处（档册段讲解），修订后复审转 pass——全流程零人工逐字审稿。

工具层另修两个狗食 bug：narrative_gate 表格误判正则（`\s` 跨行匹配表头/分隔行）、record-review 对已在位审稿文件的 SameFileError。

## 后记 3：声音指纹与转述语域（2026-07-17，v3.1.2）

方向来自用户的观察：LLM 讲大白话时语域自然——AI 味很大程度来自生成时调用的"文学表演"语域。两个落地机制：

1. **转述语域（生成时）**：起草指令框架改为"把正在发生的事讲给一个具体的人听"，替代"写一章小说"。已写入 SKILL.md 单章流程起草步。
2. **声音指纹（可测量的范文锚定）**：新模块 `voice_signature.py` 从范文提取 11 项风格指标（句长均值/方差、对白占比、碎段率、比喻密度、分句复杂度等），`--vs` 做漂移对比。实测：DeepSeek 章节对 Kimi 章节漂移 4/7 项（对白占比 0.09 vs 0.21、碎段率 0.27 vs 0.12、比喻 3.5‰ vs 0.6‰、分句复杂度 1.4 vs 2.8），自身对比零漂移——"像不像本书"从玄学变成距离。指纹贴在 voice-bible 的 exemplar_notes（ch02 起 narrative_gate 检查），texture-editor 的漂移检查用 `--vs` 执行。
