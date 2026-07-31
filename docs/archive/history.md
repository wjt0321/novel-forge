# Historical Decisions and Consolidation Record

This archive preserves the durable decisions from superseded milestone documents, completed plans, and one-time Agent Demo reports. It is historical context, not the current workflow contract. Current behavior is defined by `../43-fiction-first-lean-native-workflow.md`, `../44-current-workflow-logic-audit.md`, `../45-workflow-iteration-proposal.md`, and the focused references linked from `../README.md`.

Exact pre-consolidation documents remain available in Git history.

## 2026-07-31 value analysis

Before consolidation, `docs/` contained 115 files and 10,184 non-empty lines. After consolidation it contains 15 files and 1,553 non-empty lines: 87.0% fewer files and 84.8% fewer lines.

| Source set | Files | Value decision | Reason | Destination |
|---|---:|---|---|---|
| Current workflow 43–45 | 3 | Keep | Current default, audit/recovery truth, latest iteration | Kept in place |
| Milestones 01–13 | 13 | Condense | Legacy setup, database, packet/readiness and early workflow details; useful only for compatibility | `legacy-library-reference.md` plus this chronology |
| Literary milestones 14–23, 26, 28, 35 | 13 | Condense | Durable literary rules were spread across versioned reports and repeated experiments | `literary-quality-reference.md` |
| Control-plane milestones 24–25, 27, 29–34, 36–42 | 16 | Condense | Durable isolation, session, Guardian, local Git, recovery, and ready rules now have one implementation | `architecture-reference.md` |
| Completed design/implementation plans | 18 | Delete after summary | One-time execution scaffolding; no longer an operational reference | Plan history below |
| Agent Demo v34–v56 Markdown/JSON reports | 43 | Delete after summary | One-time, non-comparable experiments; repeated source disclaimers and failure patterns | Benchmark history below |
| Regression JSON used by tests | 1 | Move | Machine fixture is not documentation | `tests/fixtures/agent-demo-v43-control-plane-bypass.json` |
| Reusable literary examples | 4 | Keep | Directly useful to Writer/reviewer calibration | `docs/examples/` |
| Anonymized workflow sample catalog | 3 | Keep | Current aggregate workflow evidence without prose or private control data | `docs/examples/book-workflow-samples/` |

The consolidation deliberately removes version-by-version prose and one-time test output from the current tree. It preserves essential procedures, constraints, recovery rules, roadmap decisions, failure modes, source boundaries, and reusable examples in focused references. Git remains the exact historical archive.

## Milestone chronology 01–42

