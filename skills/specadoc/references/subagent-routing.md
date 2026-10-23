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

Use `worker` only when:
- one task is fully specified and has low decision risk;
- relevant files and interfaces are known;
- expected behavior is explicit;
- a deterministic verification command exists;
- no material behavior, architecture, authorization, schema, ownership, or
  compatibility decision remains.

The overall change may be high risk. Delegate bounded tests, mechanical
migrations, and scoped static-analysis fixes when their task-level decision risk
is low. A task with `Decision risk: low` defaults to `worker` even when the
overall change is high risk — running tools and fixing what they find is
worker's job, not controller's, and expensive controller time
is for tasks that carry real decision risk, not for rg sweeps, full test runs,
or static-analysis cleanup. Keeping such a task on `controller` requires a
`**Controller justification:**` line on the task naming the specific exception
below (e.g. the one-file, one-cycle fix exception) — `validate_change.py`
rejects `Owner: controller` + `Decision risk: low` without one.

Size each worker task so its startup is worth it: merge adjacent mechanical
tasks into one when they share files and one Verification command, and keep
tasks with different risk areas separate. Never merge a task into the
reviewer's work.

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
- Prefer direct controller execution for a one-file, one-cycle fix when handoff
  overhead exceeds the expected context savings. This is mandatory for a small
  UI follow-up: one controller, one final build, and one browser check; do not
  fan out browser screenshots or parallel visual investigations.

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

Use this for every worker dispatch when the scripts are available, and always
for a worker on another runtime (see `runners.md`):

1. `python3 <skill-root>/scripts/specadoc_step.py dispatch <slug> T<n>` runs
   `review_snapshot.py baseline`, which records the whole working tree, and
   `task_brief.py`, which writes `runs/T<n>-brief.md`. FAIL lists `Files:`
   items that are not paths; fix them in the plan before dispatching. The
   dispatch prompt is then only: the brief path, the report path
   `runs/T<n>-report.md`, and any context added after a previous NEEDS_CONTEXT.
2. After the worker returns and before reading its report, run
   `python3 <skill-root>/scripts/specadoc_step.py accept <slug> T<n> --verify`.
   It runs `review_snapshot.py check-scope`; FAIL lists every change outside
   the task's `Files:` or under the artifact root: revert or justify each
   before acceptance; never widen `Files:` after the fact to make the check
   pass. Inspect Verification and obtain any host-required approvals first:
   `--verify` executes shell commands with the caller's permissions. The field
   must contain only exact backticked commands, separated by semicolons; prose
   with inline code returns BLOCKED for manual verification. Scope is checked
   again after verification. The worker's report is a claim, not evidence.
   Without `--verify`, PASS covers scope only, not task acceptance.

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

## Escalation

Keep work in the controller, or advise a stronger role binding (`model-routing.md` → Binding advice), when:

- Requirements remain ambiguous.
- Architecture must be selected.
- A material public-contract, schema, permission, money, migration, security,
  concurrency, or sensitive-data decision remains.
- A worker attempt failed.
- Review findings conflict with the specification.

After a failed delegation, add missing context, split the task, revise the plan, or escalate. Never repeat an unchanged delegation prompt.
