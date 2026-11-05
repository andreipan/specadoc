# Coordination state without another lifecycle

Use an existing authorized shared plan when one exists. Before creating a
record, search the work area for one (`orchestration/*/`, or the directory the
brief names) covering the same repository or roadmap; a later step of that
roadmap appends to it. Keep the record in the project work area, not in
host-private session storage: the next step may run in another session or host.
Otherwise choose a small coordination directory in an authorized workspace, for
example `orchestration/<task>/`, containing:

- **brief.md:** shared goal, verbatim user invariants, boundaries, mandate,
  acceptance scenario, and shared contract ownership/revisions.
- **status.md:** controller identifiers and work areas, local change/plan links,
  observed bindings, dependencies and readiness evidence, last checkpoint key and
  response, current state, blockers, next action, and any active timer identifier.
- **decisions.md:** cross-project decisions, rationale, affected owners/revisions,
  authorization provenance, and how to undo an agreed reversible choice.

For a small task these can be sections of one existing file. Do not create local
specification/plan copies here. Local behavior, task progress, approvals, review,
and verification remain in each controller's Specadoc records. The coordination
record links to them and stores only the relationship or shared decision.

The orchestrator owns coordination notes; each controller owns its local records.
Send a relevant brief/decision into each controller's accessible work area or
message rather than granting broad filesystem access. Shared databases, ports,
services, and deployment targets need explicit owners too.

Append transitions and decisions as dated entries instead of rewriting earlier
lines in place; keep one short current-state block at the top. Use
`python3 <skill-root>/scripts/coordination_log.py decision <file> --title '<t>'
--file -` for a decision (numbered `### D<n>`, at most 2 KiB) and `state <file>
--file -` for the current-state block, not ad-hoc edit scripts (`<skill-root>`
is this skill's directory). The orchestrator
reads verdicts, not raw evidence: delegate bulk searches over controller
artifacts, integration runs, and field-by-field contract comparison to a bounded
scout or worker, then inspect the cited lines it returns.

Update after a transition. After compaction, read back this record, inspect actual
controller states and referenced evidence, reconcile unacknowledged/stale events,
then continue. A note saying "ready" is not compatibility evidence. Avoid replaying
whole transcripts or copying full logs; keep proof by reference and inspect it
when needed.

At closure, report local readiness separately from end-to-end acceptance, name
unverified environments and remaining live controllers, and remove owned timers.
Archive only on an explicit request under local Specadoc rules. Do not stop
unrelated processes or discard user changes during cleanup.
