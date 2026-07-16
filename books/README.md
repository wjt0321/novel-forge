# Novel Forge 书库

`books/` 是多个独立小说项目的集合。每个 `books/<slug>/` 都是自包含项目：正文、记忆、规划、审稿记录和 Agent 均不得跨项目混用。

| 项目目录 | 标题 | 状态 | 正文进度 | 工作流定位 |
|---|---|---|---|---|
| （暂无） | — | — | — | 新书经 `init-novel-project` 生成 |

## 管理约定

- 正文唯一入口始终是各项目的 `chapters/eXX/ch-XX/正文.md`。
- 新书经 `init-novel-project`（adapter 或 CLI）生成；不要在顶层共享 `memory/`、`planning/` 或 `reviews/`。
- 统一 Skill 说明位于 `.agents/skills/novel-forge/SKILL.md`（Claude Code 用户使用 `.claude/skills/` 下的镜像）；项目级写作宪法以各自的 `CLAUDE.md` 为准。
- 各书 `tools/*.py` 是仓库规则的薄壳，规则更新后经 `sync-tools <slug>` 刷新；voice-bible 等手写文件永不被覆盖。
- 项目状态仅用于导航，不替代各书的 Git 历史、章节状态或用户批准。

## 写作参考（起草与审稿前必读）

- `docs/examples/human-flavor-anatomy.md`：人味技法解剖（正面示范）。
- `docs/examples/ai-flavor-antipatterns.md`：AI 味反模式解剖（反面教材）。

> 2026-07：五本试验品（shenhao-cashback、star-ruin-sword、wasteland-echo、穿越问道、chuanyue-xiuxian-test）已完成其对照使命并清理；它们的管理结构（一书一目录、项目级隔离）保留在模板中，正/反两面的文字证据已固化进上述两份解剖文档。历史内容可从 Git 历史恢复。
