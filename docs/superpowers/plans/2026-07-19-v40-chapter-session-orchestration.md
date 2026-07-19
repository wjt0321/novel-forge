# v4.0 Chapter Session Orchestration Implementation Plan

**Goal:** Make one native writer session per chapter an enforceable,
vendor-neutral production unit while preserving long-form continuity through
bounded, auditable handoff packets.

**Architecture:** Add a filesystem-only chapter sequence state machine under
`books/<slug>/planning/chapter-sequences/`. Novel Forge does not call any model
vendor or create a native session itself. Instead, it issues a machine-readable
launch directive, requires the external Harness to claim that chapter with the
real native session ID, and advances only after the chapter passes the existing
full `ready` gate. Each next chapter receives a newly built handoff packet from
Canon, active promises, the previous chapter tail, the Voice Bible exemplar,
and the current scene package. Old tool output, review bodies, and conversational
history are excluded.

**Tech Stack:** Python 3.12, standard library JSON/filesystem APIs, pytest,
existing `book_project`, `book_memory`, `book_evidence`, `session_audit`, and
`skill_adapter` modules.

---

## Task 1: Preserve the Five-Chapter Experiment

**Files:**
- Create: `docs/examples/agent-demo-v40-deepseek-opencode-claude-session-audit.md`
- Create: `docs/examples/agent-demo-v40-deepseek-opencode-claude-session-audit.json`

1. Record only sanitized runtime totals, chapter hashes, gate outcomes, and
   cross-project contamination evidence.
2. State that named products are samples, not special cases in the protocol.
3. Record the source projects as disposable after the sample is committed.

## Task 2: Define the Chapter Sequence Contract

**Files:**
- Modify: `app/novel_forge/planning_spec.py`
- Modify: `app/novel_forge/session_audit.py`
- Test: `tests/test_chapter_sequence.py`
- Test: `tests/test_session_audit.py`

1. Add a maximum automatic sequence length of four chapters.
2. Define bounded handoff limits for memory, prior tail, Voice exemplar, and
   scene package.
3. Extend the vendor-neutral Harness Contract with sequence lifecycle
   operations and the rule that a new native session is required for every
   chapter.
4. Keep `scope.chapter_count == 1` and the 2,000,000 cached-input token ceiling.

## Task 3: Implement Persistent Sequence State

**Files:**
- Create: `app/novel_forge/chapter_sequence.py`
- Test: `tests/test_chapter_sequence.py`

1. Add `begin_chapter_sequence`, `claim_chapter_session`,
   `advance_chapter_sequence`, and `chapter_sequence_status`.
2. Persist atomic JSON records under
   `planning/chapter-sequences/<sequence-id>.json`.
3. Reject zero-length, non-contiguous, and five-or-more chapter sequences.
4. Reject native writer session reuse across chapters and sequences.
5. Require generation `run_id` to equal the claimed writer session.
6. Require the previous chapter to be fully and currently `ready` before
   issuing the next launch directive.

## Task 4: Build Bounded Chapter Handoffs

**Files:**
- Modify: `app/novel_forge/book_memory.py`
- Create: `app/novel_forge/chapter_sequence.py`
- Test: `tests/test_chapter_sequence.py`

1. Rebuild the disposable memory index when necessary.
2. Build the existing chapter memory packet.
3. Create `memory/context-cache/chXX-handoff.md` with:
   - current chapter scope and stopping rule;
   - relevant bounded memory context;
   - previous chapter SHA-256 and bounded tail;
   - bounded Voice Bible exemplar;
   - bounded current scene package.
4. Exclude prompts, tool logs, old review bodies, and previous session history.
5. Return handoff path, SHA-256, and size without returning its body through the
   adapter.

## Task 5: Expose Vendor-Neutral Adapter Operations

**Files:**
- Modify: `app/novel_forge/skill_adapter.py`
- Test: `tests/test_chapter_sequence.py`
- Test: `tests/test_skill_adapter.py`

1. Add confirmed `begin-chapter-sequence`.
2. Add confirmed `claim-chapter-session`.
3. Add confirmed `advance-chapter-sequence`.
4. Add read-only `chapter-sequence-status`.
5. Return a launch directive that an external Harness can use to create a new
   native session automatically after the prior chapter becomes `ready`.

## Task 6: Update Generated Projects and Agent Guidance

**Files:**
- Modify: `app/novel_forge/project_templates.py`
- Modify: `.agents/skills/novel-forge/SKILL.md`
- Modify: `.claude/skills/novel-forge/SKILL.md`
- Modify: `AGENTS.md`
- Create: `docs/25-chapter-session-orchestration.md`
- Test: `tests/test_novel_project.py`
- Test: `tests/test_book_project.py`

1. Bump generated workflow guidance to v4.0.
2. Teach the orchestrator to use chapter sequences and end each writer session
   after the chapter reaches `ready`.
3. Explain one-chapter manual requests and one-to-four chapter automatic
   sequences.
4. Reject five-chapter automatic batches and instruct the Harness to split
   longer work into separately approved sequences.
5. Add `planning/chapter-sequences/` to generated project structure and
   `sync-tools`.

## Task 7: Verify and Clean Disposable Projects

**Files:**
- Delete after evidence capture:
  `books/deepseek-v39-five-chapter-20260719-opencode/`
- Delete after evidence capture:
  `books/deepseek-v39-five-chapter-20260719-claude-code/`

1. Run focused sequence, adapter, template, and session audit tests.
2. Run the full test suite with `PYTHONPATH=.`.
3. Verify the two Skill copies are byte-identical.
4. Resolve and verify demo paths are inside `D:/s-black-novel/books` before
   recursive deletion.
5. Commit on `main` and push `main` to `gitea`.