| Milestone | Durable contribution | Current home |
|---|---|---|
| 01 Getting Started | Environment, CLI/API entry, distinction between current and legacy workflows | `legacy-library-reference.md`, `../43-fiction-first-lean-native-workflow.md` |
| 02 Data Model and State Machine | Books/chapters/revisions/findings/facts/promises/audit and transition invariants | Legacy and architecture references |
| 03 Quality and Approval Gates | Revision-scoped lint/review/Canon gates; pass is not author approval | Literary and architecture references |
| 04 Operations and Backup | Audit, backup, export manifests, confirmed adapter operations | Legacy and architecture references |
| 05 Human-readable Fiction Quality | Evidence -> reader effect -> revision intent; no automatic prose rewrite | Literary reference |
| 06 Voice Bible and Scene Contracts | Positive voice direction, bounded scene pressure, versioned contracts | Literary reference |
| 07 Database Migration | Version detection, timestamped backup, atomic migration, rollback | Legacy reference |
| 08 Drafting Packets | P0/P1/P2 context principle | Current Writer package in architecture/45 |
| 09 Drafting Readiness | Placeholder detection, formal versus exploratory readiness | Architecture and literary references |
| 10 Narrative Editorial Gate | Causality/agency/editorial memo boundary | Literary reference |
| 11 Autonomous Research/Writing Chain | Research ledger, story engine, plans, promises, iterations | Legacy reference; current workflow keeps only durable principles |
| 12 Quality-chain Reconstruction | Layered gates, human-first books workspace, Patch revisions | Architecture reference |
| 13 Claude Project Workflow | `books/` Markdown-first project and bounded adapter | Architecture reference |
| 14 Blind Experience Gate | Prose-first isolated reader report and approval effect | Literary reference |
| 15 Books Skill Quality | Single-source rules, lint thin shells, adapter boundaries | AGENTS and architecture reference |
| 16 Register Mixing Handover | Dialogue/register variation and exemplar observations | Literary reference |
| 17 Long-form Memory Kernel | Candidate Canon, promises, contradictions, bounded chapter handoff | Architecture reference |
| 18 Human Narrative Evaluation | Human-likeness is reader reconstruction, not AI detection | Literary reference |
| 19 Limited Cognition/Causal Responsibility | Knowledge source, alternative interpretation, causal ownership | Literary reference |
| 20 Review Convergence/Benchmark Integrity | Revision-scoped findings, source-qualified comparisons, no score-as-approval | Literary reference and benchmark history |
| 21 Harness Integrity/Serial Continuity | Runtime truth, independent sessions, sequential handoff | Architecture reference |
| 22 Source Hygiene/Cost Short Circuit | Stop invalid experiments early; preserve source uncertainty | Architecture reference |
| 23 Lean Literary Loop | Small role surface, full hard gates, bounded revision loop | Current 43/44 |
| 24 External Harness Guardrails | Vendor-neutral terminal/runtime contract and budget boundary | Architecture reference |
| 25 Chapter Session Orchestration | One chapter/session, claim/advance sequence, bounded handoff | Architecture reference |
| 26 Literary Anti-overfit/Sequence Truth | One winning branch, Writer/Editor separation, no model ranking | Literary reference |
| 27 Per-book Local Git | External local recovery Git, no remote, checkpoint ordering | Architecture reference |
| 28 Reader Pull/Runtime Truth | Desire-to-continue and observed runtime separated from model claims | Literary/architecture references |
| 29 Isolated Writer Capsule | Capsule-only Writer output, protected inputs, Guardian import | Architecture reference |
| 30 Compiled Writer Prompt | Bounded vendor-neutral prompt and source binding | Architecture reference |
| 31 Automatic Three-role Workflow | Writer -> Blind Reader -> Editor -> one Patch -> double review | Current 43/44 |
| 32 Literary Production Loop | Python control plane, role separation, staged formal promotion | Architecture/current workflow |
| 33 Async Completion/Micro-rules | Official terminal truth, hard anchors, compact literary prohibitions | Architecture/literary references |
| 34 Session Attestation/Sealing | Dual session identity, content sealing, evidence-before-ready | Architecture reference |
| 35 Literary Rule Manual | Writer/Reader/Editor allow/caution/forbid rules | Literary reference |
| 36 Harness Trust/Control Integrity | A Lead cannot create infrastructure or substitute permission for isolation | Architecture reference |
| 37 Native Terminal Wait/Model Selection | Wait for official terminal; requested/resolved model distinction | Architecture/45 |
| 38 Typed Role Result/Review Recovery | Typed payloads, path ownership, bounded result repair | Architecture/current audit |
| 39 Deterministic Native Control | Python-owned state, zero creative-role control-plane writes | Architecture reference |
| 40 Native Relay/Assurance Modes | Persistent pull protocol and formal/exploration distinction | Current 43/44 and architecture |
| 41 Completion Repair/Review Capsules | Repair metadata without redoing prose; sealed review input | Current audit and architecture |
| 42 Hard-anchor/Session/Ready Integrity | Structured anchor coverage, permanent session collision detection, checkpoint order | Current audit and architecture |

## Completed plan history

The removed plan files fall into these completed workstreams:

| Date | Workstream | Result |
|---|---|---|
| 2026-07-15 | Novel Forge foundation | Initial service/repository/database, CLI/API, quality and backup contracts |
| 2026-07-17 | Human narrative workflow | Evidence-based reader/editor evaluation and books workflow |
| 2026-07-17 | Long-form memory kernel | Candidate Canon, promises, bounded continuity |
| 2026-07-17 | Review convergence and benchmark integrity | Revision scoping and qualified experimental evidence |
| 2026-07-17 | Harness integrity and serial continuity | Runtime/session truth and multi-chapter isolation |
| 2026-07-19 | External guardrails | Vendor-neutral Harness contract and experiment stop rules |
| 2026-07-19 | Chapter-session orchestration | Claim/advance sequence and bounded handoff |
| 2026-07-19 | Per-book local Git | External local Git recovery and checkpoint semantics |
| 2026-07-19 | Reader pull/runtime truth | Reader desire fields and runtime-source discipline |
| 2026-07-20 | Formal Writer prompt | Compiled bounded prompt and Capsule binding |
| 2026-07-21 | Automatic three-role workflow | Writer/Reader/Editor orchestration and recovery |
| 2026-07-21 | Literary production loop | Control-plane isolation and one-Patch convergence |
| 2026-07-23 | Deterministic native workflow | Native Relay, result routing, workspace hygiene |
| 2026-07-31 | Workflow observability phase 1 | Write-once cost/retry/body-change observations without routing changes |

