# 文学防过拟合与序列真实性（v4.1）

## 起点

v4.1 继续追问项目最初的问题：**这篇小说像是人类写的吗？**

四组不同模型与 Agent 的正文样本表明，单纯增加思考强度、审稿轮数或风格统计，
不会稳定提高文学完成度。常见失败反而包括：

1. 高推理长期停留在自由生成阶段，形成解释、回看和反复修补；
2. Voice Bible 的范文与数值指纹被 writer 当成表层配方；
3. 同一章内的句首、短分句、物件和动作不断承担相同功能；
4. 上一章已经作出的决定在下一章被无触发地推翻；
5. 编排记录宣称 complete，但章节、session 或 generation 证据不能互相证明。

因此，本版本不针对任何模型或 Agent 产品，而是重新划分 writer、editor 与
orchestrator 各自可以看到和证明的内容。

## 分层推理

推理强度按任务分配：

| 阶段 | 默认强度 | 用途 |
|---|---|---|
| 规划、困难因果核验 | high | 反证、责任归属、不可逆行动与专业风险 |
| 正文起草 | standard/medium | 保留语言直觉，减少解释性自我修正 |
| blind-reader、chapter-editor | standard/medium | 只依据证据作收敛判断 |
| Max/长思考 | 具名例外 | 只解决一个明确难题，结论压缩回 scene package |

Max 不是文学质量档位，也不是应当吃满的预算。整章自由生成不得长期处于 Max。

## Writer 与 Editor 分离

Writer handoff 只传递：

- 叙事距离；
- 信息释放方式；
- 节奏功能；
- 与本章相关的 Canon、开放承诺、上一章末段和 scene package。

它会过滤句长、段落长度、对白占比、比喻密度等数值风格指标。Voice exemplar
可以提供一个短段，但 writer 不得复用其中的具体名词、标志动作、章末物件或
句法骨架。声音指纹由 editor 从文件计算，只用于定位需要回读的原文。

## 新增文学诊断

`voice_signature.analyze_serial_style()` 新增两个 advisory：

- `pattern-saturation`：单章内完整句、句首或短分句达到高频复用阈值；
- `voice-anchor-surface-copy`：后续章节反复挪用 Voice exemplar 的连续表层措辞。

它们不会自动改正文，也不会直接阻断 ready。chapter-editor 必须结合原文判断它是
人物的有意复沓，还是模型形成的低层语言惯性。

`lint.py` 另增加 `ascii-punctuation` advisory，用于定位中文叙事行中混入的 ASCII
逗号与直引号。它只报告位置，不做机械替换。

## 决定反转必须有桥

第 2 章起，`0b. 章际交接` 新增：

- 上一章末明确决定；
- 本章是否推翻该决定；
- 若推翻，触发事件原文。

如果本章推翻上一章决定，触发事件必须逐字存在于当前正文前 40%。这不是禁止人物
改变主意，而是要求改变发生在读者眼前，而不是由规划文件替正文补充解释。

## 序列真实性

`chapter-sequence-status` 不再只回显 JSON 中的 `status=complete`。它会重新验证：

- `completed_chapters` 与目标章节完全一致；
- `current_index` 已越过末章且没有活动 session；
- writer session 数与章节数一致；
- 每章此刻仍能通过完整 ready 复核；
- generation `run_id` 与序列中的 session 顺序一致。

任一证据不成立时，原始状态仍保留用于审计，但返回
`effective_status=inconsistent` 与具体 finding。编排器不能把自报完成当成事实。

## 样本与边界

本次四模型样本只保留统计、哈希、流程状态和文学判断，见：

- `docs/examples/agent-demo-v41-four-model-prose-comparison.md`
- `docs/examples/agent-demo-v41-four-model-prose-comparison.json`

原始 `books/` demo 已清理。样本结论用于设计通用 Harness 规则，不构成模型排名，
也不认证文学价值、作者批准或发布资格。
