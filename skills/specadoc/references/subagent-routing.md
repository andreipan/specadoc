# Subagent routing and dispatch contracts

## Responsibility split

- `SKILL.md` controls the workflow and decides which role to invoke.
- The runtime's role registry defines each role's persistent specialization, model tier, reasoning level, permissions, prohibitions, and output contract: a project role (`.claude/agents/*.md`, `.codex/agents/*.toml`, `.opencode/agents/*.md`) or the role shipped with this plugin. See `model-routing.md` → Binding resolution for the lookup order. Project `.specadoc.json` selects the runtime, not the model; the target registry supplies model and effort at each dispatch (`project-config.md`).
- The dispatch prompt supplies the current task, files, requirements, commands, and completion condition.

When the runtime has no registered role but can start subagents, include only
the selected `roles/<role>.md` portable contract from this reference directory
in the prompt. Project roles take precedence; follow `model-routing.md` for
binding resolution and the no-subagent fallback. Do not write host agent configs.

Do not place task-specific paths, requirement IDs, or feature details in the role profiles.

## Role boundaries

- `scout`: decide which facts are relevant to the investigation.
- `worker`: decide how to execute one already-defined task inside fixed boundaries.
- `reviewer`: decide whether the implementation satisfies the contract.
- `controller`: own requirements, architecture, routing, escalation, and acceptance.

## Routing policy

Use `scout` for bounded read-only repository investigation.

An explicitly requested archive run is ready work for a `worker` although it is
not a T-task (`archive.md` → Delegate the run to a worker).

A `worker` implements every task that is ready for it. The controller's
context is the scarce budget: implementing each task itself grows the
controller session until it must be replaced, and every replacement re-reads
the plan. A task is ready for a worker when:
- it is fully specified and has low decision risk;
- relevant files and interfaces are known;
- expected behavior is explicit;
- an exact deterministic Verification command exists;
- no material behavior, architecture, authorization, schema, ownership, or
  compatibility decision remains.

The controller keeps a ready task only with a recorded `Controller
justification`: an edit smaller than its brief, or a decision the controller
must make while editing. `validate_change.py --phase plan` warns on a ready
controller task without one. The overall change may be high risk; these
criteria apply per task. Never move decision-heavy work to a worker to save
controller context; prefer a session boundary (`model-routing.md` → Session
boundaries). The worker ends with `specadoc_step.py report`; the controller
reads the report and runs `accept`.

Size each worker task so its startup is worth it: merge adjacent mechanical
tasks into one when they share files and one Verification command, and keep
tasks with different risk areas separate. Never merge a task into the
reviewer's work.
Apply this before dispatch; do not fold corrective work into a completed task.

Before dispatch, check that Decisions/Interfaces are settled and Files covers
required wiring, exports, lockfiles and dependent tests. Record `Depends on`
and reuse the dependencies' **Accepted result**, not a stale historical report.
If an upstream catalog, contrast target, ownership boundary or compatibility
choice is unresolved, the controller decides before assigning `Decision risk: low`.

Use `reviewer` after implementation when:
- the complete diff and specification are available;
- verification evidence has been collected;
- an independent result is required.

Keep work in the controller when:
- requirements remain materially ambiguous;
- architecture must be selected;
- the task itself requires a material authorization, money, sensitive-data,
  migration, concurrency, public-compatibility, or irreversible decision;
- a worker has already returned BLOCKED (a decision is missing; NEEDS_CONTEXT
  only means add the named context and dispatch again);
- reviewer findings conflict with the specification.

## Execution safety

- Use at most one writer at a time when task files overlap.
- Run database-backed tests sequentially across all agents.
- Do not make a reviewer depend on a scout summary for correctness findings.
- A reviewer may use one bounded scout only for large-diff inventory and must
  inspect critical evidence itself.
- A small UI follow-up stays with one controller, one final build, and one
  browser check; do not fan out browser screenshots or parallel visual
  investigations.
- A task with `Owner: controller` uses the same gates: `dispatch` records its
  baseline without routing a worker (the brief need not be read) and `accept`
  verifies the report, scope and exact checks. It does not waive approval, TDD,
  final verification or independent review.

