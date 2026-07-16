---
name: novel-forge
description: "当需要创建、策划、起草、修订、审阅、质检、审计或导出 Novel Forge 小说项目时使用。"
metadata:
  version: "2.1"
  entrypoint: "app.novel_forge.skill_adapter"
---

# Novel Forge 小说创作

本 Skill 用于管理 Novel Forge 小说资产。不得直接改 SQLite 数据库或不可变 revision 文件。

## 路径与工作目录

- **不要硬编码盘符或绝对根路径。** 一律从当前工作目录、调用参数，或项目根的相对结构推导路径。
- 调用 adapter 时，以项目根为当前工作目录，并用 `--root .`：

```cmd
set PYTHONPATH=.&& python -m app.novel_forge.skill_adapter --root . <operation> ...
```

- `books/<slug>/` 是新项目的文件前台；`library/<slug>/` 是 legacy 审计工作流。
- 不得静默混用两套工作流。需要两者共用时，先在项目说明中声明哪一处是正文唯一来源。

## 选择工作流

- **新建短篇、Claude 项目内写作：** 默认 `books/<slug>/`。
- **需要 SQLite 审计、revision 历史、Canon 或导出：** 使用 `library/<slug>/` adapter 工作流。

## 新项目工作流：`books/<slug>/`

用户明确要求创建后，以项目根为 cwd 执行：

```cmd
set PYTHONPATH=.&& python -m app.novel_forge.skill_adapter --root . --confirm init-novel-project init-novel-project <slug> --title "<书名>" --genre "<类型>"
```

生成的核心文件：

- `CLAUDE.md`：本书宪法与进度
- `chapters/eXX/ch-XX/正文.md`：章节唯一正文
- `memory/`：既成事实、实体、世界规则和未来规划
- `planning/`：故事发动机、研究边界、事件规划
- `.claude/agents/`：`context-collector`、`consistency-guard`、`chapter-editor`
- `tools/quality_check.py`：低成本表面质检

### 单章最简流程

1. **调研：** 写手自行检索与主题有关的现实素材，保留来源链接；区分已核验事实与虚构内容。不得仿写在世作家，只能使用可说明的文学技法。
2. **故事发动机：** 在 `planning/` 写清主角欲望、阻力、不可逆选择、即时成本和一个尚未解答的承诺。
3. **场景合同 v4：** 每章准备 Scene Contract v4，至少明确空间布局与路线、身体状态与接触、最多 5 个物体的可供性、环境约束因果链、以及覆盖不可逆选择或其前置动作的 3 步具身动作链。
4. **上下文：** `context-collector` 只读必要记忆、规划、研究边界、Scene Contract v4 和上一章结尾；不得写正文。
5. **起草：** 一名写手只写一章，从正在发生的行动开始，不批量生成后续章节。
6. **质检：** 从书项目根运行 `python tools\quality_check.py chapters\eXX\ch-XX\正文.md`。
7. **独立审稿：** `chapter-editor` 最多给五条可定位的 MUST/MAY；写手不得自审自批。
8. **一次修订：** 只改必要局部，再跑质检，并由 `consistency-guard` 核对实体、时间线、角色认知与未回收承诺。
9. **如实交付：** 质检通过不等于文学保证、市场保证或用户最终批准。

### 不可违反的写作规则

- 正式短篇章节必须不少于 **5000 个 CJK 汉字**；更短的文本只能标为实验片段。
- 写手必须区分现实事实和虚构。可见线索不能直接证明未核验的历史、技术或制度性结论。
- 禁止背景卸货、清单式对话、说话人不明、重复段落与先下结论的主题升华。
- 避免“同一名词反复出现 → 连续下判断 → 补技术解释”的机械观察链。专业信息必须服务于人物此刻的选择、误判或行动；用一个有辨识度的物象和后续动作代替对裂缝、断面、颜色、结论的逐项复述。
- Scene Contract v4 中的数字与术语必须落到身体接触、相对位置、可操作物与受阻动作中，不得用面积、尺寸、参数替代画面。
- 避免整齐对仗的短句堆叠，例如“边缘如何。断面如何。时间如何。”；句长、信息密度与叙述距离应随紧张程度变化。
- **禁止跨段重复同一信息结论。** 同一章内，一旦已经明确交代某个事实、风险、数字、空间关系或判断，不得在后文以近义句再次讲解，例如先写“某处会整体崩塌，关键设施恰好经过那里”，后文又写“该处会崩塌，关键设施穿过那里”。后文只有在信息出现新证据、造成新后果、被角色误解/反驳，或推动新的选择时才能回收；回收必须写出新增变化，不能只换词复述。
- **禁止无归属的排比式对白。** 连续两句以上对话必须让读者无需猜测即可判断说话者；至少通过说话人标识、动作、视线、停顿、身体反应、周围人的反应或明确的上下文承接，持续锚定人物和空间。不得把“问一句、答一句、再抛一句漂亮话”排成脱离现场的台词卡。对白的每一次交锋至少应改变人物关系、行动条件或当下风险；否则删减或改为叙述。
- `正文.md` 中不得出现提示词、工作流标记、研究笔记或 Agent 身份。
- 未经用户明确指示，不得覆盖既有章节；历史由 Git 保存，不新增 `正文-v2.md` 等并行正文。
- 未经用户明确批准，不得宣称“已批准”。

## Legacy 审计工作流：`library/<slug>/`

仅在确实需要审计状态、不可变 revision、Canon 或导出时使用：

```cmd
set PYTHONPATH=.&& python -m app.novel_forge.skill_adapter --root . <operation> ...
```

- 查看状态：`status <slug> [章节号]`
- 创建：`--confirm init-book init-book <slug> --title "..."`；再执行 `--confirm create-chapter create-chapter <slug> <章节号> --title "..."`
- 写 revision：`--confirm write-revision write-revision <slug> <章节号> --from-file <绝对草稿路径>`
- 精确局部修订：`--confirm write-revision-patch write-revision-patch <slug> <章节号> --patch-file <绝对 JSON 路径>`
- 质量门：`lint <slug> <章节号>`、`review <slug> <章节号>`

严禁直接修改 `data/novel-forge.db` 或 `library/<slug>/manuscript/revisions/`。正式小说不得使用 `--allow-below-minimum`。

## Git

Git 是 `books/` 项目的历史层。建立检查点前先运行 `git status --short`，仅 stage 当前书项目相关文件。未经用户明确要求，不得 commit、push 或同步至 Gitea/GitHub。

## 完成汇报

只汇报：

- 项目路径与正文唯一入口
- CJK 汉字数和质检结果
- 独立编辑的 MUST/MAY 摘要
- 尚存的事实或文学风险
- 是否发生 Git 操作
