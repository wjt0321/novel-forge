# S-Black Novel Forge

可审计、可回滚、以作者批准为最终边界的**中文长篇小说生产系统**。

它首先服务于把长篇小说顺畅地写出来：Lead 分发，Writer 写，Blind Reader 与
Chapter Editor 审，有问题就回到同一份暂存正文修，双审通过后由 Python 自动晋升。
审计、表和状态只做附属记录，不得反过来要求创作 Agent 造表或重写已经有效的正文。

## 核心主张

- **少禁令，多示范，但不把范文变成配方。** 硬禁令只处理机器可证的破绽；Voice
  exemplar 只向 writer 传递叙事距离、信息释放与节奏功能，数值风格指标留给编辑器
  诊断，避免模型把句长、物件和动作学成新的模板。
- **每个字都为人物此刻的选择服务。** 物件是筹码，对白是权力，数字是赌注。八种 AI 味反模式（均匀碎句、术语堆叠、数值监控、机械观察链、感官轰炸开篇、比喻过密、危机中背景卸货、对白真空）各有对应的门拦截——证据见 `docs/examples/`。
- **规划是编辑控制面，不是正文提纲。** Writer 只接收过滤后的 Story Brief；替代
  解释、可证伪假设、因果归属和专业审计留给 Chapter Editor，避免人物在正文中
  逐项证明检查表。
- **节奏管方差，不管长短。** 句长均匀（全短或全长）是机械指纹，lint 按变异系数检测。
- **不认证文学价值。** 系统只记录可验证的编辑与校对过程；`ready` 只表示流程材料齐备，永远不等于用户批准或市场判断。

## 快速开始

```bash
pip install -r requirements.txt

# 运行测试（仓库根目录）
PYTHONPATH=. python -m pytest tests/ -q

# 自动三角色工作流（交互式宿主无需预配命令 Backend）
PYTHONPATH=. python tools/novel-workflow.py --root <仓库根绝对路径> start my-novel \
  --title "我的小说" --genre "都市" --protagonist "主角设定" \
  --world "世界观" --conflict "本章核心冲突" --hook "本章结尾钩子"

# 只搭建空项目、不自动写作
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root <仓库根绝对路径> \
  --confirm init-novel-project init-novel-project my-novel --title "我的小说" --genre "都市"

# 对任意 Markdown 直接跑规则 lint
PYTHONPATH=. python -m app.novel_forge.lint <file>
```

Windows 的 Git Bash/类 Bash 必须把根路径写成 `D:/path/to/repo`；未加引号的
`D:\path\to\repo` 会被拒绝，避免在当前目录误建嵌套书库。

## 一眼可执行的正式流程

默认模式是厂商、模型和宿主无关的 `lean_native`：

```text
start → next-action → 独立角色完成 → complete-role → 下一动作
```

只读成本观测不会进入角色上下文或质量路由。作者可查看：

```powershell
PYTHONPATH=. python tools/novel-workflow.py --root <仓库根绝对路径> cost-summary <slug> --chapter 1
```

宿主若掌握真实 token/耗时，可在 `complete-role` 时附加 `--telemetry-file <json>`；
缺失或无效遥测保持未知，不得触发正文或审稿重做。

1. 只在第一章执行 `start <slug>` 并给出书籍基本信息；章节 ready 后，按提示执行
   `start <slug> --chapter N+1`，无需重复输入原始设定；
2. `next-action` 默认只返回一张人类可执行的角色卡。每轮只完成卡上的一个角色，并用宿主
   官方 wait/join/result 等到 `completed`、`failed` 或 `timed_out`；
3. Writer 只写暂存正文；Blind Reader 与 Chapter Editor 分别提交各自的简短审稿结果；
4. `complete-role` 交回控制面。第一次 MUST 若全部为可唯一定位的 `local` 问题，则只返回 replacement fragments 由 Python 精确替换；否则集中修订一次。局部替换或整章修订后都重新跑完整硬门和双审；第二版仍有 MUST 就停在用户
   决定处，绝不无限循环。双审通过后 Python 才自动晋升章节，并提示下一章或完成状态。

没有命令 Backend 时，`start` 仍会签发宿主原生会话动作。Agent 不得先探索工作流源码、
自行改用 `init-novel-project`、直接写 `books/` 或降级为探索稿。默认 `lean_native` 下，
首个 Writer 动作直接写 Capsule 内正文；两个审稿角色把简短 JSON 写入动作的 `result_file`。
Lead 无需填写技术表单或拼装会话 ID。哈希、Generation、Runtime、Guardian、stale、状态和
Git 全由 Python 自动处理，未知遥测保持 null，不会因为技术字段缺失重写有效正文。
`--strict-audit` 仅用于明确的取证或基准。新书不生成 `.claude/agents`，协议不绑定宿主、
供应商或模型。

