# Harness Integrity and Serial Continuity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Novel Forge resilient to no-Shell writing runs and resistant to duplicate evidence, false provenance, unsupported review quotations, and cross-chapter timeline resets.

**Architecture:** Keep Markdown as the authority. Extend the shared planning/evidence specification, enforce semantic identity in `book_evidence`, bind chapter N reviews and scene packages to chapter N-1, and expose all integrity problems through `project-status`. Generated projects receive the same behavior through templates and the mirrored Novel Forge skill.

**Tech Stack:** Python 3.12, pathlib, hashlib, regular expressions, pytest, Markdown templates, JSON-only skill adapter.

---

### Task 1: Preserve the experiment and remove disposable books

**Files:**
- Create: `docs/examples/agent-demo-v35-deepseek-harness-comparison.md`
- Create: `docs/examples/agent-demo-v35-deepseek-harness-comparison.json`

**Steps:**
1. Record exact prose hashes, CJK counts, voice metrics, gate results and Harness provenance.
2. Record strengths, weaknesses and workflow anomalies without copying full prose.
3. Parse the JSON document.
4. Delete only `books/silent-era` and `books/reborn-1998` after resolving and verifying both paths remain under `books/`.
5. Verify neither directory remains.

### Task 2: Define runtime identity and semantic generation behavior

**Files:**
- Modify: `tests/test_book_evidence.py`
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/book_evidence.py`

**Steps:**
1. Write a failing test that records two generation IDs for the same chapter SHA-256 and expects `duplicate generation`.
2. Run the focused test and confirm it fails because duplicate semantic identity is not checked.
3. Write a failing status test with legacy duplicate files and expect record count 2, semantic generation count 1 and one duplicate group.
4. Write failing validation tests for Agent authority plus `user_attested`, invalid reasoning effort and invalid sandbox profile.
5. Add runtime constants and validation fields.
6. Reject same-chapter same-content generation records.
7. Count generation budgets by distinct content SHA-256 and report duplicate groups.
8. Run `tests/test_book_evidence.py`.

### Task 3: Add degraded exploration

**Files:**
- Modify: `tests/test_book_project.py`
- Modify: `tests/test_book_gates.py`
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/book_gates.py`
- Modify: `app/novel_forge/book_project.py`

**Steps:**
1. Write failing tests that `degraded_exploration` skips formal material gates, remains visible in status and cannot enter ready.
2. Run the focused tests and confirm the mode is rejected.
3. Add the mode to the shared specification.
4. Treat it like exploration for narrative checks but return a degraded advisory.
5. Preserve the ready prohibition for every non-formal mode.
6. Run the focused project and gate tests.

### Task 4: Enforce chapter handoff integrity

**Files:**
- Modify: `tests/test_book_gates.py`
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/book_gates.py`

**Steps:**
1. Write a failing ch02 test with the correct previous hash and exact source quotations.
2. Write failing tests for wrong previous hash, missing quotation and same-day time reversal.
3. Run the tests and confirm the handoff section is not implemented.
4. Add the `0b. 章际交接` field specification.
5. Validate previous chapter discovery, SHA-256, exact quotations and time-order ranks.
6. Keep flashback, parallel and cross-day transitions explicit and non-blocking when documented.
7. Run `tests/test_book_gates.py`.

### Task 5: Bind critical serial reviews to both chapters

**Files:**
- Modify: `tests/test_book_project.py`
- Modify: `app/novel_forge/book_project.py`

**Steps:**
1. Write failing tests that ch02 consistency/chapter reviews require `previous_chapter_sha256`, `evidence_quote` and `previous_chapter_quote`.
2. Write a failing test for a quotation absent from the bound prose.
3. Write a failing test showing a ch01 edit makes ch02 serial reviews stale.
4. Include the previous chapter hash in review bindings.
5. Validate exact evidence quotations for blind-reader, consistency-guard and chapter-editor.
6. Require previous-chapter evidence for consistency-guard and chapter-editor from ch02 onward.
7. Run `tests/test_book_project.py`.

### Task 6: Report non-canonical duplicate artifacts

**Files:**
- Modify: `tests/test_book_project.py`
- Modify: `app/novel_forge/book_project.py`

**Steps:**
1. Write a failing status test with `reviews/ch01/blind-reader.md` duplicating the canonical review.
2. Detect nested review copies and expose `duplicate_review_artifact`.
3. Ensure duplicate artifacts make benchmark eligibility false without deleting user files.
4. Run the focused test.

### Task 7: Update generated projects and documentation

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_novel_project.py`
- Create: `docs/21-harness-integrity-and-serial-continuity.md`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`

**Steps:**
1. Write failing template tests for v3.6, degraded run report, runtime metadata, chapter handoff and serial review bindings.
2. Update project constitution, scene package, generation template, review template and relevant Agent roles.
3. Update the canonical Skill and copy it byte-for-byte to the Claude mirror.
4. Run template and mirror tests.

### Task 8: Verify and publish

**Steps:**
1. Run focused evidence, gate, project and template tests.
2. Run `python -m compileall -q app tests`.
3. Run `PYTHONPATH=. python -m pytest tests/ -q`.
4. Run `git diff --check`.
5. Verify the experiment JSON parses and both Skill files are byte-identical.
6. Verify `books/` no longer contains either experiment.
7. Review the staged diff, commit, fetch `gitea/main`, resolve only if needed, and push without force.

