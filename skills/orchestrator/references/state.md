# Coordination state without another lifecycle

Use an existing authorized shared plan when one exists. Otherwise choose a small
coordination directory in an authorized workspace, for example
`orchestration/<task>/`, containing:

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

Update after a transition. After compaction, read back this record, inspect actual
controller states and referenced evidence, reconcile unacknowledged/stale events,
then continue. A note saying "ready" is not compatibility evidence. Avoid replaying
whole transcripts or copying full logs; keep proof by reference and inspect it
when needed.

At closure, report local readiness separately from end-to-end acceptance, name
unverified environments and remaining live controllers, and remove owned timers.
Archive only on an explicit request under local Specadoc rules. Do not stop
unrelated processes or discard user changes during cleanup.
