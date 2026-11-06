# Apply mode

Load this reference only for `specadoc apply <slug>`.

1. Require validated spec/plan and recorded approval before edits. A fresh
   session orients from `specadoc_step.py status <slug>`, `runs/handoff.md` and
   the task brief, never whole spec/plan/design. `status` prints observed context
   and session advice; `dispatch` blocks near 200k: save notes with `handoff
   <slug> --file -` and resume in a new session. Claude Code context is read
   automatically; other hosts pass `--context-tokens <n>`, never an invented count.
2. Close material decisions before RED. A ready task goes to a worker; the
   controller keeps tasks with open decisions or a Controller justification
   (`subagent-routing.md` → Routing policy). A worker task names bounded
   `Decisions`, `Interfaces`, `Depends on` and `Test context`; `Files` cover code
   and tests, `Derived files` generated or wiring paths. A lockfile is derived when
   its manifest is in scope (`package.json` here or in a workspace package below,
   `go.mod` for `go.sum`, a same-stem manifest for `<stem>.lock`). `low` risk does
   not authorize architecture, catalog, contrast or compatibility decisions.
3. `specadoc_step.py dispatch <slug> T<n>` checks readiness, paths, commands,
   routing and a current design review (`design-gate.md`), then writes
   baseline/brief; it runs no Verification. `preflight` is an optional dry check;
   retries keep the first baseline. A controller task uses the same gates without
   a worker. One fully specified worker task at a time; serialize overlapping
   writers. Routed projects pass `--controller-runtime` or rely on
   `roles.controller.runtime` (`subagent-routing.md`).
4. The implementer uses RED-GREEN-REFACTOR; a `TDD exception` names the
   deterministic check for mechanical work. REFACTOR may include
   optional behavior-preserving cleanup (`interoperability.md`). Task checks are
   focused; the full suite runs once in Final verification.
5. The implementer ends with `report <slug> T<n> --status … --summary … --red …
   --green …`. Read the report, then `accept <slug> T<n>`: it validates the
   result JSON, runs Verification (reused only for unchanged inputs, commands and
   environment), checks scope and on **ACCEPTED** records Evidence and Accepted
   result. Concerns give **NEEDS_DECISION**: rerun with `--note '<decision>'`. A
   BLOCKED report whose blocker the parent or controller removed takes
   `--resolved '<who and how>'`; never rewrite a worker report. A task with
   `External verification:` gives **EXTERNAL-PENDING**: dependents and review may
   start; record the run with `external-result <slug> T<n> --outcome PASS|FAIL
   --evidence '<run>'` (FAIL returns it to work; correct a recorded result with
   `--supersede '<why>'`, never edit `runs/*.json`). A status is a claim, not evidence.
6. Controller runs final affected-only checks once, records observed Build/Typecheck
   PASS and Browser URL/state for UI, and fills literal Review scope from the
   executable diff (`!path` means deleted).
7. On a stable diff, `pre-review <slug>` records the round; then
   run one independent read-only `reviewer` (a fresh agent). On return, before anything else, run
   `review-result <slug> --from-agent <id>` (native) or `--result-file <reply>`
   (external); never transcribe the reply.
8. Fix confirmed findings in scope, then one targeted `pre-review <slug>
   --review-type re-review` on prior findings and changed files, without waiting
   for the user. After a PASS with only MINOR findings, fix them: test/doc-only
   fixes need no round, executable ones one `re-review` (`minor-fixes`, outside the
   cap). Defer a MINOR only by a parent or user decision, as a residual risk
   (`tdd-and-review.md`). New BLOCKER/IMPORTANT after a re-review: stop and ask.
9. On PASS, update the capability specs spec.md declares (`status` names a
   missing one), the Archive summary (name post-review MINOR fixes) and residual
   risks, collect tokens after all rounds, then `validate_change.py <slug>
   --phase final`. Archive only when asked.

### Exceptions

- **Scope.** Fix a missing-context brief and resume the same worker. A required
  path outside the task: `amend <slug> T<n> --allow|--derived <path> --reason
  '<decision>'`; controller edits after review: `refresh <slug> --controller-path
  <p> --reason '<finding>'` (all tasks at once; acceptances kept).
  Verification and plan approval are frozen at dispatch; only `amend` changes
  them. Never widen Files silently.
- **Stale evidence.** `refresh <slug>` re-accepts stale tasks in dependency
  order with their report and frozen Verification, listing every failure. Without `Verification inputs` any later edit
  makes a task stale; declare them when checks are narrow.
- **Corrective work.** `dispatch <slug> T<n> --reopen '<reason>'` archives the
  attempt and starts from the current tree; only for code fixes, not staleness.
- **Review rounds.** New requirements: `--review-type initial --reason
  requirements`; polish: `--reason polish`; corrections stay `re-review`. A
  fourth `initial` needs `--review-decision '<decision, author, scope>'`. One
  documentation-only follow-up is allowed after a documentation-only FAIL.
- **Size.** Over eight tasks warns; add T9 rather than fold work into a done task.
- `pre-review --dry-run` prints the snapshot without recording;
  `review_snapshot.py diff <slug> --previous G<n>` lists changes since a round.

## Reading order

| Reference | Read it when |
|---|---|
| `spec.md`, the task's `plan.md` section, its `Files:` targets, the relevant `AGENTS.md` | Before RED for that task |
| `subagent-routing.md` | Before dispatching a worker or reviewer subagent |
| `runners.md` | Before the first dispatch to a runtime other than the controller's |
| `measurement.md` | Before recording final evidence/tokens |
| `tdd-and-review.md` | Before a review round |
| `artifacts.md` | Only when changing spec.md/plan.md structure |
