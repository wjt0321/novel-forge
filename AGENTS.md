# AGENTS.md

> 本文件面向 AI 编码 Agent，介绍本仓库的结构、约定与操作边界。阅读前无需任何项目背景。

## 项目概览

**S-Black Novel Forge**（包名 `app.novel_forge`，版本 0.1.0）是一个**可审计的中文长篇小说生产系统**。产品定位（见 `research/03-production-architecture.md`）：不是自动写书机，而是可审计、可回滚、以作者批准为最终边界的长篇小说生产链。

核心设计原则：

- Markdown 正文与导出 manifest 是长期真相来源；`data/novel-forge.db`（SQLite）只是可重建的审计索引。
- revision 文件不可变：rollback 不修改历史文件，而是把目标 revision 复制为新 revision。
- 系统只记录可验证的编辑与校对过程，**不认证文学价值、市场表现或可读性**；`publication_eligibility` 恒为 `False`，公开发布始终需要外部明确决定。
- 不实现真实 LLM 调用或联网抓取；所有正文由人类或外部写作 Agent 通过 `write-revision` 提交。
- 不提供删除操作（仅软删除）。

## 技术栈与运行环境

- Python 3.12+，仅四个依赖（`requirements.txt`）：`fastapi`、`uvicorn`、`pydantic`（v2）、`pytest`。
- 数据库为标准库 `sqlite3`，无 ORM；schema 版本见 `app/novel_forge/db.py` 的 `CURRENT_SCHEMA_VERSION`（当前为 8）。`init_db()` 自动检测并原子迁移，迁移前在 `data/` 生成带时间戳的备份。
- 可选依赖：Pandoc（DOCX/EPUB/PDF 导出；未安装时返回清晰错误并记录审计，Markdown 导出不受影响）。
- **没有 `pyproject.toml` / `setup.py`，本仓库不是可安装包**，通过 `PYTHONPATH` 直接运行。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试（从仓库根目录；320 个测试，约 50 秒）
PYTHONPATH=. python -m pytest tests/ -q
# Windows cmd: set PYTHONPATH=. && python -m pytest tests/ -q

# 人类 CLI（注意 PYTHONPATH=app，模块名为 novel_forge）
set PYTHONPATH=app
python -m novel_forge.cli init-book my-novel --title "我的小说"
python -m novel_forge.cli init-novel-project my-novel --title "我的小说" --genre "都市"
python -m novel_forge.cli create-chapter my-novel 1 --title "第一章"
python -m novel_forge.cli write-revision my-novel 1 --from-file chapter1.md --note "初稿"
python -m novel_forge.cli lint-chapter my-novel 1
python -m novel_forge.cli review-chapter my-novel 1
python -m novel_forge.cli approve-chapter my-novel 1 --note "通过"
python -m novel_forge.cli export-book my-novel --format markdown
python -m novel_forge.cli audit my-novel --limit 50

# 直接对单个 Markdown 文件跑规则 lint
PYTHONPATH=. python -m app.novel_forge.lint <file>

# Skill-first 受限 JSON 入口（自动化/编排器唯一推荐通道；--root 必须是绝对路径）
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root D:\s-black-novel <operation> ...
# 变更类操作强制 --confirm <operation>；只输出 JSON，永不返回正文全文
# books/ 工作流专用 op：project-status / run-gates / record-review / advance-state / sync-tools

