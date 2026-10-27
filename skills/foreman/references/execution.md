# Execution capabilities

Read before the first launch and again only if the runtime or environment changes.

## Preflight

Establish capabilities from exposed tools, installed role configuration, and host
instructions, not from a file's existence or an assumed product feature:

| Capability | Required behavior |
|---|---|
| Launch and continuation | Capture a stable session/thread identifier and verify the same executor can receive another task. |
| Binding | Show the actual configured model/effort when observable; otherwise label it unverified. Do not infer it from a session title. |
| Scope | Confirm the executor can read its brief, write its work area, and use authorized access. |
| Delivery | Identify how completion, questions, errors, and permissions reach the parent. |
| Status and interruption | Distinguish observable status, queued messages, acknowledged messages, and actual cancellation. |
| Scheduling | Determine whether a durable timer and notification mechanism really exist. |

Without continuation, stop before doing the task and explain that persistent
Foreman is unavailable. Offer a normal bounded worker or a supported persistent
thread, and let the user choose. Do not silently launch fresh substitutes.

## Host mapping, not invented APIs

- **Native child sessions:** use the exposed launch and resume handles. Check
  whether children may use required tools; an agent file is not registration.
- **BB or another thread host:** use its installed instructions for thread
  creation, continuation, status, and permission responses. A separate thread is
  not proof of delivery or of permissions inside the runtime it hosts.
- **ACP:** honor foreground requirements for sequential work. Do not finish the
  parent turn while a required child result is pending when doing so cuts off
  progress forwarding. Background execution is for independent work when allowed.

Prefer event-driven completion. If the host provides a durable timer, keep at
most one future check, reset it after an observation, and remove it when waiting
for the user or finished. If no timer exists, say so; do not simulate durable
monitoring with shell sleep, duplicate watchers, or promises to return later.
Use supported foreground waiting when required; do not busy-poll full logs.

## Failures and permissions

Do not retry a launch blindly after timeout or a lost reply: inspect the recorded
identifier, status, artifacts, and diff first. Work may have completed. Before
resuming after compaction, read back the brief, last accepted evidence, pending
question, and executor status. Never infer success from a session title.

Put authorized brief/report files inside the executor's accessible work area.
Do not broaden permissions or use another tool to evade a denied operation.
An actual approval question can be answered only with an exposed permission tool
and a real user mandate covering the exact action, preferably allow_once. Record
the request and reason. Text sent to the executor is not permission approval.
If the host denies the operation, respect the denial; ask the user for the
appropriate intervention or use a genuinely different authorized approach.

Escalate production changes, destructive actions, system settings, money,
secrets, external publication, or any out-of-mandate action. Model defaults and
this skill do not supply consent. Stop cleanly on quota/rate limits and report
the unfinished state; do not retry indefinitely or silently change providers.
