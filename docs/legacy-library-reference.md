# Legacy Library Reference

This document consolidates compatibility information for the legacy `library/` + SQLite workflow. The default product is the Markdown-first `books/` Lean Native workflow. Never mix the two state machines or manuscript locations.

## Scope

Legacy flow:

```text
cli / api / skill_adapter -> service -> repository -> SQLite
```

Primary legacy assets include:

- `library/<slug>/manuscript/revisions/` for immutable revision files;
- `data/novel-forge.db` for the ledger and index;
- audits, findings, facts, promises, exports, and migration records.

Do not edit the database or revision directory directly. Use `NovelForgeService`, the CLI, API, or confirmed adapter operations.

## Environment

Python 3.12+ with dependencies from `requirements.txt`:

```powershell
pip install -r requirements.txt
$env:PYTHONPATH='.'; python -m pytest tests/ -q
$env:PYTHONPATH='app'; python -m novel_forge.cli --help
```

Create a legacy project only when compatibility work explicitly requires it:

```powershell
$env:PYTHONPATH='app'
python -m novel_forge.cli init-novel-project my-novel --title '我的小说' --genre '都市'
```

For new author-facing work use `tools/novel-workflow.py` and `books/` instead.

## Data model

The legacy ledger models:

- Book and Chapter identity;
- immutable Revision records and content hashes;
- lint/editorial/reader Findings bound to a revision;
- Canon Facts with candidate/promotion/conflict status;
- Promise Ledger items and resolution state;
- audit and iteration runs;
- Voice Bible and scene-contract versions;
- research/story-engine/chapter-plan records;
- export manifests.

SQLite is not the manuscript authority. Revision Markdown and exported manifests remain durable evidence.

## State and approval

Legacy chapter state progresses only through service operations. Approval requires the current revision to satisfy required lint/editorial/reader gates and Canon conflict rules. Findings are revision-scoped; a later revision invalidates stale approval evidence.

No automated score or pass can claim author approval, literary value, market performance, publication eligibility, or legal/safety clearance.

## Drafting packets and readiness

The historical Drafting Packet grouped context as P0/P1/P2 and introduced readiness checks for Voice Bible and scene contracts. The current `books/` workflow reuses the bounded-context principle in Guardian `writer-context.md`; it does not use the legacy packet state.

Exploratory or incomplete legacy drafts must remain explicitly marked and cannot be promoted as formal output merely because a file exists.

## Quality records

Legacy quality layers include:

- deterministic prose lint;
- reader-facing evidence/effect/revision-intent findings;
- Blind Experience report;
- Editorial Memo;
- Canon conflict and knowledge-gap checks;
- acceptance summaries.

These records do not automatically rewrite prose. Patch operations create a new immutable revision and preserve the parent binding.

## Database migration

`init_db()` detects schema version and upgrades supported legacy databases. Migration behavior:

1. identify versioned or recognized unversioned schemas;
2. create a timestamped backup under `data/`;
3. run the upgrade in an atomic transaction;
4. preserve the original database if migration fails;
5. verify expected tables, columns, indexes, and version metadata.

Before migration, make an external copy of `data/` when the ledger matters. Never hand-edit `PRAGMA user_version`, table definitions, or migration rows.

## Backup and export

Back up together:

- the SQLite database;
- `library/<slug>/manuscript/revisions/`;
- research and planning source files;
- export manifests and audit records.

An export manifest records inputs and hashes; it is stronger evidence than an untracked generated DOCX/EPUB/PDF. Optional Pandoc output is a derivative artifact.

## Adapter and API boundaries

- Adapter `--root` must be absolute.
- Mutating adapter operations require `--confirm`.
- API and adapter do not return full prose bodies.
- Path traversal and cross-book access are rejected.
- Legacy operations cannot mutate `books/` state or per-book local Git.

## Maintenance rule

When fixing a legacy compatibility bug, add a regression test and update this file only if the public compatibility contract changes. New features belong to `books/` unless the user explicitly requests legacy support.
