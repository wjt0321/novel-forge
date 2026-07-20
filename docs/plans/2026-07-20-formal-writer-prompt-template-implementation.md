# Formal Writer Prompt Template Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Compile a short `formal-writer/v1` prompt into each isolated writer capsule and bind its hash through Guardian receipt and formal generation evidence.

**Architecture:** A new pure `writer_prompt.py` module owns the template ID, length limit, and rendering. `guardian.py` creates and protects `instructions.md`, then carries prompt provenance through control and signed receipts. Book evidence and ready validation bind the current generation to the same template ID and hash.

**Tech Stack:** Python 3.12, pathlib, hashlib, pytest, existing Novel Forge Guardian and books workflow.

---

### Task 1: Define the prompt renderer

**Files:**
- Create: `app/novel_forge/writer_prompt.py`
- Create: `tests/test_writer_prompt.py`

**Step 1: Write the failing tests**

Test that `render_formal_writer_instructions(1)`:

- returns `formal-writer/v1`;
- names chapter 01;
- names only `handoff.md` and `draft/正文.md`;
- includes the 5,000 CJK floor and stop behavior;
- excludes vendor names, validator details, and numeric style targets;
- stays below 1,200 characters;
- rejects non-positive chapter numbers.

**Step 2: Run the tests to verify RED**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_writer_prompt.py -q
```

Expected: FAIL because `app.novel_forge.writer_prompt` does not exist.

**Step 3: Implement the minimal renderer**

Create constants:

```python
FORMAL_WRITER_PROMPT_ID = "formal-writer/v1"
MAX_FORMAL_WRITER_PROMPT_CHARS = 1200
```

Return a small immutable result containing the template ID and rendered text.

**Step 4: Run the focused tests**

Expected: all `tests/test_writer_prompt.py` tests pass.

### Task 2: Compile and protect `instructions.md`

**Files:**
- Modify: `app/novel_forge/guardian.py`
- Modify: `app/novel_forge/guardian_contract.py`
- Modify: `tests/test_guardian.py`

**Step 1: Write failing Guardian tests**

Assert that a prepared capsule contains `instructions.md`, exposes no extra
control-plane input, returns only prompt ID/hash metadata, and marks the file as
protected. Assert that changing `instructions.md` produces a compromised
receipt with `protected_input_changed:instructions.md`.

**Step 2: Run the tests to verify RED**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_guardian.py -q
```

Expected: FAIL because the capsule does not contain `instructions.md`.

**Step 3: Implement Guardian integration**

Render the prompt before `capsule.json`, write `instructions.md`, add it to the
allowed/protected file sets, and add `prompt_template_id` plus `prompt_sha256`
to manifest, control, receipts, and sanitized adapter results.

**Step 4: Run Guardian tests**

Expected: all Guardian tests pass.

### Task 3: Bind formal generation evidence

**Files:**
- Modify: `app/novel_forge/book_evidence.py`
- Modify: `app/novel_forge/book_project.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_book_evidence.py`
- Modify: `tests/test_book_project.py`

**Step 1: Write failing evidence and ready tests**

Test paired validation of `prompt_template_id` and `prompt_sha256`. Test that a
formal agent generation with missing or mismatched prompt provenance is
rejected by Guardian ready validation, while matching provenance passes.

**Step 2: Run the tests to verify RED**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_book_evidence.py tests/test_book_project.py -q
```

Expected: FAIL because prompt provenance is not parsed or compared.

**Step 3: Implement minimal provenance validation**

Add the two fields to the generation template and validate them as a pair.
Require exact agreement with the signed clean Guardian receipt for formal
non-human generations.

**Step 4: Run focused tests**

Expected: all evidence and book-project tests pass.

### Task 4: Update contracts and guidance

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/session_audit.py`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/29-isolated-writer-capsule.md`
- Modify: `tests/test_novel_project.py`
- Modify: `tests/test_session_audit.py`

**Step 1: Write failing contract/template tests**

Require `instructions.md`, `formal-writer/v1`, prompt provenance, one-chapter
default guidance, and byte-identical Skill mirrors under the existing size
budget.

**Step 2: Run the tests to verify RED**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_novel_project.py tests/test_session_audit.py -q
```

Expected: FAIL until templates and contracts describe the new prompt input.

**Step 3: Update generated and canonical guidance**

Document that the user may issue a short one-chapter request, while the
workflow compiles the complete prompt. Keep machine enforcement explicitly
separate from prompt instruction.

**Step 4: Run focused tests**

Expected: all template and contract tests pass.

### Task 5: Verify, integrate, and push

**Files:**
- Verify all modified files.

**Step 1: Run compilation and full tests**

```bash
PYTHONPATH=. python -m compileall -q app tests
PYTHONPATH=. python -m pytest tests/ -q
git diff --check
```

Expected: zero errors and all tests pass.

**Step 2: Verify prompt and repository invariants**

- Skill files are byte-identical and below 9,000 characters.
- Prompt is below 1,200 characters and vendor-neutral.
- Capsule inventory contains only declared files.
- Working tree contains no generated books or `.local-guardian` assets.

**Step 3: Commit and merge**

Commit on `codex/formal-writer-prompt-v1`, merge into `main`, rerun the full
suite on merged `main`, then push `main` to Gitea.
