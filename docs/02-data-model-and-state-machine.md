# 02 - 数据模型与状态机

## 数据模型

### 书籍（Book）

- `slug`：URL 友好的唯一标识
- `title`：书名

### 章节（Chapter）

- `number`：章节号，每本书内唯一
- `title`：章标题
- `state`：状态机当前状态
- `current_revision_id`：当前 revision 指针
- `current_hash`：当前 revision 内容 SHA256

### Revision

- Markdown 文件的真实路径
- `content_hash`：SHA256
- `revision_number`：章节内递增序号
- 不允许覆盖；rollback 也会生成新的 revision 文件

### Finding

- `lint_findings`：静态 prose lint 结果，关联 revision
- `review_findings`：四维审稿发现，关联 chapter/revision

### Fact

- `candidate_facts`：草稿或抽取产生的事实候选
- `canon_facts`：已批准、不可静默冲突的事实
- 唯一索引 `(subject, predicate)` 防止冲突

### Promise Ledger

- `promise_ledger` 按书记录叙事承诺/伏笔生命周期
- 状态：`planned` → `planted` → `partially_paid` → `paid_off`；任意非终态可转至 `abandoned`
- 可选 `target_chapter_number` / `target_scene_ref` 支持逾期与本章提醒
- 每次状态变更写入 `audit_events`，保留前后状态

### Audit

- 所有状态变更、审批、导出均写入 `audit_events`

## 状态机

```text
                         write_revision
                              │
                              ▼
draft ──write_revision──► revised ──lint──► linted ──review──► reviewed
                              │                                  │
                              │                                  │
                              └────────approve_chapter───────────┘
                                   (需 reopen_reason,
                                    无 blocking/S1/S2)
```

章节还可能从 `reviewed` 经 `write-revision` 回到 `draft`（新 revision 必须重新走 lint + review）。

### 关键规则

- `create-chapter` → `draft`。
- `write-revision` → `draft`；若当前为 `approved` 且提供 `--reopen-reason` → `revised`。
- `lint-chapter` 必须有当前 revision；执行成功后无条件进入 `linted`（无论是否有 finding，blocking 只在审批门被拦截）。
- `review-chapter` 只允许从 `linted`、`revised`、`reviewed` 执行，结果进入 `reviewed`。
- `approve-chapter` 只允许从 `reviewed` 执行，且当前 revision 不得有未关闭的 blocking lint 或 S1/S2 finding。
- `rollback-chapter` 只允许在有 revision 的非 `draft` 状态执行，结果进入 `revised`；不修改历史文件，而是把目标 revision 复制为新的 revision。
- 每个新 revision 都是一次干净的审核起点：旧 revision 的未关闭 finding 保留为审计记录，但不会阻塞新 revision 的审批。
- 所有删除在本里程碑中不支持或采用软删除。
