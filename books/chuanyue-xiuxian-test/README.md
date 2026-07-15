# 《岩心问道》

- 类型: 穿越修仙
- 创建时间: 2026-07-15T17:33:13.770482+00:00

## 如何阅读
打开最新正文：

```
books/chuanyue-xiuxian-test/chapters/eXX/ch-XX/正文.md
```

## 目录
- `chapters/` — 正文唯一入口
- `memory/` — 人物、历史、世界设定
- `planning/` — 故事发动机、研究边界、事件卡
- `reviews/` — 审稿记录
- `patches/` — 局部修订 patch
- `.snapshots/` — 临时快照（可由 Claude 或外部工具保存）

## 默认工作流
1. 写前：让 `context-collector` 收集上下文。
2. 起草：按 `CLAUDE.md` 宪法写 `正文.md`。
3. 自检：运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md`。
4. 审稿：让 `chapter-editor` 审阅。
5. 修订：小改放 `patches/`，结构失败才重写场景。
