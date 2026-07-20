# S-Black Novel Forge

可审计、可回滚、以作者批准为最终边界的**中文长篇小说生产系统**。

它不是自动写书机。它是一条生产链：把"写得像人"这件事拆成可验证的规划材料、机器门禁和独立审稿，让写作 Agent 在约束中产出没有 AI 味的正文，并把每一次编辑与校对留痕。

## 核心主张

- **少禁令，多示范，但不把范文变成配方。** 硬禁令只处理机器可证的破绽；Voice
  exemplar 只向 writer 传递叙事距离、信息释放与节奏功能，数值风格指标留给编辑器
  诊断，避免模型把句长、物件和动作学成新的模板。
- **每个字都为人物此刻的选择服务。** 物件是筹码，对白是权力，数字是赌注。八种 AI 味反模式（均匀碎句、术语堆叠、数值监控、机械观察链、感官轰炸开篇、比喻过密、危机中背景卸货、对白真空）各有对应的门拦截——证据见 `docs/examples/`。
- **节奏管方差，不管长短。** 句长均匀（全短或全长）是机械指纹，lint 按变异系数检测。
- **不认证文学价值。** 系统只记录可验证的编辑与校对过程；`ready` 只表示流程材料齐备，永远不等于用户批准或市场判断。

## 快速开始

```bash
pip install -r requirements.txt

# 运行测试（仓库根目录）
PYTHONPATH=. python -m pytest tests/ -q

# 创建一本新书（生成 v4.4 项目骨架，并初始化每书本地 Git）
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root <仓库根绝对路径> \
  --confirm init-novel-project init-novel-project my-novel --title "我的小说" --genre "都市"

# 对任意 Markdown 直接跑规则 lint
PYTHONPATH=. python -m app.novel_forge.lint <file>
```

一本书的工作循环（详见 `.agents/skills/novel-forge/SKILL.md`）：

1. 收集最小上下文，填写 Voice Bible、故事发动机与一页式场景包；
2. 每章新开 writer session，绑定真实 `run_id`，再由外部 Harness 创建仓库外
   writer capsule；writer 只能读取有界 handoff，只能写正文；
3. 任意 Harness 先读 `evaluation/harness-contract.json` 与
   `evaluation/guardian-contract.json`，输出
   `novel-forge-runtime/v1` 累计快照；每次模型响应后运行 `session-audit`，
   超预算或来源不实立即停止，结束时由 Guardian 导入正文并固化隔离回执，再
   `record-session-audit`；
4. 跑质量、叙事与跨章文学结构门；极端逐字复用、长段复制和损坏对白会阻断，
   章内模式饱和、Voice 表层复制与 ASCII 标点会提示编辑器回读；
5. 在独立会话运行 prose-only blind-reader，记录 `human_likeness`、追读意愿与
   情绪余波，再由 chapter-editor 综合审读；
6. generation 绑定后自动提交 `chapter: chNN draft`，推进到 `ready` 后自动提交
   `chapter: chNN ready`；每五章建立一个本地 checkpoint 标签；
7. 状态机推进到 `ready`；它只表示材料齐备，不是作者批准。

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
  guardian_contract.py # 隔离 writer capsule 的纯机器合同
  guardian.py        #   仓库外 capsule、原子导入、不可变回执与会话失效
  project_templates.py # 新书骨架生成（Voice Bible、七角色、薄壳工具）
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
