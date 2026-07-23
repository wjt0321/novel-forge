# Deterministic Native Workflow Design

## Goal

Finalize Novel Forge as a vendor-neutral Skill workflow in which a visible CLI
host supplies real isolated creative sessions while Python owns every
deterministic transition, evidence write, retry decision, ready check, and
per-book Git checkpoint.

The production architecture remains:

`Writer -> Blind Reader -> Chapter Editor -> optional Patch Writer -> full re-review`

ACP remains a forensic tool only. It is not a production session launcher,
result channel, ready dependency, or hidden controller.

## Boundary

The creative Lead is a transport loop, not a control plane:

1. Python supplies the next bounded role directive.
2. The host creates a real isolated native session.
3. The host waits on the exact typed operation handle.
4. The host returns the official terminal envelope and bound role result.
5. Python validates and performs the next deterministic transition.

Planning files, chapter prose, reviews, evidence, state, Guardian records, and
Git checkpoints are never authored by the Lead. Writer output stays in an
external capsule. Review roles return structured judgments; Python writes the
canonical review records.

## Trust Model

Repository code cannot turn an unrestricted model process running as the same
OS user into a security boundary. Formal production therefore requires the
host to keep the deterministic controller outside creative-role write
authority. Novel Forge enforces the boundary it can verify:

- a completed role result is bound to the expected role, native session,
  underlying session instance, typed operation handle, and result transport;
- no role invocation may add, delete, or modify any repository path;
- only the active controller writes immutable completion records or advances
  `ready`;
- a command bridge must remain outside the repository and hash-pinned;
- missing host attestation fails closed instead of being reconstructed by the
  Lead.

The old importable `_issue_workflow_authority()` shortcut is removed. This
eliminates the observed accidental bypass, while OS-level host isolation
remains the final defense against a deliberately unrestricted process.

## Literary Context

Seven final stress samples are reduced to one aggregate audit and one compact
rule packet. Daily prompts do not load demo prose, transcripts, model rankings,
or numerical style targets.

Each role receives four short judgments:

- what normally creates living prose;
- what is risky and should earn its place;
- what human irregularity must be allowed;
- what must never enter or pass the chapter.

The Writer packet emphasizes concrete choice, embodied work, private cost,
unequal dialogue, incomplete knowledge, and persistent physical state. It
forbids checklist prose, explanatory repair seams, perfect evidence chains,
mechanical precision, and control-plane language.

## Cost Model

Python performs all hashes, validation, evidence binding, stale calculation,
retry accounting, state transitions, and Git work locally. Default model calls
remain:

- one planning response in the Writer session;
- one full draft response;
- one Blind Reader response;
- one Chapter Editor response;
- only when a real MUST exists, one concentrated Patch response and two full
  re-reviews.

MAY and advisory findings do not trigger generation. The second literary
version still containing MUST stops for the user's A/B/C decision.

## Workspace Hygiene

Creative sessions have a zero-write repository policy:

- Writer writes only `draft/正文.md` inside the external capsule.
- Planning and review roles return structured results through the host result
  channel.
- New scripts, `.uploads`, `.tmp-capsule`, scratch Markdown, runtime files,
  review files, or any other repository-local artifact cause
  `unexpected_project_artifact`.
- Failure preserves the original record, retires the session, and retries with
  a fresh session where the existing retry policy allows it.

Demo cleanup removes each experimental book together with its external
per-book Git, external Guardian ledger, matching legacy workspace, and matching
temporary capsule assets after the aggregate samples have been committed.
