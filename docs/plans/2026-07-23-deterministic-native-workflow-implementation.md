# Deterministic Native Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finalize the generic three-role Novel Forge workflow with compact literary rules, host-bound terminal results, deterministic Python control, repository pollution detection, complete demo cleanup, and verified Git delivery.

**Architecture:** Reuse `NovelWorkflowOrchestrator`, `SessionBackend`, Guardian, chapter sequence, evidence, state gates, and per-book Git. Strengthen the existing role completion envelope and controller ownership rather than adding a parallel orchestration system. Keep ACP forensic-only and keep provider/model choices outside the core protocol.

**Tech Stack:** Python 3.12, Pydantic v2, standard-library JSON/hash/filesystem APIs, pytest, Markdown Skill/templates.

---

### Task 1: Preserve the final stress-test evidence

**Files:**
- Create: `docs/examples/agent-demo-v56-final-multi-host-stress-audit.md`
- Create: `docs/examples/agent-demo-v56-final-multi-host-stress-audit.json`
- Modify: `docs/35-literary-rule-manual.md`
- Modify: `app/novel_forge/planning_spec.py`
- Test: `tests/test_novel_project.py`
- Test: `tests/test_review_prompt.py`
- Test: `tests/test_writer_prompt.py`

1. Add failing tests for `literary-micro-rules/v4`, bounded prompt size, and the new concise positive/negative rules.
2. Run the focused tests and confirm the old v3 rules fail them.
3. Write the deidentified seven-sample aggregate with literary, workflow, and cost conclusions.
4. Upgrade the canonical short rules and long manual without injecting demo prose into daily prompts.
5. Run the focused tests.

### Task 2: Bind role completion to the real host terminal

**Files:**
- Modify: `app/novel_forge/role_completion.py`
- Modify: `app/novel_forge/workflow.py`
- Modify: `app/novel_forge/artifact_integrity.py`
- Test: `tests/test_role_completion.py`
- Test: `tests/test_workflow.py`
- Test: `tests/test_book_project.py`
- Test: `tests/test_guardian.py`

1. Add failing tests proving a completed result without matching session ID,
   session instance, typed handle, role, or transport is rejected.
2. Add failing tests proving completion receipts preserve the exact host
   operation binding.
3. Remove the directly importable workflow-authority issuer used by the failed
   experiment and move issuance behind the active orchestrator.
4. Extend role terminal normalization and completion receipts.
5. Run the focused tests.

### Task 3: Enforce zero project writes by creative roles

**Files:**
- Create: `app/novel_forge/workspace_integrity.py`
- Modify: `app/novel_forge/workflow.py`
- Test: `tests/test_workflow.py`

1. Add failing tests where planning, Writer, Blind Reader, and Chapter Editor
   create an extra repository-local file.
2. Implement stable repository snapshots with cache/VCS exclusions only.
3. Wrap every backend creative call and reject any changed repository path as
   `unexpected_project_artifact`.
4. Verify the normal external capsule/runtime path remains allowed.
5. Run the focused tests.

### Task 4: Simplify the generic Skill control loop

**Files:**
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`
- Modify: `CLAUDE.md`
- Modify: `app/novel_forge/project_templates.py`
- Modify: `app/novel_forge/session_audit.py`
- Create: `docs/39-deterministic-native-control-and-workspace-hygiene.md`
- Test: `tests/test_novel_project.py`
- Test: `tests/test_session_audit.py`

1. Add failing documentation/template tests for v5.0, the five-step Python
   control loop, ACP-forensics-only, and zero-write role policy.
2. Update the canonical Skill first, then sync the Claude mirror byte-for-byte.
3. Update root and generated project instructions without naming a required
   provider, model, IDE, or CLI product.
4. Keep generated instructions within their existing size bounds.
5. Run the focused tests.

### Task 5: Clean all final demos and leaked assets

**Files:**
- Delete local ignored demo assets only after sample preservation.

1. Resolve and verify every target path under the explicitly allowed demo
   roots.
2. Remove the seven `books/<slug>/` directories.
3. Remove matching `.local-book-git/<slug>.git` and
   `.local-guardian/<slug>/`.
4. Remove matching legacy demo workspaces and matching external capsule files.
5. Remove repository-root scratch files and verify no `.tmp-capsule`,
   `.uploads`, or book-internal `.local-guardian` remains.
6. Do not delete application history, user configuration, framework files, or
   deidentified sample documents.

### Task 6: Verify, commit, and push

**Files:**
- Review all changed files.

1. Run focused tests for rules, role completion, workflow, templates, Guardian,
   book project, and session audit.
2. Run `PYTHONPATH=. python -m pytest tests/ -q`.
3. Run `git diff --check`, inspect `git status`, and review the final diff.
4. Verify demo and extra-asset cleanup with explicit filesystem checks.
5. Commit on `main` with a focused message.
6. Push to `gitea/main`; push `github/main` as a best-effort secondary remote
   only if the connection succeeds without delaying the Gitea delivery.
