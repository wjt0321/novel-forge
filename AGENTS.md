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

# 运行测试（从仓库根目录；约 50 秒）
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
# books/ 工作流专用 op：project-status / set-draft-mode / run-gates / record-review / advance-state / sync-tools
# v4.1 章节序列 op：begin-chapter-sequence / claim-chapter-session / advance-chapter-sequence / chapter-sequence-status
# 人类叙事证据 op：evidence-status / record-evidence
# 长篇记忆 op：memory-status / record-memory-candidate / promote-memory-candidate / rebuild-memory-index / build-memory-context

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
| `lint.py` | 中文网文 prose lint 规则（含 `sentence-rhythm`、`term-density`、`simile-density` 与 ASCII 标点提示）；只标位置、只读、永不自动改正文；`python -m app.novel_forge.lint <file>` 可直接运行 |
| `voice_signature.py` | 声音指纹与跨章文学诊断：提取可量化风格指标，检测句长塌缩、复读、章内模式饱和与 Voice exemplar 表层复制；指标只供编辑器诊断，不作为 writer 生成目标 |
| `review_gates.py` | Reader Review、Blind Experience Gate、Editorial Memo Gate（mixin） |
| `planning.py` | Voice Bible、Scene Contract、Drafting Readiness、Drafting Packet（mixin） |
| `canon.py` | candidate fact 审批/驳回与 canon 列表（mixin） |
| `readiness.py` | 无依赖的轻量 Markdown 标题解析器（仅服务 readiness 评估） |
| `export.py` | 导出与 manifest；Pandoc 调用封装 |
| `autonomous.py` | 第六里程碑自主研究写作链（研究账本、故事发动机、章节计划、Promise Ledger、迭代记录、分层验收、git-checkpoint，支持 `library/` 与 `books/`）；与核心状态机刻意隔离，共享同一 DB |
| `planning_spec.py` | books/ 工作流共享常量唯一来源：场景包必填小节、8 态章节状态链、默认/按需审稿角色、运行与交接预算、证据 kind、人类叙事策略 ID、genre 预设 |
| `book_gates.py` | books/ narrative gate 规范实现（场景包校验 + 书级材料校验）；各书 `tools/narrative_gate.py` 是它的薄壳 |
| `book_project.py` | books/ 工作流业务层（无数据库）：稿件模式、门禁、审稿来源绑定、相邻状态迁移、ready 复核、project-status、sync-tools |
| `book_evidence.py` | books/ Markdown 权威创作证据：generation、盲评、单胜者分支、作者偏好、跨章审计、规则生命周期；不可变原子落盘 |
| `session_audit.py` | v4.1 厂商无关 Harness Contract：定义 `novel-forge-runtime/v1` 累计快照、分层推理策略与硬停预算；具体产品日志解析仅为兼容导入 |
| `chapter_sequence.py` | v4.1 章节独立会话编排：持久化 1–4 章顺序序列、签发不含数值风格目标的有界 handoff、绑定真实 native session，并审计 complete 序列是否真能证明各章 ready |
| `book_memory.py` | books/ 每书长篇记忆内核：Markdown 记录解析、candidate 晋升、冲突检测、SQLite 原子重建、章节上下文包 |
| `project_templates.py` | `books/<slug>/` 前台项目模板生成（含 voice-bible、四个默认 agent、evaluation/evidence、reviews 模板、薄壳 tools；genre 预设生效）；不依赖数据库 |
| `cli.py` | 人类命令行入口 |
| `skill_adapter.py` | 自动化受限入口：JSON-only、`--confirm` 强制、不泄露正文 |
| `api.py` | FastAPI 本地只读 API（books/chapters/audit；不返回正文全文） |

## 运行时数据布局

- `data/novel-forge.db`：SQLite 审计账本（已 gitignore，损坏可从 `library/` 与导出 manifest 重建）。
- `library/<slug>/`：**legacy 审计工作流**。`manuscript/revisions/`（不可变 revision 文件）、`canon/`、`planning/`（Voice Bible / Scene Contract revisions）、`exports/`。
- `books/<slug>/`：**新前台工作流**（`init-novel-project` 生成）。**整个 `books/` 目录已 gitignore，仅存本地不上传**。正文唯一入口是 `chapters/eXX/ch-XX/正文.md`；`memory/canon/**/*.md` 是本书连续性权威源，`memory/candidates/` 是待审增量，`.novel-forge/index.sqlite3` 是按书生成且可删除重建的检索缓存；`planning/chapter-sequences/*.json` 是可更新的章节编排状态；`memory/context-cache/chXX-handoff.md` 是可删除的有界会话交接包；`evaluation/` 保存评测宪法与实验模板，`evidence/` 保存不可变创作证据及 `runtime-audits/` 脱敏运行审计。各书自包含，资产不得跨项目共享。
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

