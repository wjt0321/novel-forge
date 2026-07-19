# 每书独立本地 Git 设计

## 目标

主仓库继续只管理 Novel Forge Harness；每个 `books/<slug>/` 小说项目拥有独立、
不配置 remote 的本地 Git 历史。正文、规划、Canon、审稿和 evidence 可以按章节
比较与恢复，但不会进入主仓库或被上传。

## 存储布局

```text
<root>/
├─ books/<slug>/                  # 小说工作区
│  └─ .git                        # gitdir 指针文件
└─ .local-book-git/<slug>.git/    # 外置 Git 元数据，主仓库忽略
```

使用 `git init --separate-git-dir` 创建仓库。书内 `.gitignore` 继续排除
`.novel-forge/`、`memory/context-cache/`、`.snapshots/` 和 Python 缓存。
仓库设置本地身份 `Novel Forge <novel-forge@local.invalid>`，不读取或修改全局身份，
不创建 remote。

## Checkpoint

- 初始化完成：`book-init: initialize <title>`。
- generation evidence 记录并绑定后：`chapter: chNN draft`。
- 章节进入 `ready` 后：`chapter: chNN ready`。
- 第 5/10/15... 章 ready 后：创建 annotated tag
  `checkpoint/ch01-ch05`、`checkpoint/ch06-ch10` 等；已有标签永不移动。

每个 checkpoint 在书仓库中执行 `git add -A`，提交该书全部可追踪文件。无变化时
返回 no-op。Git 不修改 evidence，也不替代状态机、ready、人类批准或发布决定。

## 迁移与状态

新书自动初始化。旧书运行 `sync-tools` 时补建本地仓库；dry-run 只报告计划，不写入。
新增只读 `book-git-status`，返回 initialized、head、dirty、remote_count、git_dir
和最近提交，不返回正文。新增显式 `init-book-git` 用于修复或单独迁移旧书。

## 删除与恢复

删除 `books/<slug>` 后，外置历史仍存在，可用同一 Git 目录恢复工作区。实验样本若
要求彻底清除原文，必须同时清除对应 `.local-book-git/<slug>.git`；系统不提供自动
删除操作，继续遵守“无删除 API”边界。

## 失败边界

- 找不到 Git、gitdir 指向错误、仓库配置 remote 或提交失败时返回明确错误。
- 初始化失败不留下半成品 gitdir：新建的元数据目录会清理，书文件保持不变。
- evidence 或 ready 已成功写入后，checkpoint 结果随 adapter 返回；失败不伪造提交，
  `book-git-status` 会显示 dirty，下一次显式 checkpoint 可收敛。
- Git 命令只在 `books/<slug>` 工作区运行；Novel Forge adapter 仍以显式
  `--root <主仓库绝对路径>` 定位 Harness。
