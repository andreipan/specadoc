# Plan structure

[Русский](../../ru/reference/plan-structure.md)

This page lists the sections of each Specadoc artifact and the size limits.
For each section, it says whether a command writes it or a person writes it by
hand. The templates are in
[`skills/specadoc/assets/`](../../../skills/specadoc/assets/). For the reasons
behind the artifacts and gates, read
[Artifacts and gates](../concepts/artifacts-and-gates.md).

`<root>` is the artifact root, `docs/specadoc` by default (see
[Configuration](config.md#artifact-root)). `<skill-root>` is the installed
`skills/specadoc` folder.

## Layout of the artifact root

| Path | Content | Lifetime |
|---|---|---|
| `<root>/<slug>/spec.md` | The behavioral contract of one change | Until archive |
| `<root>/<slug>/plan.md` | Tasks, decisions, approvals and evidence | Until archive |
| `<root>/<slug>/design.md` | Design decisions, only when required | Until archive |
| `<root>/<slug>/research.md` | Research evidence, only when required | Until archive |
| `<root>/<slug>/runs/` | Transient role handoff files, ignored by git | Removed by archive |
| `<root>/archive/<slug>/record.md` | The compact record of a closed change | Permanent, never reopened |
| `<root>/specs/<capability>.md` | The current behavior of one capability | Permanent, updated by changes |
| `<root>/contracts/<contract>.md` | A cross-service contract, in the repository of the shared package | Permanent |

`init_change.py` creates `spec.md` and `plan.md` from the templates. With
`--with-design` and `--with-research`, it also creates `design.md` and
`research.md`. It fills the title, risk, date and scout fields. Do not create
`tasks.md`, unless a repository workflow with higher priority requires it.

## Who writes what

In the tables below, "by hand" means the controller or the user edits the text.
"Command" names the script step that writes the text. Do not edit text that a
command writes. Run the command again instead.

## spec.md

`spec.md` is the stable behavioral contract. It changes little after approval.
Template: [`spec-template.md`](../../../skills/specadoc/assets/spec-template.md).

| Section | Required | Written by | Content |
|---|---|---|---|
| Header: `Status`, `Risk`, `Created` | Yes | `init_change.py` (risk, date), by hand (status) | One risk value. It must match the plan and design headers. |
| `## Goal` | Yes | by hand | The observable outcome for a user or system. |
| `## Non-goals` | Yes | by hand | Behavior that the change excludes. |
| `## Current context` | Yes | by hand | Only the current behavior and constraints needed to understand the change. |
| `## Affected capabilities` | Yes | by hand | The capability operations, see below. |
| `## Requirements` | Yes | by hand | `### R<n> — <name>` blocks with observable, testable behavior. |
| `## Acceptance scenarios` | Yes | by hand | `### A<n> — <name>` blocks with `Covers:`, `Given:`, `When:` and `Then:`. |
| `## Constraints` | Yes | by hand | Compatibility, security, platform, dependency and performance constraints. |
| `## Assumptions` | Yes | by hand | Safe defaults selected instead of low-impact questions. |
| `## Requirement coverage` | Yes | by hand | A table that maps each requirement to its scenarios. |

Rules:

- Each behavioral requirement maps to at least one acceptance scenario.
- Requirements contain no file paths, classes, frameworks or implementation
  order.
- No behavior-changing question stays open when the spec is ready.

The review snapshot covers four spec sections: Requirements, Acceptance
scenarios, Constraints and Affected capabilities. A change to them after a
review PASS makes the PASS stale. `approve` stores a hash of `spec.md` and
`design.md` in `runs/approval.json`.

### Affected capabilities

The section lists each capability spec, followed by the capability operations
on its `C<n>` requirements:

```text
- `docs/specadoc/specs/platform-connection-storage.md`
  - RENAMED C2 (R3) — The identifier is a `cnx_` ULID
  - REMOVED C3 (R6)
  - MODIFIED C5 (R6) — deleting a bound application no longer detaches the connection
  - ADDED C8 (R7) — A connection carries an owning agency
```

- Write the operations in the order `RENAMED`, `REMOVED`, `MODIFIED`, `ADDED`.
- Cite at least one requirement in parentheses after the `C<n>` id. Cite every
  requirement that the operation implements.
- For a new capability spec, write `(new capability)` after the path. Then only
  `ADDED` is valid.

`validate_change.py --phase spec` checks the syntax and the order. It also
checks that each `MODIFIED`, `REMOVED` and `RENAMED` id exists in the target
file, and that no `ADDED` id collides with an existing id. The final gate
(`validate_change.py --phase final`) and `archive_change.py` check that the
capability spec contains the result.

## plan.md

`plan.md` is the mutable technical state: tasks, decisions, approvals and
evidence. Template: [`plan-template.md`](../../../skills/specadoc/assets/plan-template.md).
The template is normative. A change to the template changes the plan gate.

| Section | Required | Written by | Content |
|---|---|---|---|
| Header: `Status`, `Mode`, `Specification`, `Risk`, `Scout`, `Created` | Yes | `init_change.py`, `approve` (status) | `approve` sets `Status: Approved, apply not started`. |
| `## Handoff` | Yes | by hand, `approve` and `review-result` (`Plan checkpoint`) | The plan checkpoint, `### Read before continuing`, `### Completed phases`, `### Continue with`. |
| `## Reconnaissance evidence` | Yes | by hand | At most 8 paths or symbols, 5 reusable patterns, exact verification commands, confirmed constraints. |
| `## Confirmed decisions` | Yes | by hand, `design-brief --attempt-decision continue:` | One line for each settled decision, with who settled it. |
| `## Technical approach` | Yes | by hand | Written after the spec is ready. |
| `## Migration matrix` | Conditional | by hand | Only for mechanical namespace, path, symbol or type migrations. Delete it otherwise. |
| `## Global constraints` | Yes | by hand, `design-brief --attempt-decision accept:` | Constraints for all tasks. Design obligations go here. |
| `## Files and interfaces` | Yes | by hand | A table of path or symbol, action and responsibility. |
| `## Class inventory` | Conditional | by hand | Every new non-test file: file, layer, reason, kind (`port`, `concrete` or `file`). Delete the example row if the change adds no such file. |
| `## Design review` | With a Class inventory | `design-review` | The design verdict, bound to the inventory hash. |
| `## Tasks` | Yes | by hand, `accept`, `amend`, `external-result` | `### T<n> — <outcome>` blocks, see [Task fields](#task-fields). |
| `## Requirement-to-check matrix` | Yes | by hand, `finalize --requirements` (status) | One row for each requirement: scenarios, exact check, status. |
| `## Plan approval` | Yes | `approve` | `Status`, `Bindings shown`, `Approved at`, `Approval provenance`. |
| `## Review scope` | Before review | `scope` | One backticked repository-relative file path per bullet. `!path` for a deleted file. |
| `## Final verification` | Yes | `finalize` | Checkboxes and the `Observed (<time>):` line. |
| `## Review result` | Yes | `pre-review`, `review-result` | `Result`, `Reviewed requirements`, `Reviewed tasks`, `### Findings`, `### Round log`. |
| `## Archive summary` | Yes | by hand | The durable outcome, accepted decisions, capability impact and residual risks. |
| `## Completion evidence` | Yes | `finalize`, `collect_tokens.py --append` | Commands, requirement mapping, execution tokens, review rounds, residual risks. |

`validate_change.py` requires the sections marked "Yes". Delete only the
sections that the template marks as conditional.

### Handoff

Session notes do not go in `plan.md`. Write them to `runs/handoff.md` with
`specadoc_step.py handoff <slug> --file -`. The step overwrites the file each
time.

`### Read before continuing` is the start list of a fresh `apply` session. It
names the `status` output, `runs/handoff.md`, `spec.md`, `plan.md`, the design
or research file, and at most five critical repository paths.

### Task fields

A task block starts with `### T<n> — <independently testable outcome>` and a
`- [ ] Complete` checkbox. Each field is a bullet `- **<Field>:** <value>`.

Required fields (from the validator):

| Field | Content |
|---|---|
| `Requirements` | The `R<n>` ids that the task implements. |
| `Risk` | The task risk. |
| `Decision risk` | `low`, `medium` or `high`. `Owner: worker` needs `low`. |
| `Owner` | `worker` or `controller`. |
| `Verification owner` | `worker` or `controller`. Worker tasks only. Delete it for controller tasks. |
| `Files` | Backticked paths, folders or globs. Symbols go in parentheses after a path. |
| `Test first` | The specific behavioral test. |
| `Expected RED` | Why the test fails first. |
| `Implementation` | The minimum technical direction. |
| `Verification` | Exact commands, each in backticks, separated by semicolons. Nothing else. |
| `Surface` | `code`, `ui` or `mixed`. |
| `Delivery verification` | For `ui` and `mixed`: build, typecheck and browser check. For `code`: `N/A`. |
| `Done when` | The objective completion condition. |
| `Evidence` | Written by `accept`. One or two lines. |

Other fields in the template:

| Field | Content |
|---|---|
| `Depends on` | Earlier tasks, or `None`. |
| `Decisions` | Settled technical choices for this task. |
| `Interfaces` | Current contracts, exemplar paths, required wiring, exports, lockfiles and tests. |
| `Open decisions` | Must be `None` before a worker dispatch. |
| `Controller justification` | Why a task that is ready for a worker stays with the controller. |
| `Derived files` | Generated or wiring paths that the task can also change. Changes there are listed, not violations. |
| `TDD exception` | An approved exception and its deterministic check. Keep `None` for behavior changes. |
| `Verification inputs` | Read-only configs, test helpers, tool paths and manifests that Verification uses. Gives no write permission. |
| `Test context` | Test exemplar, bootstrap helper, test-only environment and one runbook section. |
| `External verification` | A run that the controller must not execute: who runs it and when. |
| `Checkpoint` | An optional intermediate commit point. It adds no review round. |
| `Evidence hash` | Written by `accept`, or by hand with `validate_change.py --files-hash`. |
| `Accepted result` | Written by `accept`: the delivered result, at most 400 characters of the worker summary. |

`accept` ticks the `Complete` checkbox and writes `Evidence`, `Evidence hash`
and `Accepted result`. A `dispatch --reopen` clears the checkbox. `amend` is
the only way to change the scope or the frozen Verification of a dispatched
task.

### Review result and round log

`pre-review` adds one `### G<n>` block to `### Round log` for each reviewer
dispatch. `review-result` settles it. A settled round is immutable. A round
block has these fields:

| Field | Written by |
|---|---|
| `Type` (`initial` or `re-review`) | `pre-review` |
| `Snapshot` | `pre-review` |
| `Policy snapshot` | `pre-review` |
| `Previous` | `pre-review` |
| `Outcome` | `pre-review` (Pending), `review-result` (PASS or FAIL) |
| `Reason` | `pre-review` |
| `Review decision` | `pre-review --review-decision` |
| `Manifest` | `pre-review`, path `runs/G<n>-manifest.json` |
| `Reviewer verdict`, `Reviewer agent`, `Result source`, `Result digest` | `review-result` |
| `#### Recorded findings` | `review-result` |

A stale snapshot gives `Outcome: FAIL` with `Snapshot status: stale` and a
`Stale reason`. The reviewer verdict stays in the block.

Each finding has a severity: `BLOCKER`, `IMPORTANT` or `MINOR`.

`finalize` removes the template text of the round log after the first real
round.

### Completion evidence

| Block | Written by |
|---|---|
| `Commands:` | `finalize`, from `runs/final-verification.json` or the `Observed` line |
| `Requirement mapping:` | `finalize`, from the matrix |
| `Execution tokens:` | `collect_tokens.py --append` |
| `Review rounds:` | `finalize`, from the `### G<n>` blocks |
| `Residual risks or waivers:` | `finalize --residual` |

Each `finalize` call writes these blocks again from the recorded state.

## Conditional artifacts

If one of these conditions is true, create `design.md`. Otherwise, do not create it.

- More than one service or major module is involved.
- A public API, event contract or persistent schema changes.
- A migration or rollback is not trivial.
- Security, privacy, concurrency, distributed behavior or performance is
  central.
- Several architectures have materially different trade-offs.

If the evidence does not fit in `plan.md` in a concise form, create
`research.md`. Otherwise, do not create it.

### design.md

Template: [`design-template.md`](../../../skills/specadoc/assets/design-template.md).
All sections are written by hand.

| Section | Content |
|---|---|
| Header: `Status`, `Risk`, `Created` | The risk must match the spec and the plan. |
| `## Context` | Why a separate design decision is necessary. |
| `## Decision drivers` | Constraints and quality attributes. |
| `## Options considered` | `### Option <n> — <name>` with benefits, costs and risks. |
| `## Decision` | The selected approach and the reason. |
| `## Interfaces and data flow` | Contracts, state transitions, events and schemas. |
| `## Migration and rollback` | Only when relevant. |
| `## Risks and mitigations` | Each risk and its mitigation. |

`## Interfaces and data flow` can contain one PlantUML diagram for each concern,
in a `plantuml` code block. Use a diagram only for these cases:

- a sequence diagram for a call flow across more than two services or
  processes
- a state diagram for a lifecycle with more than two states or a guarded
  transition
- an activity diagram for a flow with branches or parallel steps.

A diagram is illustrative. No validator checks it. If a diagram conflicts with
the requirements or the code, fix or delete the diagram.

### research.md

Template: [`research-template.md`](../../../skills/specadoc/assets/research-template.md).
All sections are written by hand.

| Section | Content |
|---|---|
| Header: `Created` | |
| `## Relevant files and symbols` | Path or symbol, with a short observation. |
| `## Existing patterns` | Patterns to reuse. |
| `## Verification commands` | Exact commands. |
| `## Constraints and external contracts` | Each constraint with its evidence. |
| `## Decision-relevant conclusions` | Short conclusions that affect the spec or the plan. |
| `## Material unknowns` | At most three. |

Store paths, symbols, commands, external contracts, constraints and short
conclusions. Do not store reasoning chains or a general narrative of the
repository.

## Capability spec

A capability spec is `<root>/specs/<capability>.md`. It describes the behavior
that exists now. Template:
[`capability-template.md`](../../../skills/specadoc/assets/capability-template.md).

| Section | Content |
|---|---|
| Header: `Status`, `Last updated` | `Last updated` changes with each contributing change. |
| `## Scope` | One paragraph: the behavior this capability owns and its boundary. |
| `## Current behavior` | `### C<n> — <name>` blocks: `The system SHALL <observable behavior>.` |
| `## Invariants` | Conditions that must stay true across future changes. |
| `## Key paths` | At most five entrypoints or public contracts. Paths only. |
| `## Provenance` | A table row `Change | Date | Effect` for each contributing change. |

A capability spec never lists tasks, diffs, file inventories or history. In
`propose` and `apply`, the controller updates it from the accepted `spec.md`
after the review PASS, never from the diff. In `light`, the spec delta is
written in place before the implementation.

`doctor.py` warns about a key path that does not exist.

## Contract file

A cross-service contract change has a file `<root>/contracts/<contract>.md` in
the repository of the shared package. Template:
[`contract-template.md`](../../../skills/specadoc/assets/contract-template.md).

| Section | Content |
|---|---|
| Header | Owning package, producer service, version that introduces the change. |
| `## Goal` | The observable change to the contract. |
| `## Surface` | Endpoint or SDK method, change, breaking (yes or no). |
| `## Breaking part` | What existing callers can no longer do, and from which version. `None` if additive. |
| `## Consumers` | Each repository that requires the package: current constraint, required version, plan, status. |
| `## Verification` | Producer check, package test and tag, check for each consumer. |

A consumer's `spec.md` cites `<package> <version>`, not the prose of the
contract.

## record.md

`archive_change.py` writes `<root>/archive/<slug>/record.md`. Nobody edits it by
hand. It is immutable: to change archived behavior, open a new change.

The record starts with front matter:

```text
---
schema: specadoc.archive/v1
slug: <slug>
archived_at: <UTC time>
status: archived | forced
---
```

| Section | Source | Limit for `--force` |
|---|---|---|
| `## Goal` | `spec.md` Goal | 1200 bytes |
| `## Outcome` | `plan.md` Archive summary, plus `migration-summary.md` for legacy archives | 2200 bytes |
| `## Affected capabilities` | `spec.md` Affected capabilities | 1800 bytes |
| `## Decisions` | `plan.md` Confirmed decisions | 1600 bytes |
| `## Review` | `plan.md` Review result without round manifests, plus the tidy record | 700 bytes |
| `## Measurement` | Token totals from `plan.md` Completion evidence | 900 bytes |
| `## Forced exceptions` | The unmet gates of a forced archive, or `None.` | |
| `## Source manifest` | Name, size and SHA-256 of each source file | |

In a normal archive, an empty section becomes `Not recorded.` A forced archive
cuts each section to the limit in the table. The record must mention every
`R<n>` and `C<n>` id of the spec. The required parts are the schema line, the
slug line, `## Goal`, `## Outcome` and `## Source manifest`.

The files in `runs/` collapse into one row of the source manifest. Archive
removes them with the change folder.

## What the validator checks

`validate_change.py` checks structure only:

- the required sections
- the requirement and scenario ids and their coverage
- the capability operations
- the task count and the completeness of task fields
- the owner values
- unfilled placeholders such as `<text>`, `Pending` or `TBD`
- the Review scope paths
- the latest review round.

It cannot check meaning. A passing validator does not make a spec accepted.
Legacy changes created before these sections existed are not expected to pass.

## Size limits

| Item | Limit | Effect |
|---|---|---|
| `plan.md` | 48 KiB | Warning. It names the largest sections. No step waits for it. |
| `## Handoff` section of `plan.md` | 2 KiB | Warning. |
| `runs/handoff.md` | 4 KiB | `handoff` fails. |
| Tasks in one plan | 8 | Warning above 8. Usually three to eight tasks. |
| Worker brief `runs/T<n>-brief.md` | 16,000 bytes | Warning that names the largest parts. |
| `runs/lessons.md` in a brief | 2048 bytes | Cut to the limit. |
| Accepted result | 400 characters | The worker summary is cut. |
| `record.md` | 16 KiB | Archive fails. |
| `spec.md`, `plan.md`, `design.md`, `research.md` at archive | 512 KiB | Warning about pasted logs. |
| Capability key paths | 5 | Template rule. |
| `initial` review rounds | 3 | A fourth needs `--review-decision`. Re-reviews do not count. |
| Design review rounds | 4 | The next round after a FAIL needs `--attempt-decision`. |
| Controller context at `dispatch` and `design-brief` | 200k tokens (`context.dispatch_guard`) | The step stops. Write a handoff and continue in a new session. |

The skill text also has byte limits, in
[`assets/mode-budget.json`](../../../skills/specadoc/assets/mode-budget.json).
`SKILL.md` is at most 5632 bytes. Each reference file is at most 15360 bytes. Each
mode has a total for `SKILL.md` plus the references that the mode always loads.

| Mode | Total limit (bytes) |
|---|---|
| `explore` | 14336 |
| `light` | 12288 |
| `propose` | 31744 |
| `apply` | 11264 |
| `archive` | 10240 |
