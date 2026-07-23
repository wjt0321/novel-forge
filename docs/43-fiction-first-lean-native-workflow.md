# 43. Fiction-First Lean Native Workflow

Date: 2026-07-23

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

Novel Forge v5.3 uses `lean_native` as the default interactive workflow.
Existing strict audit behavior remains available through `--strict-audit`.
This is one state machine with two assurance levels, not a parallel workflow.

### Lean role contract

The host performs only four duties:

1. Create or reuse the independent session requested by `next-action`.
2. Give the role only the action's sealed Capsule.
3. Wait for the host's official terminal state.
4. Run `complete-role <slug> --session-id <real-session-id>`.

Planning and review roles write their small JSON payload to the external
`result_file` named by the action. Writer writes only `draft/正文.md`.
The Lead does not construct Generation, Runtime, Guardian, hash, token,
request-count, state, or Git fields.

### Python-owned records

The deterministic control plane now owns:

- content and planning hashes;
- Generation creation and stale transitions;
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
Writer and reviewer outputs still live outside the repository, and unexpected
changes inside the current book remain a technical failure.

Strict audit retains the repository-wide snapshot and the complete native
terminal envelope for forensic or benchmark runs.

## Generic host boundary

Novel Forge does not generate `.claude/agents` files for new books and does not
ask a creative task to register host-specific Agent types. The Skill uses
generic independent Session, Teams, Task Agent, or Role capabilities supplied
by the host. Existing generated files in old books are not deleted
automatically because they may contain user edits.

## Literary workflow

The three creative roles are unchanged:

`Writer -> Blind Reader -> Chapter Editor -> optional Patch Writer -> full re-review`

Writer planning remains available in the Writer's own session because research
and story architecture can materially improve prose. It is a supporting
artifact, not a fourth role and not a reason to reject a completed chapter.

## Compatibility

- `NativeWorkflowRelay(strict_audit=True)` preserves the v5.2 completion
  envelope for existing integrations.
- CLI `start` defaults to Lean; add global `--strict-audit` before the
  subcommand to request the old assurance level.
- Legacy full JSON completion remains accepted through
  `complete-role --from-file`.
- No existing book, sample, framework, or user data is deleted.
