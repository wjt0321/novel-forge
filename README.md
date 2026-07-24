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

没有命令 Backend 时，`start` 会签发宿主原生会话动作；Lead 只循环
`next-action → 创建/运行角色 → 等官方终态 → complete-role`。Agent 不得先探索
工作流源码、自行改用 `init-novel-project`、直接写 `books/` 或降级为探索稿。
默认 `lean_native` 下，首个 Writer 动作直接写 Capsule 内正文；两个审稿角色把简短
JSON 写入动作的 `result_file`。Lead 无需填写技术表单或拼装会话 ID。哈希、Generation、
Runtime、Guardian、stale、状态和 Git 全由 Python 自动处理，未知遥测保持 null，
不会因为技术字段缺失重写有效正文。`--strict-audit` 仅用于明确的取证或基准。
新书不生成 `.claude/agents`，协议不绑定宿主、供应商或模型。

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
docs/                # 里程碑与实验审计文档
docs/examples/       # 人味解剖 + AI 味反模式（起草与审稿前必读）
books/               # 小说项目（一书一目录，项目级隔离；gitignored，仅存本地不上传）
.local-book-git/     # 每书外置 Git 元数据（gitignored、本地、无 remote）
library/             # legacy 审计资产（gitignore）
data/                # SQLite 账本（gitignore，可重建）
research/            # 前期调研
```

## 文档地图

- 快速开始：`docs/01-getting-started.md`
- 数据模型与状态机：`docs/02`
- 质量门控：`docs/03`、`docs/05`、`docs/06`、`docs/12`、`docs/14`
- books/ 工作流与 Skill 化：`docs/13`、`docs/15`
- 外置 Harness 护栏：`docs/24-external-harness-guardrails.md`
- 章节独立会话：`docs/25-chapter-session-orchestration.md`
- 文学防过拟合与序列真实性：`docs/26-literary-anti-overfit-and-sequence-truth.md`
- 每书本地版本历史：`docs/27-per-book-local-git.md`
- 读者追读与运行真相：`docs/28-reader-pull-and-runtime-truth.md`
- 隔离 Writer Capsule：`docs/29-isolated-writer-capsule.md`
- 编译 Writer Prompt：`docs/30-compiled-writer-prompt.md`
- 自动三角色工作流：`docs/31-automatic-three-role-workflow.md`
- 文学生产闭环与控制面隔离：`docs/32-literary-production-loop.md`
- 异步终态、证据封存与 Harness 信任：`docs/33`、`docs/34`、`docs/36`、`docs/37`、`docs/38`
- 文学短规则与完整解释：`docs/35-literary-rule-manual.md`
- Python 确定性控制与零污染：`docs/39-deterministic-native-control-and-workspace-hygiene.md`
- 原生 Relay 双保证模式：`docs/40-native-relay-and-assurance-modes.md`
- 完成补交与封存 Review Capsule：`docs/41-completion-repair-and-sealed-review-capsules.md`
- 硬锚、会话与 ready 完整性：`docs/42-hard-anchor-session-and-ready-integrity.md`
- 正文优先 Lean 原生工作流：`docs/43-fiction-first-lean-native-workflow.md`
- 现行逻辑审计与恢复矩阵：`docs/44-current-workflow-logic-audit.md`
- 写作证据（**写作者必读**）：`docs/examples/human-flavor-anatomy.md`、`docs/examples/ai-flavor-antipatterns.md`
- 阶段交接（语域配比下一阶段）：`docs/16-register-mixing-handover.md`

## 边界

- 严禁直接修改 `data/novel-forge.db` 与 `library/<slug>/manuscript/revisions/`。
- 正式章节硬门槛：≥ 5000 CJK 汉字（不可下调）。
- 正文里不得出现提示词、工作流标记或 Agent 身份。
- 未经用户明确批准，不得宣称"已批准"。Harness 主仓库的 commit / push 需用户
  明确要求；每书本地 Git 的自动 checkpoint 属于工作流恢复机制，永不 push。

## 技术栈

Python 3.12+，仅四个依赖（fastapi、uvicorn、pydantic v2、pytest）；SQLite 用标准库，无 ORM；Pandoc 可选（DOCX/EPUB/PDF 导出）。
