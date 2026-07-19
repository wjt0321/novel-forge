# v4.3 Reader Pull and Runtime Truth Implementation

## Task 1: Preserve the experiment

- Record prose hashes, sizes, CJK counts, style metrics, workflow state, local
  Git history, and runtime evidence hashes for both samples.
- Store a short positive Flash excerpt set with an explicit
  `not_writer_exemplar` boundary.
- Record the Pro false-ready contradictions and the resulting protocol changes.

## Task 2: Define failing tests

- Blind-reader pass rejects weak or absent reader desire.
- Blind-reader pass rejects missing emotional residue or next-chapter pull.
- Runtime audit rejects one-chapter scope bound to multiple generations.
- Project status blocks cross-chapter reuse of a writer `run_id`.
- Ready transition rejects missing or exceeded mutation/review metrics.
- Harness Contract forbids review-confirmation pauses and requires automatic
  fresh-session review launch.

## Task 3: Implement the gates

- Extend review parsing and validation.
- Add generation runtime-integrity validation shared by ready and status.
- Upgrade ready-chapter runtime-budget findings from warnings to blockers.
- Add cross-chapter `run_id` collision detection.
- Extend the machine-readable Harness Contract.

## Task 4: Update generated projects and guidance

- Update review template and blind-reader role.
- Update generated `CLAUDE.md` and `README.md` to v4.3.
- Update canonical and mirrored Novel Forge skills byte-for-byte.
- Add the v4.3 milestone document and refresh top-level guidance.
- Allow `sync-tools` to migrate generated v4.2 project constitutions.

## Task 5: Verify and clean

- Run focused tests after each implementation slice.
- Run the full test suite.
- Verify both evidence records are tracked by the Harness repository.
- Resolve and verify both `books/<slug>` and `.local-book-git/<slug>.git`
  targets, then remove all four local sample paths.
- Merge to `main`, remove the development branch/worktree, and push `main` to
  Gitea and GitHub.

