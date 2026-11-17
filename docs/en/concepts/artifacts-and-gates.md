# Artifacts and gates

[Русский](../../ru/concepts/artifacts-and-gates.md)

Specadoc keeps the state of a change in a few Markdown files. Deterministic
scripts check those files between phases. This page explains what each file
holds, why the spec and the plan are separate, and what each gate checks.

In the commands below, `<skill-root>` is the installed `skills/specadoc` folder.

## Where the files live

All files live under the artifact root, `docs/specadoc` by default. The scripts
resolve the root in this order:

1. The `--root` option.
2. The `SPECADOC_ROOT` environment variable.
3. `root` in `.specadoc.json` at the repository root.
4. The legacy `docs/agent`, when it exists and `docs/specadoc` does not.
5. `docs/specadoc`.

The artifact root has three areas, one responsibility each:

| Path | Holds |
|---|---|
| `<root>/<slug>/` | the change folder of a change in progress |
| `<root>/specs/<capability>.md` | one capability spec per capability: the behavior that exists now |
| `<root>/archive/<slug>/record.md` | the record of a closed change |

A change that crosses a service boundary adds a fourth area,
`<root>/contracts/<contract>.md`. It lives in the repository of the shared
package that carries the contract.

## The four kinds of file

| File | Lifetime | Holds | Changes |
|---|---|---|---|
| spec (`spec.md`) | one change | goal, non-goals, requirements `R<n>`, acceptance scenarios `A<n>`, constraints, assumptions, affected capabilities | mostly stable after approval |
| plan (`plan.md`) | one change | decisions, tasks, approvals, review rounds, evidence, archive summary | at every step |
| capability spec | permanent | `C<n>` SHALL statements, invariants, at most five key paths, provenance rows | once per change, from the accepted spec |
| record (`record.md`) | permanent | outcome, capability delta, decisions, review, token totals, forced exceptions, source manifest | never (immutable) |

The change folder can also hold `design.md` and `research.md`. A design file is
needed in specific cases, for example several services, a public API or
persistent schema change, or a non-trivial migration. A research file holds
evidence that does not fit in the plan in short form. The `runs/` folder holds
transient role handoff files: briefs, reports, review replies and manifests.

A capability spec states observable behavior only. It lists no tasks, diffs or
history. On a conflict between a capability spec and the code, the code wins.
The drift is recorded and fixed in the change that touches the capability.

## Why the spec and the plan are separate

The two files change at different rates and answer to different readers.

The spec is the behavioral contract. It names no file paths, classes,
frameworks or implementation order. After approval it is mostly stable.
When it does change, the change is significant: the approval and the review
must see it.

The plan is the mutable technical state. It changes after every accepted task,
every review round and every handoff.

The separation lets the scripts treat the two files differently:

- Plan approval stores a hash of `spec.md` (and `design.md`). A later spec edit
  shows up as drift and needs a new approval. Plan edits do not.
- The review snapshot includes the contract sections of the spec:
  requirements, acceptance scenarios, constraints and affected capabilities. An
  edit there makes the recorded PASS stale. Plan edits leave it valid.
- The plan is read again at every task and review. Its size multiplies the
  cost of the change, so it keeps only decisions, tasks, one-line evidence and
  the current state.

## Capability operations

The spec does not describe the capability update in prose. Its `## Affected
capabilities` section lists operations per capability spec:

```
- `docs/specadoc/specs/platform-connection-storage.md`
  - RENAMED C2 (R3) — The identifier is a `cnx_` ULID
  - REMOVED C3 (R6)
  - MODIFIED C5 (R6) — deleting a bound application no longer detaches the connection
  - ADDED C8 (R7) — A connection carries an owning agency
```

Operations are listed in the order RENAMED, REMOVED, MODIFIED, ADDED. Each one
cites the requirements it implements. The spec gate checks the order, the ids
and the citations. After the review PASS, the controller updates the
capability specs from the accepted spec. The final gate and the archive script
then check that each capability spec matches the operations. The archive script
never writes capability prose itself.

