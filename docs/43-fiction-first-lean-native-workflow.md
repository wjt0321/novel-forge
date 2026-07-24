# 43. Fiction-First Lean Native Workflow

Date: 2026-07-24

## Problem

The v5.2 native Relay protected session isolation and immutable evidence, but
its daily completion contract made the host Lead assemble operation handles,
result transports, runtime snapshots, model provenance, token counters, and
other audit fields. In production tests, valid 5000+ CJK drafts were discarded
or rewritten because a technical envelope used the wrong field name or lacked
telemetry the host could not expose.

That reversed the product priority. The novel body is the product; planning,
evidence, runtime records, state, and Git are supporting records.

## Decision

Novel Forge v5.4 uses `lean_native` as the default interactive workflow.
Existing strict audit behavior remains available through `--strict-audit`.
This is one state machine with two assurance levels, not a parallel workflow.

### Lean role contract

The host performs only four duties:

1. Create or reuse the independent session requested by `next-action`.
2. Give the role only the action's sealed Capsule or review input.
3. Wait for the host's official terminal state.
4. Run `complete-role <slug>`.

The first Lean Writer action is `stage=draft`: Writer writes only
`books/<slug>/.novel-forge/diff/chNN/writer/draft/正文.md`. Python creates the
minimum continuity and scene materials in its control plane, so Writer may
think through planning without returning a separate planning result. Blind
Reader and Chapter Editor read the staged body and write their small JSON
payloads to the same chapter's diff workspace. The Lead does not construct
Generation, Runtime, Guardian, hash, token, request-count, state, Git fields,
or a session-ID envelope.

### Python-owned records

The deterministic control plane now owns:

- content and planning hashes;
- freezing the accepted first draft as `初稿.md` and rendering `修订.diff`;
- promotion from the staged body to `chapters/` after both reviews pass;
- Generation creation and stale transitions after promotion;
- Review binding and stale transitions;
- Guardian inventory verification and immutable receipts;
- truthful null runtime telemetry when the host exposes no counters;
- chapter state and ready verification;
- per-book Git draft and ready checkpoints.

Unknown telemetry remains null. It is recorded as `unassessed`, not converted
to invented values and not used to discard otherwise valid prose.

### Integrity scope

Daily Lean actions snapshot and restore only the current book. A concurrent
change elsewhere in the repository no longer invalidates a valid role result.
Writer and reviewer outputs live in the current book's ignored
`.novel-forge/diff/chNN/` workspace. The action names the exact writable file;
unexpected changes elsewhere inside the current book remain a technical
failure.

Strict audit retains the repository-wide snapshot and the complete native
terminal envelope for forensic or benchmark runs.

## Generic host boundary

Novel Forge does not generate `.claude/agents` files for new books and does not
ask a creative task to register host-specific Agent types. The Skill uses
generic independent Session, Teams, Task Agent, or Role capabilities supplied
by the host. Existing generated files in old books are not deleted
automatically because they may contain user edits.

## Literary workflow

The daily production loop is deliberately small:

`Lead dispatches Writer -> Writer stages draft -> Blind Reader + Chapter Editor review -> MUST returns to the same staged body -> both reviewers re-review -> Python promotes -> ready`

Em dashes, ellipses, and the `not X but Y` construction remain blocking because
high-frequency model output can saturate a chapter with them. The Writer prompt
forbids all three up front and requires a whole-text search before submission.
If any remain, Python returns every located occurrence in one consolidated
`stage=patch` action against the same file; this creates no Generation, Git
checkpoint, or technical retry. Lean allows up to three same-file cleanup
rounds instead of dropping into a state with no next action. After surface
checks, Python freezes the first draft but still does not write `chapters/`.
Both reviewers read the staged body. When reviews produce
MUST findings, the control plane issues Writer `stage=patch` against that same
file and prefers reusing the current host Writer session. Both reviewers then
read the complete revised body again. Only a double pass causes Python to
promote the body, record the technical evidence, advance `ready`, and
checkpoint the per-book Git history.

Lean review transport is deliberately compact. Chapter Editor returns only a
generic `pass` or `needs_revision`, one complete MUST list, a short summary,
and one prose quote. Python accepts `pass` as the internal editor-ready verdict
and derives supporting record fields itself. Analysis matrices and hard-anchor
coverage tables remain strict-audit evidence, not daily creative work.
For Lean result files, Python makes one deterministic repair attempt for the
common case where a prose quotation was left unescaped inside JSON. Legacy
plain-text hard-anchor coverage is ignored because it is not a Lean gate.
Neither condition may turn an otherwise valid literary judgment into a new
review session or a prose rewrite.

Writer planning remains available inside the Writer's writing process because
research and story architecture can materially improve prose. It is a
supporting activity, not a fourth role, not a separate action, and not a
reason to reject a completed chapter.

## Compatibility

- `NativeWorkflowRelay(strict_audit=True)` preserves the v5.2 completion
  envelope for existing integrations.
- CLI `start` defaults to Lean; add global `--strict-audit` before the
  subcommand to request the old assurance level.
- Lean review result files remain inside the per-book diff workspace. Legacy
  full JSON completion remains accepted through
  `complete-role --from-file`; Lean itself does not require it for Writer
  completion.
- No existing book, sample, framework, or user data is deleted.
