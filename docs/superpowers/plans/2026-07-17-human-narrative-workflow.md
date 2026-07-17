# Human Narrative Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn Novel Forge's human-narrative recommendations into an auditable workflow for controlled creative variation, author preference learning, blind comparison, long-arc residue tracking, reviewer provenance, and progressive gates.

**Architecture:** Keep prose, evaluation records, preferences, branch decisions, and arc audits as Markdown authority inside each `books/<slug>/` project. Add a small filesystem-only evidence layer that validates marked JSON metadata and stores immutable evidence records without judging literary value. Extend the existing books workflow through `planning_spec.py`, `project_templates.py`, `book_gates.py`, `book_project.py`, and JSON-only adapter operations; no new dependency, root database table, real LLM call, or automatic approval.

**Tech Stack:** Python 3.12 standard library, Markdown plus fenced JSON metadata, existing argparse skill adapter, pytest.

---

### Task 1: Define The Evaluation Constitution And Project Assets

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/planning_spec.py`
- Test: `tests/test_novel_project.py`

1. Write failing tests that a new project contains:
   - `evaluation/constitution.md`
   - `evaluation/case-template.md`
   - `evaluation/experiment-template.md`
   - `evaluation/rule-registry.md`
   - evidence directories for preferences, branches, evaluations, generations, and arc audits.
2. Assert the constitution separates factual correctness, causal integrity, limited character perception, expressive asymmetry, and author preference.
3. Assert it explicitly rejects deliberate typos/random defects, model scores as approval, silent branch blending, and imitation of living authors.
4. Add template factories and required directories.
5. Run `PYTHONPATH=. python -m pytest tests/test_novel_project.py -q`.

### Task 2: Close State And Evidence Integrity Gaps

**Files:**
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/book_project.py`
- Modify: `app/novel_forge/project_templates.py`
- Test: `tests/test_book_project.py`

1. Write failing tests proving the current workflow incorrectly permits non-adjacent forward state jumps and stale reviews after prose changes.
2. Define an explicit legal transition graph in `planning_spec.py`; do not infer transition permission from tuple ordering.
3. Bind every review to `chapter_sha256`, required planning hashes, `generation_id`, and the persisted chapter `draft_mode`.
4. Mark a review stale when the chapter or bound planning material changes; stale verdicts cannot satisfy `ready`.
5. Make `advance-state --to ready` rerun the formal gates instead of trusting old evidence rows.
6. Return `author_approval: false` and `publication_eligibility: false` from ready/status results.
7. Run `PYTHONPATH=. python -m pytest tests/test_book_project.py -q`.

### Task 3: Add Markdown-Authoritative Creative Evidence

**Files:**
- Create: `app/novel_forge/book_evidence.py`
- Create: `tests/test_book_evidence.py`

1. Write failing parser tests for the marker `<!-- novel-forge-evidence:v1 -->` and kinds:
   - `preference`
   - `branch`
   - `evaluation`
   - `generation`
   - `arc_audit`
   - `rule_decision`
2. Require common fields: schema version, ASCII id, kind, created_at, source paths, summary, and explicit human/agent authority.
3. Add kind-specific validation:
   - preference records selected and rejected candidates plus reasons;
   - branch records select exactly one winner and preserve discarded trade-offs;
   - evaluations use blinded candidate labels and concrete reconstruction questions;
   - generation records identify writer type/provider/model and content hash;
   - arc audits cover an explicit chapter range and record open MUST items;
   - rule decisions carry hypothesis, evidence scope, lifecycle, and retirement reason when retired.
4. Reject path traversal, missing sources, duplicate IDs, overwrite attempts, prose bodies in adapter return data, and branch records that silently merge every candidate.
5. Implement atomic copy into the canonical evidence directory selected by kind.
6. Implement `evidence_status()` returning IDs, counts, due arc audit, and provenance warnings without returning Markdown bodies.
7. Run `PYTHONPATH=. python -m pytest tests/test_book_evidence.py -q`.

### Task 4: Expose Evidence Through The Restricted Adapter

**Files:**
- Modify: `app/novel_forge/skill_adapter.py`
- Test: `tests/test_book_evidence.py`

1. Write failing adapter tests for:
   - `evidence-status <slug> [chapter]`
   - `record-evidence <slug> --file <absolute-markdown>`
2. Dispatch `record-evidence` by the validated `kind` in the Markdown file and require exact `--confirm record-evidence`.
3. Keep output JSON-only and return paths, IDs, counts, verdicts, and warnings only.
4. Run `PYTHONPATH=. python -m pytest tests/test_book_evidence.py -q`.

### Task 5: Add Decision Questions And Scene Residue

**Files:**
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/book_gates.py`
- Test: `tests/test_novel_project.py`
- Test: `tests/test_book_project.py`

1. Write failing tests that the scene package requires `1c. 决策问题` and `7. 场景余波` in formal mode.
2. Require decision evidence for incompatible wants, refusal, misreading, unsayable speech, and accepted cost.
3. Require residue evidence for body, object, relationship, knowledge/false belief, and unpaid debt/promise.
4. Keep these checks structural only; never score prose or infer the answers from the chapter.
5. Teach the causal editor and consistency guard to verify the planned decision and post-scene residue.
6. Run the focused project and gate tests.

### Task 6: Introduce Exploration And Formal Gate Modes

**Files:**
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/book_gates.py`
- Modify: `app/novel_forge/book_project.py`
- Modify: `app/novel_forge/skill_adapter.py`
- Test: `tests/test_book_project.py`

