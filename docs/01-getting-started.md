# 01 - 快速开始

> 当前自动长篇工作流以 `books/`、`lean_native` 和 diff 暂存正文为默认；请先阅读
> `docs/43-fiction-first-lean-native-workflow.md` 与
> `docs/44-current-workflow-logic-audit.md`。本页后半部分的 `library/` 命令是 legacy
> 审计工作流，仍受支持，但不是通用写作 Agent 的默认入口。

## 环境要求

- Python 3.12+
- 可选：Pandoc（用于 DOCX/EPUB/PDF 导出）

## 安装

```bash
pip install -r requirements.txt
```

## 当前推荐：自动三角色写作

```bash
PYTHONPATH=. python tools/novel-workflow.py --root <仓库根绝对路径> start my-novel \
  --title "我的小说" --genre "都市" --protagonist "主角设定" \
  --world "世界观" --conflict "本章核心冲突" --hook "本章结尾钩子"
```

Windows 的 Git Bash/类 Bash 请把 `--root` 写成 `D:/path/to/repo`；反斜杠路径必须整体加引号。CLI 会在创建资产前拒绝 `D:foo` 一类驱动器相对路径。

随后由 Lead 循环执行 `next-action`、等待宿主官方终态、调用 `complete-role`。Writer
只写当前书 diff 暂存正文，两个审稿角色只写简短结果；双审通过后 Python 自动晋升、
记证据并建立每书 Git 恢复点。

## Legacy：创建并初始化一本书

源码包位于 `app/novel_forge`。运行 CLI 前请将 `app` 加入 `PYTHONPATH`：

```bash
# Windows (cmd)
set PYTHONPATH=app
python -m novel_forge.cli init-book my-novel --title "我的小说"

# Windows (PowerShell)
$env:PYTHONPATH="app"
python -m novel_forge.cli init-book my-novel --title "我的小说"
```

这会创建：

```text
library/my-novel/
├─ manuscript/revisions/   # 章节 revision Markdown 文件
├─ canon/                  # 已批准 Canon 事实镜像
├─ planning/chapters/      # 场景合同模板
└─ exports/                # 导出产物与 manifest
data/novel-forge.db        # SQLite 审计账本
```

## 创建章节并写入 revision

```bash
python -m novel_forge.cli create-chapter my-novel 1 --title "第一章"
python -m novel_forge.cli write-revision my-novel 1 --from-file chapter1.md --note "初稿"
```

## 静态检查与审稿

```bash
python -m novel_forge.cli lint-chapter my-novel 1
python -m novel_forge.cli review-chapter my-novel 1
python -m novel_forge.cli approve-chapter my-novel 1 --note "通过"
```

## 导出

```bash
python -m novel_forge.cli export-book my-novel --format markdown
```

## 本地 API

```bash
set PYTHONPATH=app
python -c "from app.novel_forge.api import create_app; import uvicorn; uvicorn.run(create_app('.'), host='127.0.0.1', port=8000)"
```

访问 `http://127.0.0.1:8000/health` 和 API 文档 `http://127.0.0.1:8000/docs`。
