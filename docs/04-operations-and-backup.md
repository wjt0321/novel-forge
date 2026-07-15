# 04 - 操作与备份

## 审计账本

所有关键操作写入 `audit_events`：

```bash
python -m novel_forge.cli audit my-novel --limit 50
```

## 备份策略

- Markdown 正文与 manifest 是长期真相来源。
- `data/novel-forge.db` 损坏时，可从 `library/<slug>/manuscript/revisions/` 和导出 manifest 重建索引。
- 建议将 `library/` 纳入 Git 版本控制，`data/` 加入 `.gitignore`。

## 导出产物

每次导出生成：

- 产物文件（如 `{slug}-{timestamp}.md`）
- manifest（`{slug}-{timestamp}-manifest.json`），包含来源 revision、sha256、时间戳

DOCX/EPUB/PDF 导出依赖 Pandoc；未安装时返回清晰错误并记录审计。

## Skill-first 受限入口

自动化脚本、Skills、编排器不应直接操作 SQLite 或 `library/` 下的 revision 文件。请通过受限 adapter 访问：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root D:\my-novel <operation> ...
```

`--root` 必须是绝对路径；相对路径会被 JSON error `invalid_root` 拒绝，不会创建目录。

可用操作（完整列表）：

- 只读/诊断：`status`、`lint`、`review`、`audit`
- 书籍/章节生命周期：`init-book`、`create-chapter`、`write-revision`、`rollback-chapter`
- 审稿：`add-finding`、`resolve-finding`、`add-reader-review`、`resolve-reader-review`
- 事实/Canon：`add-candidate-fact`、`approve-fact`、`reject-fact`
- 审批/导出：`approve-chapter`、`export-book`
- 创作资产（第二里程碑）：`voice-bible-status`、`write-voice-bible`、`scene-contract-status`、`write-scene-contract`
- 写作上下文包（第三里程碑）：`build-drafting-packet`
- 写作就绪度门（第四里程碑）：`drafting-readiness`
- 叙事编辑门（第五里程碑）：`submit-editorial-memo`、`editorial-memo-status`
- 自主研究写作链（第六里程碑）：`add-research-entry`、`update-research-entry`、`list-research`、`set-story-engine`、`get-story-engine`、`set-chapter-plan`、`get-chapter-plan`、`update-promise`、`list-promises`、`record-iteration`、`list-iterations`、`check-acceptance`、`git-checkpoint`
- 质量链重构（P0–P4）：`init-workspace`、`refresh-workspace`、`write-revision-patch`

特点：

- 只输出 JSON；成功 `{ok:true, operation, data}`，可预期业务失败 `{ok:false, error:{code,message}}`。
- 不返回正文全文或输入 Markdown 内容；Voice Bible / Scene Contract / Reader Review / Editorial Memo 正文也不会泄露。
- 对 init/create/write/add/resolve/approve/reject/rollback/export 以及 `write-voice-bible`、`write-scene-contract`、`add-reader-review`、`resolve-reader-review`、`submit-editorial-memo`、`add-research-entry`、`update-research-entry`、`set-story-engine`、`set-chapter-plan`、`update-promise`、`record-iteration`、`git-checkpoint`、`init-workspace`、`refresh-workspace`、`write-revision-patch` 等变更操作强制 `--confirm <operation>`。
- `write-revision`、`write-voice-bible`、`write-scene-contract` 拒绝 `<root>/library` 内的输入路径，避免就地覆盖或循环引用。
- 输入 Markdown 必须是 UTF-8 编码（允许带 BOM）；非 UTF-8 源文件会在创建 revision 前被拒绝。

## 数据库迁移

`init_db()` 会自动检测 schema 版本并在需要时升级。迁移前会在 `data/` 目录生成带时间戳的备份，例如 `novel-forge.backup-YYYYMMDD-HHMMSS-migration-to-v5.db`。迁移是原子事务，失败时原库不变。详细说明与恢复步骤见 `docs/07-database-migration.md`。

未版本化的旧 v1/v2/v3/v4 数据库会被自动识别并迁移到 v5。新库初始化不产生备份。

## 限制

- 本里程碑不实现删除操作。
- 不实现真实 LLM 调用或联网抓取。
- `submit-editorial-memo` 只校验字段非空和 blocking issue 结构，不判断内容质量。
- `check-acceptance` 仅验证流程覆盖度（字数、场景数、研究、承诺、编辑备忘录、质量门），不评判文学价值。
- `git-checkpoint` 只 stage `library/<slug>/` 与 `docs/<slug>/`，不会提交 `data/`、全局 `docs/` 或密钥文件。
- UI（React/Vite）待 CLI/API 稳定后实现。
