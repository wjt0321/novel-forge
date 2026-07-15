# 13 - Claude 项目内工作流（第一阶段）

## 目标

把 Novel Forge 从“数据库门禁优先”调整为“每本小说独立项目、Claude 在项目内自主编排、正文优先”的架构。新目录 `books/<slug>/` 是面向写作者和 Claude 的推荐前台； legacy `library/` 与 SQLite 账本保持兼容，不强迁移。

## 核心变化

- 新增 `init-novel-project <slug> --title ... --genre ...` 创建 `books/<slug>/` 结构。
- 正文明确定义在 `books/<slug>/chapters/eXX/ch-XX/正文.md`。
- 三份 Claude Agent 角色说明自动生成在 `books/<slug>/.claude/agents/`：
  - `context-collector.md`：写前收集最小上下文。
  - `consistency-guard.md`：写后检查一致性。
  - `chapter-editor.md`：独立审稿，最多 5 条问题。
- 轻量 `tools/quality_check.py` 做基础表面检查，不替代文学判断。
- 默认低 token：不强制 Research Ledger / Promise Ledger / 多轮自动验收；它们在复杂长篇或强历史事实题材时才可选。

## 新目录结构

```text
books/<slug>/
  CLAUDE.md                  # 小说宪法、进度、输入优先级、严格边界
  README.md                  # 人类入口
  chapters/                  # 正文唯一入口
  memory/
    entities/                # 角色/组织实体卡
    future/                  # 未来规划
    past.md                  # 已发生事实
    worldbuilding.md         # 世界设定
  planning/
    events/                  # 事件卡
    story-engine.md          # 核心张力
    research-boundaries.md   # 事实/虚构边界
  reviews/archive/           # 审稿记录
  patches/                   # 局部修订 patch
  .snapshots/                # 临时快照
  tools/
    quality_check.py         # 轻量质量脚本
  .claude/agents/
    context-collector.md
    consistency-guard.md
    chapter-editor.md
```

## 默认工作流与预算

推荐单章流程：

```
1 次 context-collector 最小上下文收集
    ↓
1 次完整初稿（Claude 按 CLAUDE.md + story-engine + memory 写正文）
    ↓
1 次 quality_check.py + consistency-guard 自检
    ↓
1 次 chapter-editor 独立审稿（最多 5 条，分 MUST/MAY）
    ↓
最多 1 次局部修订（patch 或重写受影响场景）
    ↓
最终检查
```

预算原则：
- 审稿与修订 token 不应超过初稿 token。
- 禁止演变成多轮全文重写；结构失败才重写场景，其余用 patch。
- 不默认调用外部 Kimi / 不默认联网研究。

## Adapter 命令

```bash
# 创建新项目（精确 confirm）
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
  --root D:\s-black-novel \
  --confirm init-novel-project \
  init-novel-project my-book --title "我的小说" --genre "现实悬疑"
```

该操作只创建文件系统项目；不写入 SQLite，不创建 `library/` 目录，不与 legacy workflow 冲突。

## 与 legacy workflow 的关系

| 能力 | books/ 项目 | library/ + SQLite |
|------|-------------|-------------------|
| 正文入口 | `chapters/eXX/ch-XX/正文.md` | `library/<slug>/manuscript/revisions/...` |
| 需要数据库 | 否 | 是 |
| 审计/状态机 | 否（由 Git + 文件历史承担） | 是 |
| 多章长篇小说 | 支持 | 支持且更完整 |
| 自动验收门 | 不默认启用 | `check-acceptance` 可选 |
| 推荐场景 | 短篇、Claude 项目内快速迭代 | 长篇、强审计、多人协作 |

## 质量脚本

`tools/quality_check.py` 检查：
- 禁用符号 `——`、`……`
- 否定翻转句式 `不是X而是Y / 不是X是Y`
- 重复引号 `""...""`
- 疑问语气词后用句号
- 显式字数口癖

它是 advisory/blocking 表面检查，不判断文学性。

## 已知限制

- `init-novel-project` 不覆盖已存在的用户文件。
- 新项目不强制与 `library/` 同步；若需 legacy 审计，可同时使用 `init-book`。
- Agent 角色说明是 Markdown 指南；Claude 是否调用它们取决于项目配置。
- 本阶段不做 GUI、不做自动 LLM 调用、不做联网抓取。
