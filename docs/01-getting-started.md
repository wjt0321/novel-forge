# 01 - 快速开始

## 环境要求

- Python 3.12+
- 可选：Pandoc（用于 DOCX/EPUB/PDF 导出）

## 安装

```bash
pip install -r requirements.txt
```

## 创建并初始化一本书

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
