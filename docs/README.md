# Documentation Map

S-Black Novel Forge documentation is intentionally split into a small current set, three focused references, and one historical archive. Markdown prose, book evidence, and export manifests remain the long-term facts; documentation explains their contracts but does not replace them.

## Read first

| Need | Document |
|---|---|
| Run the current `books/` workflow | `43-fiction-first-lean-native-workflow.md` |
| Understand current states, retries, recovery, and truth boundaries | `44-current-workflow-logic-audit.md` |
| Understand the P0/P1/P2, local Patch, capability, risk, and budget iteration | `45-workflow-iteration-proposal.md` |
| Read the production-blocker review and the next iteration proposal | `46-workflow-iteration-blockers-liangu.md`、`47-workflow-iteration-proposal.md` |

Daily chapter work should normally stop after these documents. Do not read historical milestones before executing `next-action`.

## Focused references

| Topic | Document | Purpose |
|---|---|---|
| Control plane, evidence, isolation, recovery, local Git | `architecture-reference.md` | Current technical reference for maintainers |
| Voice, scene contracts, Writer/Reader/Editor literary rules | `literary-quality-reference.md` | Current literary-quality reference |
| Legacy `library/`, SQLite, migration, export | `legacy-library-reference.md` | Compatibility maintenance only; never mix with `books/` |

## Evidence examples

Only reusable author-facing examples remain under `examples/`:

- `human-flavor-anatomy.md`: positive human-text anatomy.
- `ai-flavor-antipatterns.md`: recurring model-flavor failure patterns.
- `human-readable-positive-sample-deepseek-v4-flash.md`: bounded positive model sample.
- `benchmark-jianlai-analysis.md`: human benchmark analysis with source boundaries.
- `book-workflow-samples/`: anonymized workflow-level sample catalog without prose.

Historical Agent Demo reports were one-time experiment records, not production documentation. Their durable conclusions are consolidated in `archive/history.md`; the JSON artifact used by a regression test now lives under `tests/fixtures/`.

## Archive

`archive/history.md` contains:

- the value analysis used for the 2026-07-31 documentation consolidation;
- milestones 01–42 and their durable contribution;
- implementation-plan history;
- benchmark and failure-mode conclusions from Agent Demo v34–v56.

Detailed superseded prose remains available through Git history. The archive is not a current rule source.

## Documentation rules

1. Current behavior belongs in 43, 44, or 45, or one of the three focused references.
2. A new implementation milestone updates an existing current document; it does not automatically create a new numbered document.
3. One-time plans and experiment reports are summarized in `archive/history.md` after completion.
4. Tests and machine fixtures belong under `tests/fixtures/`, not `docs/`.
5. Examples must state provenance and must never imply model ranking, author approval, literary certification, or publication eligibility.
6. `.agents/skills/novel-forge/SKILL.md` is canonical and `.claude/skills/novel-forge/SKILL.md` must remain byte-identical.

## Consolidation record

On 2026-07-31 the documentation tree was reduced from 115 files / 10,184 non-empty lines to 15 files / 1,553 non-empty lines (87.0% fewer files and 84.8% fewer lines). Most of the former sprawl came from 42 sequential milestone documents, 18 completed design/implementation plans, and paired Markdown/JSON experiment reports. They were consolidated because the repository already identifies 43/44/45 as the current truth and Git preserves exact historical versions.
