# Novel Forge 书库

`books/` 是多个独立小说项目的集合。每个 `books/<slug>/` 都是自包含项目：正文、记忆、规划、审稿记录和 Agent 均不得跨项目混用。

| 项目目录 | 标题 | 状态 | 正文进度 | 工作流定位 |
|---|---|---|---|---|
| `star-ruin-sword` | 《星墟剑主》 | active | e01 / ch-01 | v3 叙事工作流试点：场景因果、信息账本、双编辑与章节编排 |
| `chuanyue-xiuxian-test` | 《岩心问道》 | experimental | e01 / ch-01 | 早期实验样本，用于比较与回归观察，不与活跃项目共享资产 |
| `穿越问道` | 《穿越问道》 | template | 尚无正文 | 新书项目模板；初始化说明见其 `README.md` |

## 管理约定

- 正文唯一入口始终是各项目的 `chapters/eXX/ch-XX/正文.md`。
- 新书从模板复制为新的 `books/<slug>/`；不要在顶层共享 `memory/`、`planning/` 或 `reviews/`。
- 统一 Skill 说明位于 `skills/novel-forge/SKILL.md`；项目级写作宪法以各自的 `CLAUDE.md` 为准。
- 项目状态仅用于导航，不替代各书的 Git 历史、章节状态或用户批准。
