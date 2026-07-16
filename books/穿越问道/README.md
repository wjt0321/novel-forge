# 《穿越问道》

- 类型: 穿越修仙悬疑
- 创建时间: 2026-07-16T13:12:57.545334+00:00
- 默认工作流: v3；完整编排说明见 `skills/novel-forge/SKILL.md`。

## 如何阅读
打开最新正文：

```
books/穿越问道/chapters/eXX/ch-XX/正文.md
```

## 目录
- `chapters/` — 正文唯一入口
- `memory/` — 人物、历史、世界设定
- `planning/` — 故事发动机、研究边界、事件卡
- `reviews/` — 审稿记录
- `patches/` — 局部修订 patch
- `.snapshots/` — 临时快照（可由 Claude 或外部工具保存）

## 默认工作流
1. `context-collector` 收集最小上下文，并建立章节状态。
2. 填写 `scene-package`、`action-draft`；有关键对白时填写 `dialogue-ledger`。
3. 按 `CLAUDE.md` 宪法起草 `正文.md`，润色不得偷渡关键事件、设定或动机。
4. 运行 `quality_check.py` 和 `narrative_gate.py`。
5. 依次交 `causal-editor`、`line-editor`、`consistency-guard` 审阅；由 `orchestrator` 记录门禁及回退。
6. 修订：结构问题回到场景包/动作稿，纯行文问题才用局部 patch。

所有 v3 资产只在本书目录内使用；不得复制其他书的正文、记忆、审稿报告、上下文缓存或已填写章节实例。完整约定见 `skills/novel-forge/SKILL.md`。
