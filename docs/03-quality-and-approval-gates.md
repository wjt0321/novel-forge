# 03 - 质量与审批门控

## Prose Lint

`lint-chapter` 对当前 revision 执行只读检查，规则包括：

| 规则码 | 级别 | 说明 |
|--------|------|------|
| `em-dash` | blocking | 禁止使用 `——` |
| `ellipsis` | blocking | 禁止使用 `……` |
| `not-is-flip` | blocking | 禁止“不是 X，而是 Y / 不是 X，是 Y”式否定翻转 |
| `explanation-tic` | advisory | 疑似作者解释 / 总结腔 |
| `word-count-tic` | advisory | 具体字数表述，如“这五个字” |
| `colon-density` | advisory | 冒号总数与每千字密度 |
| `rhythm-monotony` | advisory | 连续多个段落均为短段（≤2 句），节奏可能过于均匀 |
| `mechanical-triplet` | advisory | 连续三句以上同构短句，或段落开头的清单化名词独句；排除普通动词短句 |
| `explanatory-punchline` | advisory | 孤立于连续叙事的结论性短句（单句段，或两句段末尾的短结论）；不标长段落内的普通短句 |
| `question-mark-mismatch` | advisory | 疑问语气词后误用句号 |
| `quote-consistency` | advisory | 对话引号不成对 |
| `quote-duplication` | advisory | 连续双引号，多为 patch/转义错误 |
| `common-error` | advisory | 常见错字、搭配或病句 |

lint 不自动修改正文；每个新 revision 必须重新 lint。

## 四维审稿

`add-finding` 和 `review-chapter` 使用四个视角：

- `structure`：结构、节奏、钩子
- `character`：角色动机、对话区分度
- `narrative`：视角、信息载体、机械叙述
- `continuity`：事实、时间线、设定一致性

严重度：S1 > S2 > S3 > S4。

## Blind Experience Gate

当前 revision 必须通过 prose-only Blind Experience Review。盲读者不能看到 Scene Contract、Voice Bible、大纲、Canon、Promise、Drafting Packet 或作者意图，只能根据带行号的正文重建：

- 空间与物体相对位置；
- 人物身体姿态、接触和受力；
- 环境造成的行动限制；
- 通过行动可推断的情绪轨迹；
- 对话前后的关系或局势变化；
- 至少三个有正文原句证据的可记忆画面；
- 任何必须借助外部设定才能理解的知识缺口。

缺少报告、报告要求修订、存在知识缺口、存在 blocking issue，或可记忆画面的证据不在当前 revision 中，均阻止批准。详见 `docs/14-blind-experience-gate.md`。

## Editorial Memo Gate

当前 revision 还必须具有独立编辑 Memo：verdict 为 `ready_for_editor_decision`，且没有 blocking issue。Memo 负责叙事必要性、人物主动性、细节选择和因果链；Blind Experience Review 负责验证正文实际交付给读者的画面与体验。两者不能互相替代。

## 审批规则

`review-chapter` 只允许从 `linted`、`revised`、`reviewed` 状态执行，结果进入 `reviewed`。

`approve-chapter` 只允许从 `reviewed` 状态执行，且必须满足：

1. 存在当前 revision；
2. 当前 revision 无 blocking lint；
3. 当前 revision 无未关闭 S1/S2 review finding；
4. 当前 revision 无未关闭 S1/S2 Reader Review；
5. 当前 revision 具有通过的 Blind Experience Review；
6. 当前 revision 具有 ready 且无阻断项的 Editorial Memo。

`review-chapter` 的 verdict：

- S1 → REJECT；
- S2、blocking lint、Blind Experience Gate 未通过或 Editorial Memo Gate 未通过 → CONCERNS；
- 否则 → APPROVE。

## Revision 作用域

所有 lint、review、Reader Review、Blind Experience Review 和 Editorial Memo 都绑定具体 revision。新 revision 不继承旧 revision 的通过状态，必须重新检查。

## Canon 冲突

Canon Fact 的冲突判断限定在同一本书内。同一 `subject + predicate` 已存在时，新的 `approve-fact` 被拒绝，避免静默覆盖。

## 分层自动验收

`check-acceptance` 的自动结果只证明可验证流程完成，不是文学、市场或可读性认证。公开发布始终需要外部明确决定。

## Candidate Fact 来源

`add-candidate-fact` 必须关联当前 revision，因此章节必须先写入 revision 才能添加 candidate fact。
