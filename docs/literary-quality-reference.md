# Literary Quality Reference

This document consolidates the durable literary rules from the earlier Voice Bible, scene-contract, blind-reader, anti-overfit, cognition, reader-pull, and short-rule milestones. It is a production guide, not an AI detector and not a certificate of literary value.

## Core principle

Reduce the process burden shown to the Writer, not the quality standards applied to the finished chapter. Deterministic rules block recurring mechanical contamination; human-like reading roles judge reader effect, causality, agency, texture, continuity, residue, and desire to continue.

All literary findings use:

```text
evidence -> reader effect -> revision intent
```

A preference without a current prose quote is not a MUST.

## Voice assets

### Book-level Voice Bible

The book voice establishes:

- narrative distance and focalization;
- information-release order;
- dialogue and silence behavior;
- sentence-rhythm variance rather than a fixed sentence length;
- sensory palette and terminology discipline;
- emotional restraint;
- approved exemplars described by narrative function.

An exemplar is positive evidence, not a reusable sentence template. Do not copy its nouns, signature actions, ending object, joke, or syntactic skeleton.

### Volume override

`memory/voice-bible-vNN.md` changes only what the current volume needs. It records volume-specific distance, information release, dialogue/silence, private cost, one or two approved exemplar summaries, and Writer model calibration history. Unfilled fields inherit the book-level Voice Bible.

## Scene contract

A formal chapter package must make the following usable by a Writer without exposing the control plane:

- immediate goal and pressure;
- physical space and embodied constraints;
- resistance from people, world, time, or procedure;
- hard anchors and forbidden contradictions;
- current knowledge sources and uncertainty;
- character choice, alternative action, and private cost;
- causal steps and irreversible point;
- chapter stop boundary and unresolved pressure;
- terminology and promise budget.

Planning is not proof that prose achieved the event. Reviewers reconstruct the chapter from prose first, then compare the package.

## Writer rules

### Must do

- Keep one limited viewpoint and expose only information available through perception, evidence, memory, or justified inference.
- Let scenes advance through action, obstruction, choice, and consequence.
- Make important decisions costly and leave alternatives visible.
- Ground professional or technical judgment in evidence, conditions, execution cost, and risk.
- Let dialogue alter plan, power, knowledge, relationship, or immediate action.
- Preserve body position, object state, time, knowledge ownership, and previous-chapter continuity.
- End on unresolved pressure produced by the chapter, not an unrelated teaser.

### May do

- Use dry humor, irony, silence, pure dialogue, slow beats, or an imperfect judgment when they arise from the character and situation.
- Vary narrative presence by function. A transition can guide; action and confrontation usually stay close to the body.
- Leave uncertainty unresolved when the character lacks decisive evidence.

### Must not do

- Put prompts, workflow language, Agent identity, hashes, scores, or control-plane explanations in prose.
- Use `——`, `……`, mechanical `不是 X，而是 Y`, or explanatory cognition leads such as “他意识到/终于明白”.
- Summarize emotion or theme where body, choice, delay, or action should carry it.
- Turn terminology into exposition detached from touch, position, operation, or obstruction.
- Make every important judgment immediately correct or make the world exist only to prove the protagonist.
- Create deliberate typos, broken grammar, or random noise to simulate humanity.
- Merge every experimental branch; preserve one winning branch and its cost.

Formal prose remains at least 5000 CJK.

## Blind Reader

The Blind Reader first sees only the current complete staged prose. The role reconstructs:

- space and body positions;
- constraints and available alternatives;
- emotional movement without relying on labels;
- dialogue action;
- memorable images;
- residue after the final line;
- desire to read the next chapter and the concrete source of that pull.

Required outputs include `human_likeness`, `reader_desire`, emotional residue, next-chapter pull, evidence quote, and bounded findings. The Blind Reader cannot infer success from planning, state, score, or author intent.

A local issue may be marked `scope=local`; a causal/scene-level defect is `structural`; a fact, safety, or process-stopping issue is `blocking`. If uncertain, do not label it local merely to reduce cost.

## Chapter Editor

The Chapter Editor reads the complete current prose and bounded planning context. It checks:

- causality and knowledge sources;
- agency, alternatives, and private cost;
- dialogue function and attribution;
- texture and explanation load;
- continuity and hard-anchor coverage;
- whether the stopping point is earned.

The verdict is `pass`/ready-for-editor-decision or `needs_revision`, with complete MUST findings, summary, and prose evidence. A planning promise is not counted as covered unless the prose supplies a valid quote and consequence.

## Anti-overfit rules

- Model or harness scores do not equal author approval.
- A role label does not prove an independent session.
- Aesthetic preference does not override facts, viewpoint, causality, or character knowledge.
- The protagonist's competence must remain executable and fallible.
- Reader-pull is separate from surprise; it can come from obligation, cost, relationship change, incomplete action, or an unanswered practical question.
- “Human-like” means situated choice, uneven but purposeful rhythm, private cost, selective attention, and independent world resistance—not injected defects.

## Revision convergence

Only open MUST findings trigger literary revision. MAY findings remain advisory. Local Patch is allowed only for uniquely locatable paragraph-scale defects; otherwise one concentrated whole-chapter Patch is used. Every revised body is read in full by both review roles. A second reviewed body with MUST stops for the author.

## Evidence examples

Read these as bounded evidence, not style templates:

- `examples/human-flavor-anatomy.md`
- `examples/ai-flavor-antipatterns.md`
- `examples/human-readable-positive-sample-deepseek-v4-flash.md`
- `examples/benchmark-jianlai-analysis.md`

Never copy wording from a benchmark into production prose. Source claims and model labels in historical experiments remain qualified and cannot support a universal model ranking.
