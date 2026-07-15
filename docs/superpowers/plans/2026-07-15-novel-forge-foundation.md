# S-Black Novel Forge Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for every production code change. Write failing tests first, then minimal implementation, then refactor.

**Goal:** Implement the Foundation + Vertical Slice milestone of S-Black Novel Forge: CLI + SQLite audit ledger + Markdown asset storage + FastAPI local API + pytest coverage.

**Architecture:** SQLite stores state, audit, findings, facts, and revision metadata; Markdown files in `library/<slug>/manuscript/revisions/` store the immutable chapter revisions. All operations go through a service layer that enforces state machines, immutability, and audit logging. CLI and API are thin adapters over the service layer.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, pydantic, pytest, stdlib sqlite3/pathlib/subprocess.

## Global Constraints

- Python 3.12+.
- Runtime deps: `fastapi`, `uvicorn`, `pydantic`. Test dep: `pytest`.
- No real secrets in source, config, or tests.
- SQLite uses transactions and `PRAGMA foreign_keys=ON`.
- Markdown is the single source of truth for prose; DB never stores chapter body as the only copy.
- No overwrite/delete of user prose. New revisions create new files; rollback copies an old revision to a new file.
- All deletions are soft deletes or unsupported in this milestone.
- Commands have clear errors, `--help`, and non-zero exit codes.
- Project root is `D:\s-black-novel`.

## File Structure

```text
D:\s-black-novel\
├─ app\novel_forge\
│  ├─ __init__.py
│  ├─ cli.py              # Typer/argparse CLI; all 14 commands
│  ├─ db.py               # SQLite connection, schema, migrations
│  ├─ models.py           # Pydantic models for API/service boundaries
│  ├─ repository.py       # Low-level DB operations (books, chapters, revisions, findings, facts, audit)
│  ├─ service.py          # Business logic, state machines, immutability rules
│  ├─ lint.py             # Prose lint rules and runner
│  ├─ export.py           # Markdown / Pandoc export with manifest
│  └─ api.py              # FastAPI factory `create_app(root)`
├─ tests\                 # pytest tests mirroring modules
├─ docs\                  # Numbered product docs
├─ library\               # Book assets created at runtime
└─ requirements.txt
```

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `app/novel_forge/__init__.py`
- Create: `app/novel_forge/db.py` (schema)
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- `get_db_path(root: Path) -> Path`
- `init_db(root: Path) -> sqlite3.Connection`
- Schema creates tables: books, chapters, revisions, lint_findings, review_findings, candidate_facts, canon_facts, audit_events, exports, scene_contracts.

## Task 2: Models

**Files:**
- Create: `app/novel_forge/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Pydantic models: `Book`, `Chapter`, `Revision`, `LintFinding`, `ReviewFinding`, `CandidateFact`, `CanonFact`, `AuditEvent`, `ExportManifest`, `ChapterSummary`.

## Task 3: Repository Layer

**Files:**
- Create: `app/novel_forge/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- `BookRepository`, `ChapterRepository`, `RevisionRepository`, `FindingRepository`, `FactRepository`, `AuditRepository`, `ExportRepository`.
- All methods accept `conn: sqlite3.Connection`.

## Task 4: Service Layer — Books & Chapters

**Files:**
- Create: `app/novel_forge/service.py`
- Test: `tests/test_service_book_chapter.py`

**Interfaces:**
- `NovelForgeService(root: Path)`
- `init_book(slug, title)`
- `create_chapter(slug, number, title)`
- Reject duplicate slug / duplicate chapter number with clear errors.

## Task 5: Service Layer — Revisions

**Files:**
- Modify: `app/novel_forge/service.py`
- Test: `tests/test_service_revisions.py`

**Interfaces:**
- `write_revision(slug, number, from_file, note, reopen_reason=None)`
- Copy source file to `library/<slug>/manuscript/revisions/ch{number:04d}/{ts}-{hash}.md`.
- Update chapter `current_revision_id` and `current_hash`.
- If chapter state is `approved`, require `reopen_reason` and transition to `revised` with audit.

## Task 6: Prose Lint

**Files:**
- Create: `app/novel_forge/lint.py`
- Test: `tests/test_lint.py`

**Interfaces:**
- `lint_revision(revision_path: Path) -> List[LintFinding]`
- Rules: em-dash, ellipsis, not-is-flip, explanation-tic, word-count-tic, colon-density.
- `lint_chapter(slug, number)` writes findings to DB with source revision, updates chapter state to `linted` if blocking exists (approval still blocked).

## Task 7: Review Findings & Review Command

**Files:**
- Modify: `app/novel_forge/service.py`
- Test: `tests/test_service_findings.py`

**Interfaces:**
- `add_finding(...)`, `resolve_finding(finding_id, note)`
- `review_chapter(slug, number) -> ReviewResult` with APPROVE/CONCERNS/REJECT based on open findings.
- State transitions to `reviewed`.

## Task 8: Approval Gate

**Files:**
- Modify: `app/novel_forge/service.py`
- Test: `tests/test_service_approval.py`

**Interfaces:**
- `approve_chapter(slug, number, note)`
- Reject if blocking lint, open S1/S2 findings, or no current revision.
- Transition to `approved` with audit.

## Task 9: Candidate & Canon Facts

**Files:**
- Modify: `app/novel_forge/service.py`
- Test: `tests/test_service_facts.py`

**Interfaces:**
- `add_candidate_fact(...)`, `approve_fact(...)`, `reject_fact(...)`
- Canon conflict detection on same subject+predicate.
- Audit all transitions.

## Task 10: Rollback

**Files:**
- Modify: `app/novel_forge/service.py`
- Test: `tests/test_service_rollback.py`

**Interfaces:**
- `rollback_chapter(slug, number, revision_id, note)`
- Copy old revision Markdown to a new revision file; set chapter state to `revised`.

## Task 11: Export

**Files:**
- Create: `app/novel_forge/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- `export_book(slug, fmt)`
- `markdown`: compile approved chapters in order, write manifest JSON with source revisions, sha256, timestamp.
- `docx/epub/pdf`: call Pandoc if available; otherwise error cleanly and audit.

## Task 12: CLI

**Files:**
- Create: `app/novel_forge/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- `python -m novel_forge.cli <command> --root <path> ...`
- All 14 commands, with `--help` and non-zero exit codes on errors.

## Task 13: FastAPI API

**Files:**
- Create: `app/novel_forge/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- `create_app(root: Path) -> FastAPI`
- Routes: `/health`, `/books`, `/books/{slug}`, `/books/{slug}/chapters`, `/books/{slug}/chapters/{number}`, `/books/{slug}/audit`.
- Chapter endpoint does not return full body; returns metadata, finding counts, approved canon facts.

## Task 14: Numbered Docs

**Files:**
- Create: `docs/01-getting-started.md`
- Create: `docs/02-data-model-and-state-machine.md`
- Create: `docs/03-quality-and-approval-gates.md`
- Create: `docs/04-operations-and-backup.md`

## Task 15: Final Verification

- Run `pytest -q`.
- Run CLI smoke test with temporary root.
- Report file changes, test results, known limitations.
