# 06 - Voice Bible 与 Scene Contract

Voice Bible 和 Scene Contract 是 Novel Forge 的"人可读创作资产"。它们以 Markdown 形式存在，带版本历史，不自动覆盖旧版本。

## Voice Bible（书籍级）

路径：`library/<slug>/planning/voice-bible/revisions/`

书籍初始化时会自动生成 revision 1 模板。后续通过 `write-voice-bible` 从外部 Markdown 写入新 revision，旧版本保留。

### 字段说明

| 字段 | 含义 | 填写原则 |
|------|------|----------|
| narrative_distance | 叙述距离 | 例如：close-third limited，或全知但受限 |
| tense_or_time_handling | 时态/时间处理 | 过去时/现在时，回忆、闪回的处理规则 |
| focalization | 视角焦点与禁止越界 | 谁的眼睛看世界，哪些信息不能由叙述者直接说出 |
| sentence_rhythm | 句长、段落节奏 | 紧张场景短句，舒缓场景可长，避免均匀 |
| dialogue_rules | 人物对白差异与禁忌 | 每人说话方式不同，禁止解释性对白 |
| sensory_palette | 感官/意象偏好 | 本书偏好的感官通道，不是词库硬塞 |
| taboo_patterns | 禁用套路、解释腔、陈词滥调 | 明确列出本书不写的句子类型 |
| emotional_restraint | 情绪克制规则 | 何时不直接写情绪，让动作承担 |
| exemplar_notes | 正反例说明 | 人工填写的具体例子 |

### 反空话示例

- ❌ "叙述距离要自然"
- ✅ "close-third limited：只能进入主角的感知，不能写反派的内心"

- ❌ "对白要有特点"
- ✅ "A 说话简短，不带主语；B 习惯用问句回避直接回答"

## Scene Contract v3（章节级）

路径：`library/<slug>/planning/chapters/ch<NNNN>-contract/revisions/`

创建章节时自动生成 revision 1 模板（当前为 v3）。后续通过 `write-scene-contract` 写入新 revision。旧 v2 合同不会被强制迁移，仍可读取，但会触发 `scene_contract_legacy_v2` 警告。

### v2 字段

| 字段 | 含义 | 填写原则 |
|------|------|----------|
| scene_question | 本场读者想知道什么 | 一个具体的问题，不是"推进剧情" |
| viewpoint_character | 视角人物 | 本场的眼睛和内心是谁 |
| present_want | 当下欲求 | 人物在这场里最想得到的具体东西 |
| opposing_force | 对抗力 | 阻止他得到的东西，可以是环境、他人或自身 |
| irreversible_turn | 不可逆转的转折 | 本场结束后，什么再也回不到从前 |
| cost_or_tradeoff | 代价或取舍 | 人物得到或失去什么 |
| information_change | 信息变化 | 读者或人物知道了什么新信息 |
| emotional_shift | 情绪位移 | 从什么情绪到什么情绪，用动作体现 |
| concrete_anchor | 具体锚点 | 至少 2 个可感知的物件/动作/环境细节 |
| entry_late_exit_early_note | 晚进早出 | 本场从哪一刻开始、在哪一刻离开 |
| continuity_dependencies | 连续性依赖 | 关联 Canon、上章、伏笔 |
| forbidden_easy_moves | 禁止的取巧解法 | 本场不允许用的廉价脱身方式 |
| ending_pressure | 结尾压力 | 留给下一场的张力或问题 |

### v3 新增字段

| 字段 | 含义 | 填写原则 |
|------|------|----------|
| character_blindspot_or_pressure | 人物盲点/压力 | 此刻不愿承认或无法回避的个人压力；不能写"无" |
| irreversible_choice | 不可逆转的选择 | 由视角人物主动作出，改变后续走向；不是外部事件 |
| choice_consequence | 选择后果 | 立刻失去、暴露、承诺或伤害什么 |
| detail_payoff_plan | 细节回收计划 | 最多 3 条"强调细节 → 如何回收"；无则写 `无刻意强调细节` |
| scene_necessity | 场景必要性 | 删掉本场会损失什么具体变化；不能写"推动剧情" |
| ending_change | 结尾变化 | 相对开头改变了什么：知识、关系、行动资格、风险 |

### 反空话示例

- ❌ "本场很重要"
- ✅ "scene_question：主角能否在不被发现的情况下把信交给对方？"

- ❌ "情绪很复杂"
- ✅ "emotional_shift：从侥幸（动作：把信塞进口袋）到恐惧（动作：手指停在门把上）"

- ❌ "增加细节"
- ✅ "concrete_anchor：生锈的信箱、对方袖口磨损的纽扣"

## 版本化规则

- 每次写入都生成新文件，不覆盖旧版本。
- `voice_bibles` / `scene_contracts` 表保存 current pointer。
- adapter 只返回 metadata（path、hash、revision number），不返回全文。
- 输入 Markdown 必须是 UTF-8（可带 BOM），且不能位于 `library/` 目录内。
