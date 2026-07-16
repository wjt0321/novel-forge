# 小说宪法：《穿越问道》

## 基本信息
- slug: `穿越问道`
- 标题: 《穿越问道》
- 类型: 穿越修仙悬疑
- 创建时间: 2026-07-16T13:12:57.545334+00:00
- **工作流版本**: v3（场景包、动作稿、对白账本、双编辑与章节编排）

## 正文明确定义
本书唯一正文入口：

```
books/穿越问道/chapters/eXX/ch-XX/正文.md
```

- 每章一个目录，命名规则 `e{序号}/ch-{序号}`。
- 目录内只放 `正文.md`，不放多个草稿版本。
- 历史版本由外部 Git 管理；不要在此目录堆叠 `正文-v2.md`。

## 当前进度
- 最新场景/章节: ________________
- 下一场目标: ________________
- 未回收承诺（最多列 3 条）: ________________

## 写作输入优先级
当接到“写下一章/场景”时，按以下顺序读取：
1. `planning/story-engine.md` — 核心张力
2. `memory/past.md` — 已发生事实
3. `memory/worldbuilding.md` — 世界规则
4. `planning/scene-package-chXX.md` — 目标、阻力、beat 因果链与信息账本
5. `planning/action-draft-chXX.md` — 动作版因果底稿
6. `planning/dialogue-ledger-chXX.md` — 关键对白账本（如有）
7. 上一条 `chapters/eXX/ch-XX/正文.md` 的最后 20%
8. `planning/research-boundaries.md` — 事实红线

## 严格边界
- 禁止自动批量生成多章。
- 禁止在未读 `memory/` 和 `planning/story-engine.md` 的情况下写正文。
- 禁止在正文里解释穿越/奇幻机制；只呈现感官与后果。
- 禁止 `——`、`……`、`不是X而是Y`、结论性旁白升华。
- 起草前完成本章场景包和动作稿；存在关键对白时完成对白账本。正文润色不得新增动作稿外的关键事件、设定、人物动机或长线谜团。
- 每章写完后必须运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md` 与 `python tools/narrative_gate.py chapters/eXX/ch-XX/正文.md planning/scene-package-chXX.md`。
- 修订优先局部 patch；因果或信息失败时回到场景包/动作稿，结构失败才重写场景。
- patch 命名：`patches/ch-{章节号}-{功能}.md`；只记录局部修订意图、位置、替换范围和验证结果，不替换整章正文。应用后重跑质检、相关编辑和一致性检查。
- 本模板默认包含 v3 编排资产；所有状态、记忆、审稿和上下文材料只留在本书目录内，严禁复制其他书的正文、`memory/`、`reviews/`、`context-cache/` 或已填写 `chXX` 实例。

## 角色团队（Claude 项目内调用）
- `context-collector`: 写前收集最小上下文，输出到 `memory/context-cache/`。
- `consistency-guard`: 写后检查实体、时间线、未回收承诺，输出报告。
- `orchestrator`: 维护章节状态、门禁证据与回退决策，不写正文。
- `causal-editor`: 审场景因果、信息账本与人物行动后果。
- `line-editor`: 审对白归属、重复、节奏与解释性行文。
- `chapter-editor`: 旧版兼容审稿器，最多 5 条问题，分 MUST/MAY。
