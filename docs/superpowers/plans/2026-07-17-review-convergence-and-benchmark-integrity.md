# Review Convergence And Benchmark Integrity Plan

> **For Novel Forge maintainers:** Execute this plan test-first. Preserve
> Markdown as the authority, keep all new controls auditable, and do not turn
> workflow signals into claims of literary value or author approval.

**Goal:** Preserve the second three-agent demo as reusable experiment data,
remove the disposable book projects, and make the `books/` workflow detect
planning contradictions, provenance weakness, state drift, excessive rewrite
cycles, and memory over-recording before they consume another long agent run.

**Architecture:** Extend the existing single-source constants in
`planning_spec.py`; keep gates pure in `book_gates.py`; keep immutable run
metadata in generation evidence; calculate chapter workflow integrity in
`book_project.py`; keep memory salience in Markdown metadata and expose volume
warnings without mutating Canon. Project templates, generated Agent prompts,
the canonical Skill, and tests must stay synchronized.

**Tech Stack:** Python 3.12, Markdown/JSON evidence, `sqlite3`, `pytest`.

---

## Task 1: Preserve And Remove The Demo Projects

**Files:**
- Create: `docs/examples/agent-demo-v34-model-agent-comparison.md`
- Create: `docs/examples/agent-demo-v34-model-agent-comparison.json`

1. Record exact prose SHA-256, CJK count, voice signature, workflow state,
   provenance confidence, observed elapsed time, pause behavior, review rounds,
   strengths, defects, and comparison confounds.
2. State that the three stories are workflow-diagnostic samples, not a clean
   model leaderboard.
3. Resolve and verify the three requested directories are exactly below
   `D:/s-black-novel/books`.
4. Delete `mingyun`, `shentong-90`, and `夜班怪谈` with native PowerShell.
5. Verify the three paths no longer exist while the experiment files remain.

## Task 2: Add Planning Falsification Gate

**Files:**
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/book_gates.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_book_gates.py`
- Modify: `tests/test_book_project.py`

1. Add a required `1e. 规划反证与常识检查` scene-package section.
2. Require explicit checks for time/calendar arithmetic, physical action
   mechanics, character knowledge source, irreversible-choice retractability,
   and the intended scene stop.
3. Keep this deterministic: the gate checks that each field has an auditable
   answer; it does not certify the answer as true.
4. Update all scene-package fixtures and generated templates.

## Task 3: Add Review Anchoring And Confidence Signals

**Files:**
- Modify: `app/novel_forge/book_project.py`
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_book_project.py`
- Modify: `tests/test_novel_project.py`

1. Normalize simple Markdown emphasis around parsed review metadata.
2. Require causal-editor and chapter-editor prompts to reconstruct the prose
   before comparing it with planning intent.
3. Calculate `review_confidence` as `single_origin`, `mixed_origin`, or
   `independent`.
4. Calculate `benchmark_eligible` separately from `ready`; benchmark
   eligibility requires current, passing, non-generation-origin blind-reader
   and chapter-editor reviews.
5. Preserve offline operation: same-origin reviews remain visible and may
   satisfy the production `ready` chain, but never count as independent.

## Task 4: Detect State Drift And Rewrite Budget Exhaustion

**Files:**
- Modify: `app/novel_forge/book_project.py`
- Modify: `app/novel_forge/book_evidence.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_book_project.py`
- Modify: `tests/test_book_evidence.py`

1. Discover chapters from the union of chapter files and chapter-state files.
2. Report missing state files, prose present while still `planned`, unrecorded
   or stale generation bindings, stale/invalid review verdicts, and placeholder
   state evidence.
3. Add optional immutable generation metrics:
   `elapsed_seconds`, input/output/total tokens, `metrics_source`,
   `pause_count`, `interaction_count`, `review_round`,
   `parent_generation_id`, `generation_stage`, and provenance confidence.
4. Report generation count and rewrite-cycle status per chapter.
5. Adopt a two-cycle budget: initial generation plus one consolidated patch and
   one final full reread. A third generation/rewrite cycle sets
   `human_decision_required`; it does not delete or reject historical evidence.
6. Update orchestrator instructions so formal mode continues through the
   predeclared review batch without asking “whether to review”; it pauses only
   at explicit human-decision boundaries.

## Task 5: Add Memory Salience And Volume Warnings

**Files:**
- Modify: `app/novel_forge/book_memory.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_book_memory.py`
- Modify: `tests/test_novel_project.py`

1. Add optional `salience` (`high`, `medium`, `low`) with a backward-compatible
   default of `medium`.
2. Store salience in the disposable index and prioritize higher-salience rows
   in chapter context packets.
3. Report per-chapter candidate/canonical counts and an advisory warning above
   the configured threshold.
4. Keep promotion human-controlled; volume warnings must not auto-delete or
   auto-merge memory records.

## Task 6: Close Lint And Documentation Drift

**Files:**
- Modify: `app/novel_forge/lint.py`
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_lint.py`
- Create: `docs/20-review-convergence-and-benchmark-integrity.md`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`

1. Move explanation-lead patterns to the planning specification and include
   `他/她意识到` and `他/她突然意识到`.
2. Keep `explanation-tic` advisory to preserve the documented legacy approval
   boundary; texture review remains responsible for contextual severity.
3. Document the new benchmark, convergence, preflight, and memory rules.
4. Keep the two Skill files byte-identical.

## Task 7: Verify End To End

1. Run focused tests for lint, gates, evidence, project workflow, memory, and
   project templates.
2. Run `PYTHONPATH=. python -m pytest tests/ -q`.
3. Verify the Skill mirror with a byte comparison.
4. Inspect `git diff --check`, `git status --short`, and the remaining
   `books/` directory.
5. Report test results, deleted sample directories, preserved experiment paths,
   and any residual limitations.
