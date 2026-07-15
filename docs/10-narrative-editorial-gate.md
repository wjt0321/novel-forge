# 10 Narrative Editorial Gate

## What this milestone does NOT do

Novel Forge **cannot** judge literary value, originality, or emotional depth. It does not run an "AI detector" and it does not award a quality score.

The Narrative Editorial Gate only records that an independent, evidence-based macro-editorial review happened for a specific revision. The system can then block approval when that review is missing, when it says "revision required", or when it lists unresolved blocking issues. The final decision to publish, revise, or discard remains a human/editor judgment.

## Core components

### 1. Scene Contract v3

New chapters are created with a v3 Scene Contract template. It keeps all v2 fields and adds:

- `character_blindspot_or_pressure` — the viewpoint character's personal pressure they cannot admit or avoid.
- `irreversible_choice` — a choice *made by the viewpoint character* that changes what follows.
- `choice_consequence` — what the choice immediately loses, exposes, promises, or harms.
- `detail_payoff_plan` — up to three "emphasized detail → how it pays off" entries. Write `无刻意强调细节` if none.
- `scene_necessity` — what concrete change would be lost if this scene were deleted.
- `ending_change` — what has changed by the end (knowledge, relationship, agency, risk).

A v3 contract is detected by `contract_version: 3` in its footer or by the presence of any v3-only heading. Legacy v2 contracts are not forcibly migrated; they produce a warning (`scene_contract_legacy_v2`) but do not block existing work.

### 2. Editorial Memo

Each revision can have one active Editorial Memo. It is stored in SQLite, scoped to `chapter_id` and `revision_id`, and supersedes the previous active memo for the chapter with an audit trail.

Required fields:

- `reviewer_role`: fixed to `independent_reader_editor` (the system does not impersonate a human).
- `narrative_necessity`
- `character_agency`
- `detail_selection`
- `causal_chain`
- `prose_observation`
- `verdict`: `ready_for_editor_decision` or `revision_required`
- `blocking_issues`: list of objects, each with `location`, `evidence`, `effect`, `revision_intent`

A memo belongs to exactly one revision. A new revision requires a new memo.

### 3. Gate behavior

`review_chapter`:

- No active memo for the current revision → `CONCERNS` and `editorial_memo_missing` summary.
- Memo verdict is `revision_required` → `CONCERNS`.
- Memo has blocking issues → `CONCERNS`.
- Only `APPROVE` when all existing gates pass and the memo is `ready_for_editor_decision` with zero blocking issues.

`approve_chapter`:

- Blocks if there is no active memo for the current revision.
- Blocks if the memo verdict is not `ready_for_editor_decision`.
- Blocks if the memo has unresolved blocking issues.

This `APPROVE` means "eligible for human/editor decision" — not a literary endorsement.

## CLI

```bash
python -m novel_forge.cli submit-editorial-memo test 1 --memo-file C:\memos\ch1.json
```

The JSON file must be UTF-8, must not be inside the project `library/`, and must contain all required fields.

Example memo file:

```json
{
  "narrative_necessity": "This chapter forces the protagonist to act rather than wait.",
  "character_agency": "She breaks the window; alternative is surrender; cost is a cut hand and lost alibi.",
  "detail_selection": "rusty key (functional), broken window (irreversible), blood (consequence).",
  "causal_chain": "trap → choice → injury → escape.",
  "prose_observation": "The action is shown through concrete motion, not summary; paragraph 3 loses focus.",
  "verdict": "ready_for_editor_decision",
  "blocking_issues": []
}
```

## Skill adapter

```bash
python -m app.novel_forge.skill_adapter --root D:\my-book --confirm submit-editorial-memo submit-editorial-memo test 1 --memo-file D:\memos\ch1.json
python -m app.novel_forge.skill_adapter --root D:\my-book editorial-memo-status test 1
```

The adapter returns only metadata (verdict, blocking issue count, IDs). It never returns the full memo prose or manuscript body.

## Migration

Databases from earlier milestones are automatically migrated to schema v3 on first use. A single timestamped SQLite backup is created before migration. Legacy v2 Scene Contracts remain readable and continue to work; new chapters receive v3 templates.

## Known limits

- The memo fields are free text; the system only checks that they are non-empty and that blocking issues have the required schema. It does not evaluate whether the prose observations are accurate or insightful.
- A chapter can still receive `APPROVE` from `review_chapter` while being dull, derivative, or emotionally flat; the gate only verifies that editorial coverage occurred.
- The system cannot tell whether a filled Scene Contract v3 is honest or敷衍; it only checks presence and non-placeholder content.
