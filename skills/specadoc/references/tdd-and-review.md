# TDD, review, and completion

Load this reference only during implementation, review, or completion verification.

## TDD loop

For each behavior-changing task:

1. Write one minimal behavioral test.
2. Run it and observe failure.
3. Confirm the failure is caused by the missing behavior, not syntax, setup, or an unrelated defect.
4. Write the minimum implementation needed to pass.
5. Run the focused test.
6. Run relevant neighboring regression tests.
7. Run required lint, type-check, build, or repository-specific checks.
8. Refactor only while all relevant checks remain green.
9. Verify the task's objective completion condition.
10. Update `plan.md` immediately with the checkbox, command, and concise result.

Prefer tests of observable behavior over mocks of internal implementation.

REFACTOR may use an installed cleanup companion; see `interoperability.md` →
Behavior-preserving cleanup.

## Mechanical migration protocol

Use this protocol for broad namespace, path, symbol, import, or type migrations:

1. Build the migration matrix from `recon-and-clarify.md` before bulk edits.
2. Add or identify characterization tests for each semantic difference or
   compatibility boundary. Run them before implementation when they can fail
   for the intended behavioral reason.
3. For import-only or equivalent-signature categories, use a deterministic
   legacy-reference search plus focused static analysis instead of an
   artificial RED test.
4. Apply one classified replacement batch at a time. Do not globally replace a
   short symbol when multiple classes share that name; replace the qualified
   contract or a bounded file set.
5. Run focused checks after a batch only when they can reveal a new class of
   failure. Reuse previous evidence when the relevant files have not changed.
6. Delete legacy contracts only after target consumers compile and the
   legacy-reference search is empty.

Tests added after implementation are appropriate when implementation or review
reveals a previously unidentified semantic invariant. They must reproduce that
gap before any corrective code change. Do not defer all behavioral coverage
until after implementation by default.

## TDD exceptions

Allow an exception only when explicitly recorded in `plan.md`, such as:

- Documentation-only work.
- Generated code where the generator is tested elsewhere.
- One-off exploratory prototypes that will not ship.
- Configuration with no testable behavior and a better deterministic validation command.
- Purely mechanical namespace, path, import, or equivalent-signature migration
  steps with deterministic searches and focused static analysis. Any changed
  behavior or compatibility boundary still requires behavioral coverage.

A missing convenient test harness is not automatically an exception. Prefer adding the smallest practical test seam.

## Verification cadence

- A worker runs the focused and neighboring checks for its own task. The
  controller runs and classifies the final affected-only set. Reuse successful
  evidence only when its relevant files, commands and environment are unchanged;
  independent judgement does not require repeating every successful broad suite.
- During implementation, run the smallest deterministic check for the current
  task. Do not repeatedly run the same broad suite after edits outside its
  scope.
- For browser failures, save one diagnostic artifact (synthetic URL/state,
  relevant error and sanitized body excerpt). Do not rerun just for another
  tail/grep view of the same log. A retry needs changed input, implementation or
  an explicit new hypothesis; repeated failure without new evidence is
  NEEDS_CONTEXT/BLOCKED, not permission to widen scope. Never save credentials,
  cookies, tokens or real personal data in diagnostics.
- Run one structural static-analysis/type-check after the first stable migration batch,
  before broad regression tests. Scope it to changed production paths and
  separate migration errors from a confirmed baseline.
- Run final affected production static-analysis/type-check immediately before review if
  production code changed since the structural run. Otherwise reuse the
  structural result and record that no relevant code changed.
- Do not rerun a broad static-analysis command merely to reproduce known baseline
  errors. Use a narrower command for files changed after the baseline was
  established.
- Run stateful or database tests sequentially unless the repository explicitly
  guarantees isolated workers/databases. Parallelize only independent,
  stateless checks.
- Do not run database-backed checks concurrently across controller or worker
  sessions.
- Prefer the repository's compact human-readable test output. Use JSON only
  when a tool consumes it or compact output loses required diagnostics. Use an
  `agents`, parallel-worker, or process flag only when the runner documents it
  and test-state isolation is confirmed.
- Before final review, collect one concise affected-only evidence set: focused
  behavioral tests, deterministic migration searches, final static analysis,
  and repository-required hygiene checks.
