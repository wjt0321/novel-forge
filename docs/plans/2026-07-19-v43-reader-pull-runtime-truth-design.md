# v4.3 Reader Pull and Runtime Truth Design

## Goal

Preserve the literary signal exposed by the DeepSeek V4 Flash sample without
turning that sample into a writer-visible imitation recipe. At the same time,
prevent a formally complete file tree from reaching `ready` when the observed
session, generation, or mutation history contradicts the workflow contract.

## Sample Diagnosis

The Flash sample is the first current-harness sample that creates a credible
desire to keep reading. Its useful signal comes from social relationships,
subtext, restrained emotional offers, and choices that expose character. It
also contains copy defects, repeated language, invalid reviews, unrecorded
generations, and a pause asking whether review should begin.

The Pro sample is more mechanically explicit. It reaches `ready` for all three
chapters, but all generations reuse one `run_id`, one runtime audit claims three
generation records for a one-chapter scope, and each generation reports eleven
draft mutations against a limit of three. The old workflow reports those facts
as warnings instead of invalidating `ready`.

## Design Principles

1. Do not add more prose-production checklists to the writer.
2. Keep the positive excerpts in audit documentation, outside generated books.
3. Ask an isolated blind reader whether they voluntarily want to continue.
4. Treat runtime identity and mutation budgets as facts, not literary advice.
5. Make automatic review launch a machine-readable harness obligation.
6. Keep all new gates vendor-neutral and based on normalized evidence.

## Reader Pull Gate

The blind-reader record gains three fields:

- `reader_desire: continue | conditional | stop`
- `emotional_residue`: the feeling, relationship pressure, or unresolved human
  consequence that remains after reading
- `next_chapter_pull`: the concrete question or relationship movement that
  makes the reader want the next chapter

A blind-reader `pass` requires:

- `human_likeness=convincing`;
- `reader_desire=continue`;
- substantive `emotional_residue`;
- substantive `next_chapter_pull`;
- all existing prose-only reconstruction and independent-session requirements.

These fields are reader evidence, not a model score, author approval, or a
writer-visible numeric target.

## Runtime Truth Gate

For a non-human formal generation:

1. its `run_id` must be unique to that chapter;
2. the matching runtime audit must bind exactly that generation record;
3. the audit must retain `scope_chapter_count=1`;
4. draft write/edit/review counts must be observed;
5. draft mutations and review calls must stay within the canonical limits.

Any violation blocks transition to `ready`. Existing ready chapters with such
violations appear as workflow-integrity blockers in `project-status`.

## Orchestration Contract

The vendor-neutral Harness Contract gains a `review_orchestration` object:

- review starts automatically after `surface_checked`;
- no user confirmation is required;
- blind review requires a fresh native session;
- inability to create that session returns a machine status instead of an
  open-ended question;
- optional “do you want review?” pauses are forbidden.

Novel Forge still does not create third-party sessions. It states the contract
that Claude Code, OpenCode, MiniMax Code, Reasonix, or another harness must
implement.

## Non-Goals

- No automatic judgment of literary value.
- No positive-sample prose copied into generated projects.
- No vendor-specific session parser or prompt branch.
- No increase in the default number of review roles.
- No automatic rewrite triggered by weak reader pull.

