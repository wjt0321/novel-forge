# Blind Experience Gate

## Purpose

The Blind Experience Gate prevents planning knowledge from filling gaps that the prose itself does not render. A writer and an editor who both saw the Scene Contract may believe a room, emotion, or relationship is visible when the reader received only an abstract fact.

Example failure:

```text
The navigation cabin is only three square metres.
```

This states a measurement. It does not establish where the character's knees, feet, chair, controls, or surrounding objects are, what movement is blocked, or how the restriction changes action.

## Isolation Boundary

Build the packet with:

```cmd
python -m app.novel_forge.skill_adapter --root D:\s-black-novel --confirm build-blind-reader-packet build-blind-reader-packet <slug> <chapter> --output-file <absolute-path>
```

The packet contains only:

- book slug, chapter number, and revision ID;
- current revision prose with line numbers;
- reconstruction questions.

It MUST NOT contain the Scene Contract, Voice Bible, Story Engine, chapter plan, Drafting Packet, Canon, promises, or author intent.

## Required Report

The blind reader submits UTF-8 JSON containing:

- `spatial_reconstruction`: relative positions and navigable space visible in prose;
- `body_position_and_contact`: what the body touches, carries, avoids, or endures;
- `action_constraints`: how setting and pressure limit available action;
- `emotional_trajectory`: emotion inferred from perception, delay, choice, and action;
- `dialogue_dynamics`: what changes between speakers, beyond information exchange;
- `memorable_images`: at least three objects with `location`, exact prose `evidence`, and the resulting `reader_image`;
- `knowledge_gaps`: anything requiring outside planning knowledge;
- `verdict`: `experience_reconstructable` or `revision_required`;
- `blocking_issues`: evidence, reader effect, and revision intent.

Every memorable-image and blocking-issue evidence string must exist in the current revision. A passing review cannot contain knowledge gaps or blocking issues.

Submit with:

```cmd
python -m app.novel_forge.skill_adapter --root D:\s-black-novel --confirm submit-blind-experience-review submit-blind-experience-review <slug> <chapter> --report-file <absolute-json-path>
```

## Approval Effect

A chapter cannot receive `APPROVE` or be formally approved unless its current revision has:

- no blocking lint;
- no unresolved S1/S2 review or reader-review findings;
- a passing prose-only Blind Experience Review;
- a ready Editorial Memo with no blocking issues.

A new revision invalidates the old blind review automatically because reviews are bound to an immutable revision ID.