## Scout dispatch example

```text
Investigate how Billing sends overdue-invoice reminders today.

Read:
- AGENTS.md and src/billing/AGENTS.md
- src/billing/reminders/
- src/billing/jobs/
- tests and contracts discovered during the investigation

Find:
- the scheduled entry point and the identity carried in its payload;
- where the mail provider credentials are resolved for an account;
- the nearest behavioral tests under tests/billing/;
- the exact focused test command for that area.

Follow the repository's command conventions. Do not edit files.
Return the standard scout report.
```

## Worker dispatch example

```text
Implement task T5 from docs/specadoc/overdue-invoice-reminders/plan.md.

Requirements:
- R4
- Acceptance scenarios A3 and A4

Read:
- docs/specadoc/overdue-invoice-reminders/spec.md
- the T5 section of plan.md
- src/billing/reminders/send-reminders.ts
- src/billing/jobs/send-reminders-job.ts
- tests/billing/reminders/send-reminders.test.ts
- AGENTS.md and src/billing/AGENTS.md

Constraints:
- Keep the job a transport-only wrapper (src/billing/AGENTS.md §1.1).
- Do not change the job signature or schedule.
- Do not edit spec.md or other plan tasks.

Test first:
Add a test proving the handler skips invoices that were already reminded today.

Verification:
npm test -- tests/billing/reminders/send-reminders.test.ts
npx tsc --noEmit -p src/billing

Completion:
A3 and A4 pass, existing billing reminder tests pass, and no unrelated files change.
```

## Reviewer dispatch example

```text
Review the implementation of overdue-invoice reminders.
Follow the repository's review skill or checklist when one is installed.

Read:
- docs/specadoc/overdue-invoice-reminders/spec.md
- docs/specadoc/overdue-invoice-reminders/plan.md
- the diff from the plan baseline to the current worktree
- AGENTS.md and src/billing/AGENTS.md

Review only:
- R1, R2, R4
- A1, A3, A4
- tasks T1-T6

Verification evidence:
- npm test -- tests/billing/reminders: passed
- affected production type-check over src/billing: passed; tests were not analysed
- git diff --check: passed

Follow the repository's command conventions. Do not edit files.
Use the standard reviewer response.
```

## Targeted re-review dispatch example

The one authorized re-review after fixes reads only what changed, not the full
spec/plan/diff again:

Compute the changed list from the prior and current `Review scope` manifests.
Do not derive it from task `Files:`, which may contain symbols rather than
literal paths.

```text
Re-review every confirmed finding fixed since Round 1, including MINOR.

Changed since Round 1's snapshot (recomputed via review_snapshot.py):
- src/billing/reminders/send-reminders.ts (content changed)
- tests/billing/reminders/send-reminders.test.ts (content changed)

Read:
- the Round 1 findings recorded in plan.md's Review result (### G1)
- the current content of exactly the files listed above
- the spec.md requirement and plan.md task sections named in those findings only

Do not re-read the full spec.md, full plan.md, or any file not listed above as
changed. Confirm each Round 1 finding is resolved and that the fix introduced
no new violation of the same requirement.

Follow the repository's command conventions. Do not edit files.
Use the standard reviewer response.
```

## File-based worker handoff

For browser tasks, put a bounded `Test context` in the task: a verified test
exemplar, bootstrap/login helper, test-only environment, exact focused command,
and relevant runbook section. The brief already carries task fields; do not
paste the whole runbook or invent a new handoff system.
For every task, reuse known exact commands/configuration and permission limits
in `Test context`. Optional `Verification inputs` names read-only config, helpers
and tool paths needed by the checks; it grants no write scope. Do not probe an
unknown wrapper with `--help` if that might execute its default gate.

Use this for every worker dispatch when the scripts are available, and always
for a worker on another runtime (see `runners.md`):

