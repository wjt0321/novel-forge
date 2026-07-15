# 05 - 面向人类读者的小说质量层

## 这不是 AI 检测器

Novel Forge 第二里程碑不输出"AI 味分数"，也不把词频、困惑度或任何不可解释的数字当作通过标准。质量层的目标是：**让作品更像一个真人写给真人看的故事**。

判断依据永远是具体、可定位、可执行的：

- 读者在哪些地方会出戏、困惑或失去兴趣？
- 证据是什么（哪一行、哪一段、哪个动作）？
- 修订方向是什么（不改剧情，只改怎么说）？

## 证据 → 读者反应 → 修订意图

Reader Review Ledger 强制每条审稿意见使用三段式：

1. **evidence（证据）**：必须引用正文中的具体位置与文本。例如："第 12 行：'他终于明白了真相。'"
2. **reader_effect（读者反应）**：说明读者实际会如何。例如："读者被作者直接告知结论，失去了自己拼图的参与感。"
3. **revision_intent（修订意图）**：给出可执行方向。例如："用动作或对话暗示他发现真相，不要写'明白'二字。"

禁止空泛意见，例如：

- ❌ "这里不够生动"
- ❌ "去一下 AI 味"
- ❌ "节奏再紧凑点"

## 与状态机关联

Reader Review 的未关闭 S1/S2 会直接影响 `review-chapter` 和 `approve-chapter`：

- S1 = REJECT
- S2 = CONCERNS
- 未关闭 S1/S2 不能批准章节

每个新 revision 都需要重新 lint + review。旧 revision 的 reader review 保留审计，但不会自动阻塞新 revision。

## 不自动改写

Reader Review、Voice Bible、Scene Contract 都是写作和审稿的硬上下文，不是自动修改工具。系统不会：

- 自动修改正文
- 自动批准章节
- 把模型输出直接存为 revision

所有修改必须由人通过 `write-revision` 显式提交，并留下新的 revision、hash 与审计记录。

## Lens 说明

| lens | 关注点 |
|------|--------|
| immersion | 读者是否还在场景里，是否被解释拉出画面 |
| causality | 动机、因果是否清晰可信 |
| character_truth | 人物行为是否符合其内在逻辑 |
| tension | 张力是否持续，结尾是否留下压力 |
| language | 句式、节奏、对白、禁用套路 |
| continuity | 与 canon、伏笔、前文的连续性 |

## 创作者 workflow

1. 写作前：填写 Scene Contract v2，明确本场问题、视角、不可逆转折、结尾压力。
2. 就绪检查：用 `assess_drafting_readiness` / `drafting-readiness` 确认硬表单已填写，避免空模板直接喂给模型。
3. 进入写作：用 `build-drafting-packet` 把 Voice Bible、Scene Contract、Canon、上一章承接片段汇总成外部 Markdown 上下文包。
4. 写作中：对照 Voice Bible 的叙述距离、感官偏好、禁忌句式。
5. 审稿时：用 Reader Review 记录证据、读者反应、修订意图。
6. 修改后：写新 revision，重新 lint + review，直到无 S1/S2 与 blocking lint。
7. 宏观编辑审稿：为当前 revision 提交 Editorial Memo，记录叙事必要性、人物能动性、细节选择、因果链、具体 prose 观察与 verdict。
8. 批准：只有在 Reader Review、lint、Editorial Memo 三门都通过时，`approve-chapter` 才会成功。

## 与叙事编辑门的关系

Reader Review 处理微观层面的读者出戏点；Editorial Memo 处理宏观层面的叙事结构。两者都使用"证据 → 效果 → 修订意图"模板，都不自动修改正文，都按 revision 作用域生效。详见 `docs/10-narrative-editorial-gate.md`。

见 `docs/08-drafting-packets.md` 与 `docs/09-drafting-readiness.md`。