1. Write failing tests for `exploration` and `formal` modes.
2. Add persistent `draft_mode` to chapter state and a confirmed `set-draft-mode` adapter operation.
3. Make persisted chapter state the only mode authority. `run-gates --mode` may assert the expected mode but must not override it.
4. Make exploration mode run surface safety checks and minimal renderability checks while skipping the 5000-CJK, complete planning-material, and full review requirements.
5. Make formal mode enforce the 5000-CJK minimum and all narrative materials.
6. Prevent an exploration chapter from entering `ready`; switching to formal invalidates exploration gate/review evidence.
7. Return `ready_eligible` and the applied mode in JSON.
8. Run `PYTHONPATH=. python -m pytest tests/test_book_project.py -q`.

### Task 7: Record Reviewer Provenance And Independence

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/book_project.py`
- Test: `tests/test_book_project.py`

1. Write failing tests for reviewer metadata: reviewer type, reviewer id, provider, model, context scope, and independence note.
2. Require provenance for `blind-reader` and `chapter-editor` before formal `ready`.
3. Read generation evidence for the chapter and report same-provider/model self-review as an explicit warning.
4. If a key review uses the same provider/model as the writer, require a non-empty independence note; do not claim the review is independent merely because the role name differs.
5. Never turn reviewer diversity into a literary score.
6. Run focused tests.

### Task 8: Add Controlled Branching And Pairwise Blind Evaluation Protocol

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/book_project.py`
- Test: `tests/test_book_evidence.py`
- Test: `tests/test_novel_project.py`

1. Add branch and blind-evaluation templates that use anonymous candidate labels.
2. Store candidates under `evaluation/experiments/<experiment-id>/candidates/<label>.md`; these files are never formal chapter truth.
3. Require concrete reader reconstruction: desire, concealment, relationship change, memorable images, and next-chapter question.
4. Require a single winning branch; a newly synthesized candidate is allowed only as its own candidate with stated trade-offs, never as an unrecorded blend.
5. Add preference records that link the selected branch/evaluation to accepted and rejected qualities.
6. Expose unresolved branch experiments and recent preference evidence in `project-status`.
7. Run focused tests.

### Task 9: Add Five-Chapter And Arc-Level Audits

**Files:**
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/book_project.py`
- Test: `tests/test_book_project.py`

1. Define a default five-chapter checkpoint interval in the shared spec.
2. Add an arc-audit template covering promises, character arc, relationship debt, motif recurrence, pacing, contradictions, and abandoned threads. Records distinguish `scope=checkpoint|volume`, explicit chapter ranges, and optional volume IDs.
3. Make `evidence-status` and `project-status` report when an audit is due.
4. Require a recorded checkpoint audit with no open MUST before chapters 5, 10, 15, and so on may enter formal `ready`.
5. Keep the audit verdict limited to `continue` or `replan`; neither means author approval or publication eligibility.
6. Run focused tests.

### Task 10: Teach Agents The Human-Narrative Protocol

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`
- Test: `tests/test_novel_project.py`
- Test: `tests/test_book_evidence.py`

1. Run baseline pressure scenarios without the new instructions and record failures in test fixtures:
   - deliberate errors used as “humanization”;
   - all branch candidates blended together;
   - model score presented as author approval;
   - aesthetic preference promoted into factual canon;
   - short exploration promoted as a formal chapter;
   - same model self-review described as independent.
2. Update context collector, orchestrator, causal editor, blind reader, chapter editor, and Skill instructions to close those loopholes.
3. Add the four-layer rule: factual order, causal order, experiential limitation, author taste.
4. Add the sequence: decision questions, optional branch experiment, generation provenance, formal gates, blind evaluation, preference record, residue extraction, periodic arc audit.
5. Keep both Skill copies byte-identical and bump the workflow version.
6. Re-run the same pressure scenarios and repository tests.

### Task 11: Documentation, Migration, And Verification

**Files:**
- Create: `docs/18-human-narrative-evaluation-workflow.md`
- Modify: `docs/15-books-workflow-skill-quality.md`
- Modify: `AGENTS.md`
- Modify: `app/novel_forge/book_project.py`
- Test: `tests/test_book_project.py`

1. Document the evidence schema, gate modes, provenance semantics, checkpoint rules, and non-certification boundary.
2. Extend `sync-tools` to create missing evaluation/evidence assets and refresh managed templates without overwriting hand-maintained evidence or the evaluation constitution.
3. Run focused tests for migration of an existing book.
4. Run `PYTHONPATH=. python -m pytest tests/ -q`.
5. Run `git diff --check`.
6. Inspect `git status --short`, the complete diff, and generated project samples for accidental prose, `books/`, `data/`, SQLite, or cache changes.
