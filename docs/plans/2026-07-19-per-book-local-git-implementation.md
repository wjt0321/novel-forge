# Per-Book Local Git Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give every `books/<slug>/` project an isolated, local-only Git history with automatic draft and ready checkpoints.

**Architecture:** Add a filesystem-only `book_git.py` module that owns separate-git-dir initialization, status, commit, tag, and restore behavior. Project initialization and `sync-tools` create or migrate repositories; adapter operations attach checkpoints after generation binding and ready transitions without changing evidence authority.

**Tech Stack:** Python 3.12 standard library, subprocess Git CLI, pytest, existing JSON-only skill adapter.

---

### Task 1: Local Git Core

**Files:**
- Create: `app/novel_forge/book_git.py`
- Create: `tests/test_book_git.py`

**Step 1: Write failing tests**

Cover separate git-dir initialization, local identity, no remotes, status metadata, scoped commits,
no-op commits, annotated checkpoint tags, invalid gitdir detection, and restore after deleting the
book worktree.

**Step 2: Verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest tests/test_book_git.py -q
```

Expected: collection/import failure because `book_git.py` does not exist.

**Step 3: Implement minimal core**

Expose:

```python
initialize_book_git(root, slug, title) -> dict
book_git_status(root, slug) -> dict
checkpoint_book(root, slug, message, *, tag=None) -> dict
restore_book_worktree(root, slug) -> dict
```

All subprocess calls use argument arrays, `cwd=book_dir`, UTF-8 text capture, and explicit
return-code checks. Verify the repository top level and common git dir match the expected paths.

**Step 4: Verify GREEN**

Run the focused test file and confirm all tests pass.

### Task 2: Project Initialization and Migration

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/book_project.py`
- Modify: `.gitignore`
- Test: `tests/test_novel_project.py`
- Test: `tests/test_book_project.py`

**Step 1: Write failing tests**

Assert new books receive an initial commit and external git directory. Assert `sync-tools --dry-run`
reports a planned Git initialization without writing it, and real `sync-tools` initializes an old
book while preserving hand-written files.

**Step 2: Verify RED**

Run the named project tests and confirm missing `local_git` metadata.

**Step 3: Implement**

Call `initialize_book_git` after templates are written. Add `local_git` to initialization and
sync results. Ignore `.local-book-git/` in the Harness repository.

**Step 4: Verify GREEN**

Run `tests/test_novel_project.py` and the sync-tools tests.

### Task 3: Adapter Operations and Automatic Checkpoints

**Files:**
- Modify: `app/novel_forge/skill_adapter.py`
- Test: `tests/test_skill_adapter.py`
- Test: `tests/test_book_evidence.py`
- Test: `tests/test_book_project.py`

**Step 1: Write failing tests**

Cover:

```text
book-git-status <slug>
init-book-git <slug>
restore-book-git <slug>
```

Verify `record-evidence` generation creates `chapter: chNN draft`, `advance-state --to ready`
creates `chapter: chNN ready`, and checkpoint chapters create the expected annotated tag.

**Step 2: Verify RED**

Run focused adapter tests and confirm parser/response failures.

**Step 3: Implement**

Register mutating operations, parsers, dispatch, and checkpoint result fields. Keep existing evidence
and state writes authoritative; return checkpoint metadata without returning prose.

**Step 4: Verify GREEN**

Run focused adapter and workflow tests.

### Task 4: Templates, Skill, and Documentation

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Create: `docs/27-per-book-local-git.md`
- Test: `tests/test_novel_project.py`

**Step 1: Write failing documentation-contract assertions**

Require v4.2, `book-git-status`, `draft + ready`, `.local-book-git`, no remote, and purge guidance.

**Step 2: Verify RED**

Run the Skill/template tests and observe missing v4.2 guidance.

**Step 3: Update managed templates and both byte-identical Skill copies**

Explain that Git is a local recovery/diff layer, not approval evidence. Document external metadata,
automatic checkpoints, volume tags, and explicit removal of both worktree and external history when
purging experiments.

**Step 4: Verify GREEN**

Run the documentation-contract and mirror tests.

### Task 5: Full Verification and Integration

**Files:** all changed files

**Step 1: Run focused suites**

```powershell
$env:PYTHONPATH='.'
python -m pytest tests/test_book_git.py tests/test_novel_project.py tests/test_book_project.py tests/test_skill_adapter.py -q
```

**Step 2: Run full regression**

```powershell
$env:PYTHONPATH='.'
python -m pytest tests/ -q
git diff --check
```

**Step 3: Run a real recovery smoke test**

Initialize a temporary book, make draft and ready checkpoints, delete only its worktree after
verifying absolute paths, restore from the external git directory, and compare tracked file hashes.

**Step 4: Commit, merge, and verify**

Commit on `codex/local-book-git`, merge into `main`, rerun the full suite on merged `main`, remove
the worktree and temporary branch, then push only `gitea main`.