1. `python3 <skill-root>/scripts/specadoc_step.py dispatch <slug> T<n>` checks
   plan approval, dependency readiness and bounded decisions, records the original
   whole-tree baseline and writes `runs/T<n>-brief.md`. Retries retain the baseline.
   FAIL lists invalid `Files:` items or unapproved changes; resolve them before dispatch. The
   dispatch prompt is then only: the brief path, the report path
   `runs/T<n>-report.md`, and any context added after a previous NEEDS_CONTEXT.
2. Read the worker report and its concerns, then run
   `python3 <skill-root>/scripts/specadoc_step.py accept <slug> T<n>`.
   Obtain any host-required approvals first: it executes the task's Verification
   with the caller's permissions. The field must contain only exact backticked
   commands separated by semicolons; prose returns BLOCKED for manual checks.
   `accept` validates the report JSON, runs Verification (reused automatically
    when owned files, verification inputs, commands and environment are unchanged), and checks scope before and
   after. One call reports scope violations and check results together.
   `derived:` lists Derived-file and lockfile changes; they are not violations.
   **ACCEPTED** records Evidence, Evidence hash and Accepted result in `plan.md`.
   Concerns return **NEEDS_DECISION**; rerun with `--note '<actual decision>'`,
   which also records controller corrections. `--scope-only` gives **CHECKED**,
   never acceptance. For a required out-of-scope path use
   `amend --allow <path>` or `--derived <path>` with `--reason`; controller edits
   outside the artifact root use `--controller-path`. Preserve the original
    baseline and report; never silently widen Files.
3. `specadoc_step.py manifest <slug> T<n>` prints actual baseline-relative changed
   paths and literal Review scope bullets for the report, without editing either.
   Run it before acceptance/next dispatch; preserve unrelated dirty files and
   inspect the proposed paths. Scope violations fail instead of being adopted.

Every step prints the same five fields (`checked`, `result`, `changed files`,
`blocking reason`, `next`) and only the tail of a failing command. The
underlying scripts stay available for a single check.

One writer at a time: the baseline belongs to one task; do not edit the working
tree while a worker runs.

## Worker status handling

- `DONE` — run check-scope and Verification, then accept.
- `DONE_WITH_CONCERNS` — resolve or record each concern before acceptance.
- `NEEDS_CONTEXT` — add exactly the named context and dispatch again; this is
  not a failed attempt.
- `BLOCKED` — the controller makes the missing decision (or asks the user),
  updates the plan, and only then dispatches again; see Escalation.

Dispatch every scout, worker, tidy worker and reviewer in the foreground, never
with `run_in_background: true`: Claude Code's Agent tool starts sub-agents in the
background by default, so pass `run_in_background: false`. Background work led to
reading the code yourself and to polls (4.10: a 120 s timeout, a TaskStop, two
sleep polls; 5.1: a background scout, `select` polls and propose at 169k; a
background tidy and a `sleep 20` loop). A resumed
task worker (a follow-up message to a finished one) answers asynchronously:
right after the message run `specadoc_step.py wait <slug> T<n>`, which returns on
a new report of any status or after its timeout; it knows task reports only,
not scouts, reviewers, tidy or archive workers. For those, end the turn and
take the host's completion notice. Never poll an agent's output file or run a
sleep loop: a reply reaches the controller only when the running command
returns (4.3: a scout report waited 9 minutes, 4.5: a NEEDS_CONTEXT waited 10
minutes behind a loop that exited only on DONE, 4.10: an archive worker was
polled with `sleep 5`).

## Escalation

Keep work in the controller, or advise a stronger role binding (`model-routing.md` → Binding advice), when:

- Requirements remain ambiguous.
- Architecture must be selected.
- A material public-contract, schema, permission, money, migration, security,
  concurrency, or sensitive-data decision remains.
- A worker attempt failed.
- Review findings conflict with the specification.

After a failed delegation, add missing context, split the task, revise the plan, or escalate. Never repeat an unchanged delegation prompt.

Distinguish transport failure from task failure. First inspect the existing
session, report and diff; a lost response may accompany finished work. Resume the
same native session with its original baseline. For external processes, inspect
`run_role.py status` before waiting, stopping or starting a named retry. A
buffered Claude log is not evidence of a stall. Record introduced integration
debt and the task that closes it; do not call it an unrelated pre-existing failure.