- Pass a compact manifest to the controller and reviewer. Its exact content is
  defined once, in `measurement.md`; do not redefine it per dispatch.

## Final review

Run one independent, read-only review only after the diff is stable and final
verification evidence is collected. Follow the host's explicit delegation and
review policy; this skill does not grant an exception to it. If independent
review cannot run, report the incomplete gate, never a self-reviewed PASS.
Do not launch reviewers per task
or change code while reviewing. Its recorded PASS is the input to `archive`, not
a review to repeat during archival. A new reviewer is required only for a new
executable diff — detected mechanically via `review_snapshot.py`, see
`apply.md` — updates limited to evidence, capability documents, or archive
material retain the existing PASS. A targeted re-review (after fixes) reads
only the prior round's findings and the files the snapshot shows changed since
that round, not the full spec/plan/diff again; see `subagent-routing.md`'s
targeted re-review dispatch example.

Before an initial review, reconcile `plan.md`'s `Review scope` with the actual
executable diff. Snapshot computation reads only this literal-path scope and
the synthetic specification contract; task `Files:` remains implementation
metadata and may contain symbols. Add a new or previously unplanned executable
file to Review scope before review. Use `!path` for an intentional deletion.

Check four things, in this order. The reviewer's role profile defines the
response format; this list defines the scope.

- **Completeness** — every requirement maps to implementation and verification, every task is complete, no planned integration is missing.
- **Correctness** — acceptance scenarios are represented in tests or deterministic verification, error and boundary behavior matches the specification, tests assert observable behavior.
- **Coherence** — implementation follows the chosen architecture and repository conventions, interfaces and names are consistent, no unrelated scope was added.
- **Regression risk** — related existing tests pass, compatibility is preserved where required, migration and rollback obligations are satisfied.

Before reporting `BLOCKER` or `IMPORTANT`, try to falsify the finding: check
schema constraints, persisted-data invariants, public contracts, existing
tests, scenario reachability, and dirty-worktree attribution. Run the smallest
read-only check that can confirm or disprove the consequence.

Classify findings:

- `BLOCKER`: unmet requirement, incorrect behavior, security/data risk, or unsafe completion claim.
- `IMPORTANT`: likely defect, significant scenario gap, or material deviation.
- `MINOR`: maintainability improvement that does not block correctness.

Fix every confirmed finding, `MINOR` included, inside the same apply run. Leave a
finding open only when fixing it would leave the approved scope or contradict
`spec.md`, or when the user explicitly accepts a bounded deferral; record the
decision next to the finding. After a FAIL, dispatch the one targeted re-review
immediately, without waiting for the user; the explicit `specadoc apply`
invocation already authorizes it. Stop and report instead of fixing again if a
re-review returns new BLOCKER or IMPORTANT findings. The cap on new-diff review
rounds is enforced at `pre-review`, before the next reviewer is dispatched; it is
not a completion gate after an allowed round has passed. See `apply.md`.

A PASS with only MINOR findings closes the review. Fix the MINOR findings:
- changes only to tests or prose (test directories, `*_test.go`, `*.test.*`/`*.spec.*`
  scripts, `*.md`/`*.rst`/`*.adoc`) need
  no new round; the final gate accepts them and asks you to name them in the
  Archive summary;
- executable fixes take one `re-review`, recorded as `minor-fixes`; it does not
  count toward the cap and is never chained. MINOR findings it returns are
  recorded as residual risks.

Correction rounds stay `re-review`; new user requirements or polish use a
justified `initial` round. Persist each result with `review-result` before asking
the user. A blanket archive request is not a round-cap override. Extra-round
decisions are consumed by the named round. If code or approval changes during
review, the returned verdict is saved as stale/FAIL against the original
manifest; reconcile Review scope and start the next round without restoring old
code.

## Completion gate

Declare completion only when:

- All plan tasks are checked.
- Every requirement has implementation evidence.
- Every acceptance scenario has a test or explicit deterministic verification.
- Focused and relevant regression tests pass.
- Required build, lint, type-check, and repository checks pass.
- Final review is complete and its recorded PASS is ready for archive.
- No `BLOCKER` or `IMPORTANT` finding remains.
- Final evidence is persisted in `plan.md`, including the requirement-to-check
  matrix, the per-execution token finals, and the review-round count
  (`measurement.md`).
