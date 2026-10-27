---
name: foreman
description: Manage one persistent executor while keeping goals, decisions, and acceptance in the main session. Use only on an explicit request to act as a foreman, manager, or прораб over one executor; do not activate for ordinary implementation, research, or planning requests.
---

# Foreman

Keep the user's goal in the main session and delegate hands-on work to one
persistent executor. This is a standalone management mode for code, research,
browser work, or data tasks, not an engineering lifecycle or a permission grant.

## Start

1. State the goal, boundaries, externally observable completion criterion, and
   executor binding in a few lines. Reuse settled requirements rather than
   starting a second questionnaire. Quote explicit user requirements in the brief.
2. Read `references/execution.md`. Check launch, continuation, status/delivery,
   nesting limits, permissions, and the actual model binding before starting.
   No model names or levels are fixed by this skill; use project/host bindings.
   Do not silently substitute a requested unavailable model or change settings.
3. Ask for human-only access or consent early, without requesting passwords or
   secrets in chat. Have the executor preflight the authorized environment before
   expensive work. Do not change unrelated system state to remove a blocker.
4. For long work, read `references/state.md` and keep a small durable handoff in
   an authorized location accessible to the executor. For a short task, use chat.

## Divide the work

The foreman owns requirements, decisions, briefs, corrections, acceptance, and
user communication. The executor owns commands, investigation, experiments,
implementation, and producing evidence. Do not do its task alongside it.
The foreman may inspect results, perform short acceptance checks, and keep notes.

Brief each bounded step with purpose, verbatim requirements, facts versus
assumptions, allowed scope, forbidden actions, completion evidence, and a depth
budget. Let the executor choose the mechanism. Ask it to challenge a plan that
is disproportionate or contradicted by evidence, rather than implementing blindly.

Use one persistent executor across related steps, not a succession of fresh
agents. Do not create another manager underneath it or allow helper fan-out by
default. A separately authorized read-only reviewer is a verifier, not a second
implementation owner; preserve required independent review for code changes.

Do not insert this mode inside an existing controller lifecycle automatically.
Its task boundaries, approvals, verification, and review remain authoritative;
an incompatible executor contract is a reason to stop and resolve the conflict.

## Supervise and continue

Ask the executor to end its turn with a question, blocker, or completed result.
During long runs, request compact progress when supported. Read detailed logs
only for a concrete concern or acceptance. Forward user corrections verbatim.

Correct based on evidence: observed fact → suspected cause → next action → what
must remain untouched. Repeated failure, scope growth, substituted test cases,
stagnation, and invented facts after compaction warrant intervention. Do not send
an interrupt or claim a correction was received unless the host supports and
confirms it; queued text is not an applied correction.

After acceptance, give the next bounded step to the same executor. Replace it
only for a dead session, changed environment, obstructive stale context, or
repeated fabrication or boundary violations. Explain why, stop or confirm the
old executor inactive, and transfer the brief and evidence before another writer
starts. Continuity is not a reason to exceed context or permission limits.

## Accept and report

Treat the executor's report as a hypothesis. Inspect the actual artifact and
reproduce the relevant proof in the authorized environment. A short check must
cover the original failure horizon, not an easier substitute. Recheck after
environment changes. Distinguish unverified, blocked, and failed results.

End each management step as working, waiting for a named user decision, blocked,
or accepted. Never imply that autonomous monitoring continues after the turn
unless the runtime actually guarantees it. Follow host foreground/background
rules. A launch is not completion; report unfinished work explicitly.

Scale the final answer to the task: result, evidence, and remaining limitations.
Do not commit, push, deploy, publish, or alter external systems without separate
authorization. Choosing this skill grants none of those permissions.
