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
| `question-mark-mismatch` | advisory | 疑问语气词（吗/呢/吧/句末么）后用句号；排除“什么/怎么/这么/那么/多么/要么”等词内的“么” |
| `quote-consistency` | advisory | 对话引号不成对 |
| `quote-duplication` | advisory | 连续双引号（\"\"…\"\"），多为 patch/转义错误 |
| `common-error` | advisory | 常见错字、搭配或病句 |

lint 不自动修改正文；执行后章节状态进入 `linted`，blocking 会阻止 `approve-chapter`。advisory 规则不阻断 approval，但会计入 `proofread_status` / `prose_edit_status`，从而影响 `check-acceptance` 的分层结果。每个新 revision 必须重新 lint。

## 四维审稿

`add-finding` 和 `review-chapter` 使用四个视角：

- `structure`：结构、节奏、钩子
- `character`：角色动机、对话区分度
- `narrative`：AI 味、视角、信息载体
- `continuity`：事实、时间线、设定一致性

严重度：S1 > S2 > S3 > S4。

## 审批规则

`review-chapter` 只允许从 `linted`、`revised`、`reviewed` 状态执行，结果进入 `reviewed`。

`approve-chapter` 只允许从 `reviewed` 状态执行，且必须满足：

1. 存在当前 revision
2. 当前 revision 无未关闭 blocking lint finding
3. 当前 revision 无未关闭 S1/S2 review finding

`review-chapter` 的 verdict：

- S1 → REJECT
- S2 或 blocking lint → CONCERNS
- 否则 → APPROVE

## Finding 与 revision 的作用域

lint finding 和 review finding 都关联到具体 revision。`approve-chapter` 只检查**当前 revision** 的未关闭 finding；旧 revision 的未关闭 finding 会保留为审计记录，但不会自动成为新 revision 的阻塞项。这意味着：写一个新 revision 并重新 lint + review 后，即使旧 revision 曾有未解决的 S1，也可以获得审批。

## Canon 冲突

Canon Fact 的冲突判断限定在**同一本书**内：同一 `subject + predicate` 的 Canon Fact 在同一本书中已存在时，新的 `approve-fact` 会被拒绝，避免静默覆盖。不同书籍之间的相同 subject + predicate 互不干扰。

## 分层自动验收

`check-acceptance` 把结果拆为可审计维度：

- `workflow_coverage`：plan、revision、字数、研究、承诺、独立编辑轮次等流程门。
- `proofread_status`：基础校对 lint（`question-mark-mismatch`、`quote-consistency`、`common-error`）。
- `prose_edit_status`：语言编辑 lint（`rhythm-monotony`、`mechanical-triplet`、`explanatory-punchline`）。
- `independent_editorial_status`：当前 revision 是否存在 `ready_for_editor_decision` 且无 blocking issues 的独立编辑 memo。
- `publication_eligibility`：始终为 `False`，系统不自动公开发布。

`autonomous_acceptance_complete` 要求 workflow + editorial ready + proofread/prose 全 clean。它只证明“已完成可验证流程”，不是文学、市场或可读性认证。

## Candidate Fact 来源

`add-candidate-fact` 必须关联当前 revision（事实证据必须能定位到 source revision），因此章节必须先写入 revision 才能添加 candidate fact。
