# Artifact rules

Load this reference only when creating, updating, or validating lifecycle artifacts.

## Artifact roots

Three roots, one responsibility each:

- `docs/agent/<change-slug>/` - the change currently being delivered.
- `docs/agent/archive/<change-slug>/record.md` - a compact immutable history
  record produced by `scripts/archive_change.py`. Never reopen it; open a new
  change instead.
- `docs/agent/specs/<capability>.md` - the cumulative description of behavior
  that currently exists, one file per capability.

A capability file states observable behavior only: `C<n>` SHALL statements,
invariants, at most five key paths, and a provenance row per contributing
change. It never lists tasks, diffs, file-by-file inventories, or history
narrative. It is written from the accepted `spec.md` at archive time, never from
the diff, and never while the change is still in flight.

### Declaring the change as operations

`spec.md` does not describe the capability update in prose. Its
`## Affected capabilities` section lists, per capability file, the operations
this change performs on that file's `C<n>` requirements:

```
- `docs/agent/specs/platform-connection-storage.md`
  - RENAMED C2 (R3) — The identifier is a `cnx_` ULID
  - REMOVED C3 (R6)
  - MODIFIED C5 (R6) — deleting a bound application no longer detaches the connection
  - ADDED C8 (R7) — A connection carries an owning agency
```

Operations are applied in the order `RENAMED, REMOVED, MODIFIED, ADDED`, and the
list must be written in that order: a rename has to land before anything
addresses the new heading, and an id freed by `REMOVED` must not collide with one
`ADDED` in the same change. A capability this change establishes is marked
`` `docs/agent/specs/<name>.md` (new capability) `` and admits only `ADDED`.

Every operation must cite at least one requirement it implements, in
parentheses right after the `C<n>` id — `ADDED C8 (R7) — <effect>`. This is what
lets `check_plan`'s requirement→task→matrix sweep actually see a capability
delta: without a citation, a capability operation is invisible prose that can
drift from `plan.md`'s tasks and the requirement-to-check matrix undetected
until an expensive reviewer round happens to notice (this happened in
practice — see the `d9c20354` incident referenced in the specadoc remediation
plan). Cite every requirement the operation actually implements, not just one.

This is what makes the archive-time update mechanical rather than a rewrite from
memory. `validate_change.py --phase spec` checks the syntax, the order, that
every `MODIFIED`/`REMOVED`/`RENAMED` id exists in the target file while no
`ADDED` id collides with one, and that every operation cites a real
requirement id. `archive_change.py` then checks the other end: that each
`ADDED`/`MODIFIED`/`RENAMED` id is present in the capability file and each
`REMOVED` id is gone.

Create one by copying the template:

```bash
cp <skill-root>/assets/capability-template.md docs/agent/specs/<capability>.md
```

On a conflict between a capability file and the code, the code wins. Record the
drift as a review finding and correct the capability file in the change that
touches it.

## Cross-service contract changes

A change that crosses a service boundary has a fourth root, in the repository of
the shared package (library, SDK, or schema module) that carries the contract:

- `docs/agent/contracts/<contract>.md` - the contract being changed, its consumers,
  and the version that delivers it.

The package is the owner because it is where the contract is materialized and
versioned; a consumer's reference to it is checkable from its dependency lock
file. Do not
place this file in the producing service, and do not centralize it outside the
package.

Create one by copying the template:

```bash
cp <skill-root>/assets/contract-template.md docs/agent/contracts/<contract>.md
```

Sequence: determine the consumer set (from a repository landscape map or
dependency search) before the first edit;
write the contract file in the package; implement in the producer under its own
`docs/agent/<change-slug>/`; tag the package; then one session per consumer, each
with its own `spec.md` referencing the contract file and the required version.

A consumer's spec cites `<package> <version>`, never the contract's prose. When a
consumer sits more than one major behind, raising it is a separate change unless
the contract file states otherwise.

## Default artifact set

