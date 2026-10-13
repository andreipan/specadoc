# Apply mode

Load this reference only for `specadoc apply <slug>`.

1. Refuse to edit until `spec.md`, `plan.md`, model approval, and plan approval
   pass deterministic validation.
2. Implement behavior with RED-GREEN-REFACTOR. Mechanical migrations use their
   accepted migration matrix rather than manufactured RED failures.
   REFACTOR may include optional behavior-preserving cleanup; see
   `interoperability.md` → Behavior-preserving cleanup.
3. Delegate only one fully specified low-decision task at a time to `worker` when
   it reduces controller context. Architecture and ambiguous decisions remain in
   the controller.
4. Record exact commands and one-line results in `plan.md`; never paste raw
   successful logs.
5. The controller runs the final affected-only verification and populates
   `plan.md`'s `Review scope` from the actual executable diff. The scope is
   independent of task `Files:`: use repository-relative literal file paths,
   and prefix an intentional deletion with `!`. Then run
   `validate_change.py <slug> --phase pre-review`.
6. On a stable executable diff, run one independent read-only `reviewer` and
   record its PASS as the archive input. Record the round as a `### G<n>`
   block under `plan.md`'s `Review result` → `Round log`
   (`assets/plan-template.md`): `**Type:** initial` for a new-diff round,
   `**Snapshot:**` and the manifest from `review_snapshot.py compute <slug>`,
   `**Previous:**`,
   `**Outcome:**`, and `**Reason:**` on FAIL. `check_pre_review`
   (`--phase pre-review`) refuses to dispatch a 4th `initial`-type round
   without a recorded `**Round cap override:** <reason>` on the latest
   block — stop and ask the user whether to consolidate or split the change
   instead of overriding by default. Fix every confirmed finding, MINOR included
   (see `tdd-and-review.md` for the only allowed deferral), then dispatch the
   one targeted re-review of the fixes (`**Type:** re-review`) immediately,
   without waiting for the user, scoped
   to only the files `review_snapshot.py diff` shows changed since the prior
   round — see `subagent-routing.md`'s targeted re-review example; do not
   resend the full `spec.md` or `plan.md` for that round. If a later
   production-code, test, migration, executable-configuration,
   public-contract, or approved-requirement change creates a new executable
   diff — detected by `review_snapshot.py verify` reporting a mismatch
   against the latest round's snapshot, not by judgment alone — update Review
   scope, repeat final verification, and run one reviewer for that diff. Do not
   dispatch another reviewer solely because evidence, capability documents, or archive
   material was completed.
7. On PASS, update capability specifications and fill `Archive summary` with the
   durable outcome, decisions, and residual risks, then run
   `validate_change.py <slug> --phase final`. The final gate validates the
   latest round's Outcome, manifest, Snapshot hash, header Result, and current
   snapshot; it does not re-apply the reviewer-dispatch cap. Do not archive implicitly.

## Reading order

Load only what the current step needs — do not front-load every reference
below before RED. Controller front-loading (not the reviewer, which
`subagent-routing.md` already scopes) was independently measured as a larger
raw read-token cost than the reviewer subagent itself in at least one traced
session.

| Reference | Read it when | Not before |
|---|---|---|
| `spec.md`, the current task's `plan.md` section, its `Files:` targets, and the relevant `AGENTS.md` scope | Before writing the failing test (RED) for that task | — |
| `subagent-routing.md` | Immediately before dispatching a worker or reviewer subagent | Not for a task the controller implements directly |
| `measurement.md` | Immediately before recording final evidence/tokens for a task | Not during RED/GREEN/REFACTOR |
| `tdd-and-review.md` | Immediately before initiating a review round | Not during implementation |
| `artifacts.md` | Only when authoring/updating spec.md/plan.md structure | Not needed during apply's TDD loop |