# 本地只读 API
set PYTHONPATH=app
python -c "from app.novel_forge.api import create_app; import uvicorn; uvicorn.run(create_app('.'), host='127.0.0.1', port=8000)"
# 访问 /health 与 /docs
```

## 代码组织（`app/novel_forge/`）

分层：CLI / API / skill_adapter → service（业务逻辑与状态机，由多个 mixin 组成）→ repository（纯函数式 DB 操作，使用调用方事务边界）→ db（连接、schema、迁移）。

| 模块 | 职责 |
|---|---|
| `models.py` | Pydantic 模型、`ChapterState` 枚举、`NovelForgeError` 基异常 |
| `db.py` | SQLite 连接、schema、版本化迁移（v1–v8），迁移前自动备份 |
| `repository.py` | 低层 DB 操作；函数接收已有连接，不自行开事务 |
| `service.py` | `NovelForgeService` 核心：书籍/章节生命周期、revision、rollback、导出、审计、`work/<slug>/` 人类工作区；继承 `QualityMixin`/`PlanningMixin`/`ReviewGatesMixin`/`CanonMixin` |
| `quality.py` | lint、review、approval 门控（mixin） |
| `lint.py` | 中文网文 prose lint 规则（含 `sentence-rhythm` 句长方差、`term-density` 术语密度、`simile-density` 比喻密度）；只标位置、只读、永不自动改正文；`python -m app.novel_forge.lint <file>` 可直接运行 |
| `review_gates.py` | Reader Review、Blind Experience Gate、Editorial Memo Gate（mixin） |
| `planning.py` | Voice Bible、Scene Contract、Drafting Readiness、Drafting Packet（mixin） |
| `canon.py` | candidate fact 审批/驳回与 canon 列表（mixin） |
| `readiness.py` | 无依赖的轻量 Markdown 标题解析器（仅服务 readiness 评估） |
| `export.py` | 导出与 manifest；Pandoc 调用封装 |
| `autonomous.py` | 第六里程碑自主研究写作链（研究账本、故事发动机、章节计划、Promise Ledger、迭代记录、分层验收、git-checkpoint，支持 `library/` 与 `books/`）；与核心状态机刻意隔离，共享同一 DB |
| `planning_spec.py` | books/ 工作流共享常量唯一来源：场景包必填小节、13 态章节状态链、审稿角色与 verdict、genre 预设 |
| `book_gates.py` | books/ narrative gate 规范实现（场景包校验 + 书级材料校验）；各书 `tools/narrative_gate.py` 是它的薄壳 |
| `book_project.py` | books/ 工作流业务层（无数据库）：project-status、run-gates、record-review、advance-state、sync-tools |
| `project_templates.py` | `books/<slug>/` 前台项目模板生成（含 voice-bible、七个 agent、reviews 模板、薄壳 tools；genre 预设生效）；不依赖数据库 |
| `cli.py` | 人类命令行入口 |
| `skill_adapter.py` | 自动化受限入口：JSON-only、`--confirm` 强制、不泄露正文 |
| `api.py` | FastAPI 本地只读 API（books/chapters/audit；不返回正文全文） |

## 运行时数据布局

- `data/novel-forge.db`：SQLite 审计账本（已 gitignore，损坏可从 `library/` 与导出 manifest 重建）。
- `library/<slug>/`：**legacy 审计工作流**。`manuscript/revisions/`（不可变 revision 文件）、`canon/`、`planning/`（Voice Bible / Scene Contract revisions）、`exports/`。
- `books/<slug>/`：**新前台工作流**（`init-novel-project` 生成，无需数据库）。正文唯一入口是 `chapters/eXX/ch-XX/正文.md`；另有 `memory/`（含 `voice-bible.md` 本书声音宪法）、`planning/`（场景包/动作稿/对白账本/章节状态）、`reviews/`（审稿落盘，含 verdict）、`patches/`、`tools/quality_check.py` + `narrative_gate.py`（**仓库规则的薄壳**，经 `sync-tools` 刷新，勿手改）、`.claude/agents/`（七个写作/审稿角色）与本书宪法 `CLAUDE.md`。各书自包含，资产不得跨项目共享。
- `work/<slug>/`：人类优先工作区（`init-workspace` / `refresh-workspace` 生成的只读镜像与索引，非破坏性行为）。
- 两套工作流（`books/` 与 `library/`）不得静默混用；选择标准见 `.agents/skills/novel-forge/SKILL.md`。

## 章节状态机与质量门

legacy 状态机：`draft → revised → linted → reviewed → approved`（`approve-chapter` 仅从 `reviewed` 执行）。`write-revision` 回到 `draft`；已批准章节提供 `--reopen-reason` 可进入 `revised`。

`approve-chapter` 的六个硬性前置条件（全部绑定当前 revision，新 revision 不继承旧状态）：

1. 存在当前 revision；
2. 无 blocking lint（`em-dash`、`ellipsis`、`not-is-flip`）；
3. 无未关闭 S1/S2 review finding（四维：structure / character / narrative / continuity）；
4. 无未关闭 S1/S2 Reader Review；
5. 有通过的 Blind Experience Review（盲读者仅凭正文重建空间、身体、行动约束、情绪轨迹、对话动态与至少三个有原文证据的可记忆画面）；
6. 有 `ready_for_editor_decision` 且无 blocking issue 的 Editorial Memo（且 `prose_observation` 必须含可定位证据，纯抽象赞扬会被拒绝）。

books/ v3.1 章节状态链（`planning/chapter-state/chXX.md`，由 `advance-state` 校验迁移）：

`planned → context_collected → scene_packaged → action_drafted → dialogue_planned → drafted → surface_checked → causal_reviewed → line_reviewed → consistency_checked → blind_read → editorial_reviewed → ready`

- 审稿角色：`causal-editor`、`line-editor`、`consistency-guard`、`blind-reader`（只读正文重建画面）、`chapter-editor`（五维宏观审稿，输出 verdict）；结论落盘 `reviews/chXX-<role>.md`。
- 进入 `ready` 强制要求 blind-reader verdict=pass 且 chapter-editor verdict=ready_for_editor_decision；`ready` 不等于用户批准。
- narrative_gate 书级材料门：`worldbuilding.md`/`research-boundaries.md` 必须填写或显式标注"无需"；voice-bible 缺失 ch01 advisory、ch02 起 blocking，exemplar_notes 自 ch02 起必填。

Canon Fact 冲突判定限定同一本书内：`(subject, predicate)` 唯一，重复批准会被拒绝而非静默覆盖。

## 测试策略

- `pytest`，测试平铺在 `tests/`，大体一模块一文件（`test_lint.py`、`test_service.py`、`test_migration.py`、`test_skill_adapter.py`、`test_book_project.py` 等，共 19 个测试文件、320 个用例）。
- 共享辅助在 `tests/conftest.py`：`service` fixture（每测试独立 `tmp_path`，不碰真实 `data/`）、`filled_voice_bible` / `filled_scene_contract_v3` / `filled_scene_contract_v4` / `ready_memo`（构造可通过全部编辑门控的 fixture）。
- 新功能应补对应模块的测试文件；修改状态机或门控规则时同步更新 `conftest.py` 辅助与受影响用例。
- 运行前确保从仓库根执行并设置 `PYTHONPATH=.`（测试以 `from app.novel_forge...` 导入）。
- 生成的薄壳工具在 tmp 目录测试时需设 `NOVEL_FORGE_ROOT` 指向真实仓库根（见 `tests/test_novel_project.py` 的 `_tool_env`）。

## 开发约定

- 文档语言：里程碑文档（`docs/01`–`15`）、`.agents/skills/novel-forge/SKILL.md`、各书 `README.md`/`CLAUDE.md` 主要为中文（`docs/10`、`docs/14` 为英文）；代码 docstring 与注释为英文。改动代码时保持此分工。
- 每个里程碑对应一份 `docs/NN-*.md`；实现里程碑级功能时应同步更新对应文档与 `SKILL.md`。
- 代码风格：标准 PEP 8、类型注解（`int | None` 等 3.12 语法）、模块顶部一句话 docstring；mixin 模块在 docstring 中声明对宿主 `NovelForgeService` 的依赖（`self._conn()`、`self.root` 等）。
- 最小改动原则：lint 规则只标记不修改；gate 只记录人工判断，不做文学评判。
- 规则单源原则：books/ 的 tools 只是 `lint.py`/`book_gates.py` 的薄壳；场景包小节、状态链、审稿角色改 `planning_spec.py` 一处即全链路生效，禁止在模板字符串里另起炉灶。

## 安全与操作边界（重要）

- **严禁直接修改** `data/novel-forge.db` 或 `library/<slug>/manuscript/revisions/` 下的文件；一切变更经 `NovelForgeService` 或 skill_adapter。
- skill_adapter：`--root` 只接受绝对路径（相对路径返回 `invalid_root`）；变更操作必须 `--confirm <operation>`；`write-revision` 等拒绝 `library/` 内的输入路径；输入 Markdown 必须是 UTF-8（允许 BOM）。
- API 与 adapter 永不返回正文全文、Voice Bible / Scene Contract / Reader Review / Editorial Memo 内容。
- `git-checkpoint` 只 stage 当前书的目录（`library/<slug>/` 或 `books/<slug>/`，加 `docs/<slug>/` 如存在）；`data/` 永不入库。未经用户明确要求不得 commit / push。
- 正式短篇章节硬门槛：≥ 5000 个 CJK 汉字（用户硬性要求，不可下调）；正式小说不得使用 `--allow-below-minimum`。
- 不得在正文（`正文.md`）中写入提示词、工作流标记、研究笔记或 Agent 身份；未经用户明确批准不得宣称"已批准"。

## 其他目录速览

- `docs/`：15 份里程碑文档（快速开始、数据模型与状态机、质量门控、运维备份、数据库迁移、Blind Experience Gate、books/ 工作流 Skill 化等）+ `docs/examples/`（人味解剖与 AI 味反模式两份证据文档，起草与审稿前必读）+ `superpowers/plans/`。
- `.agents/skills/novel-forge/SKILL.md`：写作 Agent 的统一操作说明（canonical 位置，Kimi Code 与遵循 agents 约定的工具按项目级 skill 扫描）；`.claude/skills/novel-forge/SKILL.md` 是其逐字节镜像（Claude Code 扫描位置），**两份必须保持一致**（`tests/test_novel_project.py` 有防漂移测试）。
- `research/`：三份前期调研（开源 landscape、源码架构发现、已批准的生产系统架构）。
- `upstream/`：只读参考的开源项目源码（denova、NovelClaw、show-me-the-story），不参与构建。
- `experiments/`：草稿区（已 gitignore）；`library/`：legacy 书的实际资产（已 gitignore）。
- `run_novel_test.py`：一次性脚本示例（调用 `project_templates.init_book_project` 创建 `books/穿越问道`）。