books/ v4.1 章节状态链（`planning/chapter-state/chXX.md`，由 `advance-state` 校验迁移）：

`planned → context_collected → scene_packaged → drafted → surface_checked → blind_read → editorial_reviewed → ready`

- 向前迁移只能到相邻状态；允许明确回退。`record-review` 只记录审稿，不自动推进状态。
- 章节模式持久化为 `formal` / `exploration` / `degraded_exploration`；降级探索用于 Shell、adapter 或子代理不可用的真实受限运行，必须记录工具能力与失败，所有非正式稿都不能进入 `ready`。
- 默认审稿只运行 `blind-reader` 与 `chapter-editor`。`causal-editor`、`line-editor`、`texture-editor`、`consistency-guard` 保留为按需专业工具；只有 chapter-editor 指出具体风险时才调用一个。结论绑定当前正文 SHA-256、规划 SHA-256、generation 和模式；第 2 章起 chapter-editor 还绑定上一章正文 SHA-256。
- blind-reader 必须只读当前正文并填写 `human_likeness=convincing|uncertain|synthetic`；只有 convincing 可与 pass 同时成立。v3.9 起 model/agent blind-reader pass 还必须记录真实 `review_session_id`，且与 generation `run_id` 不同；同一写作会话只能标记 `simulated_blind + needs_revision`。进入 `ready` 强制要求正式模式、当前 generation evidence、匹配且未超限的 runtime audit、formal gates 无 blocking、blind-reader=pass、chapter-editor=ready_for_editor_decision；第 5/10/15…章还要求 `open_must=0` 的 checkpoint arc audit。`ready` 不等于用户批准。
- 复审协议：任何角色复审时必须重读修订后的完整正文与 patch 记录，不得仅核对原 finding 是否被删除。
- formal narrative_gate 书级材料门：`worldbuilding.md`/`research-boundaries.md` 必须填写或显式标注"无需"；`story-engine.md` 必须填写且不可豁免；voice-bible 缺失 ch01 advisory、ch02 起 blocking，exemplar_notes 自 ch02 起必填。
- v3.4 有限认知门：决策问题至少两项真实成立；认知账本区分观察/假设/替代解释/可推翻证据；因果归属账本至少一条；专业判断必须登记执行条件与风险或明确豁免。v3.8 起对白意图写入一页式场景包，独立对白账本降为按需材料。
- v3.2 长篇记忆门：起草前 `memory-status` 必须为 `clean` 并生成本章 context packet；写后新增连续性信息只能先记录为 candidate，显式晋升后才进入 Canon。事实有效期重叠会阻断重建或晋升。
- v3.9 Harness 完整性与预算门：任何 Agent/Harness 开始 formal 写作前必须读取 `evaluation/harness-contract.json` 或调用 `harness-contract`，并把原生遥测规范化为 `novel-forge-runtime/v1` 累计快照；每次模型响应后审计，`continue_allowed=false` 时必须在下一次请求前停机。具体产品日志解析只是兼容导入，不是架构边界。同章同正文 SHA-256 只算一个 generation；初稿后最多一次集中 patch，第三个不同版本在写入前要求 author/human_delegate 的 `human_regeneration_authorized=true` 与决定引用。结束时经 `record-session-audit` 固化脱敏真相。默认硬上限：每章 30 请求、2,000,000 cached-input tokens，单请求上下文 120,000 tokens；外部 provider/model/Harness/reasoning/tool failure 与 generation 不一致时不能 ready。降级探索必须记录受限能力和至少一条工具失败，Agent authority 不得自称 `user_attested`。
- v4.0 章节独立会话门：每章必须使用新的原生 writer session；单次序列默认 1 章、最多 4 章，五章及以上必须拆分。`begin-chapter-sequence` 只签发当前章，Harness 创建会话后经 `claim-chapter-session` 绑定真实 session ID；generation `run_id` 必须与 claim 一致，session ID 不得跨章或跨书复用。当前章完整 `ready` 后 `advance-chapter-sequence` 才能生成下一章 launch directive。连续性只从 Canon、开放承诺、上一章末段、Voice exemplar 与当前 scene package 组成的有界 handoff 传递，不续传旧会话、旧工具输出或旧审稿全文。
- v3.6 章际连续性门：第 2 章起场景包必须填写 `0b. 章际交接`，绑定上一章路径/哈希、章末 20% 与章首 20% 的原文短引、时间/地点/动作与转场类型；关键审稿引文必须逐字存在于绑定正文。`project-status` 与 `ready` 会复用 `record-review` 的完整校验，直接写 review 文件不能绕过门禁。
- v3.6 人类叙事证据门：分支必须引用盲评并选择单一胜者；作者偏好必须引用同一分支/盲评且不得修改 Canon；同模型换角色名不算独立审稿；来源元数据不实、嵌套重复审稿文件或同正文重复 generation 的样本不得参与模型比较。
- v3.9 文学性与成本短路门：`正文.md` 禁止 Markdown 粗体/强调、`ch05`、`正文.md`、generation、SHA-256、surface_checked、ready 等生产元数据；进入 `surface_checked` 会重跑 blocking lint 与跨章文学结构门。极端逐字复用覆盖、长段跨章复制和嵌套说话人标签为 blocking；句长塌缩与低量复读保持 advisory。writer 每章使用独立会话，只加载一页最小上下文；原始正文默认 standard/medium，Max 仅用于用户明确的基准实验或困难反证。formal ready 使用空值或 `-` 的状态证据会成为 workflow integrity blocker。
- v4.1 文学防过拟合与序列真实性门：规划和困难因果检查可用 high，正文与默认审稿使用 standard/medium，Max 只能绑定具名难题；writer handoff 会剔除句长、对白率等数值风格目标，只传 Voice exemplar 的叙事功能。`pattern-saturation`、`voice-anchor-surface-copy` 与 ASCII 标点为 advisory；第 2 章起若推翻上一章末明确决定，必须引用当前正文前 40% 的触发事件原文。`chapter-sequence-status` 会复核 complete 声明、每章 ready、generation `run_id` 与 session 顺序，伪造完成态返回 `effective_status=inconsistent`。

