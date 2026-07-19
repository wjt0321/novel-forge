# S-Black Novel Forge

可审计、可回滚、以作者批准为最终边界的**中文长篇小说生产系统**。

它不是自动写书机。它是一条生产链：把"写得像人"这件事拆成可验证的规划材料、机器门禁和独立审稿，让写作 Agent 在约束中产出没有 AI 味的正文，并把每一次编辑与校对留痕。

## 核心主张

- **少禁令，多示范。** 硬禁令只有机器可检测的三条（`——`、`……`、`不是X而是Y`）；其余全部转为每本书的 Voice Bible 正面引导、范文锚定与症状化角色语言指纹。
- **每个字都为人物此刻的选择服务。** 物件是筹码，对白是权力，数字是赌注。八种 AI 味反模式（均匀碎句、术语堆叠、数值监控、机械观察链、感官轰炸开篇、比喻过密、危机中背景卸货、对白真空）各有对应的门拦截——证据见 `docs/examples/`。
- **节奏管方差，不管长短。** 句长均匀（全短或全长）是机械指纹，lint 按变异系数检测。
- **不认证文学价值。** 系统只记录可验证的编辑与校对过程；`ready` 只表示流程材料齐备，永远不等于用户批准或市场判断。

## 快速开始

```bash
pip install -r requirements.txt

# 运行测试（仓库根目录）
PYTHONPATH=. python -m pytest tests/ -q

# 创建一本新书（生成 v3.9 项目骨架）
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root <仓库根绝对路径> \
  --confirm init-novel-project init-novel-project my-novel --title "我的小说" --genre "都市"

# 对任意 Markdown 直接跑规则 lint
PYTHONPATH=. python -m app.novel_forge.lint <file>
```

一本书的工作循环（详见 `.agents/skills/novel-forge/SKILL.md`）：

1. 收集最小上下文，填写 Voice Bible、故事发动机与一页式场景包；
2. 一次写完整章，记录 generation 并绑定真实 writer `run_id`；
3. 任意 Harness 先读 `evaluation/harness-contract.json`，输出
   `novel-forge-runtime/v1` 累计快照；每次模型响应后运行 `session-audit`，
   超预算或来源不实立即停止，结束时再 `record-session-audit`；
4. 跑质量、叙事与跨章文学结构门；极端逐字复用、长段复制和损坏对白会阻断；
5. 在独立会话运行 prose-only blind-reader，再由 chapter-editor 综合审读；
6. 状态机推进到 `ready`；它只表示材料齐备，不是作者批准。

## 两种工作流

| | `books/<slug>/`（默认） | `library/<slug>/`（legacy） |
|---|---|---|
| 用途 | 写作 Agent 项目内写作，质量门完整 | SQLite 审计、不可变 revision、Canon 事实库、Pandoc 导出 |
| 正文 | `chapters/eXX/ch-XX/正文.md` | `manuscript/revisions/` 不可变文件 |
| 驱动 | adapter：`project-status` / `session-audit` / `run-gates` / `record-review` / `advance-state` / `sync-tools` | adapter：`write-revision` / `lint` / `review` / `approve-chapter` 等 45+ ops |
| 数据库 | 不需要 | `data/novel-forge.db`（可重建的审计索引） |

两者不得静默混用；选择标准见 SKILL.md。

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
  session_audit.py   #   厂商无关 Harness Contract、标准快照审计与兼容导入
  project_templates.py # 新书骨架生成（Voice Bible、七角色、薄壳工具）
tests/               # pytest 回归测试
docs/                # 里程碑与实验审计文档
docs/examples/       # 人味解剖 + AI 味反模式（起草与审稿前必读）
books/               # 小说项目（一书一目录，项目级隔离；gitignored，仅存本地不上传）
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
- 写作证据（**写作者必读**）：`docs/examples/human-flavor-anatomy.md`、`docs/examples/ai-flavor-antipatterns.md`
- 阶段交接（语域配比下一阶段）：`docs/16-register-mixing-handover.md`

## 边界

- 严禁直接修改 `data/novel-forge.db` 与 `library/<slug>/manuscript/revisions/`。
- 正式章节硬门槛：≥ 5000 CJK 汉字（不可下调）。
- 正文里不得出现提示词、工作流标记或 Agent 身份。
- 未经用户明确批准，不得宣称"已批准"；Git commit / push 需用户明确要求。

## 技术栈

Python 3.12+，仅四个依赖（fastapi、uvicorn、pydantic v2、pytest）；SQLite 用标准库，无 ORM；Pandoc 可选（DOCX/EPUB/PDF 导出）。
