# 12 - 质量链重构（P0–P4）

本里程碑把 Novel Forge 从“流程完成”与“文本可读/校对完成”混为一谈的状态中拆出来，明确系统只能记录可验证的编辑与校对过程，不能认证文学价值或市场表现。

## P0 分层验收状态

`check-acceptance` 输出拆为五个维度：

- `workflow_coverage`：是否具备 plan、revision、>=5000 中文汉字、研究闭环、承诺闭环、独立编辑轮次。
- `proofread_status`：基础校对层（`question-mark-mismatch`、`quote-consistency`、`common-error`）是否 clean。
- `prose_edit_status`：语言编辑层（`rhythm-monotony`、`mechanical-triplet`、`explanatory-punchline`）是否 clean。
- `independent_editorial_status`：当前 revision 是否存在有效独立编辑 memo（`ready_for_editor_decision` 且无 blocking issues）。
- `publication_eligibility`：始终为 `False`；系统不自动公开发布。

`autonomous_acceptance_complete` 要求 workflow + editorial ready + proofread/prose 全 clean。它只表示“已完成可验证流程”，不是文学/市场/可读性保证。

## P1 只读语言/校对审计

`lint-chapter` 扩展以下 advisory 规则：

| 规则码 | 说明 |
|--------|------|
| `rhythm-monotony` | 连续多个段落均为 ≤2 句短段，节奏可能过于均匀 |
| `mechanical-triplet` | 连续三句以上同构短句或清单化名词独句 |
| `explanatory-punchline` | 结论性独词句或解释性收尾 |
| `question-mark-mismatch` | 疑问语气词后用句号 |
| `quote-consistency` | 对话引号不成对 |
| `common-error` | 常见错字/搭配/病句（可维护规则列表） |

这些规则只标位置、不自动改正文，也不阻断 approval；但它们会进入 `proofread_status` / `prose_edit_status`，从而影响 `autonomous_acceptance_complete`。

## P2 Editorial Memo 证据强化

`submit-editorial-memo` 要求 `prose_observation` 至少包含以下一种可定位证据：

- 场景引用（如 `S1`、`S2`）
- 行/段引用（如 `第3行`、`第一段`）
- 具体失效/修订语言（如“可优化”、“改为”、“生硬”、“删除”）
- 直接引用当前 revision 中的原文片段

纯抽象赞扬会被拒绝。Reader Review 的 `language` lens 明确涵盖节奏、机械短段、模板清单、标点与病句。

## P3 人类优先书工作区

每本书可在 `<root>/work/<slug>/` 生成人类可读目录入口：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root D:\my-novel --confirm init-workspace init-workspace my-novel
```

生成结构：

- `README.md`：书的入口说明；**首要阅读入口是 `manuscript/chapter-<number>-current.md`**，权威 library 路径仅作为来源标注。
- `CURRENT.md`：表格化索引，包含每章标题、状态、CJK 字数、当前 revision、hash、镜像路径；若镜像文件被用户编辑过，会在 Warnings 中列出。
- `manuscript/`：当前 revision 的只读镜像（由 `refresh-workspace` 更新）。
- `planning/`：Voice Bible / Scene Contract 只读镜像。
- `research/`、`reviews/`、`iterations/`、`archive/`：人工工作区。

`init-workspace` 和 `refresh-workspace` 都是非破坏性的：不会删除已存在的用户文件。`refresh-workspace` 在覆写 `manuscript/` 或 `planning/` 下的镜像前会检查文件头：如果文件不是由本系统生成的 `<!-- MIRROR of ...` 开头，则跳过覆写并在 `CURRENT.md` 与 JSON 返回的 `warnings` 中提示。

## P4 Patch Revision

允许对当前 revision 做精确定位替换，生成新的不可变 revision，而不是直接修改 library：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root D:\my-novel --confirm write-revision-patch write-revision-patch my-novel 1 --patch-file D:\patches\fix.json --note "fix typo"
```

`patch.json` 格式：

```json
[
  {
    "location": "S1 第3行",
    "evidence": "桌上有一封信",
    "replacement": "桌上摆着一封未拆的信",
    "reason": "增加具体性"
  }
]
```

约束：

- `evidence` 必须在当前 revision 中**唯一**匹配。
- 多项 patch 的 `evidence` 区间不得重叠。
- `replacement` 不能为空。
- 补丁文件必须是 library 外的绝对路径、有效 UTF-8。
- 已批准章节需要 `--reopen-reason`；patch 成功后章节状态变为 `revised`。
- patch 通过 `write_revision` 写审计并生成新 revision，旧 revision 文件保持不变。

Patch 适合局部校对修复；修复后仍需重新 lint、review 和独立编辑审稿。

## 已知限制

- P1 规则是表面模式匹配，可能误报；不能替代人工校对。
- 系统仍不能“读懂”文学性；最终判断属于人类或外部 Agent。
- 不自动改正文、不自动批准、不自动发布。