## Gates

Each gate is a script with a non-zero exit code on failure. A failed gate blocks
the next step. The scripts check structure only. They cannot judge whether a
requirement is testable or whether evidence is honest, so a passing script is
not an accepted spec.

| Gate | Command | Runs | Checks |
|---|---|---|---|
| spec | `validate_change.py <slug> --phase spec` | before technical planning | required sections, `R<n>` and `A<n>` ids, requirement-to-scenario coverage, capability operations |
| plan | `validate_change.py <slug> --phase plan` | before the plan preview | plan sections, task fields and owners, exact Verification commands, class inventory rows |
| design | `specadoc_step.py design-brief` and `design-review` | before plan approval, when the plan adds new non-test files | an independent review of the class inventory |
| pre-review | `validate_change.py <slug> --phase pre-review` | before each reviewer dispatch | task readiness, design gate, review round structure and cap, a computable snapshot |
| final | `validate_change.py <slug> --phase final` | after the review PASS | final verification boxes, latest round PASS with a matching snapshot, reviewed requirements and tasks, completion evidence, a current `verification.final` run when configured |
| archive | `archive_change.py <slug> --dry-run` | before archive | closed gates, PASS still current, capability provenance, record size |

`specadoc_step.py` runs most of these gates as part of its steps. For example,
`dispatch` checks plan approval, the design PASS and dependency readiness
before it writes a task brief. `pre-review` runs the pre-review gate and records
the snapshot for the new round.

### Design gate

The plan lists every new non-test file in `## Class inventory` with its layer,
its reason and its kind (`port`, `concrete` or `file`). A port needs a real
boundary or a second implementation. "The neighboring feature has one" is not a
reason.

An independent reviewer checks the inventory before any code exists. The PASS
is bound to a hash of the inventory, so any later inventory change invalidates
it. During `apply`, `accept`, `pre-review` and the final gate refuse a new
non-test file outside the inventory. An unplanned file is a design change: it
gets a row and a new design review.

After four recorded design rounds, a FAIL needs a decision to go on.
`continue: <source>` allows one more round. `accept: <source>` turns the open
IMPORTANT items into obligations for `apply`. A BLOCKER is never accepted.

## Approvals

The full lifecycle has one approval stop: the plan checkpoint after `propose`.
`specadoc_step.py approve <slug> --by user|orchestrator --source '<decision>'`
records it. Approval is never written into the plan by hand.

`--by orchestrator` records a decision made under a user mandate. The
orchestrator skill uses it. Without a real mandate, approval stays with you.

Approval also stores hashes of `spec.md` and `design.md`. If either changes
after approval, `status` asks for a new approval, and `pre-review` refuses to
start a round. `approve` refuses while a review round has no result yet. Settle the
approval before a round starts, because a new approval during a round makes its
PASS stale.

An explicit request for uninterrupted execution waives the plan checkpoint. It
does not waive the spec, the tests or the completion evidence.

In `light` mode, one approval in chat covers both the spec delta and the plan.

## Review rounds

Each round is recorded in the plan as a `### G<n>` block. It holds the round
type, the snapshot hash, the outcome and a manifest file under `runs/`.
`review-result` saves the reviewer's reply verbatim, so nobody copies it by hand.

Findings have three levels:

- `BLOCKER`: an unmet requirement, incorrect behavior, a security or data risk,
  or an unsafe completion claim.
- `IMPORTANT`: a likely defect, a significant scenario gap or a material
  deviation.
- `MINOR`: a maintainability improvement that does not block correctness.

The verdict is FAIL when any BLOCKER or IMPORTANT finding exists.

Round types:

- `initial` reviews a new diff. The third recorded `initial` round is the last
  one without a decision. A fourth needs `--review-decision` with the decision,
  its author and its scope.
- `re-review` follows a FAIL. It reads only the previous findings and the files
  that changed since that round. It does not count toward the cap. If it
  returns a new BLOCKER or IMPORTANT finding, the controller stops and asks you.
