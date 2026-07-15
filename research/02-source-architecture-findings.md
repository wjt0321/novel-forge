# 源码级架构取证：首批候选

> 日期：2026-07-15
>
> 范围：仅静态阅读隔离克隆源码；未安装依赖、未启动服务、未写入任何上游项目。

## 目的

README 中的“支持长篇一致性”“有记忆库”“有审稿”不构成工程证据。本文件记录目前从源码结构和核心数据模型中确认的可借鉴点，以及不能照搬的边界。

## 1. Show Me The Story

- 隔离路径：`D:\s-black-novel\upstream\show-me-the-story`
- 上游许可：MIT。
- 源码中有实际单元测试：章节块、导入、弧线、伏笔、存储、字数、删除、元数据、引用等。

### 已确认的数据模型

`internal/story/storage.go` 定义了：

- `ChapterState`：章节号、标题、章节纲要、摘要、状态、字数、稳定段落块。
- 章节状态机：`pending → writing → review → accepted`。
- `Foreshadow`：名称、描述、埋设章、目标回收章、状态、事件历史、回收结论。
- 伏笔状态：`planted / progressing / resolved / abandoned`。
- `MemoryEntry`：按角色、地点、物件、事件、承诺等分类，并绑定章节和位置。
- `Arc`：卷/弧线级范围与在完成后生成的摘要。
- `WritingConflict`：章节冲突、原因、是否可调和、建议动作。

### 已确认的存储策略

`internal/story/state.go` 与 `storage.go` 使用“元数据与正文分离”：

- 项目元数据存 `project.json`。
- 每章正文单独存 `chapters/000001.json`。
- 保存时按正文哈希只更新变更章节。
- API 列表读取时移除完整正文，只返回状态、字数、内容修订 hash 与记忆片段。
- 文件写入采用原子写入 helper。

### 对正式系统的价值

这套“分章正文不可混入总状态文件 + 章节接受状态 + 伏笔生命周期 + 原子保存 + revision hash”是正式系统必须吸收的架构原则。

### 不照搬的部分

- 不把正文作为 JSON 字符串保存为唯一真相；正式系统以 Markdown 正文为真相来源，数据库/JSON 只存索引、状态、审稿和运行记录。
- 不能在大纲重生成时静默删除“孤儿章节”。任何移除正文必须进入显式归档/回收站和人工确认。

## 2. NovelClaw

- 隔离路径：`D:\s-black-novel\upstream\NovelClaw`
- 上游许可：MIT。
- 架构为 Python 多应用/Docker 工作台，包含 run 目录、worker/progress 日志、章节输出、分镜/稿件/世界观/人物/风格表面。

### 已确认的记忆银行分层

其源码中存在显式 memory-bank 分组，而不是一段混合式“长期记忆”：

- 角色与关系。
- 世界状态。
- 连续性事实。
- 工具观察。
- 修订循环。
- 运行现场。

其中“连续性事实”明确指后续章节不得违背的 Canon facts；界面/API 支持查看、添加、编辑记忆条目。

### 对正式系统的价值

正式系统应区分：

1. **Canon**：人工批准的不可违背事实。
2. **Candidate Facts**：从正文/模型输出提取，尚未批准的候选事实。
3. **Working Memory**：单次生成临时上下文，可过期。
4. **Review Findings**：审稿问题及处理状态。
5. **Run Evidence**：模型、提示版本、输入上下文清单、检查输出、产物 hash。

五类数据不可混写。尤其禁止让模型把 Candidate Facts 自动升级为 Canon。

### 不照搬的部分

- 不直接采用 Docker 多服务工作台。
- 不把 UI 页面当作系统事实来源。
- 不将“可编辑记忆”放宽为任何 Agent 都能编辑 Canon。

## 3. Denova

- 隔离路径：`D:\s-black-novel\upstream\denova`
- 上游许可：Apache-2.0。
- README 宣称核心能力包括 Skills、Subagent Workflow、Actor State、项目 Git/Diff、OpenAI-compatible 模型接入、工作区配置。

### 当前可取原则

- 将角色状态作为显式一等数据，而不是只存在人物小传。
- 每次变更都应支持 diff / 回滚，而不是“修订覆盖原文”。
- 模型接入应抽象为 provider adapter，避免业务逻辑绑定特定模型。

### 待进一步核验

当前隔离拉取已完成 Git 工作区，但尚未完成其具体 Go/TypeScript 数据层与测试覆盖阅读。不得仅依据 README 选其为底座。

## 4. 研究结论：正式系统的最小不可妥协架构

以下不是 MVP 范围，而是成品必须具备的质量底线：

```text
Markdown Manuscript（正文真相来源）
        │
        ├── Canon Registry（审批后事实、版本、来源章节）
        ├── Story State（人物状态、时间线、伏笔、场景、关系）
        ├── Run Ledger（提示、模型、上下文、输出、hash、时间）
        ├── Review Ledger（四维 finding、严重度、处置状态）
        └── Export Ledger（DOCX/EPUB/PDF 版本、校验、渲染证据）
```

状态改变必须经过明确动作：

```text
Draft → linted → reviewed → revision requested → revised → approved → exported
```

- Writer 只能产生 Draft。
- Lint 只能发现问题。
- Review 只能提出 finding。
- Author/Editor 才能批准事实进入 Canon、批准章节、批准导出。
- 已批准的章节只能生成新的修订版本，不能静默覆盖。

## 后续研究任务

- 对 `show-me-the-story` 的导入、伏笔冲突、审稿与全书润色实现继续做源码审查。
- 对 NovelClaw 的 memory index、运行产物和权限边界做源码审查。
- 对 Denova 的 Actor State、Git/Diff 与 Skills 调度做源码审查。
- 对 AGPL 项目仅分析数据/流程思想，记录不可复制的边界。
- 独立调研导出链：Markdown → DOCX/EPUB/PDF 的格式、目录、脚注、中文字体与回归测试。
