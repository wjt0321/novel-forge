# v3.9 External Harness Guardrails Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move cost, provenance, blind-review isolation, and high-confidence serial prose failures outside the writing Agent's self-assessment so a runaway harness cannot mark its own output ready.

**Architecture:** Define a vendor-neutral, machine-readable Harness Contract and canonical cumulative runtime snapshot. Treat product-specific session-log parsers as compatibility importers only. Add a sanitized immutable per-book runtime audit record, bind formal readiness to a matching audit, verify blind-reader session isolation, and block machine-detectable literary damage while leaving literary judgment with reviewers.

**Tech Stack:** Python 3.12 standard library, existing Markdown evidence layer, filesystem-only books workflow, pytest.

---

## Task 1: Session audit parser and budget decision

**Files:**
- Create: `app/novel_forge/session_audit.py`
- Create: `tests/test_session_audit.py`
- Modify: `app/novel_forge/planning_spec.py`

1. Add failing tests for the vendor-neutral contract and canonical runtime snapshot.
2. Add compatibility tests for representative nested-message and item-stream exports.
3. Assert exact token, cache, request, context-reset, tool-failure, model, harness, and reasoning-effort extraction.
4. Assert aggregate per-chapter budget findings and `continue_allowed=false`.
5. Implement all parsers without returning message, reasoning, prompt, tool-result, or prose bodies.

## Task 2: Provenance comparison and sanitized audit records

**Files:**
- Modify: `app/novel_forge/session_audit.py`
- Modify: `app/novel_forge/book_evidence.py`
- Modify: `app/novel_forge/skill_adapter.py`
- Modify: `tests/test_session_audit.py`
- Modify: `tests/test_skill_adapter.py`

1. Add failing tests for provider/model/harness/reasoning/tool-failure mismatches.
2. Add a read-only `session-audit` adapter operation.
3. Add a confirmed `record-session-audit` operation that stores only normalized metadata under `evidence/runtime-audits/`.
4. Make records immutable and content-addressed by source-log SHA-256.
5. Ensure adapter output contains no prompts, prose, reasoning, or raw tool results.

## Task 3: Blind-review session isolation

**Files:**
- Modify: `app/novel_forge/book_project.py`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `tests/test_book_project.py`

1. Add `review_session_id` to critical review metadata.
2. Permit `simulated_blind` only for a non-passing diagnostic review.
3. Require a model/agent blind-reader pass to use `prose_only`, a known writer `run_id`, and a different review session.
4. Preserve provider/model origin reporting separately from session isolation.
5. Make benchmark eligibility require both independent origin and verified isolation.

## Task 4: Literary structural blockers

**Files:**
- Modify: `app/novel_forge/voice_signature.py`
- Modify: `app/novel_forge/book_project.py`
- Modify: `tests/test_voice_signature.py`
- Modify: `tests/test_book_project.py`

1. Add failing tests for malformed nested dialogue labels.
2. Add failing tests for extreme cross-chapter exact-sentence coverage.
3. Add failing tests for long exact paragraph reuse.
4. Keep ordinary motifs and low-volume repetition advisory.
5. Feed only high-confidence structural findings into `surface_checked`, `ready_eligible`, ready revalidation, and project integrity.

## Task 5: Templates, Skill, and migration

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`
- Create: `docs/24-external-harness-guardrails.md`
- Modify: `tests/test_novel_project.py`

1. Bump generated projects to v3.9.
2. Document the external guardian call order and hard-stop response.
3. Add runtime-audit and review-session fields to generated templates.
4. Keep both Skill files byte-identical.
5. Update `sync-tools` migration recognition from v3.7/v3.8 to v3.9.

## Task 6: Real-sample evidence, cleanup, and release

**Files:**
- Create: `docs/examples/agent-demo-v39-deepseek-minimax-harness-audit.md`
- Create: `docs/examples/agent-demo-v39-deepseek-minimax-harness-audit.json`

1. Run the auditor against both retained JSON exports.
2. Run literary gates against both retained books projects.
3. Preserve only aggregate metrics, defect counts, thresholds, and conclusions.
4. Run focused tests, then the full suite.
5. Delete the two local books projects and two root JSON exports only after verification.
6. Confirm no sample prose/session bodies were committed.
7. Commit and push `codex/v39-external-guardrails`.
