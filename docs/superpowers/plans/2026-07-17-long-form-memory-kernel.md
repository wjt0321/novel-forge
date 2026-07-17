# Long-Form Memory Kernel Implementation Plan

> **For Novel Forge maintainers:** implement this plan test-first and keep
> `books/<slug>/` memory isolated from the legacy root database.

**Goal:** Add a per-book, Markdown-authoritative continuity memory with a
deletable SQLite index, candidate-to-canon promotion, conflict detection, and
chapter-scoped context packets.

**Architecture:** Canonical records live under
`books/<slug>/memory/canon/`; pending deltas live under
`books/<slug>/memory/candidates/`. Each record is a normal Markdown document
containing one fenced JSON metadata block marked `novel-forge-memory:v1`.
`books/<slug>/.novel-forge/index.sqlite3` and its source manifest are derived
artifacts rebuilt atomically from canonical Markdown. The root
`data/novel-forge.db` is never opened.

**Tech Stack:** Python 3.12 standard library (`json`, `sqlite3`, `hashlib`,
`os`, `tempfile`), existing argparse JSON adapter, pytest.

---

## Record Contract

Every record contains:

```markdown
# Human-readable title

<!-- novel-forge-memory:v1 -->
```json
{
  "schema_version": 1,
  "id": "fact.chen-shi.life-state.ch01",
  "kind": "fact",
  "status": "candidate",
  "tier": "hard",
  "chapter": 1,
  "source_path": "chapters/e01/ch-01/正文.md",
  "evidence": "可定位的短证据",
  "summary": "供上下文包使用的短摘要",
  "subject": "char.chen-shi",
  "predicate": "life_state",
  "object": "alive",
  "valid_from": 1,
  "valid_to": null,
  "supersedes": null
}
```
```

Supported kinds and required fields:

- `entity`: `name`, `entity_type`; optional `aliases`.
- `fact`: `subject`, `predicate`, `object`, `valid_from`; optional
  `valid_to`.
- `event`: `event_type`, `participants`; optional `location`.
- `knowledge`: `knower`, `proposition`, `knowledge_state`.
- `promise`: `promise`, `promise_status`, `planted_chapter`; optional
  `target_chapter`, `resolved_chapter`, `related_entities`.

Common enum constraints:

- `tier`: `hard`, `active`, `soft`
- candidate status: `candidate`, `promoted`, `rejected`
- canon status: `canonical`
- promise status: `planned`, `planted`, `partially_paid`, `paid_off`,
  `abandoned`
- knowledge state: `known`, `suspected`, `false_belief`

IDs use ASCII letters, digits, `.`, `_`, and `-`. Source paths are relative to
the book directory, may not traverse upward, and must exist when a candidate is
recorded or an index is rebuilt.

## Task 1: Parser and Validation

**Files:**

- Create: `app/novel_forge/book_memory.py`
- Test: `tests/test_book_memory.py`

1. Write failing tests for extracting the marked JSON block, rejecting invalid
   IDs/enums/fields, rejecting paths outside the book, and rendering a
   round-trippable record.
2. Implement immutable `MemoryRecord` data and validation helpers.
3. Run `PYTHONPATH=. python -m pytest tests/test_book_memory.py -q`.

## Task 2: Canon Scan and Atomic Index

**Files:**

- Modify: `app/novel_forge/book_memory.py`
- Test: `tests/test_book_memory.py`

1. Write failing tests for empty rebuild, all five record kinds, source hashes,
   manifest freshness, and stale detection after Markdown changes.
2. Create schema tables: `metadata`, `source_files`, `records`, `entities`,
   `facts`, `events`, `event_participants`, `knowledge`, `promises`, and
   `chapter_snapshots`.
3. Build a temporary database and manifest, then replace both atomically while
   holding `.novel-forge/index.lock`.
4. Treat schema changes as rebuilds; do not add migrations.

## Task 3: Candidate Promotion and Conflicts

**Files:**

- Modify: `app/novel_forge/book_memory.py`
- Test: `tests/test_book_memory.py`

1. Write failing tests for recording without overwrite, duplicate IDs,
   overlapping hard-fact conflicts, and explicit supersession.
2. On promotion, scan canonical Markdown directly rather than trusting the
   cache.
3. For `supersedes`, update the superseded record with `superseded_by`; for
   facts, close an open validity interval at `new.valid_from - 1`.
4. Write the canonical record, mark the candidate `promoted`, and rebuild the
   index. Use rollback copies so a failed rebuild cannot leave a half-promoted
   Markdown state.

## Task 4: Context Packet

**Files:**

- Modify: `app/novel_forge/book_memory.py`
- Test: `tests/test_book_memory.py`

1. Write failing tests that a packet requires a clean index.
2. Query facts valid for the requested chapter, current knowledge, active/due
   promises, relevant entities/events, and soft texture records.
3. Write `memory/context-cache/chXX-memory.md` with P0 hard canon, P1 active
   narrative, and P2 soft texture sections.
4. Return only paths, IDs, and counts to callers, never the packet body.

## Task 5: Skill Adapter

**Files:**

- Modify: `app/novel_forge/skill_adapter.py`
- Test: `tests/test_book_memory.py`

Add:

- `memory-status <slug>` (read-only)
- `record-memory-candidate <slug> --file <absolute UTF-8 Markdown>`
- `promote-memory-candidate <slug> <candidate-id>`
- `rebuild-memory-index <slug>`
- `build-memory-context <slug> <chapter>`

All writes require exact `--confirm`. Adapter output remains JSON-only and
never includes full prose or record Markdown.

## Task 6: Templates and Workflow Documentation

**Files:**

- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/book_project.py`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`
- Modify: `AGENTS.md`
- Create: `docs/17-long-form-memory-kernel.md`
- Test: `tests/test_novel_project.py`
- Test: `tests/test_book_project.py`

1. Create canon kind directories, candidates directory, and `.novel-forge/`.
2. Add record examples/README files and ignore `.novel-forge/`.
3. Teach context collector and consistency guard to use a clean generated
   memory packet and to submit discovered deltas as candidates.
4. Let `sync-tools` create new memory templates without overwriting
   hand-maintained canon records.
5. Keep both Skill copies byte-identical.

## Task 7: Verification

1. Run focused tests after each red/green cycle.
2. Run `PYTHONPATH=. python -m pytest tests/ -q`.
3. Run `git diff --check`.
4. Inspect `git status --short` and the final diff for accidental demo-book,
   root database, or generated cache changes.
