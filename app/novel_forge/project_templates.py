"""Templates for the new `books/<slug>/` front-of-house project layout.

This module is intentionally separate from the core SQLite-backed service.
The new layout does not require a database to be usable by a writing Agent;
legacy `library/` workflows remain intact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProjectTemplateError(Exception):
    """Raised when project template arguments are invalid."""


QUALITY_CHECK_PY = r'''"""Lightweight prose quality checker for a single Markdown file.

This script is intentionally small and rule-based. It flags surface problems
that are cheap to detect and expensive to miss (wrong punctuation, duplicated
quotes, forbidden patterns). It does NOT claim to detect "AI writing" or
literary quality.

Usage:
    python tools/quality_check.py PATH_TO_CHAPTER.md
"""

import re
import sys
from pathlib import Path


# CJK Unified Ideographs (Han)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def check(text: str, path: str = "") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        # Blocking / forbidden patterns
        if "——" in line:
            findings.append({
                "line": idx,
                "rule": "em-dash",
                "severity": "blocking",
                "message": "Chinese em-dash '——' is forbidden.",
                "snippet": line.strip(),
            })
        if "……" in line:
            findings.append({
                "line": idx,
                "rule": "ellipsis",
                "severity": "blocking",
                "message": "Chinese ellipsis '……' is forbidden.",
                "snippet": line.strip(),
            })

        # Negation flip patterns
        if re.search(r"不是[^，。！？\n]{1,15}而是", line) or \
           re.search(r"不是[^，。！？\n]{1,15}是[^，。！？\n]{1,15}", line):
            findings.append({
                "line": idx,
                "rule": "negation-flip",
                "severity": "blocking",
                "message": "'不是X而是Y / 不是X是Y' pattern is forbidden.",
                "snippet": line.strip(),
            })

        # Duplicated quotes like ""...""
        if re.search(r'""[^"]*""', line):
            findings.append({
                "line": idx,
                "rule": "quote-duplication",
                "severity": "advisory",
                "message": "Duplicated quotes \"\"...\"\" detected.",
                "snippet": line.strip(),
            })

        # Question particle followed by period
        if re.search(r"[吗呢吧么]。", line) and not re.search(r"[什么怎么这么那么多么要么]。", line):
            findings.append({
                "line": idx,
                "rule": "question-mark-mismatch",
                "severity": "advisory",
                "message": "Question particle followed by period instead of '?'.",
                "snippet": line.strip(),
            })

        # Common word-count tic: explicit quantifier immediately before 字.
        # Excludes ordinals (第...) and classifier 行 (一行字 / 第一行字).
        if re.search(r"(?<![第])[零一二三四五六七八九十百千万两0-9]{1,4}(?:个|枚)?字", line):
            findings.append({
                "line": idx,
                "rule": "word-count-tic",
                "severity": "advisory",
                "message": "Explicit word-count phrase like '五个字' detected.",
                "snippet": line.strip(),
            })

    return findings


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("Usage: python quality_check.py <markdown-file>", file=sys.stderr)
        return 2

    path = Path(argv[0])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8-sig")
    findings = check(text, str(path))
    blocking = [f for f in findings if f["severity"] == "blocking"]
    advisory = [f for f in findings if f["severity"] == "advisory"]

    print(f"File: {path}")
    print(f"CJK characters: {count_cjk(text)}")
    print(f"Blocking: {len(blocking)}, Advisory: {len(advisory)}")
    if findings:
        print("Findings:")
        for f in findings:
            print(f"  L{f['line']} [{f['rule']}] {f['severity']}: {f['message']}")
    else:
        print("No findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _claude_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    return f"""# 小说宪法：《{title}》

## 基本信息
- slug: `{slug}`
- 标题: 《{title}》
- 类型: {genre}
- 创建时间: {timestamp}

## 正文明确定义
本书唯一正文入口：

```
books/{slug}/chapters/eXX/ch-XX/正文.md
```

- 每章一个目录，命名规则 `e{{序号}}/ch-{{序号}}`。
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
4. 上一条 `chapters/eXX/ch-XX/正文.md` 的最后 20%
5. `planning/research-boundaries.md` — 事实红线

