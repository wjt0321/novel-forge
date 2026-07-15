# 07 - 数据库迁移与备份

## 版本管理

Novel Forge 使用 SQLite `PRAGMA user_version` 跟踪 schema 版本：

- `v1`：第一里程碑（Foundation）
- `v2`：第二里程碑（Human-Readable Fiction Quality Layer），新增 Voice Bible、Scene Contract v2、Reader Reviews、book-scoped Canon Facts
- `v3`：第三/四里程碑，新增 Editorial Memo
- `v4`：第六里程碑初版，新增 Research Ledger、Story Engine、Chapter Plan、Promise Ledger、Iteration Runs
- `v5`：第六里程碑修正，为 Research Ledger 增加 `verification_state` 与 `verification_ref`，支持 B/C 级 `plot_support` 的 A 级佐证

`app/novel_forge/db.py` 中的 `init_db()` 在打开数据库时自动检测版本并应用迁移。

## 未版本化旧 v1 数据库的自动识别

第一里程碑的 `init_db()` 没有写入 `PRAGMA user_version`，因此真实旧库是 `user_version=0` 但已经包含 `books`/`chapters` 等表。系统通过以下规则区分：

- `user_version=0` 且不存在 `books` 表：视为全新空库，直接创建 v5 schema，不生成备份。
- `user_version=0` 但已存在 `books` 表：视为遗留未版本化 v1 库，先备份再迁移。
- `user_version=1`：显式 v1 库，先备份再迁移。
- `user_version > 5`：拒绝启动，提示升级 Novel Forge，不写入、不备份。

## 自动备份

当且仅当数据库需要升级时，`init_db()` 会在迁移前创建带时间戳的备份：

```text
data/novel-forge.backup-YYYYMMDD-HHMMSS-migration-to-v5.db
```

- 备份与主 DB 在同一目录。
- 文件名包含时间戳，不会覆盖旧备份。
- 新数据库初始化不会产生备份。
- 迁移失败时回滚，原数据库文件不变，备份文件保留。

## 迁移内容

### Scene Contract

旧 `scene_contracts` 表（每章一行，含 `file_path`/`content_hash`）会被重命名为 legacy 表，然后：

1. 为每行旧数据创建一条 `scene_contract_revisions` 记录（revision_number = 1）。
2. 在新 `scene_contracts` 表中建立 current pointer。
3. 保留原 Markdown 文件，不修改、不删除。

### Canon Facts

旧 `canon_facts` 表（无 `book_id`，全局 `subject/predicate` 索引）会被重命名为 legacy 表，然后：

1. 创建带 `book_id` 的新表。
2. 根据 `chapter_id` 回填 `book_id`。
3. 删除旧的全局索引，建立 `(book_id, subject, predicate)` 唯一索引。

### 新增表

迁移会自动创建：

- `voice_bible_revisions`、`voice_bibles`
- `scene_contract_revisions`
- `reader_reviews`
- `editorial_memos`
- `research_entries`
- `story_engines`
- `chapter_plans`
- `promise_ledger`
- `iteration_runs`

旧书不会自动获得 Voice Bible 模板；首次调用 `write-voice-bible` 时会创建 revision 1。

### v4 → v5

仅当 `research_entries` 缺少 `verification_state`/`verification_ref` 时：

1. 添加 `verification_state` 列，默认 `collected`。
2. 添加 `verification_ref` 列，可空。
3. 创建 `research_entries_verification_ref` 索引。

旧数据保持 `verification_state=collected`、`verification_ref=NULL`，不影响既有流程。

## 验证迁移

打开数据库检查版本：

```bash
sqlite3 data/novel-forge.db "PRAGMA user_version;"
# 应输出 5
```

检查 scene contract 是否已迁移：

```bash
sqlite3 data/novel-forge.db "SELECT chapter_id, current_revision_id FROM scene_contracts;"
sqlite3 data/novel-forge.db "SELECT chapter_id, revision_number, file_path FROM scene_contract_revisions;"
```

检查备份：

```bash
ls data/novel-forge.backup-*-migration-to-v5.db
```

## 恢复

如果迁移后出现问题，先停止所有 Novel Forge 进程，然后用备份替换当前 DB：

```bash
cp data/novel-forge.backup-YYYYMMDD-HHMMSS-migration-to-v5.db data/novel-forge.db
```

恢复后的 DB 仍是旧版本，下次启动服务会再次触发迁移并生成新的备份。

## 注意事项

- 迁移在单个事务中执行；失败时原库不变。
- 不要手动修改 `data/novel-forge.db` 的 `user_version`，否则会导致迁移逻辑混乱。
- Markdown 文件（`library/`）是长期真相来源；DB 损坏时可从 revision 目录重建。
