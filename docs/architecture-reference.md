# Architecture Reference

This document is the maintainers' compact technical reference for the current `books/` workflow. For day-to-day role execution use `43-fiction-first-lean-native-workflow.md`; for recovery semantics use `44-current-workflow-logic-audit.md`.

## Truth hierarchy

1. `books/<slug>/chapters/.../正文.md`, Markdown memory/planning files, immutable evidence, and export manifests are durable facts.
2. `books/<slug>/.novel-forge/index.sqlite3` and the legacy database are rebuildable indexes or ledgers, not the primary manuscript.
3. Native Relay state and `.local-guardian/` are local control/recovery data.
4. Model analysis, scores, `ready`, high-risk confirmation, and budget continuation are not author approval and never establish publication eligibility.
5. `publication_eligibility` remains `False`.

## Current component map

| Component | Responsibility |
|---|---|
| `native_relay.py` | Issues one restricted role action, accepts official completion, stages prose, routes reviews/Patch/recovery |
| `workflow.py` | Orchestration services and user CLI |
| `guardian.py` | Isolated Writer capsule, runtime binding, CAS-style import/promotion, receipts |
| `workflow_iteration.py` | P0/P1/P2 context, model continuity, local Patch, capability/risk/budget policies |
| `workflow_observability.py` | Write-once local call observations and cost summaries |
| `book_project.py` / `book_gates.py` | Chapter state, gates, formal-ready enforcement |
| `book_git.py` | Per-book local recovery history; no remote |
| `book_memory.py` | Markdown Canon and rebuildable memory index |
| `planning_spec.py` | Single source for chapter states, required sections, role and scene-package rules |
| `review_prompt.py` / `writer_prompt.py` | Bounded role instructions |

The legacy chain remains `cli/api/skill_adapter -> service -> repository -> db` and is compatibility-only.

## Default production state flow

```text
planned
  -> context_collected
  -> scene_packaged
  -> drafted (staged only)
  -> blind_read
  -> editorial_reviewed
  -> ready
```

The user-facing Relay compresses this into:

```text
待写 -> 写作中 -> 硬检查 -> 双审中
     -> 待局部修订 / 待作者决定 -> 已归档
```

Only Python advances formal chapter state. A missing role action is never permission to hand-edit state or fabricate evidence.

## Writer isolation and context

- Formal Writer work happens inside `books/<slug>/.novel-forge/diff/chNN/writer/`.
- The role normally reads protected `writer-context.md`, compiled as P0/P1/P2.
- `handoff.md`, prompt, capsule manifest, and Guardian contract remain protected inputs.
- Initial or structural Writer output is only `draft/正文.md`.
- A local Patch Writer outputs only the signed `replacements.json` result.
- Creative roles cannot modify `app/`, `tools/`, `tests/`, root rules, Skills, other books, control-plane files, or Harness configuration.

A volume SHOULD keep one primary Writer model. Unknown model telemetry stays unknown. A different known model requires an author-referenced calibration before the next Writer action.

## Role and result isolation

- Writer, Blind Reader, and Chapter Editor are distinct roles and sessions.
- Role names alone do not prove independence; the host capability and official terminal binding matter.
- Review roles can write only their issued `result_file`.
- File appearance, task creation, acceptance, progress, idle, or availability is not completion.
- The Relay waits for completed/failed/timed-out terminal truth, then imports or retries only the current role.
- Invalid delivery metadata can be repaired without rewriting accepted prose.

Capability tiers:

| Tier | Formal production | Meaning |
|---|---:|---|
| `native-isolated` | Yes | Host can create/wait/bind independent roles |
| `managed-relay` | Yes | Python/adapter manages one restricted role call at a time |
| `exploration` | No | Staged prose and reviews may be retained, but promotion/ready is blocked |

## Gates and promotion

Before formal `ready`, the system requires:

- formal draft mode;
- at least 5000 CJK Han characters;
- deterministic prose and narrative gates;
- current scene-package and hard-anchor coverage;
- independent Blind Reader and Chapter Editor results bound to the current body;
- no unresolved MUST;
- Guardian/session/content integrity;
- successful per-book local Git checkpoint.

Formal chapter files, Generation evidence, Guardian receipts, review history, and ready checkpoints are created only during Python promotion. Failed promotion returns to the last truthful state.

## Patch routing

The workflow allows at most one literary revision round.

### Local Patch

Used only when every open MUST:

- has `scope=local`;
- contains an evidence quote in the current staged body;
- maps to one unique continuous paragraph;
- does not require changing the core event, hard anchors, or chapter-end goal.

Python signs the body SHA and target set, accepts replacement fragments, performs exact unique replacement, then runs whole-body hard checks and a complete new double review.

### Structural Patch

Any structural, blocking, unclassified, duplicate, stale, or non-locatable finding returns to the same staged whole chapter for one concentrated Patch. A second reviewed version with MUST enters author decision; it never loops automatically.

## High risk and budgets

High-risk chapter types are volume start/end, major turn, character death, and core reveal. They complete normal hard gates and double review, then stop before promotion for author confirmation.

Optional budgets never certify quality:

- soft limit disables optional depth calls but preserves core gates and double review;
- hard limit preserves staged prose and review bindings and stops before additional Patch/re-review calls;
- author continuation permits the call, not publication.

## Evidence and observability

Call observations are local, write-once records under:

```text
.local-guardian/<slug>/workflow-observations/chNN/<action-id>.json
```

Unknown tokens or elapsed time remain `null`; invalid telemetry produces warnings and cannot force compliant prose or reviews to be repeated. Cost observations do not affect routing unless the author explicitly configured a budget.

Canon facts follow candidate -> explicit promotion. Review analysis, model inference, and benchmark scores never become Canon automatically.

## Recovery and local Git

- Each book has an external local Git directory under `.local-book-git/` with no remote.
- A ready checkpoint is created only after state/evidence finalization succeeds.
- Technical transport failure retries the current role, not the Writer body.
- Control-plane mutation is restored from the action snapshot and recorded as failure.
- Review correction refreshes only the bound result when its evidence still matches the staged prose.
- No hard-delete command is exposed. Full experimental-book deletion must verify and remove the book, local-book Git, and local Guardian paths together after preserving allowed anonymized aggregate evidence.

## Interfaces and safety

- `tools/novel-workflow.py` is the author-facing automatic entry.
- `next-action` is human-readable by default; `--json` is for host integration.
- Adapter mutations require an absolute `--root` and `--confirm`.
- API and adapter responses do not return full manuscript prose.
- Main-repository commit/push requires explicit user instruction. Per-book checkpoints are local workflow recovery and never push.