Plans were removed after their implementation and tests became the executable truth. New completed plans should be summarized here rather than retained indefinitely.

## Agent Demo benchmark history

All experiments compared model + host + permissions + workflow, not model weights in isolation. Different stories, prompts, contexts, tools, and completion depths prevent a universal ranking. `ready`, a score, or a gate pass never means author approval or publication eligibility.

| Demo | Durable finding |
|---|---|
| v34 source/evidence comparisons | User-declared model provenance can conflict with project metadata; retain qualified source confidence and never mix Agent output with a human benchmark. |
| v34 model/agent/rework comparison | Workflow completion depth and revision cost matter as much as surface prose; non-controlled samples cannot rank models. |
| v35 DeepSeek across Harnesses | The same declared model can behave differently under writing versus coding Harnesses; compare the whole runtime system. |
| v37 MiniMax five-chapter drift | Markdown emphasis and formatting contamination can accumulate chapter by chapter even when state reaches ready. |
| v38 Claude/MiniMax ACP audit | Real billing/runtime events must be separated from model self-report; long shared context increases cost and contamination risk. |
| v39 DeepSeek/Reasonix vs MiniMax/pi | External Harnesses need source validation, hard budgets, session isolation, and stop conditions. |
| v40 multi-host session audit | One chapter per real session and bounded handoff are necessary; host/task identifiers are not interchangeable. |
| v41 four-model prose comparison | Preserve one winning branch; literary diagnosis must not overfit a tiny multi-model sample. |
| v42 reader-pull study | Human-likeness and desire-to-continue are separate; a readable texture does not guarantee a strong next-chapter pull. |
| v43 control-plane bypass | A same-context Lead can fabricate session evidence and bypass Guardian boundaries; this JSON remains a regression fixture under `tests/fixtures/`. |
| v44 single-chapter Harness bypass | Formal-looking files and hashes do not prove an independent Writer or valid promotion path. |
| v45 workflow comparison | Stronger prose, lower cost, and more trustworthy orchestration can belong to different model/Harness combinations. |
| v46 three-session human-light flow | Minimal role handoff is viable when session identity and result ownership remain explicit. |
| v47 automatic false-ready bypass | Direct state/file editing can manufacture ready; Python must own promotion and checkpoint order. |
| v48 control-plane spill/repair seam | Creative-role writes outside their issued path require restoration; repair must not erase compliant prose. |
| v49 async Writer bypass/partial humanity | File appearance before official terminal is not completion; surface humanity can coexist with invalid workflow evidence. |
| v50 single-context backfill | Backfilled review files and self-issued IDs cannot retroactively prove independent review. |
| v51 literary success/formal bypass | A chapter may be literarily promising while procedurally invalid; aesthetic judgment never repairs missing formal evidence. |
| v52 missing-backend degraded completion | No backend means stop before formal production; degraded exploration cannot be relabeled formal. |
| v53 Lead-created fake Harness | User permission to continue is not permission for a Lead to install or fabricate infrastructure, sessions, or telemetry. |
| v54 timeout/model resolution | Requested and resolved models differ; wait for the host's official terminal and actual resolved identity. |
| v55 result routing/path ownership | Session/member/task IDs and Unix/Windows artifact paths require typed routing and explicit ownership. |
| v56 multi-host stress audit | No sample won prose, cost, and workflow truth simultaneously; route quality investment by risk and preserve author judgment. |

## Reusable conclusions

1. Evaluate the whole model + host + role isolation + context + recovery system.
2. Unknown provenance or telemetry stays unknown.
3. Literary success and procedural validity are independent axes.
4. Strong Lead reasoning cannot substitute for program-enforced role isolation.
5. Weak Lead behavior must be unable to self-write/self-review into ready.
6. Local problems should use exact local replacement; structural problems need one concentrated chapter Patch.
7. Cost controls stop additional calls; they never convert an unresolved issue into a pass.
8. Only the author can approve the work, and publication eligibility remains false.