- A `re-review` recorded as `minor-fixes` follows a PASS whose MINOR findings
  needed executable fixes. It is outside the cap and is never chained.
- One documentation-only follow-up can follow a documentation-only FAIL.

New requirements and polish use a justified `initial` round
(`--reason requirements` or `--reason polish`). Corrections stay `re-review`.

If code or approval changes while a reviewer works, the verdict is saved as
stale. A stale round uses no review allowance.

## When a PASS stays valid

The review snapshot is a SHA-256 manifest of every file in the plan's
`## Review scope`, plus the contract sections of the spec. It does not depend on
git, so it works on a dirty working tree.

The PASS stays valid while the snapshot is unchanged. Edits to the plan,
capability specs, the archive summary, token accounting or the record do not
change it. Any change to production code, tests, migrations, executable
configuration, public contracts or approved requirements needs a new review.

MINOR fixes to tests or prose only need no new round. A comment or docblock
inside a source file counts as executable.

`archive` runs `review_snapshot.py verify` against the manifest of the latest
round. A mismatch stops the archive, and the change goes back to `apply`.

## Amendment, reopen and exception

A failed gate never authorizes these actions:

- rewriting a baseline
- weakening a frozen Verification
- hiding completed work
- altering an approval

Specadoc gives three recorded ways forward instead.

An amendment widens a task. `specadoc_step.py amend <slug> T<n> --allow <path>`
(or `--derived <path>`) with `--reason` adds a path outside the task's files.
The task's Verification and the plan approval are frozen at dispatch. Only
`amend` changes them.

A reopen sends a task back for corrective code. `dispatch <slug> T<n> --reopen
'<reason>'` archives the previous attempt and starts from the current tree. Use
it for code fixes, not for stale evidence. For stale evidence, `refresh`
accepts the affected tasks again in dependency order.

An exception is a recorded, authorized departure from a gate. Examples are a
`TDD exception` in a task, a round cap override, a design `accept:` decision, a
`Snapshot waiver` for a technical read failure, and `archive --force`. Force
always runs as `--force --dry-run` first. Only an explicit request authorizes
the real run. The record keeps the unmet gates.

Without one of these, the controller reports the blocker.

## External verification

The controller is not allowed to run some checks itself. Examples are an integration
suite on a shared database, or a check that is allowed only after review. You
or another executor run such a check. It goes into the task's
`External verification:` field. The
task keeps a local exact check in `Verification`.

`accept` then ends in `EXTERNAL-PENDING`. Dependent tasks and the review can
start. The controller records the observed result:

```bash
python3 <skill-root>/scripts/specadoc_step.py external-result <slug> T<n> --outcome PASS --evidence '<run>'
```

A FAIL sends the task back to work. `--supersede '<why>'` corrects a recorded
result. The final gate needs a recorded PASS, and static checks do not replace
it.

## Size budgets

| Item | Limit | Kind |
|---|---|---|
| `record.md` | 16 KiB | hard limit: archive refuses a larger record |
| `plan.md` | 48 KiB | warning only: no step waits for it |
| `## Handoff` section of the plan | 2 KiB | warning |
| `runs/handoff.md` | 4 KiB | limit of `specadoc_step.py handoff` |
| tasks per plan | 8 | warning: add a task, do not fold work into a done one |
| key paths per capability spec | 5 | capability spec rule |
| scout, worker and reviewer reports | 500, 600 and 1,200 words | role contracts |

## Related pages

- [Lifecycle](lifecycle.md)
- [Roles](roles.md)
- [Plan structure](../reference/plan-structure.md)
- [Scripts](../reference/scripts.md)
- Agent-facing detail:
  [artifacts.md](../../../skills/specadoc/references/artifacts.md),
  [design-gate.md](../../../skills/specadoc/references/design-gate.md),
  [tdd-and-review.md](../../../skills/specadoc/references/tdd-and-review.md)
