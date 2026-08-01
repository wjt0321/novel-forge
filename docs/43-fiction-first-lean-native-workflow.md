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
- freezing the accepted first draft as `控制面冻结稿.md` and rendering `修订.diff`;
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

Daily Lean actions snapshot and restore the current book. A concurrent change
to another book or an ordinary repository file no longer invalidates a valid
role result. A second bounded snapshot protects executable control-plane
sources and entry rules: `app/`, `tools/`, `tests/`, both Novel Forge Skills,
the root instruction/configuration files, and the current book's external
Guardian and local Git ledgers. Action and state files are restored before
their in-memory values are used again. Snapshot directories include a hash of
the repository's absolute path, so identical slugs in different repositories
cannot share an active-action namespace. This prevents a creative role
from changing code or tests to make itself pass without paying the cost or
concurrency risk of a full-repository Harness snapshot. Writer and reviewer
outputs live in the current book's ignored
`.novel-forge/diff/chNN/` workspace. The action names the exact writable file;
unexpected changes elsewhere inside the current book remain a technical
failure.

Lean review capsule inputs are Python-managed control-plane paths, distinct
from the reviewer's writable result file. Workspace delta therefore does not
attribute a valid capsule refresh to the reviewer. The manifest and every
declared input are still verified by SHA-256 before accepting the result, while
undeclared extra files remain unexpected project artifacts. This prevents a
`rewrite capsule -> control_plane_mutation -> rewrite capsule` retry loop
without weakening capsule integrity.

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
read the complete revised body again. Python writes `修订.diff` immediately
after the revised body passes surface checks, before the new review cycle.
Only a double pass causes Python to
promote the body, record the technical evidence, advance `ready`, and
checkpoint the per-book Git history.

Lean review transport is deliberately compact. Chapter Editor returns only a
generic `pass` or `needs_revision`, one complete MUST list, a short summary,
and one prose quote. Python accepts `pass` as the internal editor-ready verdict
and derives supporting record fields itself. Analysis matrices and hard-anchor
coverage tables remain strict-audit evidence, not daily creative work.

Blind Reader's canonical JSON keys are `must`, `evidence_quote`, and
`emotional_residue`. `must_issues`, `quote`, and `emotional_aftertaste` are
accepted only as compatibility aliases and are normalized immediately, so the
state cache and the rendered review cannot disagree on field names. Its two
ratings are canonical strings: `human_likeness` is `convincing`, `uncertain`,
or `synthetic`; `reader_desire` is `continue`, `conditional`, or `stop`.
Natural 0--10 values are deterministically mapped to those enums (7--10,
4--6, and 0--3 respectively) before they enter state. Invalid values report
the actual value and the accepted values rather than silently becoming an
unusable string.

Python records the accepted Blind Reader result together with its result-file
digest and capsule-bound session. A Python-managed refresh can replace that
cached copy only when the file digest changes; a creative role may never edit
a previous role's result while another action is active. Each accepted staged
review also receives a provisional external session-completion receipt. The
receipt is finalized against the canonical review only after double-pass
promotion, preserving the rule that no formal Review History exists before
promotion while retaining evidence if promotion is interrupted.

For Lean result files, Python makes one deterministic repair attempt for the
common case where a prose quotation was left unescaped inside JSON. Legacy
plain-text hard-anchor coverage is ignored because it is not a Lean gate.
Neither condition may turn an otherwise valid literary judgment into a new
review session or a prose rewrite.

Technical retry budgets are scoped to the current role execution. A new
review cycle after Writer patch starts Blind Reader and Chapter Editor at zero
technical retries instead of inheriting transport failures from the previous
body; the already addressed `must_findings` are cleared at that transition.
If review delivery exhausts its automatic retries, an explicit user retry
validates the staged body SHA-256 (falling back to already-promoted prose when
necessary) and resumes the failed reviewer even though Generation has not
been created yet. Valid staged prose is never regenerated merely because
evidence promotion intentionally happens later.

A second reviewed failure stops the automatic loop at an author decision
instead of retrying forever. Decision options are generated by the control
plane from state-machine reachability: revision-class decisions
(`literary_revision_required`, `local_patch_hard_gate_failed`) offer only
`authorize-revision <slug> --reference <依据>` (one concentrated revision plus
a complete re-review, then the same author decision again) and stop; budget,
high-risk, and model-calibration decisions offer their own official commands.
While a decision is pending, `next-action` returns a `user_decision` card and
`complete-role` is rejected. The `retry` command regenerates a fresh draft and
is never re-routed into a patch carrying stale MUSTs.

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

## Documentation authority

`README.md`, `AGENTS.md`, both mirrored Novel Forge Skills, this document,
`docs/44-current-workflow-logic-audit.md`, and `docs/45-workflow-iteration-proposal.md`
describe the current default. Superseded milestones and experiment reports are
condensed in `docs/archive/history.md`; historical requirements for an external
daily Writer Capsule, pre-review Generation creation, complete Lean terminal
envelopes, or mandatory analysis tables do not override the current workflow.

## Relay handoff and context budget (2026-07-29)

The daily CLI now renders `next-action` as a compact handoff card: the role,
its sealed input directory, its only writable output, and the follow-up
`complete-role <slug>` command. It intentionally omits JSON, hashes, session
IDs, Guardian, runtime, and Git details. Host integrations that need the full
machine action opt in with `next-action --json`.

