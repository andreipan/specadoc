# Apply mode

Load this reference only for `specadoc apply <slug>`.

1. Require validated spec/plan and recorded explicit approval before edits.
   Start apply in a fresh session after propose. `dispatch` blocks at roughly 150k
   controller context: save a compact handoff and resume `apply <slug>` in a new
   session. Claude Code sessions are read automatically; other hosts pass the
   observed count with `--context-tokens <n>`. Never invent a count.
2. Close material decisions before RED. Tasks are controller-owned unless the
   plan marks a worker (`subagent-routing.md` → Routing policy). A worker task
   also names bounded
   `Decisions`, `Interfaces`, `Depends on` and `Test context`; its `Files` cover
   the code and tests, and `Derived files` covers generated or wiring paths
   (barrel exports, generated clients). A lockfile is derived when its manifest
   is in scope: `package.json` in its directory or a workspace package below it,
   `go.mod` for `go.sum`, or a same-stem manifest for `<stem>.lock`. A `low` label does not authorize architecture,
   catalog, contrast or compatibility decisions.
3. `specadoc_step.py dispatch <slug> T<n>` validates readiness, paths, commands
   and routing before writing baseline/brief; it executes no Verification.
   Optional `preflight <slug> T<n>` checks without writes; do not repeat it before
   dispatch. Retries keep the original baseline. A controller
   task uses the same gates without a worker and need not read its brief.
   Delegate one fully specified worker task at a time; serialize overlapping
   writers. Routed projects pass `--controller-runtime`; see `subagent-routing.md`.
4. The implementer, controller or worker, uses RED-GREEN-REFACTOR; an explicit `TDD exception` names the
   deterministic check for mechanical work. REFACTOR may include
   optional behavior-preserving cleanup (`interoperability.md`). Task checks
   are focused; the full suite runs once in Final verification.
5. Read the report, then `specadoc_step.py accept <slug> T<n>`. It validates the
   report JSON, runs Verification (reused only for unchanged content inputs,
   commands and environment), checks scope, and on **ACCEPTED** records Evidence, Evidence hash
   and Accepted result. One call reports both scope violations and check results.
   Concerns return **NEEDS_DECISION**: rerun with `--note '<decision>'`.
   A task with `External verification:` (integration on a shared database, a
   check allowed only after review) returns **EXTERNAL-PENDING**: dependents
   may start and review may open. Record the run with `external-result <slug>
   T<n> --outcome PASS|FAIL --evidence '<run and result>'`; `--phase final`
   needs a PASS on the current content. FAIL returns the task to work.
   A returned status is a claim, not evidence.
6. Controller runs final affected-only checks once, records observed Build/Typecheck
   PASS and Browser URL/state for UI, and fills literal Review scope from the
   executable diff (`!path` means deleted).
7. On a stable diff, `specadoc_step.py pre-review <slug>` records the pending
   round; then run one independent read-only `reviewer`.
   On return run `specadoc_step.py review-result <slug> --result-file <json>`
   before anything else, including a user question.
8. Fix confirmed findings within the approved scope, then
   `pre-review <slug> --review-type re-review` for one targeted round limited to
   prior findings and changed files, without waiting for the user. After a PASS
   with only MINOR findings, fix them: test/doc-only fixes need no new round;
   executable fixes take one `re-review` (recorded as `minor-fixes`, outside the
   round cap). New BLOCKER/IMPORTANT after a re-review: stop and ask.
9. On PASS, update capability specs, the Archive summary (name post-review MINOR
   fixes) and residual risks, collect tokens after all review rounds, then run
   `validate_change.py <slug> --phase final`. Archive only when asked.

### Exceptions

- **Scope.** Fix a missing-context brief and resume the same worker. For a
  required path outside the task: `amend <slug> T<n> --allow <path>` or
  `--derived <path>`, with `--reason '<decision>'`. Controller edits outside the
  artifact root use `--controller-path`. This change's `plan.md` is the
  controller's, but the task's Verification and the plan approval are frozen at
  dispatch; only `amend` changes them. Never widen Files silently.
- **Stale evidence after later tasks.** `specadoc_step.py refresh <slug>`
  re-accepts every stale accepted task in dependency order with its report and
  frozen Verification. Edits inside a later-dispatched task's `Files` are
  attributed to that task, not counted as scope violations. Without
  `Verification inputs`, a task's check inputs are the whole repository, so any
  later edit makes it stale; declare them when the checks are narrow.
- **Corrective task work after later tasks.** `dispatch <slug> T<n> --reopen
  '<reason>'` archives the previous attempt and report and starts from the current
  tree. Use it only for code fixes, not for stale evidence. Without `--reopen`, a
  retry compares against the first attempt.
- **Review rounds.** New user requirements use `--review-type initial --reason
  requirements`; optional polish uses `--reason polish`. Corrections stay
  `re-review`. The cap blocks a fourth `initial`; an extra round needs
  `--review-decision '<user decision and bounded scope>'` (a generic archive
  request is not one). One documentation-only follow-up stays allowed with an
  unchanged Snapshot/Policy after a documentation-only FAIL.
- **Size.** More than eight tasks is a warning; add T9 rather than folding new
  work into a completed task.
- `pre-review --dry-run` runs the gate and prints the snapshot without recording.
  `review_snapshot.py diff <slug> --previous G<n>` lists changes since a round.

## Reading order

Load references when needed, not all before RED.

| Reference | Read it when | Not before |
|---|---|---|
| `spec.md`, the current task's `plan.md` section, its `Files:` targets, and the relevant `AGENTS.md` scope | Before writing the failing test (RED) for that task | — |
| `subagent-routing.md` | Immediately before dispatching a worker or reviewer subagent | Not for a task the controller implements directly |
| `runners.md` | Before the first dispatch of a role whose runtime is not the controller's | Not when every role runs natively |
| `measurement.md` | Immediately before recording final evidence/tokens for a task | Not during RED/GREEN/REFACTOR |
| `tdd-and-review.md` | Immediately before initiating a review round | Not during implementation |
| `artifacts.md` | Only when authoring/updating spec.md/plan.md structure | Not needed during apply's TDD loop |