## 严格边界
- 禁止自动批量生成多章。
- 禁止在未读 `memory/` 和 `planning/story-engine.md` 的情况下写正文。
- 禁止在正文里解释穿越/奇幻机制；只呈现感官与后果。
- 禁止 `——`、`……`、`不是X而是Y`、结论性旁白升华。
- 每章写完后必须运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md`。
- 修订优先局部 patch；结构失败才重写场景。

## 角色团队（Claude 项目内调用）
- `context-collector`: 写前收集最小上下文，输出到 `memory/context-cache/`。
- `consistency-guard`: 写后检查实体、时间线、未回收承诺，输出报告。
- `chapter-editor`: 独立审稿，最多 5 条问题，分 MUST/MAY。
"""


def _readme_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    return f"""# 《{title}》

- 类型: {genre}
- 创建时间: {timestamp}

## 如何阅读
打开最新正文：

```
books/{slug}/chapters/eXX/ch-XX/正文.md
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
"""


def _memory_past_md() -> str:
    return """# 过去时间线

## 已锁定事实
- 记录既成事件，不写未发生内容。
- 每条事实尽量带场景出处。

## 待揭示 / 角色未知
- 写角色不知道的真相，并标注“角色未知”。

## 当前时间锚
- 故事现在时: ________________
"""


def _memory_worldbuilding_md() -> str:
    return """# 世界设定

## 物理规则
- 现实世界还是奇幻？__________
- 限制 / 不可能发生的事：__________

## 社会规则
- 时代、地点、权力结构：__________
- 日常物件与语言：__________

## 禁忌
- 人物不能说什么、做什么：__________
"""


def _memory_future_index_md() -> str:
    return """# 未来索引

## 已规划但尚未写的场景
- 场景 ref / 目标 / 关键转折

## 未回收承诺
- 承诺内容 / 预计回收场景

## 备用结局 / 分支
- 仅供参考，不自动执行
"""


def _planning_story_engine_md() -> str:
    return """# 故事发动机

## 核心秘密
- 主角或世界隐藏什么？__________

## 欲望
- 主角想要什么？__________

## 替代行动
- 主角本可以做但未做的选择：__________

## 不可逆选择
- 一旦作出便改变后续的选择：__________

## 即时代价
- 选择立刻失去 / 暴露 / 伤害什么？__________

## 主题压力
- 贯穿全篇的追问或张力：__________
"""


def _planning_research_boundaries_md() -> str:
    return """# 研究边界

## 已验证事实
| 来源 | 日期 | 用途 | 事实红线 |
|------|------|------|----------|
|      |      |      |          |

## 虚构种子
- 明确标注为虚构的内容：__________

## B/C 级或不确定声明
- 不能作为唯一关键情节支点：__________
"""


def _agent_context_collector_md() -> str:
    return """# Context Collector

## 角色
只收集，不写正文。

## 任务
当用户要求“准备写第 X 章/场景”时：
1. 读 `CLAUDE.md` 宪法。
2. 读 `planning/story-engine.md` 和 `planning/research-boundaries.md`。
3. 读 `memory/past.md` 和 `memory/worldbuilding.md`。
4. 读上一条 `chapters/eXX/ch-XX/正文.md` 的最后 20%。
5. 读 `memory/future/00-index.md` 中的相关条目。
6. 输出一份 **最小上下文摘要** 到 `memory/context-cache/`。

## 输出格式
- 场景目标（1 句）
- 必须出现的物件/动作（最多 3 个）
- 不能违反的设定红线（最多 3 条）
- 上一条未回收的张力（最多 2 条）
- 禁止在正文中出现的内容（如机制解释、结论升华）

## 边界
- 不生成正文。
- 不修改 `chapters/`。
- 不调用外部搜索。
"""


def _agent_consistency_guard_md() -> str:
    return """# Consistency Guard

## 角色
写后检查员，不写正文。

## 任务
在 Claude 完成一段正文后，读：
1. 刚写的 `chapters/eXX/ch-XX/正文.md`
2. `memory/past.md`
3. `memory/worldbuilding.md`
4. `memory/entities/` 中相关实体卡（如存在）

## 检查清单
- [ ] 实体名称与已记录一致
- [ ] 角色认知不超过其已知信息
- [ ] 时间线无矛盾
- [ ] 已埋承诺有回收或明确未回收
- [ ] 无现代语汇/网络用语出现在非现代背景
- [ ] 无突兀背景卸货句

## 输出
写一份简短报告到 `reviews/` 或直接在对话中返回：
- 问题（最多 3 条）
- 位置（场景/行）
- 建议修订方向