Relay `status` is derived from the persisted native phase, so a waiting Writer,
Blind Reader, or Chapter Editor is described consistently with `next-action`.
After a completed chapter, `next-action` returns a `start_next_chapter`
handoff instead of an empty-action error; `start <slug> --chapter N` reuses the
persisted book metadata for later chapters.

Canonical final-prose paths are derived solely from the chapter number:
`chapters/eNN/ch-NN/正文.md`. Artifact seals are idempotent for exactly the same
signed artifact identity, preventing a transport retry from turning an already
valid review into an integrity collision. A changed artifact or invalid
signature remains a hard failure.

## Phase 1 local cost observations

Lean Native records one local, write-once call observation per Native action under
`.local-guardian/<slug>/workflow-observations/chNN/`. The record contains nullable host
tokens, request count, elapsed-time source, technical retry index, revision round, and
content-free before/after prose summaries. Review MUST scope labels are sampled as
`local`, `structural`, `blocking`, or `unclassified`, but they do not change the existing
chapter-level Patch route.

Authors may inspect these records through `cost-summary <slug> [--chapter N]`; host
integrations may provide actual metrics through `complete-role --telemetry-file`. Missing
or malformed telemetry is never a reason to regenerate compliant prose or redo an
accepted review. Cost observations are diagnostic only: they do not change gates,
promotion, author approval, or `publication_eligibility=False`.


## 2026-07-31 iteration 45 routing

Lean Writer capsules contain a protected `writer-context.md`. Minimal mode compiles P0/P1/P2 at 1500/850/450 CJK, with a total ceiling of 2800 CJK; full mode remains an explicit comparison switch. Volume voice overrides live in `memory/voice-bible-vNN.md`, while Writer model continuity and author-approved switch references are enforced by Python rather than chosen by the role.

Review MUST findings affect routing only when every open finding is marked `local` and maps to one unique paragraph. The Writer then returns replacement fragments only; Python performs exact replacement, runs whole-body hard checks, and restarts the complete Blind Reader and Chapter Editor pair. All other findings retain the single chapter-level Patch path.

Host capability is explicit: `native-isolated` and `managed-relay` may run formal production; `exploration` may keep staged prose and review results but cannot promote or reach formal `ready`. High-risk chapter classes stop after the full double review and before promotion for author confirmation. Optional token budgets never waive a quality failure: a hard limit preserves the staged body and review context and stops before additional Patch/re-review calls.

## 2026-07-31 literary-core compression

The default chain, states, and call count are unchanged. The existing Scene Package now carries three compact human-pressure fields in the same file: private desire, relationship friction, and viewpoint-specific perceptual bias. Writer reads only `writer-context.md`, then silently removes redundant explanation and its most mechanical repeated reaction before returning final prose.

A deterministic `literary_texture` analyzer records repeated paragraph openings, delayed-reaction formulas, explanatory echoes, sentence-length variance, and repeated short phrases. It is advisory only: `blocking=False`, `routing_affected=False`, and it cannot establish AI authorship or literary value. A high-risk result may add at most a 160-character hint to the existing Lean Chapter Editor capsule; it never creates another role or call. Cost summaries aggregate `low`, `medium`, `high`, and `unknown` counts without feeding them back into routing.

Blind Reader treats `uncertain` as non-triggering by default. A `synthetic` verdict is accepted only with an exact prose quote, `needs_revision`, and exactly one `structural` MUST. Chapter Editor independently decides whether the issue is distributed and worth the single allowed literary revision. `MAX_AUTOMATIC_GENERATIONS=2`, the complete double review after any revision, and the author decision after a second reviewed failure remain unchanged.

## 2026-08-02 iteration 47: author-revision routing

A second reviewed failure (`decision_required` with `literary_revision_required` or `local_patch_hard_gate_failed`) is no longer a dead end. The CLI adds `authorize-revision <slug> --reference <依据>`, which records the author's decision as a lightweight evidence file under `.local-guardian/<slug>/native-relay/author-revisions/`, then resumes one concentrated staged revision followed by a complete re-review. It is not an unlimited retry: after the next full double review the chapter returns to the same author decision.

The `retry` path (regenerate) no longer depends on guardian receipt history: `authorize_regeneration(require_body_history=False)` accepts an explicit author decision in Lean mode, where receipts are not written. The strict-audit gate of two distinct body versions still applies to un-authorized automatic retries.

Decision options are generated by Python from state-machine reachability (`_decision_options`): revision-class decisions show only the authorize-revision and stop paths; `next-action` returns a `user_decision` card instead of failing, and `complete-role` is rejected while a decision is pending.

The frozen first draft is renamed `控制面冻结稿.md` so its read-only nature is explicit. Writer actions carry `read_only_project_files`; the action card prints it, the writer instructions call it out, and a control-plane mutation failure message names the only permitted write target.

Review evidence quotes are matched with bounded tolerance: exact substring wins, then whitespace/punctuation normalization, then a normalized 20-character prefix window with at most 15 per-character differences. A fabricated tail cannot pass on prefix alone. Failure messages report the first mismatching character position with expected and actual fragments.
