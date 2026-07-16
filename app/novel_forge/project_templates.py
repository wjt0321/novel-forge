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

Known limitations:
- This script covers only hard surface gates such as em-dashes, ellipses, and negation flips.
- It does not detect whether professional detail serves character action or whether a causal chain is complete.
- It does not judge cross-paragraph near-duplicate meaning; use an independent line editor for that review.
- It does not judge narrative structure; use a scene-level narrative review.
- A passing result does not mean the prose is literary, publishable, or user-approved.

Usage:
    python tools/quality_check.py PATH_TO_CHAPTER.md
"""

import re
import sys
from pathlib import Path
from typing import Any


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
- **工作流版本**: v3（场景包、动作稿、对白账本、双编辑与章节编排）

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
- patch 命名：`patches/ch-{{章节号}}-{{功能}}.md`；只记录局部修订意图、位置、替换范围和验证结果，不替换整章正文。应用后重跑质检、相关编辑和一致性检查。
- 本模板默认包含 v3 编排资产；所有状态、记忆、审稿和上下文材料只留在本书目录内，严禁复制其他书的正文、`memory/`、`reviews/`、`context-cache/` 或已填写 `chXX` 实例。

## 角色团队（Claude 项目内调用）
- `context-collector`: 写前收集最小上下文，输出到 `memory/context-cache/`。
- `consistency-guard`: 写后检查实体、时间线、未回收承诺，输出报告。
- `orchestrator`: 维护章节状态、门禁证据与回退决策，不写正文。
- `causal-editor`: 审场景因果、信息账本与人物行动后果。
- `line-editor`: 审对白归属、重复、节奏与解释性行文。
- `chapter-editor`: 旧版兼容审稿器，最多 5 条问题，分 MUST/MAY。
"""


def _readme_md(slug: str, title: str, genre: str, timestamp: str) -> str:
    return f"""# 《{title}》

- 类型: {genre}
- 创建时间: {timestamp}
- 默认工作流: v3；完整编排说明见 `skills/novel-forge/SKILL.md`。

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
1. `context-collector` 收集最小上下文，并建立章节状态。
2. 填写 `scene-package`、`action-draft`；有关键对白时填写 `dialogue-ledger`。
3. 按 `CLAUDE.md` 宪法起草 `正文.md`，润色不得偷渡关键事件、设定或动机。
4. 运行 `quality_check.py` 和 `narrative_gate.py`。
5. 依次交 `causal-editor`、`line-editor`、`consistency-guard` 审阅；由 `orchestrator` 记录门禁及回退。
6. 修订：结构问题回到场景包/动作稿，纯行文问题才用局部 patch。

所有 v3 资产只在本书目录内使用；不得复制其他书的正文、记忆、审稿报告、上下文缓存或已填写章节实例。完整约定见 `skills/novel-forge/SKILL.md`。
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
5. `memory/future/00-index.md`：未回收承诺与计划兑现窗口

## 检查清单
- [ ] 实体名称与已记录一致
- [ ] 角色认知不超过其已知信息
- [ ] 时间线无矛盾
- [ ] 已埋承诺有回收或明确未回收
- [ ] 本章内容与 `memory/future/00-index.md` 中的承诺及兑现窗口对齐；偏离时明确标记“偏离：X”并说明处理方式
- [ ] 无现代语汇/网络用语出现在非现代背景
- [ ] 无突兀背景卸货句

## 输出
写一份简短报告到 `reviews/` 或直接在对话中返回：
- 问题（最多 3 条）
- 位置（场景/行）
- 建议修订方向
- 承诺状态：兑现 / 保持未回收 / 延后 / **偏离：X**

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


NARRATIVE_GATE_PY = r'''"""Structural narrative gate; it does not score literary quality.

