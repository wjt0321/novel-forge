# Formal Writer Prompt Template Design

## Goal

Let the user request one formal chapter with a short instruction while Novel
Forge compiles a complete, vendor-neutral writer prompt into the isolated
capsule. The prompt improves task clarity without becoming a substitute for
Guardian isolation, runtime provenance, review gates, or author authority.

## Scope

The first version defines one template only:

`formal-writer/v1`

It is used for the current chapter writer. Blind reader, chapter editor,
context collector, and orchestrator prompts remain unchanged. Multi-chapter
sequences remain supported for compatibility, but the default sequence size
stays one chapter and every launch continues to sign only the current chapter.

## Capsule Layout

Guardian adds one protected, read-only input:

```text
instructions.md
```

The writer capsule contains:

```text
capsule.json
guardian-contract.json
instructions.md
handoff.md
draft/
```

The writer may still produce only `draft/正文.md`. `instructions.md` is created
before the writer starts, included in the protected hash set, and rejected if
changed.

## Prompt Content

The compiled prompt is intentionally short. It states:

1. the formal writer role and current chapter scope;
2. `handoff.md` as the draft input, plus the seeded body for a patch;
3. a complete chapter with pressure, choice, consequence, and stopping point;
4. `draft/正文.md` as the only output;
5. the 5,000 CJK formal floor and prose-only body rule;
6. stop behavior for conflicts or unavailable formal capability;
7. no authority to create scripts, state, evidence, review, or runtime files.

It does not repeat the full Skill or machine contracts, expose validator
implementation, include provider/model names, carry old session context, or
provide numeric style targets.

The same template ID compiles operation-specific text: draft mode requests one
complete chapter; patch mode requires one bounded edit that preserves
unaffected prose and forbids a whole-chapter rewrite.

## Provenance

The capsule manifest, Guardian control record, clean/compromised receipt, and
adapter response carry:

- `prompt_template_id: formal-writer/v1`
- `prompt_sha256`

Formal agent generation evidence records the same two fields. Ready validation
requires them to match the signed Guardian receipt. The full prompt is not
copied into generation evidence or runtime audits.

## Token Boundary

The static compiled instructions must remain below 1,200 characters. Narrative
facts stay in the bounded handoff. Guardian rendering, hashing, and validation
are local Python operations and add no model requests or transcript
reinjection.

## Failure Behavior

- Modified or missing `instructions.md` compromises the capsule.
- Unknown template IDs are rejected before writer launch.
- Missing or mismatched generation prompt provenance blocks formal ready.
- Human-authored generations keep their existing author/human_delegate
  authority path and do not require a Guardian prompt receipt.
