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

1. Restate the user's outcome, quote explicit requirements, identify allowed
   repositories/work areas, and define an end-to-end acceptance scenario.
2. Read `references/checkpoints.md`. State which decisions remain with the user
   and whether an explicit mandate delegates ordinary local plan checkpoints.
   Invoking this skill alone does not delegate those approvals.
3. Read `references/controllers.md` before launch. Verify persistent controller
   sessions, continuation, nested worker/reviewer capability, delivery, permission
   boundaries, and model bindings. No model names or levels are fixed by this
   skill. Use installed project/host routing; never silently change bindings.
4. Read `references/state.md`. Reuse or create a compact authorized coordination
   record. It tracks relationships and shared decisions, not duplicate local
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
Tell it explicitly to use Specadoc for the local change. Let it choose its local
plan and mechanism. Do not direct their workers or modify their active diff.

Require the controller to challenge a contradictory contract or disproportionate
plan. A cross-project discovery returns to orchestration; do not quietly solve it
inside one repository and leave consumers on an obsolete contract.

## Coordinate checkpoints

Continue the same controller for related work. At a question, inspect its actual
plan/artifacts, apply only the authority recorded in the mandate, and send a
specific decision referencing the current checkpoint. Route changed requirements
through affected local plans and approvals before implementation resumes.

Use supported status/events and compact reports, not full-log polling. Follow
host foreground/background rules, especially ACP delivery limits. A controller
ending its turn can mean a checkpoint, blocker, or failure, not completion.
Do not promise unattended monitoring without a working host mechanism.

Intervene for contract drift, overlapping writers, repeated failures, missing
proof, or scope growth. Do not retry a launch blindly after a lost event; reconcile
recorded sessions and artifacts first. Stop or establish the old writer inactive
before replacing it, and transfer the accepted state without inventing progress.

## Accept locally, then end-to-end

Require each local handoff to include repository/work area, change slug, current
phase, exact diff/commit identifier when available, verification evidence,
independent review result tied to that diff, unresolved limitations, and producer
contract readiness. A commit is not required or authorized just by this handoff.

Inspect the artifacts rather than accepting a summary alone. Local review PASS
does not establish integration success. Run the agreed end-to-end scenario in
the authorized environment with compatible component versions. If integration
needs a fix, return it to the owning controller and preserve its Specadoc gates;
changed executable diffs need renewed verification and independent review.

Report accepted components, integration evidence, and anything blocked or untested.
Do not call the overall task complete until shared acceptance is proved. Do not
archive local changes implicitly, create a second lifecycle tree, commit, push,
deploy, or publish without the authorization those operations require.