Usage: python tools/narrative_gate.py CHAPTER.md SCENE_PACKAGE.md
"""
from __future__ import annotations
import re
import sys
from pathlib import Path


def _section(text: str, heading: str) -> str | None:
    found = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    return found.group(1) if found else None


def _meaningful(value: str) -> bool:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL).strip()
    return bool(value) and value not in {"待填", "TODO", "TBD", "无"}


def _rows(text: str) -> int:
    rows = 0
    for line in text.splitlines():
        if not line.startswith("|") or re.fullmatch(r"[| :\-]+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if any(_meaningful(cell) for cell in cells) and not all(cell in {"#", "信息", "人物", "触发"} for cell in cells):
            rows += 1
    return max(0, rows - 1)


def _section_has_content(body: str) -> bool:
    if _rows(body) > 0:
        return True
    for line in body.splitlines():
        if line.startswith("|"):
            continue
        value = re.sub(r"^\s*[-*]\s*", "", line).replace("**", "").strip()
        # A Markdown field label ending in ':' is not a filled field.
        if not value or re.fullmatch(r"[^:：]+[:：]", value):
            continue
        if _meaningful(value):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        print("Usage: python tools/narrative_gate.py <chapter.md> <scene-package.md>", file=sys.stderr)
        return 2
    chapter_path, package_path = map(Path, argv)
    if not chapter_path.exists() or not package_path.exists():
        print("Chapter or scene package not found.", file=sys.stderr)
        return 2
    chapter = chapter_path.read_text(encoding="utf-8-sig")
    package = package_path.read_text(encoding="utf-8-sig")
    blocking, advisory = [], []
    for heading in ["1. 场景压力", "2. 在场者状态", "3. Beat 因果链", "4. 信息账本", "5. 信息预算"]:
        body = _section(package, heading)
        if body is None or not _section_has_content(body):
            blocking.append(f"scene-package 缺少或未填写章节：{heading}")
    beats = _section(package, "3. Beat 因果链")
    if beats is None or _rows(beats) < 2:
        blocking.append("Beat 因果链少于 2 个可执行 beat")
    if len([p for p in re.split(r"\n\s*\n", chapter) if p.strip() and not p.lstrip().startswith("#")]) < 3:
        blocking.append("正文段落不足，无法验证场景推进")
    ledger_path = package_path.with_name(package_path.name.replace("scene-package-", "dialogue-ledger-"))
    if ledger_path.exists():
        ledger = ledger_path.read_text(encoding="utf-8-sig")
        if re.search(r"本场景是否有关键对白：\s*是", ledger) and _rows(ledger) < 1:
            blocking.append(f"关键对白账本未填写：{ledger_path.name}")
    print(f"Blocking: {len(blocking)}, Advisory: {len(advisory)}")
    for item in blocking: print(f"BLOCKING: {item}")
    for item in advisory: print(f"ADVISORY: {item}")
    return 1 if blocking else 0

if __name__ == "__main__":
    raise SystemExit(main())
'''


def _planning_scene_package_template_md() -> str:
    return """# Scene Package — 第XX章「标题」

## 0. 边界
- 承接上文：
- 本场景从何处开始、在何处停止：
- 允许新增的长线谜团（默认至多 1 条）：
- 不得在本场景解决的问题：

## 1. 场景压力
- **视角角色此刻想要什么：**
- **若什么都不做会失去什么：**
- **最直接的阻力：**
- **阻力背后的人的诉求：**
- **不可逆选择：**
- **选择立即造成的后果：**
- **章末遗留的具体压力：**

## 1b. 情感弧（可选）
- **开场情感状态：**
- **不可逆选择时刻的情感状态：**
- **章末残余情感状态：**
- **本场不应替角色解释的情绪：**

## 2. 在场者状态
| 人物 | 表面目标 | 不肯说/尚不知道 | 对他人的判断 | 此场结束后的变化 |
|---|---|---|---|---|
|  |  |  |  |  |

## 3. Beat 因果链
| # | 触发 | 人物行动/决定 | 阻力或反应 | 局势变化 | 进入下一 beat 的原因 |
|---|---|---|---|---|---|
| 1 |  |  |  |  |  |

## 4. 信息账本
| 信息 | 来源/证据 | 谁得到它 | 当场造成的决定 | 后续兑现 | 状态 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 5. 信息预算
- 主冲突（1 条）：
- 关系/权力变化（1 条）：
- 新世界规则（0-1 条）：
- 长线伏笔（0-1 条）：
- 延后信息：

## 6. 人物性呼吸段（可选）
- 放置在 beat # 之后：
- 人物功能（回避/拖延/误读/身体失控/关系余温/价值暴露）：
- 具体可见物或动作：
- 它不能新增的情节信息：
"""


def _planning_action_draft_template_md() -> str:
    return """# Action Draft — 第XX章「标题」

> 这是因果底稿，不追求文采。润色不得新增关键事件、设定、人物动机或长线谜团。

- 对应场景包：`planning/scene-package-chXX.md`
- 对应对白账本：`planning/dialogue-ledger-chXX.md` / 无关键对白
- 开场计划：
- 结尾计划如何被迫改变：

## 动作链
### Beat 1
- 触发：
- 行动：
- 阻力/反应：
- 决定：
- 立即后果：

### Beat 2
- 触发：
- 行动：
- 阻力/反应：
- 决定：
- 立即后果：

## 润色边界检查
- [ ] 每个关键事件均能回指到本动作稿。
- [ ] 删除感官描写后，仍能读出目标、阻力、选择与后果。
"""


def _planning_chapter_state_template_md() -> str:
    return """# Chapter State — 第XX章「标题」

- chapter: chXX
- status: planned
- revision: 0
- updated_at: YYYY-MM-DDTHH:MM:SSZ
- next_action:
- blocked_from: （仅 status=blocked 时填写）
- blocked_reason: （仅 status=blocked 时填写）
- required_human_decision: （仅 status=blocked 时填写）
- resume_state: （仅 status=blocked 时填写）
- resume_evidence: （仅 status=blocked 时填写）

## 状态证据
| 状态 | 证据文件/报告 | 命令或审稿结果 | 时间 | 备注 |
|---|---|---|---|---|
| planned |  |  |  |  |

## 当前阻断项
- 无 / 说明问题、来源与应回退状态。

