---
name: orchestrator
description: Coordinate multiple independent Specadoc controllers toward one verified outcome. Use only when the user explicitly requests an orchestrator over controllers, cross-repository Specadoc coordination, or оркестратор над контроллерами; do not activate for ordinary Specadoc work or parallel worker tasks.
---

# Orchestrator

Own the shared outcome across independent Specadoc controllers. Controllers own
their local lifecycle, architecture, bounded workers, verification, and review.
This skill is not another Specadoc lifecycle above them and does not require
Foreman inside them. For one local change, prefer one ordinary controller.

## Establish the mandate

1. Find the existing coordination record for this repository or roadmap first
   (`references/state.md`). Read its mandate and latest decisions; a step of
   the same roadmap continues that record and its standing mandate.
2. Restate the user's outcome, quote explicit requirements, identify allowed
   repositories/work areas, and define an end-to-end acceptance scenario.
3. Read `references/checkpoints.md`. State which decisions remain with the user
   and whether an explicit mandate, new or inherited, delegates ordinary local
   plan checkpoints. Invoking this skill alone does not delegate those approvals.
4. Read `references/controllers.md` before launch. Verify persistent controller
   sessions, continuation, nested worker/reviewer capability, delivery, permission
   boundaries, and model bindings. No model names or levels are fixed by this
   skill. Use installed project/host routing; never silently change bindings.
   Show each repository's routed roles beside the runtime/model you will launch;
   on a mismatch ask the user. Never edit routing or role files yourself.
5. Reuse the record found in step 1, or create one where `references/state.md`
   says. It tracks relationships and shared decisions, not duplicate local
   specifications, task lists, or verification logs.

## Partition and dispatch

Agree shared interfaces and contract ownership before dependent implementation.
Record producers, consumers, dependencies, compatibility expectations, and what
evidence makes each dependency ready. Parallelize independent work only.

Assign one writer per checkout and an explicit owner per shared resource. Separate
worktrees do not isolate databases, ports, generated artifacts, or deployments:
name those resources too. Controllers must not edit another owner's repository.
Start with one controller per repository or genuinely isolated change; do not
split one tightly coupled diff across competing controllers.

Give each controller a bounded brief: local outcome and why, user requirements
verbatim, shared contract/version, verified facts versus assumptions, scope and
prohibitions, dependency readiness, checkpoint authority, and completion evidence.
Quote the extracted source excerpt (roadmap row, decisions) so the controller
does not re-read the whole source. Tell it explicitly to use Specadoc for the
local change. Write it from `references/controller-brief.md`: cite the standing
constraints in the coordination brief instead of repeating them, in full
sentences. Let it choose its local
plan and mechanism. Do not direct their workers or modify their active diff.

Require the controller to challenge a contradictory contract or disproportionate
plan. A cross-project discovery returns to orchestration; do not quietly solve it
inside one repository and leave consumers on an obsolete contract.

## Coordinate checkpoints

Continue the same controller for related work. At a question, read the
controller's `specadoc_step.py status <slug>` and handoff, open only the plan
section the decision needs, apply only the authority recorded in the mandate,
and send a specific decision referencing the current checkpoint. Keep each
message short (about 150 words): the decision, checkpoint key and `D<n>`; the
rationale stays in the coordination record, since every message stays in the
controller's context for the rest of its session. Relay options
meant for the user verbatim (`references/checkpoints.md` → Relaying options).
Route changed requirements through affected local plans and approvals before
implementation resumes.

Use supported status/events and compact reports, not full-log polling. Prefer
the host's completion/failure event over waiting; a bounded wait is the fallback
(`references/controllers.md` → Waiting). Follow
host foreground/background rules and delivery limits. A controller ending its
turn can mean a checkpoint, blocker, or failure, not completion. Do not promise
unattended monitoring without a working host mechanism. Keep controller sessions
few and small (`references/controllers.md` → Keep sessions few and small).

Intervene for contract drift, overlapping writers, repeated failures, missing
proof, or scope growth. Do not retry a launch blindly after a lost event; reconcile
recorded sessions and artifacts first. Stop or establish the old writer inactive
before replacing it, and transfer the accepted state without inventing progress.

## Accept locally, then end-to-end

Require each local handoff to include repository/work area, change slug, current
phase, exact diff/commit identifier when available, verification evidence,
independent review result tied to that diff, unresolved limitations, and producer
contract readiness. A commit is not required or authorized just by this handoff.
When the change produces or consumes a shared contract, the handoff also maps
every field to its source of truth, a test asserts the exact field set, and the
reviewer checks that map. Review PASS on behavior does not prove field names.

Give integration runs and field comparison to one persistent integration
verifier (`references/roles/integration-verifier.md`), continued across rounds
like a Foreman executor; keep its verdicts, not its logs. It reports and never
fixes. Never place Foreman inside a controller.

Inspect the artifacts rather than accepting a summary alone, but read verdicts
and the lines they cite: do not read repository code, tests, project skills or
Specadoc script internals yourself, and do not run project quality tools,
`validate_change.py` or tests; the owning controller runs them and reports
(3.7/3.8: doing this yourself filled 200k of orchestrator context). Give a check
that needs them to a scout or the integration verifier. Recording an accepted
change (archive, stack refresh) uses the controller's final-gate evidence; do
not rerun quality tools or tests before it. Local review PASS
does not establish integration success. The integration verifier runs the
agreed end-to-end scenario in the authorized environment with compatible
component versions. If integration
needs a fix, return it to the owning controller and preserve its Specadoc gates;
changed executable diffs need renewed verification and independent review.

Report accepted components, integration evidence, and anything blocked or untested.
Do not call the overall task complete until shared acceptance is proved. Do not
archive local changes implicitly, create a second lifecycle tree, commit, push,
deploy, or publish without the authorization those operations require.