Use `docs/agent/<change-slug>/` with:

- `spec.md`: behavioral contract; mostly stable after approval.
- `plan.md`: mutable technical plan, tasks, handoff, progress, and evidence.

Do not create `tasks.md` unless a higher-priority repository workflow requires it.

## Conditional artifacts

Create `design.md` only when at least one applies:

- Multiple services or major modules are involved.
- A public API, event contract, or persistent schema changes.
- A migration or rollback is non-trivial.
- Security, privacy, concurrency, distributed behavior, or performance is central.
- Multiple architectures have materially different tradeoffs.

Create `research.md` only when evidence cannot be kept concise in `plan.md`. Store paths, symbols, commands, external contracts, constraints, and short conclusions. Do not store chain-of-thought or a general repository narrative.

### Diagrams inside `design.md`

Add a PlantUML diagram to `design.md`'s `## Interfaces and data flow` only when
prose would be harder to verify than a picture, one diagram per concern:

- **sequence** — a call flow crosses more than two services or processes.
- **state** — a capability's lifecycle has more than two states, or any
  conditional/guarded transition.
- **activity** — a single flow branches or runs steps in parallel; a strictly
  linear flow does not qualify.

Fence each as a `plantuml` code block so it stays plain text (diffable, no
renderer required to read the source). Never diagram a simple linear flow —
prose is cheaper to write and to keep correct.

A diagram is illustrative only. `spec.md` requirements, acceptance scenarios,
and each capability file's `C<n>` statements remain the authoritative,
`validate_change.py`-checked contract; nothing in a diagram is validated
mechanically. On conflict between a diagram and the requirements or the code,
the diagram loses — fix or delete it, the same rule already applied to a
capability file that drifts from code.

## Initialize files

Prefer:

```bash
python3 <skill-root>/scripts/init_change.py <change-slug> --risk <low|medium|high>
```

Optional flags:

```bash
--root <directory>
--with-design
--with-research
--force
```

The script copies templates from `assets/`. Read and fill the created files; do not load the raw templates again unless initialization failed.

## Specification quality gate

`spec.md` must include:

- Goal.
- Non-goals.
- Current context needed to understand the change.
- Stable requirement IDs such as `R1`, `R2`.
- Acceptance scenarios with Given, When, Then.
- Constraints.
- Explicit assumptions.
- Requirement-to-scenario coverage.

Requirements must describe observable and testable behavior. Keep file paths, classes, frameworks, and implementation order out of the specification.

Each behavioral requirement must map to at least one acceptance scenario. No unresolved behavior-changing question may remain when the specification is marked ready.

## Plan quality gate

`plan.md` must contain every applicable section of `assets/plan-template.md`,
which is normative: editing that template changes this gate. Delete only the
sections its own placeholder text marks as conditional.

A normal change carries three to eight ordered tasks. Each must be an
independently verifiable outcome, not a vague activity or an entire subsystem.

Immediately before review, `## Review scope` lists the actual executable diff
as repository-relative literal file paths, one backticked bullet per path. It
is deliberately separate from task `Files:`, which may contain paths or
symbols. Prefix an intentional deletion with `!`; reject symbols, globs, brace
expressions, directories, absolute paths, and paths containing `..`.

Task ownership values are `controller` or `worker`. Verification ownership is
`worker` or `controller`. Overall high risk does not prevent a
low-decision task from using a worker.

Before implementation, present the plan as a concise task table or equivalent
preview showing outcome, files or symbols, owner and model, implementation
direction, and exact verification. Record the user's plan approval in
`plan.md`. A capable model, accepted specification, or approved model profile
does not imply plan approval.

For mechanical migrations, keep the consumer classification and replacement
order in `plan.md`. Do not expand the plan into a file-by-file checklist when
targeted searches define the affected set.

Avoid tasks such as:

- "Implement the feature."
- "Add tests."
- "Handle edge cases."
- "Refactor if needed."

Also reject:

- A task that creates a new file without naming the existing file that cannot
  hold the code and why.
- Temporary adapters, stubs, or scaffolding whose only purpose is to make an
  intermediate task look shippable and that a later task removes.

## Validation

`scripts/validate_change.py` is the deterministic form of the two quality gates
above:

```bash
python3 <skill-root>/scripts/validate_change.py <change-slug> --phase <spec|plan|pre-review|final>
```

Run `--phase spec` before the model checkpoint, `--phase plan` before the plan
preview, `--phase pre-review` before dispatching the reviewer, and `--phase final`
after its PASS and before archive. A non-zero exit blocks that checkpoint.

The script checks structure: required sections, requirement and scenario
identifiers, coverage, task count, task field completeness, ownership values,
unfilled placeholders, review-scope paths, and the latest recorded review
round. It cannot check meaning. The prose gates above stay
authoritative for whether a requirement is observable and testable, whether a
task is a real outcome, and whether evidence is honest. A passing script is not
an accepted specification.

Legacy changes created before these sections existed are not expected to pass —
including changes whose `## Affected capabilities` is prose rather than the
operation list above. Do not add a compatibility flag and do not retrofit them.

## Closing a change

A change is closed, not left in place:

1. Final review is PASS and every gate in `plan.md` is checked.
2. Update every capability file named in the specification's
   `## Affected capabilities`, from the accepted `spec.md`. Add a provenance row
   with this change slug.
3. Record per-execution token totals and review rounds in `plan.md`.
4. Fill `## Archive summary` with the durable outcome and decisions, then run:

```bash
python3 <skill-root>/scripts/archive_change.py <change-slug> --dry-run
python3 <skill-root>/scripts/archive_change.py <change-slug>
```

The script refuses to archive until the gates are checked, the review result is
PASS, the affected capabilities are declared, and each named capability file
exists and carries this change in its provenance table. It publishes one
validated `record.md` under a 16 KiB budget and removes the working folder only
after readback succeeds. It never writes capability prose for you.

`--force` is an explicit lossy escape hatch for incomplete artifacts. Always run
and show `--force --dry-run` first. It records unmet gates, missing sections,
unknown attachments, and hashes, but it never overwrites an archive target.

Legacy archive compaction is separate:

```bash
python3 <skill-root>/scripts/migrate_archive.py --root docs/agent
python3 <skill-root>/scripts/migrate_archive.py --root docs/agent --apply
```

The first command is non-writing. Every legacy design, research, log, or other
file beyond spec/plan requires a concise `migration-summary.md`; apply is allowed
only after its report is approved and
creates a verified compressed backup outside `archive/`.

## Integrity doctor

Use the read-only doctor as the archive and capability corpus grows:

```bash
python3 <skill-root>/scripts/doctor.py --root docs/agent
python3 <skill-root>/scripts/doctor.py --root docs/agent --strict
```

It reports exact duplicate `C<n>` identifiers, repeated provenance rows, exact
duplicate requirement text across capability files, duplicate archive slugs, and
archive references that no longer resolve to a capability or its provenance.
It never deletes, rewrites, merges, or otherwise fixes artifacts. Warnings need
human ownership decisions; errors always return non-zero, and `--strict` also
returns non-zero for warnings.

## State update rules

- Update task checkboxes immediately after verification.
- Record commands and short results, not verbose logs; keep normal task evidence
  to one or two lines.
- Record deviations only when they affect later work.
- Never rewrite accepted behavioral requirements to match an accidental implementation.
- If behavior must change, reopen specification review first.
- Replace stale technical approaches, task paths, and verification commands when
  the accepted implementation changes; do not preserve obsolete alternatives as
  progress history.
- Keep one progress/evidence location in `plan.md`. Do not append duplicate
  progress, follow-up, or verification sections.

Before final review, check artifact coherence: planned paths match actual tests,
the technical approach matches the stable diff, commands reflect checks that
actually ran, and task ownership matches the delegation evidence.
