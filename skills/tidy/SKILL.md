---
name: tidy
description: Behavior-preserving tidy of a task, diff, or named files during REFACTOR or on request — reuse, redundant complexity, wasted work, and fixes at the wrong depth. Not a correctness/security audit or an architecture redesign.
---

# Tidy

Improve the quality of changed code without changing observable behavior. Run it
before final verification and independent review; it replaces neither.

## Scope and authority

Use the supplied task, files, diff, commit range, or PR. With none, use this
task's changes, then staged/unstaged changes and relevant untracked source; if
still empty, ask rather than auditing the repository. A worker stays inside its
bounded task; the controller owns cross-task tidying and architecture decisions.
A read-only reviewer reports findings and never runs this skill. Preserve
unrelated user work. Read repository instructions, the changed code, its callers,
and nearby helpers using the host's tool routing.

## Four angles, one pass

- **Reuse:** new code duplicating an existing helper or pattern. Name the helper
  and confirm equal errors, side effects, and edge cases.
- **Simplification:** state that can be computed instead of stored, near-duplicate
  blocks, nesting or indirection a reader must unwind, code the change left unused.
- **Efficiency:** the same work or I/O done twice, steps that could overlap but
  wait on each other, slow work newly placed on startup or a frequent path,
  queries fetching more than needed.
- **Altitude:** a patch on one symptom or caller where changing the shared
  mechanism once is simpler. Keep public contracts and mandatory layers/ports.

Work through every angle yourself. Do not spawn agents unless the controller
explicitly authorized a bounded investigation.

## Apply and verify

Record each finding with `file:line`, a one-line description, and what it costs
to keep; combine findings that share a cause, then fix them. Leave a fix out, and
say why, when it alters intended behavior, spreads beyond the scope, depends on
equivalence you cannot show, or gains too little. Finding nothing is a valid outcome.
Route correctness/security defects and new architecture choices to the controller.

Run the relevant existing tests and allowed lint/type checks afterwards; state
missing checks instead of claiming equivalence. Executable edits after a review
PASS invalidate that snapshot and need fresh verification and review.

Report what was fixed, what was skipped and why, and the checks run. Do not
commit, push, or publish unless separately authorized.