一本书的工作循环（详见 `.agents/skills/novel-forge/SKILL.md`）：

1. Python 先在后台生成最小的连续性与场景材料，再直接签发 Writer 的正文动作；
   Writer 可在写作过程中思考规划，但不回传规划表；
2. Writer 在当前书 `.novel-forge/diff/chNN/writer/draft/正文.md` 写作；Python
   冻结首次合规版本为 `初稿.md`。破折号、省略号和“不是 X，而是 Y / 不是 X，
   是 Y”属于 blocking 机械语言，命中时一次列全并在同一文件集中清理；
3. 正文仍留在 diff 区，不创建 Generation，也不写 `chapters/`；Python 运行必要的
   质量、叙事与跨章文学结构门，普通 advisory 不自动触发修订；
4. 在独立角色运行 prose-only blind-reader，记录 `human_likeness`、追读意愿与
   情绪余波，再由 chapter-editor 综合审读；两者同时检查控制面泄漏、整齐问答、
   人物可替换性和解释性修补接缝；
5. 有 MUST 时合并后直接发回 Writer，优先复用当前 Writer 会话；Writer 修改同一份
   暂存正文，Python 立即生成 `修订.diff`，两个审稿角色全文重审。第二版仍有 MUST
   时才等待用户选择；
6. 只有双审通过后，Python 才把暂存正文晋升为 `chapters/eXX/ch-XX/正文.md`，随后
   自动创建 Generation、Guardian、Runtime、Review 绑定、状态证据和每书 Git 恢复点；
7. 状态机推进到 `ready`。它只表示生产流程通过，不是作者批准或发布许可。

## 两种工作流

| | `books/<slug>/`（默认） | `library/<slug>/`（legacy） |
|---|---|---|
| 用途 | 写作 Agent 项目内写作，质量门完整 | SQLite 审计、不可变 revision、Canon 事实库、Pandoc 导出 |
| 正文 | `chapters/eXX/ch-XX/正文.md` | `manuscript/revisions/` 不可变文件 |
| 驱动 | adapter：`prepare-writer-capsule` / `ingest-writer-capsule` / `project-status` / `session-audit` / `run-gates` / `record-review` / `advance-state` / `book-git-status` / `sync-tools` | adapter：`write-revision` / `lint` / `review` / `approve-chapter` 等 45+ ops |
| 数据库 | 不需要 | `data/novel-forge.db`（可重建的审计索引） |

两者不得静默混用；选择标准见 SKILL.md。

## 每书本地版本历史

主仓库继续忽略整个 `books/`，因此小说正文不会随 Harness 推送。每个
`books/<slug>/` 同时是一个独立的本地 Git 工作区；书内 `.git` 只是指针，真实历史
位于主仓库同级管理的 `.local-book-git/<slug>.git`，主仓库也会忽略该目录。

- 新书创建时自动生成初始提交，不配置 remote；
- generation 绑定与章节 `ready` 分别形成草稿、定稿 checkpoint；
- 第 5、10、15……章 `ready` 时建立 `checkpoint/ch01-ch05` 一类标签；
- `book-git-checkpoint` 可建立人工恢复点，`restore-book-git` 可从外置历史恢复
  被误删的工作区；
- Git 只负责 diff 与恢复，不替代 evidence、审稿、作者批准或发布许可。

实验书若要彻底清理，必须同时删除 `books/<slug>/`、
`.local-book-git/<slug>.git` 和 `.local-guardian/<slug>/`；只删正文目录会有意
保留可恢复历史或 Guardian 权威账本。

## Skill 集成

本仓库自身以 skill 形式被写作 Agent 调用：

- **正本**：`.agents/skills/novel-forge/SKILL.md`（Kimi Code 及遵循 agents 约定的工具按项目级扫描）
- **镜像**：`.claude/skills/novel-forge/SKILL.md`（Claude Code 扫描位置；测试保证两份逐字节一致）

