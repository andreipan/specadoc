# Modes

[Русский](../../ru/reference/modes.md)

This page lists the five Specadoc modes: their syntax, inputs, outputs and
stop points. For the reasons behind the lifecycle, read
[Lifecycle](../concepts/lifecycle.md). The agent-facing text of each mode is in
[`skills/specadoc/references/`](../../../skills/specadoc/references/).

In the commands below, `<skill-root>` is the installed `skills/specadoc` folder.
`<root>` is the artifact root, `docs/specadoc` by default (see
[Configuration](config.md#artifact-root)).

## Summary

| Mode | Syntax | Writes files | Stop for the user |
|---|---|---|---|
| `explore` | `explore <request>` | No | At most three material questions |
| `propose` | `propose <request\|slug>` | `spec.md`, `plan.md`, optional `design.md` and `research.md` | Plan checkpoint (plan approval) |
| `apply` | `apply <slug>` | Code, tests, `plan.md` evidence, capability specs | New BLOCKER or IMPORTANT finding after a re-review, open decisions, context guard |
| `light` | `light <request>` | Code, tests, capability specs | One approval of the spec delta and plan |
| `archive` | `archive <slug> [--dry-run] [--force]` | `<root>/archive/<slug>/record.md` | Only on an explicit request |

Specadoc starts only when you name it, one of its modes, or the complete
lifecycle. It does not apply itself to ordinary coding work.

## Mode selection

An explicit mode always wins. Without an explicit mode, the controller selects
the first rule that applies:

1. `apply`, when the request names an existing slug whose plan records the plan
   approval.
2. `explore`, when material requirements are unresolved or the area is
   unfamiliar.
3. `propose`, when any [light eligibility](#eligibility) condition fails. The
   conditions cover another repository or external consumers, more than one
   session, money, the permission model and irreversible data effects.
4. `light` in all other cases, small local fixes included.

The controller never selects `archive` implicitly.

After you select a mode, follow-up requests stay in the same lifecycle. This
includes small visual or verification fixes and resumed implementation.
Specadoc starts a new lifecycle only for a changed behavioral contract or a
different change. One change is active at a time.

## explore

Syntax: `explore <request>`.

`explore` establishes facts and tests the idea. It writes no repository files.

Inputs:

- the request
- the repository rules
- up to three capability specs from `<root>/specs/` that match the request.

The controller derives up to five domain terms from the request. It finds
candidate capability specs by file name, heading and `C<n>` requirement. It
never reads `<root>/archive/`.

Procedure:

1. The controller reads the mandatory repository rules.
2. The controller selects the matching capability specs, or records
   `Relevant capability-specs: none found.`
3. The controller runs `python3 <skill-root>/scripts/doctor.py` once and reports
   each missing key path of a selected spec as drift.
4. If the area is unfamiliar, the controller dispatches one bounded read-only
   `scout`. It does the same when it expects to read more than about five files
   or 400 lines.
5. The controller stress-tests the idea with a grilling skill only when one of
   these conditions is true:
   - more than one material question stays open
   - the change touches a public contract, schema, security, concurrency or
     money
   - the reconnaissance found conflicting evidence.

If no grilling skill is installed, the controller asks the same questions
itself. If grilling is skipped, the decision log records
`Grilling: skipped — <reason>`.

Outputs (in the conversation):

- the decision log
- the safe defaults
- at most three material questions
- the selected capability specs, or the no-match result, and their effect
- every drift between code and capability specs. The code is authoritative.

Stop point: the controller returns the material questions to you. The next mode
is usually `propose` or `light`. Do not split `explore` and `propose` into
different sessions.

Details: [`references/explore.md`](../../../skills/specadoc/references/explore.md).

## propose

Syntax: `propose <request|slug>`.

`propose` writes and validates the spec and the plan of one change.

Inputs:

- the request, or the slug of an earlier change
- the accepted `explore` evidence, if it exists
- one foreground `scout` report about the code and external contracts.

Outputs:

- `<root>/<slug>/spec.md`, the behavioral contract
- `<root>/<slug>/plan.md`, the tasks, decisions and approvals
- `design.md` and `research.md`, only when the
  [artifact rules](plan-structure.md#conditional-artifacts) require them
- `<root>/<slug>/runs/`, the transient files of the design gate and approval.

Procedure:

1. The controller reuses the `explore` evidence and does not repeat the
   reconnaissance.
2. The controller creates the change folder with
   `init_change.py <slug> --risk <low|medium|high> --scout <report|agent id>`.
3. The controller resolves the behavior-changing questions and fills `spec.md`.
4. The controller runs `validate_change.py <slug> --phase spec` and clears all
   violations.
5. The controller writes a small ordered set of tasks, usually three to eight,
   and the requirement-to-check matrix.
6. The controller lists every new non-test file in `## Class inventory`.
7. An independent `reviewer` checks the inventory (the
   [design gate](../concepts/artifacts-and-gates.md)).
8. The controller runs `validate_change.py <slug> --phase plan`.
9. The controller shows a compact plan preview and stops.

A task gets `Owner: worker` only when its decision risk is `low`, its Files are
known and its Verification is exact. Other tasks stay with the controller and
need a `Controller justification`.

The plan preview contains:

- the tasks
- the role bindings line, from
  `role_routing.py --controller-runtime <runtime> --change <slug> --dry-run --compact --check-cli`
- binding advice, when a binding looks too weak for the risk
- the observed context figure from `specadoc_step.py status`, never an estimate.

Stop points:

- behavior-changing questions
- a FAIL of the design review
- the plan checkpoint. This is the only approval stop of `propose`.

The controller records your approval with
`specadoc_step.py approve <slug> --by user --source '<your words>'`. It never
edits the approval by hand. An explicit request for uninterrupted execution
can waive the plan checkpoint. It cannot waive the spec or the validation.

When `status` advises a fresh session, the controller offers `apply <slug>` in a
new session. That session starts from the plan's `### Read before continuing`
list.

Details: [`references/propose.md`](../../../skills/specadoc/references/propose.md).

## apply

Syntax: `apply <slug>`.

`apply` implements an approved plan and collects the final evidence.

Inputs:

- a change folder whose spec and plan pass validation
- a recorded plan approval
- a current design review PASS, when the plan has a Class inventory.

Outputs:

- code and tests
- task Evidence, Accepted result and review rounds in `plan.md`
- the updated capability specs that `spec.md` declares
- the Archive summary and Completion evidence in `plan.md`
- transient files in `<root>/<slug>/runs/`.

Procedure:

1. A fresh session reads `specadoc_step.py status <slug>`, `runs/handoff.md`
   and the task brief. It does not read the whole spec, plan and design.
2. The controller closes material decisions before the first failing test.
3. For each task, the controller runs `specadoc_step.py dispatch <slug> T<n>`.
   This step checks the task and writes the baseline and the brief.
4. The worker, or the controller for a controller task, uses RED-GREEN-REFACTOR.
5. The implementer ends with `report <slug> T<n> --status … --summary … --red … --green …`.
6. The controller runs `accept <slug> T<n>`. This step runs the task
   Verification and records the Evidence.
7. After all tasks, the controller runs `scope <slug>` to fill `## Review scope`.
8. The controller runs the whole suite and the gates once, with
   `finalize <slug> --run` or `finalize <slug> --observed '<run>'`.
9. The controller runs `pre-review <slug>` and dispatches one independent
   read-only `reviewer`.
10. The controller records the verdict with `review-result <slug> --from-agent <id>`
    or `--result-file <reply>`.
11. If the review finds problems, the implementer fixes them. Then the
    controller runs `pre-review <slug> --review-type re-review`.
12. After a PASS, the controller updates the capability specs, the Archive
    summary and the token totals.
13. The controller runs `finalize <slug>` and `validate_change.py <slug> --phase final`.

The results of `accept` are:

| Result | Meaning | Next action |
|---|---|---|
| ACCEPTED | Verification passed and Evidence is recorded. | Continue with the next ready task. |
| NEEDS_DECISION | The report has concerns. | Run `accept` again with `--note '<decision>'`. |
| EXTERNAL-PENDING | The task has an `External verification:` field. | Dependent tasks and review can start. Record the run with `external-result`. |
| FAIL | Scope, report or Verification failed. | Fix the cause, then run `accept` again. |
| BLOCKED | The step cannot evaluate the task. | Read the blocking reason. |

Stop points:

- `dispatch` stops near 200k tokens of controller context. Write
  `handoff <slug> --file -` and continue in a new session.
- An open decision or a BLOCKED report goes back to the controller, or to you.
- A new BLOCKER or IMPORTANT finding after a re-review: the controller stops
  and asks you.
- A fourth `initial` review round needs `--review-decision '<decision, author, scope>'`.
- A pending external verification blocks the final gate until its PASS is
  recorded.

The controller does not archive until you ask for `archive`.

Exceptions:

- To add a path outside the task, use
  `amend <slug> T<n> --allow|--derived <path> --reason '<decision>'`.
- To start a corrective attempt of an earlier task, use
  `dispatch <slug> T<n> --reopen '<reason>'`.
- To re-accept tasks with stale evidence, use `refresh <slug>`.
- More than eight tasks gives a warning. Add a new task, for example T9. Do not
  add work to a completed task.

Details: [`references/apply.md`](../../../skills/specadoc/references/apply.md).
All `specadoc_step.py` steps are in [Scripts](scripts.md#specadoc_steppy).

## light

Syntax: `light <request>`.

`light` delivers a small change in one session. The capability specs are the
durable record. The plan, the approval and the evidence stay in the
conversation.

`light` creates no change folder, no `plan.md`, no `runs/` folder and no
archive record. It dispatches no `scout` and no `worker`.

### Eligibility

All conditions must be true. The controller checks them again when new facts
appear.

- The change is in one repository, and the work fits one session.
- The requirements are clear, and no material domain question is open.
- No contract with consumers outside the repository changes, for example a
  published API, SDK, event or shared schema.
- The change does not touch money handling or the permission model.
- The change has no irreversible data effect beyond an ordinary additive
  migration.

If a condition fails, the controller stops and switches to `propose`. For open
questions, it switches to `explore`. `propose` keeps the approved spec delta
and the accepted evidence.

Inputs:

- the request
- up to three affected capability specs from `<root>/specs/`.

Procedure:

1. The controller reads the repository rules and the affected capability specs.
2. The controller writes the spec delta in place. It changes only the affected
   `C<n>` statements, invariants and key paths.
3. If no capability spec exists, the controller creates one from
   `<skill-root>/assets/capability-template.md`.
4. The controller shows one compact preview and stops for one approval.
5. The controller implements the change with RED-GREEN-REFACTOR for each
   changed `C<n>`.
6. The controller runs the final verification once: affected tests, static
   analysis and lint.
7. Unless the diff is trivial, one independent read-only `reviewer` checks the
   change.
8. The controller adds a provenance row `<slug> | <date> | <effect>` to each
   touched capability spec and updates **Last updated**.
9. The controller runs `doctor.py` once.

A trivial diff is one file with no behavior change. A change without an
observable behavior delta leaves the capability specs unchanged.

The preview contains:

- the spec delta
- the files to change
- the ordered steps
- the exact verification commands, static and style gates included
- the risk
- the controller and reviewer bindings.

Stop points:

- the one approval of the preview. An explicit request for uninterrupted
  execution waives the stop, but not the spec delta
- a new BLOCKER or IMPORTANT finding after the one re-review
- an eligibility condition that fails.

If no subagent is available, the controller reports the incomplete review gate.
It never reviews its own work. The controller commits only on request.

An interrupted `light` change is the edited specs plus the working tree. Resume
from `git diff` and the spec delta.

Details: [`references/light.md`](../../../skills/specadoc/references/light.md).
To choose between `light` and `propose`, read
[Light or propose](../guides/light-or-propose.md).

## archive

Syntax: `archive <slug> [--dry-run] [--force]`.

`archive` closes a change into one compact `record.md`. It runs only on an
explicit request.

Inputs:

- `plan.md` with a current review PASS and checked final gates
- the capability specs that `spec.md` declares, each with a provenance row for
  this slug
- a filled `## Archive summary`.

Outputs:

- `<root>/archive/<slug>/record.md`, schema `specadoc.archive/v1`, at most
  16 KiB
- the removal of the change folder, after the record is written and read back.

The controller keeps the decision. A `worker` usually runs the commands. The
worker can shorten wording in durable `plan.md` sections to fit the size
budget. It must not change a decision, requirement or evidence.

Normal procedure:

1. The controller checks the existing PASS and the closed gates.
2. Run `python3 <skill-root>/scripts/archive_change.py <slug> --dry-run`.
3. Clear every gate, unknown attachment, collision and size violation.
4. Run the same command without `--dry-run`.
5. The controller checks the record header, its size and `git status`.

`archive` never dispatches a `reviewer` and never rebuilds a code graph.
`archive_change.py` runs `review_snapshot.py verify` against the latest `### G<n>`
round. A mismatch means that executable code, tests, migrations, executable
configuration, a public contract or approved requirements changed after the
PASS. Then the change goes back to `apply`.

Stop points (the worker stops and returns):

- a snapshot manifest mismatch
- an unknown attachment or a target collision
- any gate other than size
- a size that does not fit without loss of meaning.

Forced archive:

1. Run `archive_change.py <slug> --force --dry-run` and show the result.
2. Run `--force` only after an explicit `--force` request.

`--force` bypasses the lifecycle and capability provenance gates. It cannot
overwrite a target, skip the record validation, or remove the source before
the record is read back. The forced record lists the unmet gates.

Legacy archive folders use a different command, `migrate_archive.py`. See
[Scripts](scripts.md#migrate_archivepy).

Details: [`references/archive.md`](../../../skills/specadoc/references/archive.md).
The record sections are in [Plan structure](plan-structure.md#recordmd).

## Token accounting by mode

`collect_tokens.py --mode` accepts `explore`, `light`, `propose`, `apply` and
`archive`. A mode that did not run is absent from the totals, never zero. See
[Scripts](scripts.md#collect_tokenspy).
