# 开源小说生产工具版图调研

> 调研日期：2026-07-15
>
> 目标：为 `D:\s-black-novel` 的正式小说生产系统筛选可借鉴、可复用或可隔离集成的开源能力。本文不是安装清单；所有项目须经过许可证、运行隔离、源码审查、样章回归测试后才可进入正式系统。

## 结论先行

不存在一套可以直接拿来保证小说质量的开源产品。

现有项目各自擅长一个层面：

- 写作编辑器擅长章节、场景、资料与导出管理。
- AI 小说平台擅长模型接入、长上下文、任务可观测性和界面。
- Agent 系统擅长分工、状态回写和阶段化流程。
- Skill 项目擅长把写作与审稿规范固化为可执行操作。

正式系统应采用“本地文本为真相来源 + 可审计状态库 + 场景级生成 + 独立质检 + 人工批准”的组合，而不是把任何单一项目作为底座。

## 候选项目

### A. AI 小说生产平台

| 项目 | 许可 | 观察到的能力 | 可借鉴点 | 不直接采用的原因 |
|---|---|---|---|---|
| [AI-Novel-Writing-Assistant](https://github.com/ExplosiveCoderflome/AI-Novel-Writing-Assistant) | AGPL / 商业双许可 | Creative Hub、LangGraph Agent Runtime、阶段产物、RAG、版本与桌面端 | 生产阶段可视化；产物而非聊天记录作为交付；检索轨迹；模型路由 | 许可不适合作为宽松许可的代码来源；架构重，需 Qdrant、Electron/Web monorepo |
| [NovelClaw](https://github.com/iLearn-Lab/NovelClaw) | MIT | 长篇工作台、会话、章节产物、分镜、人物/世界/风格面板、可编辑 memory banks、运行日志 | “可观测运行”与可编辑记忆库；草稿、日志、审稿面板共存 | Docker 多服务栈；需先做安全和数据模型审查；不能将它视作质量保证器 |
| [Show Me The Story](https://github.com/Nigh/show-me-the-story) | MIT | 单 Go 二进制、Web UI、章节级生成、审阅、伏笔/事实检查、全书润色、OpenAI-compatible API | 单机部署、项目文件落地、审计式章节流程、事实与伏笔检查 | 自动生成器取向强；其评审规则及“全书润色”质量必须以中文样章验证 |
| [Denova](https://github.com/alfredxw/denova) | Apache-2.0 | 小说/RPG IDE、Skills、Subagent workflow、Actor State、版本控制、多模型 | 角色状态、版本/Diff、Skill 调度、工作区优先 | Go + Node 双栈且仍 Beta；RPG 功能会造成范围膨胀；应只研究数据模型和工作流 |
| [Vela](https://github.com/heider-x/vela) | GPL-3.0 | Electron IDE、本地 SQLite、RAG、BYOK、多模型、AI Pipeline | 桌面编辑体验、本地优先知识库、模型提供商抽象 | GPL 不适合直接复用到独立主项目；RAG 与自动流水线仍须验证质量 |

### B. 长篇一致性与知识图谱

| 项目 | 许可 | 观察到的能力 | 可借鉴点 | 风险 |
|---|---|---|---|---|
| [SAGA](https://github.com/Lanerra/saga) | Apache-2.0 | LangGraph、Neo4j Canon、场景级生成、实体/关系抽取、矛盾检查、修订循环 | “正文 → 事实抽取 → 校验 → 回写 Canon”的闭环；按场景获取上下文 | 作者明确标为 not production-ready；Neo4j/Docker 对单人写作过重 |
| [Recurrent-LLM](https://github.com/jackaduma/Recurrent-LLM) | MIT | 将长短期记忆外置为人可读文件，递归生成长文本 | 可编辑、可审查、可回滚的记忆，而非隐藏提示词 | 模型和依赖较旧；不能直接作为现代生产引擎 |
| [WenShape](https://github.com/unitagain/WenShape) | PolyForm Noncommercial | 事实 JSONL、卡片、上下文选择、事件/人物/世界状态 | description-first 设定、证据服务、按章节距离衰减的召回 | 非商业许可证；不能直接复制代码或无边界整合 |

### C. 小说编辑器与人工创作管理

| 项目 | 许可 | 观察到的能力 | 可借鉴点 | 定位 |
|---|---|---|---|---|
| [novelWriter](https://github.com/vkbo/novelWriter) | GPL-3.0 | 纯文本项目、章节拆分、注释/梗概/交叉引用、版本控制友好 | Markdown/纯文本是长期资产；章节与资料分离；Git 友好 | 可作为独立人工编辑器候选，不复制进主项目 |
| [Manuskript](https://github.com/olivierkes/manuskript) | GPL-3.0 | 前提→梗概→大纲→索引卡→场景/章节、世界观、频率分析、HTML/ePub/ODT/DocX 导出 | 索引卡、时间线/剧情线、最终导出要求 | GUI 项目成熟但较重；适合作为 UX 参照或独立工具，不作核心代码来源 |

### D. 写作流程与审稿规范

| 项目 | 许可 | 可借鉴点 | 已处理情况 |
|---|---|---|---|
| [oh-story-claudecode](https://github.com/worldwonderer/oh-story-claudecode) | MIT | 场景化写作、去 AI 腔、审稿 findings、长篇扫描 | 已隔离克隆到 `D:\oh-story-claudecode`；只精选迁入 `novel-craft`，未执行 hooks/爬虫/安装器 |
| [LLM Writer Workshop](https://github.com/jrrobison1/llm-writer-workshop) | MIT | Writer、Editor、同行作者、Publisher 分离，批评优先于代写 | 借鉴审稿角色隔离；项目更接近教学 Demo |
| [Terminal Velocity](https://github.com/mind-protocol/terminal-velocity) | MIT | 10 Agent 完全自主写作、冗余扫描、整合和文档留痕 | 证明“多 Agent 自动写整本”会产生极高管理与冗余成本；只借质量角色分工，不采用自治生产模式 |

## 可复用能力地图

### 应进入正式系统的能力

- 本地 Markdown 正文与 Git 版本管理。
- 章节、场景、人物、地点、物件、时间线、伏笔的显式状态。
- 事件卡锁边界，场景合同锁镜头与冲突。
- 每次生成的输入上下文、模型、提示版本、输出、检查结果可追溯。
- 生成后从正文提取候选事实，人工批准后才写入 Canon。
- 结构、人物、叙事、连续性分离审稿。
- 只读 lint 与人工审稿分开，绝不自动机械替换正文。
- DOCX/EPUB/PDF/Markdown 的独立导出与排版验收。

### 明确排除

- 自动连续生成多章。
- 自动修改已经批准的 Canon。
- 把检索/RAG 命中当作事实正确性。
- Writer 生成后自己打分并自行通过。
- Hook 自动写文件、自动提交、自动重写正文。
- 为了降低检测率故意插错字、口误或破坏语法。

## 许可证策略

- 正式自制系统的推荐许可基线：自研代码优先 MIT 或 Apache-2.0；具体公开策略另定。
- MIT / Apache-2.0：允许在保留版权/许可声明前提下研究或选择性复用。
- GPL-3.0：仅作功能/UX 参考，除非未来明确接受 GPL 传染边界，否则不复制代码进入主系统。
- AGPL / 商业双许可：仅作架构研究，禁止复制或混入代码。
- PolyForm Noncommercial：仅作概念研究，禁止混入未来可能商用或公开的主系统。

## 当前建议

先做“成品级设计与验证”，再写产品：

1. 对 MIT/Apache 候选做隔离源码审查，提取数据模型、状态机、测试策略和导出路径。
2. 定义主系统的不可变产物和审批状态机。
3. 选取一篇全新短样章，做至少三轮盲测：生成、审稿、修订、人工阅读；不使用《无灯巷》作为质量证明。
4. 在样章连续通过文字自然度、连续性和导出验收后，才冻结技术栈并进入实现。
