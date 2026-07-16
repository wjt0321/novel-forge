# 小说宪法：《星墟剑主》

## 基本信息
- slug: `star-ruin-sword`
- 标题: 《星墟剑主》
- 类型: 星际修仙
- 创建时间: 2026-07-16T01:20:18.978911+00:00
- **工作流版本**: v3（v2 slim contract + positive voice bible；增加场景包、动作稿、对白账本、双编辑与章节编排）

## 正文明确定义
本书唯一正文入口：

```
books/star-ruin-sword/chapters/e01/ch-01/正文.md
```

- 每章一个目录，命名规则 `e{序号}/ch-{序号}`。
- 目录内只放 `正文.md`，不放多个草稿版本。
- 历史版本由外部 Git 管理。

## 当前进度
- 最新场景/章节: 第一章「渊流崩解」
- 下一场目标: 陆渊被押送至泰衡星际安全站，面临"导航劫持"指控
- 未回收承诺（最多列 3 条）:
  1. 渊流航道崩塌的共振特征与五年前青霄覆灭一致 → 目标第8-10章
  2. 陆渊的空明九斩灵力特征被泰衡安全系统记录 → 目标第15-18章
  3. 三箱星髓矿在崩解中消失（非碎裂）→ 目标第5-7章

## 写作输入优先级
当接到"写下一章/场景"时，按以下顺序读取：
1. `planning/story-engine.md` — 核心张力
2. `memory/past.md` — 已发生事实
3. `memory/worldbuilding.md` — 世界规则
4. `memory/voice-bible.md` — Voice Bible v2（正面引导版）
5. `planning/scene-package-chXX.md` — 可执行场景包（保留 Scene Contract 摘要，并新增目标、阻力、beat 因果链、信息账本）
6. `planning/action-draft-chXX.md` — 动作版草稿（无关键新增的因果底稿）
7. `planning/dialogue-ledger-chXX.md` — 关键对白账本（如有对白）
8. `planning/chXX-drafting-packet.md` — 草稿包（既有章节兼容材料）
9. 上一章正文最后 20%
10. `planning/research-boundaries.md` — 事实红线

## 严格边界

### 质量铁律（MUST — 仅保留5条核心）

1. **反跨段近义重复**: 相邻段落禁止以不同措辞重复同一信息。这是AI最常犯的错误——同一种感知被换了3-4种说法分散在不同段落。

2. **反无归属排比式对白**: 三句以上无说话人标识的短对话连续出现 → MUST错误。读者必须始终知道谁在说话。

3. **禁止台词卡**: 连续四句以上仅有引号包裹、无任何动作/心理/场景穿插的纯对白 → MUST错误。

4. **人物性呼吸段**: 不以字数配额制造无关停顿。若使用呼吸段，必须在场景包中标注其人物功能（回避、拖延、误读、身体失控、关系余温或价值暴露），且不得偷渡新的关键情节。

5. **禁止 `——`、`……`**

> 其余风格约束（情绪呈现方式、角色声音区分、感官调色板、写前独白仪式等）见 `memory/voice-bible.md` v2。该文件已从"禁令集"重构为"正面引导+范文驱动"，写作前必读。

### 创作流程约定

- 动笔前：以主角第一人称写300-500字独白（不进入正文），见 voice-bible 的「写前仪式」。
- 起草前必须完成 `planning/scene-package-chXX.md` 和 `planning/action-draft-chXX.md`；关键对白另填 `planning/dialogue-ledger-chXX.md`。
- 正文润色不得新增动作稿外的关键事件、设定、人物动机或长线谜团。
- 每章至少1个 offbeat_moment（读者猜不到的角色反应）；呼吸段按人物功能使用，不设数量配额。
- 写完后：运行 `python tools/quality_check.py chapters/eXX/ch-XX/正文.md` 与 `python tools/narrative_gate.py chapters/eXX/ch-XX/正文.md planning/scene-package-chXX.md`，再依次交 `causal-editor`、`line-editor` 审阅。
- 修订：因果或信息门禁失败时回到场景包/动作稿；仅行文问题才做局部 patch。
- patch 命名：`patches/ch-{章节号}-{功能}.md`，如 `patches/ch-01-dialogue-anchor.md`；patch 只记录局部修订意图、位置、替换范围和验证结果，不替换整章正文。
- 应用 patch 后，必须重新运行 `quality_check.py`、`narrative_gate.py` 及受影响的 `causal-editor` / `line-editor` 审稿；涉及既成事实时另跑 `consistency-guard`。

## 角色团队（Claude 项目内调用）
- `context-collector`: 写前收集最小上下文，输出到 `memory/context-cache/`。
- `consistency-guard`: 写后检查实体、时间线、未回收承诺，输出报告。
- `causal-editor`: 审场景因果、信息账本与人物行动后果。
- `line-editor`: 审对白归属、重复、节奏与解释性行文。
- `chapter-editor`: 旧版兼容审稿器；新章节优先使用两个分工编辑。
