# Coordination state without another lifecycle

Use an existing authorized shared plan when one exists. Before creating a
record, search the work area for one (`orchestration/*/`, or the directory the
brief names) covering the same repository or roadmap; a later step of that
roadmap appends to it. Keep the record in the project work area, not in
host-private session storage: the next step may run in another session or host.
Otherwise choose a small coordination directory in an authorized workspace, for
example `orchestration/<task>/`. Inside a checkout, list the directory in that
checkout's `.git/info/exclude` when you create it: otherwise Specadoc counts
your notes as task changes (a media-project run: failed reports, refreshes
and pre-reviews in five controllers). It contains:

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
`python3 <skill-root>/scripts/coordination_log.py decision <file> --by
user|orchestrator --title '<t>' --file -` for a decision (numbered `### D<n>`,
at most 2 KiB) and `state <file> --file -` for the current-state block, not
ad-hoc edit scripts (`<skill-root>` is this skill's directory). `--by user`
takes `--quote '<the user's words>'`; it refuses a bare go/ok without
`--confirms '<the one proposal it accepted>'`. `last <file>` and `get <file> D<n>` print what the log
holds, so a message to a controller cites the number the command printed, never
one from memory (4.1/4.2 sent D12 for D11 and D17 for D16). The orchestrator
reads verdicts, not raw evidence: delegate bulk searches over controller
artifacts, integration runs, and field-by-field contract comparison to a bounded
scout or worker, then inspect the cited lines it returns.

Update after a transition. After compaction, read `coordination_log.py capsule
<file>` (mandate, current state, newest decisions and the orchestrator's rules in
at most 60 lines; a host hook may already have injected it; week 47 sessions
compacted at 202-274k and lost their role), then read back this record, inspect
actual controller states and referenced evidence, reconcile unacknowledged/stale
events, then continue. A note saying "ready" is not compatibility evidence. Avoid replaying
whole transcripts or copying full logs; keep proof by reference and inspect it
when needed.

At closure, report local readiness separately from end-to-end acceptance, name
unverified environments and remaining live controllers, and remove owned timers.
Archive only on an explicit request under local Specadoc rules. Do not stop
unrelated processes or discard user changes during cleanup.

## Known facts

Facts that design reviews and research found about existing data, the platform
or the framework, and the decided non-issues, live in one file per work area,
for example `orchestration/known-facts.md` beside the record directories: one
line each with file:line, naming the repository when the work area serves
several. Every coordination record in the work area cites it on the brief's
`Known facts:` line and never copies it. Lists kept in each stage's brief hid
facts from each other: a stage brief cites earlier stages only, so 6.19's first
design round raised again a framework fact that the stage 8 brief already held.

- At a plan checkpoint add each line of the envelope's `Facts for later steps`
  that the file does not hold yet.
- Fix a wrong line in place and cite the evidence: the file holds current
  knowledge, not history.
- Delete a line once the project's rules file or code standard states it.
- List the file in `.git/info/exclude` like the record directories.
- A record whose brief has no `Known facts:` line keeps its `Known states and
  platform facts` section. Move such lists into the file between runs, never
  during one: a running controller has already read its brief.