Canon Fact 冲突判定限定同一本书内：`(subject, predicate)` 唯一，重复批准会被拒绝而非静默覆盖。

## 测试策略

- `pytest`，测试平铺在 `tests/`，大体一模块一文件（新增 `test_book_memory.py` 覆盖每书记忆），从仓库根运行全量测试。
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
- **严禁直接修改** `books/<slug>/.novel-forge/index.sqlite3`；它是可重建缓存。Canon Markdown 可人工审阅，但 Agent 产生的新信息必须经 candidate + promotion 工作流。
- `planning/chapter-sequences/*.json` 只能经章节序列 adapter 操作更新；`memory/context-cache/chXX-handoff.md` 是可重建缓存，不是 Canon 或不可变证据。
- `evidence/**/*.md` 是不可变创作过程证据；`evidence/runtime-audits/*.json` 是经 `record-session-audit` 创建的脱敏不可变运行证据。两者都不得覆盖，也都不能声明作者批准或发布许可。
- skill_adapter：`--root` 只接受绝对路径（相对路径返回 `invalid_root`）；变更操作必须 `--confirm <operation>`；`write-revision` 等拒绝 `library/` 内的输入路径；输入 Markdown 必须是 UTF-8（允许 BOM）。
- API 与 adapter 永不返回正文全文、Voice Bible / Scene Contract / Reader Review / Editorial Memo 内容。
- `git-checkpoint` 只 stage 当前书的目录（`library/<slug>/` 或 `books/<slug>/`，加 `docs/<slug>/` 如存在）；`data/` 永不入库。未经用户明确要求不得 commit / push。
- 正式短篇章节硬门槛：≥ 5000 个 CJK 汉字（用户硬性要求，不可下调）；正式小说不得使用 `--allow-below-minimum`。
- 不得在正文（`正文.md`）中写入提示词、工作流标记、研究笔记或 Agent 身份；未经用户明确批准不得宣称"已批准"。

## 其他目录速览

- `docs/`：25 份里程碑文档（快速开始、数据模型与状态机、质量门控、长篇记忆、人类叙事评测、有限认知、审稿收敛、Harness 完整性、章际连续性、精简文学闭环、外置 Harness 护栏与章节独立会话编排等）+ `docs/examples/`（人味解剖、AI 味反模式、Agent demo 证据与基准分析）+ `superpowers/plans/`。
- `.agents/skills/novel-forge/SKILL.md`：写作 Agent 的统一操作说明（canonical 位置，Kimi Code 与遵循 agents 约定的工具按项目级 skill 扫描）；`.claude/skills/novel-forge/SKILL.md` 是其逐字节镜像（Claude Code 扫描位置），**两份必须保持一致**（`tests/test_novel_project.py` 有防漂移测试）。
- `research/`：三份前期调研（开源 landscape、源码架构发现、已批准的生产系统架构）。
- `upstream/`：只读参考的开源项目源码（denova、NovelClaw、show-me-the-story），不参与构建。
- `experiments/`：草稿区（已 gitignore）；`library/`：legacy 书的实际资产（已 gitignore）。
- `run_novel_test.py`：一次性脚本示例（调用 `project_templates.init_book_project` 创建 `books/穿越问道`）。
