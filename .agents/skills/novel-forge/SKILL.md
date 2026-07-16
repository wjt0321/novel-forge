---
name: novel-forge
description: "当需要创建、策划、起草、修订、审阅、质检、审计或导出 Novel Forge 小说项目时使用。"
whenToUse: 当用户要求创建小说项目、撰写或修改章节正文、运行质量门禁、记录审稿、推进章节状态机或导出小说时使用
metadata:
  version: "2.3"
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
- **转述语域**：起草正文时的指令框架是"把正在发生的事讲给一个具体的人听"，不是"写一章小说"。LLM 的"文学表演腔"来自默认语域，讲事的语域天生具体、长短错落。
- **写前独白**：动笔前以主角第一人称写 300-500 字独白（不进入正文），找到他/她此刻最不想想的事。
- **术语预算**：每章新生造术语 0-2 条，登记在场景包第 5 节；每条必须落到身体接触、相对位置、可操作物或受阻动作，不得以解释性旁白落地。lint 的 `term-density` 规则做密度预警。

### 长篇 v3 编排

每个新项目默认具备以下资产；所有状态、记忆和审稿结果必须保留在**各自** `books/<slug>/` 内，不得放到 `books/` 顶层共享：

- `.claude/agents/orchestrator.md`：单章状态机、门禁证据与回退决策；不写正文。
- `planning/chapter-state/chXX.md`：记录章节状态、最小上下文预算、阻断项与下一步；证据表只存文件指针与 verdict。
- `planning/scene-package-chXX.md`、`action-draft-chXX.md`、`dialogue-ledger-chXX.md`：分别承载场景因果、动作底稿和关键对白意图。
- 审稿角色：`causal-editor`（因果与信息责任、术语预算）、`line-editor`（对白归属与行动性、重复簇、解释性旁白）、`texture-editor`（句子工艺：分句堆叠、排比、比喻、解释腔、句长方差、套话）、`consistency-guard`（实体/时间线/承诺）、`blind-reader`（只读正文重建画面）、`chapter-editor`（宏观五维，输出 verdict）。均不直接改写正文。
- 以上角色按职责分派给你可用的子代理机制；`.claude/agents/` 是职责定义的存放处，不绑定特定 harness。

状态链：

`planned → context_collected → scene_packaged → action_drafted → dialogue_planned → drafted → surface_checked → causal_reviewed → line_reviewed → texture_reviewed → consistency_checked → blind_read → editorial_reviewed → ready`

失败必须回退到对应材料层，而不是直接用措辞润色掩盖结构问题。`ready` 要求 texture-editor verdict=pass、blind-reader verdict=pass 且 chapter-editor verdict=ready_for_editor_decision（adapter 会强制校验）。**复审协议：任何角色复审时必须重读修订后的完整正文与 patch 记录，而不是仅核对原 finding 是否被删除**——"删过了"不等于"剩下的没问题"。

即使模型支持超长上下文，writer 也应只加载当前场景、近场连续、相关人物/承诺及必要世界规则，保留剩余上下文用于推理和审稿；全书材料只用于季末或跨章审计。

- **情感弧：** 场景包的可选情感弧记录开场、不可逆选择和章末残余状态；正文应用身体、注意力与选择呈现变化，不直接替角色命名情绪。
- **跨章一致性：** `consistency-guard` 必读 `memory/future/00-index.md`，对承诺标记兑现、保持未回收、延后或"偏离：X"。
- **patch：** 使用 `patches/ch-{章节号}-{功能}.md`，仅记录局部修订；应用后重跑 `quality_check.py`、`narrative_gate.py` 和受影响编辑审稿。

### 单章 v3 流程

1. **调研：** 写手自行检索与主题有关的现实素材，保留来源链接；区分已核验事实与虚构内容。不得仿写在世作家，只能使用可说明的文学技法。
2. **故事发动机：** 在 `planning/` 写清主角欲望、阻力、不可逆选择、即时成本和一个尚未解答的承诺。
3. **填材料：** `memory/worldbuilding.md` 与 `planning/research-boundaries.md` 必须填写或显式标注"无需"；voice-bible 填好语言指纹与感官调色板。空模板会被 narrative_gate 拦下。
4. **场景包：** 填写 `scene-package-chXX.md`，明确边界、目标、阻力、不可逆选择、情感弧、在场者状态（"不肯说/尚不知道"列必须写真秘密）、beat 因果链、信息账本、信息预算与术语预算。
5. **动作与对白：** 写 `action-draft-chXX.md`；有关键对白时写 `dialogue-ledger-chXX.md`。正文润色不得新增动作稿外的关键事件、设定、动机或谜团。
6. **上下文：** `context-collector` 只读必要记忆、规划、研究边界、voice-bible、当前场景材料和上一章结尾；不得写正文。
7. **起草：** 一名写手只写一章，从正在发生的行动开始；先完成写前独白，以"把正在发生的事讲给一个具体的人听"的语域起草（不是"写一章小说"的语域），不批量生成后续章节。
8. **门禁：** 从书项目根运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md` 和 `python tools/narrative_gate.py chapters/eXX/ch-XX/正文.md planning/scene-package-chXX.md`。
9. **独立审稿：** 依次运行 `causal-editor`、`line-editor`、`texture-editor`、`consistency-guard`、`blind-reader`、`chapter-editor`；结论落盘到 `reviews/chXX-<role>.md`。写手不得自审自批。
10. **一次修订：** 结构问题回退到场景包/动作稿；纯行文问题使用局部 patch，随后重跑受影响门禁和编辑。复审必须重读修订后的完整正文与 patch 记录，不得仅核对原 finding 是否被删除。
11. **如实交付：** 门禁通过不等于文学保证、市场保证或用户最终批准。

### books/ 的 adapter 操作

以下 op 让编排器以 JSON 驱动 books/ 工作流（只读 op 免 confirm；变更 op 强制 `--confirm <operation>`；永不返回正文全文）：

- `project-status <slug> [章节号]`：进度、章节状态机位置、审稿 verdict 汇总。
- `run-gates <slug> <章节号>`：对正文跑 quality_check + narrative_gate，返回 findings。
- `record-review <slug> <章节号> --role <角色> --file <审稿文件绝对路径>`：校验审稿结构（角色、verdict、章号一致）并存入 `reviews/`，回写 chapter-state 证据表。
- `advance-state <slug> <章节号> --to <状态> [--evidence <指针>] [--next-action <说明>]`：按状态链迁移；进入 `ready` 强制校验盲读者与宏观编辑 verdict。
- `sync-tools <slug> [--dry-run]`：用当前模板刷新该书的 tools、agent 定义与 planning 模板（voice-bible 只在缺失时创建，永不覆盖手写内容）。
- `git-checkpoint <slug> --message "..."`：对 books/ 项目同样可用（见 Git 一节）。

### 写作规则分级

**L1 工具阻断（quality_check.py blocking，机器可检）：**

- 禁止 `——`、`……`。
- 禁止 `不是X，而是Y / 不是X，是Y` 式否定翻转。

**L2 编辑门禁（narrative_gate + 审稿角色，结构性问题）：**

- 禁止背景卸货、清单式对话、说话人不明、重复段落与先下结论的主题升华。
- 避免"同一名词反复出现 → 连续下判断 → 补技术解释"的机械观察链。专业信息必须服务于人物此刻的选择、误判或行动。
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
