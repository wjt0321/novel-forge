# Automatic Three-Role Workflow Design

**Goal:** Add a user-facing orchestrator that drives the existing auditable
books workflow from six architecture inputs through writing, review, patch,
ready state, sequence truth, and local Git recovery.

**Architecture:** Keep Guardian, chapter sequence, Markdown evidence,
runtime audits, review validation, state transitions, and per-book Git as the
only authorities. Add a vendor-neutral `SessionBackend` boundary and a thin
orchestrator that creates fresh role sessions, supplies role-minimal context,
and translates internal outcomes into a small set of user messages.

**Failure model:** Guardian failures remain immutable compromised receipts.
The orchestrator never edits them; it retries by claiming a new writer session
and preparing a new capsule. Two automatic retries are allowed before the user
sees keep/regenerate/stop choices.

**Review model:** Every accepted review is copied to immutable
`reviews/history/` storage before the canonical current-review projection is
updated. Staleness is computed from source bindings, so old records remain
unchanged after prose revisions.

**Verification:** Tests cover normal completion, compromised capsule recovery,
fresh sessions, immutable receipts and reviews, patch re-review, sequence
truth, external Guardian placement, null runtime observations, retry
exhaustion, and user-safe output.