## 本章最小上下文预算
- 当前场景材料：
- 近场连续材料：
- 相关人物/承诺：
- 世界/故事发动机摘要：
- 不加载的历史材料及原因：
"""


def _planning_dialogue_ledger_template_md() -> str:
    return """# Dialogue Ledger — 第XX章「标题」

- 本场景是否有关键对白：是 / 否
- 若否，原因：

| # | 发言者 → 对象 | 触发 | 表面目标 | 隐瞒 | 归属锚点 | 回应/误解 | 局势变化 |
|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |

- [ ] 每个关键话轮都可判断谁对谁说话。
- [ ] 每段关键对白至少改变计划、权力、认知或关系之一。
"""


def _agent_causal_editor_md() -> str:
    return """# Causal Editor

## 角色
叙事因果编辑。只审读，不重写正文。

## 输入
1. `planning/scene-package-chXX.md`
2. `planning/action-draft-chXX.md`
3. `planning/dialogue-ledger-chXX.md`（如有）
4. 当前 `正文.md`、上一章末尾与必要 `memory/` 事实

## MUST
- 场景包缺少目标、阻力、不可逆选择或立即后果。
- 关键 beat 无法说明如何导致下一 beat。
- 正文关键事件、动机、规则或谜团没有动作稿/信息账本来源。
- 重点信息没有来源、知情者或行动后果。
- 关键对白不改变计划、权力、认知或关系。

## 输出
最多 6 条 MUST/MAY：位置、证据、断裂的因果/信息责任、应回退层级（场景包/动作稿/对白账本/正文）、修订意图。

## 边界
不生成新正文；不把文采偏好当作因果问题。
"""


def _agent_line_editor_md() -> str:
    return """# Line Editor

## 角色
行文编辑。在 causal-editor 通过后执行；只审读，不重写正文。

## 审稿维度
1. 对白归属：称呼、动作、位置、物件或明确反应是否足够。
2. 对白行动性：是否只为解释设定、复述信息或整齐排比而存在。
3. 重复簇：相邻段是否近义重复且未改变局势。
4. 解释性旁白：叙述者是否替读者总结情绪、主题或认知。
5. 节奏：呼吸段是否具备人物功能，短段是否过度均匀。

## 输出
最多 6 条 MUST/MAY：位置、原文证据、读者效果、修订意图。MUST 仅用于归属不明、重复造成信息停滞或解释取代关键行动。

## 边界
不擅自统一文风，不以禁词命中替代上下文判断，不生成新正文。
"""


def _agent_orchestrator_md() -> str:
    return """# Orchestrator

## 角色
章节流程编排者。维护进度、门禁证据、暂停和回退；不写正文、不审稿、不自行改写记忆事实。

## 状态机
状态记录在 `planning/chapter-state/chXX.md`：
`planned → context_collected → scene_packaged → action_drafted → dialogue_planned → drafted → surface_checked → causal_reviewed → line_reviewed → consistency_checked → ready`

- `blocked` 只用于需要人工选择、事实冲突、正文覆盖风险或外部发布。必须记录 `blocked_from`、原因、所需决定、恢复状态和恢复证据；恢复后回到原状态或更早状态，并重跑后续门禁。
- `ready` 只表示流程材料已齐备，不等于用户批准。

## 门禁与回退
- 表面质检失败 → `drafted`，修正文。
- 叙事门禁或 causal-editor MUST → `scene_packaged` 或 `action_drafted`。
- line-editor MUST → `drafted`。
- consistency-guard MUST → 由问题定位；不得静默篡改既成事实。

## 规则
- 一次只编排一个章节或场景，不批量写后续章节。
- writer 仅加载当前场景、近场连续、相关人物/承诺和必要规则；长篇全量材料留给跨章审计。
- 每次只推进一个状态，并写入证据、结果和下一步。
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
    "planning/scene-package-template.md": (_planning_scene_package_template_md, ()),
    "planning/action-draft-template.md": (_planning_action_draft_template_md, ()),
    "planning/dialogue-ledger-template.md": (_planning_dialogue_ledger_template_md, ()),
    "planning/chapter-state-template.md": (_planning_chapter_state_template_md, ()),
    "tools/quality_check.py": (lambda: QUALITY_CHECK_PY, ()),
    "tools/narrative_gate.py": (lambda: NARRATIVE_GATE_PY, ()),
    ".claude/agents/context-collector.md": (_agent_context_collector_md, ()),
    ".claude/agents/consistency-guard.md": (_agent_consistency_guard_md, ()),
    ".claude/agents/chapter-editor.md": (_agent_chapter_editor_md, ()),
    ".claude/agents/causal-editor.md": (_agent_causal_editor_md, ()),
    ".claude/agents/line-editor.md": (_agent_line_editor_md, ()),
    ".claude/agents/orchestrator.md": (_agent_orchestrator_md, ()),
}

# Directories that should exist; files under them are created via TEMPLATE_FILES.
REQUIRED_DIRECTORIES = [
    "chapters",
    "memory/entities",
    "memory/future",
    "memory/context-cache",
    "planning/events",
    "planning/chapter-state",
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
