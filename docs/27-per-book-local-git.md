# 每书本地版本历史（v4.2）

## 问题

`books/` 是本地小说工作区，长期不进入 Harness 主仓库。这样避免正文随代码公开，
但也让一部长篇在反复写作、审稿、回炉和实验清理时缺少细粒度 diff 与恢复点。

把每本书直接提交到主仓库会重新混合代码与小说资产；把所有小说塞进同一个本地
仓库又会让恢复、清理和实验隔离互相牵连。v4.2 因此采用“一书一仓库、历史外置、
不配置 remote”的结构。

## 目录结构

```text
<root>/
├─ books/<slug>/
│  ├─ .git                         # gitdir 指针
│  ├─ chapters/
│  ├─ planning/
│  ├─ memory/
│  ├─ reviews/
│  └─ evidence/
└─ .local-book-git/<slug>.git/     # 真实 Git 元数据
```

`books/` 与 `.local-book-git/` 都被 Harness 主仓库忽略。书内 Git 只追踪该书工作区，
不能读取、stage 或提交其他小说，也不得配置 remote。

外置 gitdir 有两个目的：

1. 误删 `books/<slug>/` 后仍可从本地历史恢复；
2. 清理实验项目时，是否保留历史成为一个明确选择，而不是目录删除的副作用。

## 自动 checkpoint

新项目创建后自动产生：

```text
book-init: initialize <title>
```

章节工作流在两个稳定边界自动提交：

```text
chapter: chNN draft
chapter: chNN ready
```

前者发生在当前 generation 证据成功绑定后，保存本轮正文、规划和来源状态；后者
发生在完整 ready 门通过后，保存审稿、门禁与最终章节状态。第 5、10、15……章
ready 时，还会创建不可移动的 annotated tag：

```text
checkpoint/ch01-ch05
checkpoint/ch06-ch10
```

自动 checkpoint 只在工作区确有变化时产生新 commit。重复调用不会制造空提交或
虚假的回炉轮次。

## Adapter 操作

所有操作仍走 JSON-only adapter：

```bash
# 只读状态
python -m app.novel_forge.skill_adapter --root <absolute-root> \
  book-git-status <slug>

# 为旧项目补建本地 Git
python -m app.novel_forge.skill_adapter --root <absolute-root> \
  --confirm init-book-git init-book-git <slug> --title "<title>"

# 人工恢复点
python -m app.novel_forge.skill_adapter --root <absolute-root> \
  --confirm book-git-checkpoint book-git-checkpoint <slug> \
  --message "checkpoint: before structural rewrite" \
  [--tag checkpoint/ch01-ch05]

# 工作区被删除或为空时，从外置历史恢复
python -m app.novel_forge.skill_adapter --root <absolute-root> \
  --confirm restore-book-git restore-book-git <slug>
```

`sync-tools` 会为尚未采用该结构的旧 books 项目初始化本地 Git。`project-status`
返回 metadata-only 状态，包括 HEAD、dirty、变更路径数量和 remote 数，不返回正文。

## 故障语义

Git 是恢复层，不是创作事实的事务数据库。generation evidence 或 ready 状态已经
成功落盘后，如果本地 checkpoint 因 Git 不可用、指针损坏或意外 remote 而失败：

- 原业务结果不回滚；
- 返回值中的 `local_git.status` 明确为 `failed`；
- 下一步写作前应先修复 Git 状态并建立人工 checkpoint；
- 不得把失败隐藏成成功，也不得用 Git commit 反向证明 evidence 有效。

这避免了“版本工具故障导致不可变证据被撤销”，同时让恢复能力退化保持可见。

## 权限边界

- 本地 commit 不等于 blind-reader pass、chapter-editor 决定、作者批准或发布许可；
- 自动提交不授权 push，也不允许 Agent 创建 remote；
- Harness 主仓库与每书仓库是两个独立权限域；
- `restore-book-git` 只恢复 Git 已跟踪文件，空目录或可重建缓存可由 `sync-tools`
  补齐；
- 不提供远程同步、自动发布或自动删除接口。

## 实验样本清理

实验数据完成聚合留证后，若要求彻底删除原文，必须同时处理：

```text
books/<slug>/
.local-book-git/<slug>.git/
```

删除前必须把两个路径解析为预期根目录内的绝对路径。只删除工作区会保留完整可恢复
历史；只删除 gitdir 会留下正文但失去版本历史。这种双路径设计让“恢复”和“彻底
遗忘”都成为显式、可审计的决定。
