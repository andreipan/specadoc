# Subagent routing and dispatch contracts

## Responsibility split

- `SKILL.md` controls the workflow and decides which role to invoke.
- The runtime's role registry defines each role's persistent specialization, model tier, reasoning level, permissions, prohibitions, and output contract: `.claude/agents/*.md`, `.codex/agents/*.toml`, or `.opencode/agents/*.md`. See `model-routing.md` → Role registry.
- The dispatch prompt supplies the current task, files, requirements, commands, and completion condition.

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
worker's job, not controller's, and expensive execution levels (`opus`/`high`)
are for tasks that carry real decision risk, not for rg sweeps, full test runs,
or static-analysis cleanup. Keeping such a task on `controller` requires a
`**Controller justification:**` line on the task naming the specific exception
below (e.g. the one-file, one-cycle fix exception) — `validate_change.py`
rejects `Owner: controller` + `Decision risk: low` without one.

Use `reviewer` after implementation when:
- the complete diff and specification are available;
- verification evidence has been collected;
- an independent result is required.

Keep work in the controller when:
- requirements remain materially ambiguous;
- architecture must be selected;
- the task itself requires a material authorization, money, sensitive-data,
  migration, concurrency, public-compatibility, or irreversible decision;
- a worker has already returned BLOCKED;
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
Investigate how Accounts synchronizes Google customer clients today.

Read:
- AGENTS.md and src/Modules/AGENTS.md
- src/Modules/Accounts/Application/Services/GoogleAccounts/
- src/Modules/Accounts/Infrastructure/GoogleAccounts/
- tests and contracts discovered during the investigation

Find:
- the queue entry point and the identity carried in its payload;
- where connector credentials are resolved for a center;
- the nearest behavioral tests under src/Tests/Feature/Modules/Accounts/;
- the exact focused test command for that area.

Use rtk for every shell command. Do not edit files.
Return the standard scout report.
```

## Worker dispatch example

```text
Implement task T5 from docs/agent/sync-google-accounts-architecture/plan.md.

Requirements:
- R4
- Acceptance scenarios A3 and A4

Read:
- docs/agent/sync-google-accounts-architecture/spec.md
- the T5 section of plan.md
- src/Modules/Accounts/Application/UseCases/SyncAccountsAgainstGoogle/Handler.php
- src/Modules/Accounts/Infrastructure/Queue/Jobs/SyncGoogleAccountsJob.php
- src/Tests/Unit/Modules/Accounts/Application/UseCases/SyncAccountsAgainstGoogle/HandlerTest.php
- AGENTS.md and src/Modules/AGENTS.md

Constraints:
- Keep the queue job a transport-only wrapper (src/Modules/AGENTS.md §1.1).
- Do not change the command signature or schedule.
- Do not edit spec.md or other plan tasks.

Test first:
Add a test proving the handler delegates stale cleanup to the repository.

Verification:
rtk php artisan test --compact src/Tests/Unit/Modules/Accounts/Application/UseCases/SyncAccountsAgainstGoogle/HandlerTest.php
rtk vendor/bin/phpstan analyse --configuration=phpstan-modules.neon src/Modules/Accounts/Application src/Modules/Accounts/Infrastructure

Completion:
A3 and A4 pass, existing Accounts UseCase tests pass, and no unrelated files change.
```

## Reviewer dispatch example

```text
Review the implementation of Google accounts synchronization.
Follow the `review-changes` skill, which defers CRG staleness handling to
`repo-mcp-router` → MCP and graph checks.

Read:
- docs/agent/sync-google-accounts-architecture/spec.md
- docs/agent/sync-google-accounts-architecture/plan.md
- the diff from the plan baseline to the current worktree
- AGENTS.md and src/Modules/AGENTS.md

Review only:
- R1, R2, R4
- A1, A3, A4
- tasks T1-T6

Verification evidence:
- rtk php artisan test --compact src/Tests/Feature/Modules/Accounts/Application/Services/GoogleAccounts: passed
- affected production PHPStan over src/Modules/Accounts: passed; tests were not analysed
- rtk git diff --check: passed

Use rtk for every shell command. Do not edit files.
Use the standard reviewer response.
```

## Targeted re-review dispatch example

The one authorized re-review after fixes reads only what changed, not the full
spec/plan/diff again:

Compute the changed list from the prior and current `Review scope` manifests.
Do not derive it from task `Files:`, which may contain symbols rather than
literal paths.

```text
Re-review the fixes for BLOCKER/IMPORTANT findings from Round 1 only.

Changed since Round 1's snapshot (recomputed via review_snapshot.py):
- src/Modules/Accounts/Application/UseCases/SyncAccountsAgainstGoogle/Handler.php (content changed)
- src/Tests/Unit/Modules/Accounts/Application/UseCases/SyncAccountsAgainstGoogle/HandlerTest.php (content changed)

Read:
- the Round 1 findings recorded in plan.md's Review result (### G1)
- the current content of exactly the files listed above
- the spec.md requirement and plan.md task sections named in those findings only

Do not re-read the full spec.md, full plan.md, or any file not listed above as
changed. Confirm each Round 1 finding is resolved and that the fix introduced
no new violation of the same requirement.

Use rtk for every shell command. Do not edit files.
Use the standard reviewer response.
```

## Escalation

Keep work in the controller or move to a stronger execution level when:

- Requirements remain ambiguous.
- Architecture must be selected.
- A material public-contract, schema, permission, money, migration, security,
  concurrency, or sensitive-data decision remains.
- A worker attempt failed.
- Review findings conflict with the specification.

After a failed delegation, add missing context, split the task, revise the plan, or escalate. Never repeat an unchanged delegation prompt.
