# 17. 每书长篇记忆内核

## 目标

本里程碑解决长篇小说最常见的连续性失真：已死亡人物再次出现、人物知道了不该知道的信息、状态变化被覆盖、伏笔没有回收，以及写作 Agent 因加载全书而浪费上下文。

设计边界仍然是“可审计，不替作者判断文学价值”：系统能证明某条记忆来自哪里、当前是否有效、是否与已有事实冲突；不能证明这条设定是否有趣，也不会自动批准它。

## 架构

每本书完全自包含：

```text
books/<slug>/
├── memory/
│   ├── canon/
│   │   ├── entities/
│   │   ├── facts/
│   │   ├── events/
│   │   ├── knowledge/
│   │   └── promises/
│   ├── candidates/chXX/
│   ├── context-cache/
│   ├── MEMORY.md
│   └── memory-record-template.md
└── .novel-forge/
    ├── index.sqlite3
    └── source-manifest.json
```

`memory/canon/**/*.md` 是长期权威源。SQLite 仅是标准库 `sqlite3` 生成的投影索引：无新依赖、每书一个文件、可随时删除并从 Markdown 重建。它不会接触根目录 legacy `data/novel-forge.db`，也不需要 migration；schema 变化直接重建。

## 记录模型

记录是普通 Markdown，唯一的 `<!-- novel-forge-memory:v1 -->` 标记后紧跟 fenced JSON 元数据。块外内容由人维护，晋升或状态接续时原样保留。

共同字段包括 `id`、`kind`、`status`、`tier`、`chapter`、`source_path`、`evidence`、`summary` 与可选 `supersedes`。五类投影为：

- `entity`：实体名、类型、别名。
- `fact`：`subject / predicate / object` 与章节有效期。
- `event`：事件类型、参与者、地点。
- `knowledge`：谁知道、怀疑或误信哪项命题。
- `promise`：伏笔内容、状态、埋设章、目标章与回收章。

事实不是永恒键值。`陈拾 / life_state / alive` 可以在第 1-4 章有效，第 5 章的 `dead` 用 `supersedes` 接续。系统会闭合旧事实有效期；任何未显式接续的重叠区间都会阻断晋升和全量重建。

## 证据与过期

manifest 同时记录两类 SHA-256：Canon Markdown 自身，以及每条记录引用的正文 `source_path`。任一发生变化，`memory-status` 都返回 `stale`。因此旧 Canon 不会在正文被改写后继续无声冒充当前证据。

只有 `clean` 索引可以生成章节上下文包。包按用途分层：

- P0：本章有效的硬事实。
- P1：活跃叙事与到期承诺。
- P2：软纹理。

writer 只读取本章包、近场连续和当前场景材料，不加载全书 Canon。包内保留记录 ID、短摘要、来源和证据指针，便于追溯；adapter 响应只返回路径、计数和 ID，不泄露正文或完整 Markdown。

## Candidate 晋升

正文写完后，consistency-guard 把新增事实、事件、知识变化和承诺整理为 candidate。记录 candidate 不会改变 Canon；只有显式执行 promotion 才会：

1. 直接扫描 Canon Markdown，不信任可能过期的 SQLite。
2. 检查重复 ID、来源路径、kind 与有效期冲突。
3. 按 `supersedes` 更新旧记录并保留人工说明。
4. 写入新 Canon，原子重建索引。
5. 将 candidate 标记为 promoted。

写入失败会恢复涉及的 Markdown，并尝试重建旧索引。索引本身采用临时数据库、完整性检查、锁文件和 `os.replace`；中断至多造成 `stale`，不会把缓存当作权威真相。

## Adapter 操作

```text
memory-status <slug>
record-memory-candidate <slug> --file <absolute-markdown>
promote-memory-candidate <slug> <candidate-id>
rebuild-memory-index <slug>
build-memory-context <slug> <chapter>
```

除 `memory-status` 外均为写操作，要求 `--confirm <operation>`。所有响应保持 JSON-only。

## 明确不做

- 不自动从正文抽取并批准事实。
- 不用向量相似度代替确定性事实查询。
- 不让 SQLite 成为不可重建的第二真相源。
- 不把 candidate 当成后续章节的已知事实。
- 不宣称通过一致性检查等于文学质量合格或作者批准。
