# S-Black Novel Forge：正式生产系统架构

> 状态：已批准进入实施
>
> 项目根目录：`D:\s-black-novel`
>
> 产品原则：不是自动写书机，而是可审计、可回滚、以作者批准为最终边界的长篇小说生产系统。

## 产品目标

为中文长篇小说提供从选题、设定、场景规划、单章创作、独立审稿、修订、Canon 审批到 DOCX/EPUB/PDF 导出的完整生产链。

系统必须使每一章的来源、模型输入、审稿证据、修订差异、事实升级和导出版本可追溯。

## 非目标

- 不自动连续生成多章。
- 不让模型自行批准章节或写入 Canon。
- 不用“AI 检测分数”替代人工阅读。
- 不通过机械替换标点或故意写错字来“去 AI 味”。
- 不在第一阶段绑定云端向量数据库、Docker、重型多服务或桌面壳。

## 最终模块边界

### 1. Manuscript Asset Layer

- Markdown 为章节正文唯一真相来源。
- 每次正文变动形成新 revision，不覆盖已批准版本。
- 章节按场景切分，场景和版本都可定位。
- Git 可选作为第二层备份，不承担应用事务逻辑。

### 2. Canon and Story State

- Canon Fact：已批准、带来源章节和证据范围、不可被 Agent 自动改变。
- Candidate Fact：从草稿/审稿/抽取生成，等待人工决断。
- Story State：人物、关系、地点、物件、时间线、伏笔、场景合同。
- 所有状态变化有来源、时间、操作者和审批状态。

### 3. Writing Orchestration

- 只允许用户明确请求一章或一组场景。
- 生成输入由“场景合同 + 相关 Canon + 上章承接 + 未回收伏笔 + 叙事声线”组成。
- 每次运行记录模型、提示词版本、上下文条目清单、输出 hash、耗时和错误。
- Provider 使用 OpenAI-compatible 抽象，密钥只由本地环境变量提供。

### 4. Quality Gates

- 静态风格检查：破折号、省略号、否定翻转、作者总结、字数口癖、异常标点密度等。
- 审稿账本：结构、角色、叙事、连续性四个视角，S1-S4 finding schema。
- Canon 冲突检查：草稿或候选事实不能与已批准 Canon 静默冲突。
- Gate 只能拦截或报告，绝不自动重写正文。

### 5. Approval and Revision

- 状态机：`draft → linted → reviewed → revision_requested → revised → approved → exported`。
- 只有作者/编辑可：批准章节、接受/拒绝 Candidate Fact、重开已批准章节、批准导出。
- 所有修订保留 revision、差异、处理的 findings。

### 6. Export and Evidence

- 首批交付 Markdown、DOCX、EPUB、PDF。
- 每次导出生成 manifest：来源 revision、导出设置、文件 hash、创建时间。
- 中文字体、章节标题、目录、分页和空段落都需要自动/人工验收清单。

## 数据存储策略

```text
D:\s-black-novel\
├─ app\                     # 应用源码
├─ library\                 # 小说项目资产（可迁移、可 Git）
│  └─ <book-slug>\
│     ├─ manuscript\         # Markdown 正文、revision 快照
│     ├─ canon\              # 人工可读 Canon 镜像
│     ├─ planning\           # 事件卡、场景合同、声线
│     └─ exports\            # 导出产物与 manifest
├─ data\                     # SQLite 账本、运行记录（不含密钥）
├─ tests\                    # fixture、回归和导出验收
├─ docs\                     # 产品与操作文档
└─ research\                 # 上游调研与取证
```

SQLite 为状态、索引和审计账本；Markdown 是人可读、长期可存的作品资产。数据库损坏时可以从 Markdown 和 manifest 重建索引；反过来不允许数据库成为唯一正文来源。

## 技术选型：实施基线

- **后端/CLI**：Python 3.12+，标准库 `sqlite3`、`pathlib`、`subprocess`；FastAPI 作为本地 API。
- **前端**：React + TypeScript + Vite；后续在核心 CLI/API 稳定后实现。
- **数据库**：SQLite，Fts5 用于本地全文检索。
- **导出**：Pandoc 作为受控外部转换器；每种格式保留 manifest 和检查。
- **模型**：OpenAI-compatible HTTP provider；模型调用只经 provider 层。
- **测试**：pytest；静态检查、状态机、SQLite 事务、审计账本、导出 manifest 必须有测试。

选择 Python 的原因：本地文本、SQLite、DOCX/EPUB/PDF 生态、测试和后续 NLP 校验更适合单机创作生产线。UI 不得阻塞核心 CLI/API。

## 第一实施里程碑：Foundation + Vertical Slice

必须实现，不是 Demo：

1. 初始化书籍与目录，创建 SQLite schema。
2. 创建章节、场景合同、草稿 revision。
3. Canon Fact / Candidate Fact 的创建、审批和审计记录。
4. 章节状态机及非法状态迁移阻止。
5. 只读 prose lint，并把结果写入 Review Ledger。
6. 四维 finding 的结构化增删改、关闭与 revision 关联。
7. 章节 revision diff、批准、回滚到指定 revision。
8. Markdown 导出 manifest；DOCX/EPUB/PDF 导出适配器和可用性预检。
9. CLI + 本地 FastAPI API；前端只在后端契约稳定后开始。
10. 完整 pytest 回归与一部 fixture 小说的端到端验收。

## 成品验收门槛

- 任何状态机错误、未经批准 Canon 写入、已批准正文静默覆盖均为阻塞缺陷。
- 所有正文变更可找到来源 revision 和差异。
- 全部静态检查、审稿 finding、审批动作和导出 manifest 可追溯。
- 新书 fixture 从创建到审批、修订、导出全过程可自动回归。
- 必须使用至少一篇人读样章做盲审；脚本绿灯不是通过标准。