## 边界
- 不生成新正文。
- 不修改文件。
"""


def _dot_gitignore() -> str:
    return """# Per-book ignore rules for books/<slug>/
.snapshots/
memory/context-cache/
__pycache__/
*.pyc
"""


def _agent_chapter_editor_md() -> str:
    return """# Chapter Editor

## 角色
独立编辑，不自行重写全文。

## 任务
读最新 `chapters/eXX/ch-XX/正文.md`，输出最多 5 条审稿意见。

## 审稿维度
1. 突兀背景卸货
2. 说话人不明的碎对话
3. 对话卡片化 / 清单化
4. 标点错误（尤其引号）
5. 模型化均匀短段和解释性升华

## 输出格式
每条：
- 位置
- 原文证据（1-2 句）
- 读者效果
- 修订意图（不替作者写）

## 分类
- **MUST**: blocking，必须改
- **MAY**: optional，可改可保留

## 边界
- 不生成新正文。
- 不修改文件。
- 不判断文学价值或市场潜力。
"""


# Mapping of relative path -> (template factory, factory args)
# Paths are relative to books/<slug>/.
TEMPLATE_FILES: dict[str, tuple[Any, tuple[str, ...]]] = {
    ".gitignore": (_dot_gitignore, ()),
    "CLAUDE.md": (_claude_md, ("slug", "title", "genre", "timestamp")),
    "README.md": (_readme_md, ("slug", "title", "genre", "timestamp")),
    "memory/past.md": (_memory_past_md, ()),
    "memory/worldbuilding.md": (_memory_worldbuilding_md, ()),
    "memory/future/00-index.md": (_memory_future_index_md, ()),
    "planning/story-engine.md": (_planning_story_engine_md, ()),
    "planning/research-boundaries.md": (_planning_research_boundaries_md, ()),
    "tools/quality_check.py": (lambda: QUALITY_CHECK_PY, ()),
    ".claude/agents/context-collector.md": (_agent_context_collector_md, ()),
    ".claude/agents/consistency-guard.md": (_agent_consistency_guard_md, ()),
    ".claude/agents/chapter-editor.md": (_agent_chapter_editor_md, ()),
}

# Directories that should exist; files under them are created via TEMPLATE_FILES.
REQUIRED_DIRECTORIES = [
    "chapters",
    "memory/entities",
    "memory/future",
    "memory/context-cache",
    "planning/events",
    "reviews/archive",
    "patches",
    ".snapshots",
    "tools",
    ".claude/agents",
]


def render_templates(slug: str, title: str, genre: str) -> dict[str, str]:
    """Return a mapping of relative path -> rendered content."""
    timestamp = datetime.now(timezone.utc).isoformat()
    rendered: dict[str, str] = {}
    for rel_path, (factory, arg_names) in TEMPLATE_FILES.items():
        args: list[str] = []
        for name in arg_names:
            if name == "slug":
                args.append(slug)
            elif name == "title":
                args.append(title)
            elif name == "genre":
                args.append(genre)
            elif name == "timestamp":
                args.append(timestamp)
            else:
                args.append("")
        rendered[rel_path] = factory(*args)
    return rendered


def init_book_project(root: Path, slug: str, title: str, genre: str) -> dict[str, Any]:
    """Create the recommended `books/<slug>/` layout without overwriting user files.

    Returns metadata about created directories and files.
    """
    if not slug or not slug.replace("-", "").replace("_", "").isalnum():
        raise ProjectTemplateError(
            f"Invalid book slug: {slug!r}. Use alphanumeric, dash, or underscore."
        )
    if not title or not title.strip():
        raise ProjectTemplateError("Book title cannot be empty.")
    if not genre or not genre.strip():
        raise ProjectTemplateError("Book genre cannot be empty.")

    book_dir = Path(root) / "books" / slug
    created_dirs: list[str] = []
    created_files: list[str] = []
    skipped_files: list[str] = []

    for rel_dir in REQUIRED_DIRECTORIES:
        target = book_dir / rel_dir
        target.mkdir(parents=True, exist_ok=True)
        created_dirs.append(rel_dir)

    templates = render_templates(slug, title.strip(), genre.strip())
    for rel_path, content in templates.items():
        target = book_dir / rel_path
        if target.exists():
            skipped_files.append(rel_path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created_files.append(rel_path)

    return {
        "book_dir": str(book_dir),
        "created_directories": created_dirs,
        "created_files": created_files,
        "skipped_files": skipped_files,
    }