自动化与编排器的唯一推荐通道是受限 JSON 入口：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root <绝对路径> <operation> ...
```

只输出 JSON，变更操作强制 `--confirm`，永不返回正文全文。

## 仓库结构

```
app/novel_forge/     # 核心代码（lint / gates / templates / service / adapter / api）
  planning_spec.py   #   books/ 工作流共享常量唯一来源
  lint.py            #   中文网文 prose 规则（单源，各书 tools 是它的薄壳）
  book_gates.py      #   narrative gate 规范实现
  book_project.py    #   books/ 业务层（无数据库）
  book_git.py        #   每书本地 Git、自动 checkpoint 与恢复
  session_audit.py   #   厂商无关 Harness Contract、标准快照审计与兼容导入
  writer_prompt.py   #   厂商无关的一章式短提示词编译器
  guardian_contract.py # 隔离 writer capsule 的纯机器合同
  guardian.py        #   Writer capsule、原子晋升、不可变回执与会话失效
  project_templates.py # 新书骨架生成（规划、记忆、评测与薄壳工具）
tests/               # pytest 回归测试
docs/                # 当前工作流、聚焦参考与压缩后的历史索引
docs/examples/       # 人味解剖、AI 味反模式与脱敏工作流样本（起草与审稿前必读）
books/               # 小说项目（一书一目录，项目级隔离；gitignored，仅存本地不上传）
.local-book-git/     # 每书外置 Git 元数据（gitignored、本地、无 remote）
library/             # legacy 审计资产（gitignore）
data/                # SQLite 账本（gitignore，可重建）
research/            # 前期调研
```

## 本地书库重置与回归样本

`books/`、`.local-book-git/` 与 `.local-guardian/` 是本地运行资产，默认不进主仓库。
当前工作区已在 **2026-07-29** 清理为无书籍的干净起点；新测试应从 `start` 或
`init-novel-project` 重新初始化，不能复用已删除项目的控制面或会话状态。

历史书籍只保留脱敏的文件级汇总，位于
`docs/examples/book-workflow-samples/`：其中 K3-H/K3-L/K3-M 是用户标注的流程理念成功
样本，DS/M3 是流程绕过或循环的失败样本，其余是未定论的对照样本。该目录不含正文、
标题、slug、规划内容、审稿正文、哈希、模型信息、Guardian 材料或本地 Git 对象；持久化
的 `ready` 状态也不能单独证明历史流程正确。

## 文档地图

- 总入口与维护规则：`docs/README.md`
- 正文优先 Lean 原生工作流：`docs/43-fiction-first-lean-native-workflow.md`
- 现行逻辑审计与恢复矩阵：`docs/44-current-workflow-logic-audit.md`
- 45 号迭代实现记录：`docs/45-workflow-iteration-proposal.md`
- 控制面、隔离、证据与恢复：`docs/architecture-reference.md`
- Voice、场景合同与文学规则：`docs/literary-quality-reference.md`
- Legacy `library/` 与 SQLite 兼容维护：`docs/legacy-library-reference.md`
- 历史里程碑、计划和实验结论：`docs/archive/history.md`
- 写作证据（**写作者必读**）：`docs/examples/human-flavor-anatomy.md`、`docs/examples/ai-flavor-antipatterns.md`

## 边界

- 严禁直接修改 `data/novel-forge.db` 与 `library/<slug>/manuscript/revisions/`。
- 正式章节硬门槛：≥ 5000 CJK 汉字（不可下调）。
- 正文里不得出现提示词、工作流标记或 Agent 身份。
- 未经用户明确批准，不得宣称"已批准"。Harness 主仓库的 commit / push 需用户
  明确要求；每书本地 Git 的自动 checkpoint 属于工作流恢复机制，永不 push。

## 技术栈

Python 3.12+，仅四个依赖（fastapi、uvicorn、pydantic v2、pytest）；SQLite 用标准库，无 ORM；Pandoc 可选（DOCX/EPUB/PDF 导出）。


### 45 号迭代：最小 Writer 包、能力档与风险路由

- Lean Writer 默认读取 capsule 内受保护的 `writer-context.md`（P0/P1/P2）；可用 `start --writer-context-mode full` 做旧完整 handoff 对照。
- 同卷可用 `--writer-model <name>` 固定 Writer；切换前执行 `approve-writer-model <slug> --volume N --model <name> --reference <作者校准依据>`。
- `--host-capability native-isolated|managed-relay|exploration` 明确宿主能力；`exploration` 永远不能晋升 formal `ready`。运行 `capability <slug>` 查看当前档。
- 高风险章用 `--chapter-risk volume_start|volume_end|major_turn|character_death|core_reveal` 标记；双审通过后需 `approve-high-risk <slug> --reference <作者决定依据>`。
- 可用 `--soft-token-budget N --hard-token-budget N` 设置调用预算。硬预算达到后保留暂存稿和审稿证据，作者可运行 `continue-budget <slug> --reference <继续依据>`。
- `ready`、高风险确认、预算继续授权均不等于作者批准或可发布；`publication_eligibility` 始终为 `False`。
