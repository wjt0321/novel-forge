# 09 - Drafting Readiness Gate（写作就绪度门）

## 目的

Drafting Readiness Gate 阻止在创作准备明显不足时生成 Drafting Packet。它只检查硬表单是否已填写，不评价文学质量。目标是减少“空模板喂给模型导致胡写”的情况，提高写出能读小说的概率。

## 核心原则

- **只阻止明显没准备的情况**，不是质量标准。
- **不调用 LLM**，只做轻量 Markdown heading 解析和占位符检测。
- **只读**，不改 chapter 状态，不写 audit。
- **不保证好作品**：gate 通过只说明“表单填了”，不代表写出来一定好。

## 检查项

### Voice Bible 必填段

- `narrative_distance`
- `focalization`
- `sentence_rhythm`
- `dialogue_rules`
- `taboo_patterns`
- `emotional_restraint`

若 Voice Bible 不存在，报 blocker `voice_bible_missing`。

### Scene Contract v2/v3/v4 必填段

v2/v3/v4 通用必填：

- `scene_question`
- `viewpoint_character`
- `present_want`
- `opposing_force`
- `irreversible_turn`
- `cost_or_tradeoff`
- `information_change`
- `emotional_shift`
- `concrete_anchor`（至少 2 条非占位锚点）
- `forbidden_easy_moves`
- `ending_pressure`

v3 额外必填（仅当合同为 v3/v4 时）：

- `character_blindspot_or_pressure`
- `irreversible_choice`
- `choice_consequence`
- `detail_payoff_plan`
- `scene_necessity`
- `ending_change`

v4 额外必填（仅当合同为 v4 时）：

- `spatial_layout_and_routes`：不能为空，不能只列尺寸/数字而无相对位置或行动关系
- `body_state_and_contacts`：不能为空
- `object_affordances`：至少 2 条有效列表项
- `environmental_constraints`：不能为空，且至少包含一条因果链
- `embodied_action_chain`：至少 3 条有效列表项，覆盖 `irreversible_choice` 或其前置动作

若 Scene Contract 缺失或文件不可读，报 blocker。v2/v3 合同会产生 `scene_contract_upgrade_to_v4` warning，建议升级但不阻塞已有作品；v2 还会额外产生 `scene_contract_legacy_v2` warning。

## 占位符判定

以下内容会被视为未填写：

- 空或纯空白
- 模板提示，例如“本场读者想知道什么？”
- `TBD`、`待定`、`待填写`、`N/A`
- `concrete_anchor` 中仅保留“锚点 1：/ 锚点 2：”等占位列表项

## 使用方式

### Service

```python
readiness = svc.assess_drafting_readiness("my-novel", 3)
print(readiness.ready)
print(readiness.blockers)
```

### Adapter

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
    --root D:\my-novel \
    drafting-readiness my-novel 3
```

返回 JSON 包含 `ready`、`blockers`、metadata，不含资产全文。

### 构建 Packet 时

默认情况下，`build-drafting-packet` 会先调用 readiness gate。有 blocker 时拒绝创建文件：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
    --root D:\my-novel \
    --confirm build-drafting-packet \
    build-drafting-packet my-novel 3 \
    --output-file D:\drafts\ch03-packet.md
```

## `--allow-incomplete` 与探索性草稿

仅在用户/Skill 明确授权本次探索性草稿时，才允许绕过：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
    --root D:\my-novel \
    --confirm build-drafting-packet \
    build-drafting-packet my-novel 3 \
    --output-file D:\drafts\ch03-packet.md \
    --allow-incomplete
```

绕过生成的 packet 顶部会醒目标注 `READINESS BYPASSED` 和 blocker 列表，不得看起来像已就绪。

**重要**：`--allow-incomplete` 不是自动 fallback。Skill 必须先向用户提示清楚缺失项，并获得对本次探索草稿的明确确认，才能使用。

## Status 集成

`status <slug> <number>` 的 chapter 视图包含 `drafting_readiness` summary：

```json
{
  "drafting_readiness": {
    "ready": false,
    "blocker_codes": ["voice_bible_empty_narrative_distance", "scene_contract_empty_scene_question"]
  }
}
```

## 与 Drafting Packet 的关系

见 `docs/08-drafting-packets.md`。Readiness Gate 是 Packet 的前置检查，两者共同构成“有准备才写”的闭环。
