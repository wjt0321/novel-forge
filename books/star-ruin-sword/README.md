# 《星墟剑主》

- 类型: 星际修仙
- 创建时间: 2026-07-16T01:20:18.978911+00:00

## 如何阅读
打开最新正文：

```
books/star-ruin-sword/chapters/eXX/ch-XX/正文.md
```

## 目录
- `chapters/` — 正文唯一入口
- `memory/` — 人物、历史、世界设定
- `planning/` — 故事发动机、研究边界、事件卡
- `reviews/` — 审稿记录
- `patches/` — 局部修订 patch
- `.snapshots/` — 临时快照（可由 Claude 或外部工具保存）

## 默认工作流
1. 写前：让 `context-collector` 收集上下文，并填写 `planning/scene-package-chXX.md`。
2. 先完成 `planning/action-draft-chXX.md`；有关键对白时填写 `planning/dialogue-ledger-chXX.md`。
3. 仅在动作稿因果成立后，按 `CLAUDE.md` 宪法润色 `正文.md`；润色不得新增关键事件或谜团。
4. 自检：运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md` 与 `python tools/narrative_gate.py chapters/eXX/ch-XX/正文.md planning/scene-package-chXX.md`。
5. 审稿：依次交 `causal-editor`（因果/信息）和 `line-editor`（行文/对白）；旧 `chapter-editor` 仅用于兼容。
6. 修订：因果门禁失败回到场景包或动作稿；纯行文问题才做局部 patch。
