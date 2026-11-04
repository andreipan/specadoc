# Controller capabilities and dispatch

## Check before launching

Identify actual exposed capabilities, not assumed APIs:

- persistent controller launch and continuation, with stable identifiers;
- required runtime/model binding and accessible local work area;
- controller ability to run its own workers and independent reviewer;
- completion/question/error delivery, observable status, and cancellation;
- permission response mechanism and foreground/background rules;
- optional durable timer, notifications, and cross-runtime limits.

A generic child agent that cannot launch workers is not a full Specadoc
controller. Do not discover this after sending it an implementation brief. Use
supported independent top-level sessions/threads, or report the limitation and
offer user-managed controllers or one controller with bounded workers. Do not
silently collapse the hierarchy or claim independent review when unavailable.

Show actual model/effort bindings when observable and label unknowns unverified.
Respect project-owned routing. A stronger/weaker-model suggestion is advice,
not permission to edit a role or substitute a requested unavailable model.

## Map to the current host

This skill names capabilities, not host commands. Take concrete commands from the
host's own instructions or from workspace host notes, and record the observed
mapping once in the coordination record:

| Capability | Use |
|---|---|
| launch / continue | one resumable session per controller in its assigned work area |
| wait for completion | one bounded wait (minutes) per active controller; on a timeout read status and the last error before waiting again; read its final output only after the wait returns |
| fork at a point | optional; start a phase or step from a prepared base session instead of re-reading context |
| cancel / status | stop a stale writer; read status from evidence, not a title |
| delivery limits | whether a parent turn may end while a child result is pending |

- **Thread hosts:** each controller is an independent resumable thread. Confirm
  the hosted runtime's tools and delivery too. A polling loop or monitor over the
  thread list is improvised monitoring; use the host's wait.
- **Cross-runtime CLI controllers:** the child inherits the launcher's
  environment. Remove the launcher runtime's session variables (`run_role.py`
  shows which) so Specadoc context checks measure the controller, and pass
  `--controller-runtime` on every routed step. Write logs to the coordination
  directory and wake on process completion.
- **Native child sessions:** verify nesting depth and delegation tools. A
  resumable child alone does not prove it can act as a controller.
- **Foreground-delivery hosts:** obey foreground requirements for sequential
  dependent work. Do not end a parent turn while a required result is pending if
  delivery stops then. Use background work only when independent, supported, and
  observable.

## Waiting

A failed provider call can leave a controller errored while a wait for
completion keeps waiting: in 3.5 a 30-minute wait returned after 46 minutes and
the network error behind it was noticed late. Wait in bounded intervals of a few
minutes. After each, read the controller's status and its last error event: an
errored turn needs a supported retry or a decision, not another wait. A wait
that returns late is not evidence of progress.

Resume a controller from `specadoc_step.py status <slug>` and its
`runs/handoff.md`, not by re-reading spec, plan and design: in 3.5 the
orchestrator re-read plan.md five times.

## Keep sessions few and small

- Continue the controller that finished a change for its integration fix and
  archive. Archive dispatches no worker, so the dispatch context guard does not
  force a new session.
- A controller ends its turn only in an envelope state: checkpoint, blocked,
  failed or locally-ready. Starting a worker is not a reason to end the turn.
- When the host can fork a session, prepare one base controller session with only
  step-independent context (skills, repository rules, tooling notes) and fork it
  for each phase or step; send the step brief as the fork's first prompt. Without
  a fork, start fresh from a compact handoff.
- Start each roadmap step in a fresh orchestrator session from the coordination
  record, or fork from the point right after the mandate was set. Extract a large
  source (roadmap, sweep) into the step brief once, with a scout, and do not
  re-read it whole.

Prefer completion events. With a supported durable timer, keep at most one future
coordination tick for the whole orchestration; inspect only controllers that need
attention. Cancel it when finished or waiting solely for the user. Without one,
use supported event/foreground waiting and state the limitation. Never improvise
durable monitoring with shell sleep or duplicate watcher processes.

## Integration verifier

The integration verifier is the orchestrator's executor, not a controller. It
sits beside the controllers, not inside them. Launch it once, in the
orchestrator's harness, as a continuable session: a native subagent you can
message again, or a host thread. Brief it with the acceptance scenario,
component revisions, the coordination directory, and contract snapshots. Save
external sources such as wiki pages there as files first, because the verifier
may lack the connector. Its role binding belongs to the installed harness;
`.specadoc.json` does not route it. Route each failure it reports to the owning
controller.

A Specadoc task whose integration run belongs to the verifier carries
`External verification:`. Its controller accepts the local Verification
(EXTERNAL-PENDING) and may open review; it does not wait for the run. Hand the
verifier's result to that controller, which records it with
`specadoc_step.py external-result`; the final gate needs the PASS. The order of
review and integration is then the user's authorization, not a gate deadlock.

## Report and decision envelope

Ask controllers to end a turn at checkpoints rather than wait mid-run for a reply:

    Controller / repository / change slug:
    Event ID or checkpoint key / phase:
    State: working | checkpoint | blocked | failed | locally-ready
    Result and artifact references:
    Diff/contract revision and verification/review evidence:
    Question, recommendation, and next action:

Record a checkpoint key from the host event ID or controller+slug+phase+revision.
Acknowledge each current checkpoint once. A decision names that key, accepted
evidence, scope, and next authorized action. Do not auto-reply to repeated or
stale reports: reconcile first. Queued text is not proof a decision was consumed.

## Lost events, replacement, and permissions

Do not retry a launch blindly after a timeout or missing event. Inspect the
recorded session, work area, artifacts, and diff: it may already be working or
finished. Read status from evidence, never from a session title. If inspection is
unavailable, report uncertainty and ask rather than launch a second writer.

Before replacing a controller, stop it or confirm it inactive, transfer its
local plan and accepted evidence, and record the new identifier. After compaction,
read back the coordination record and current local checkpoints; revalidate
dependencies before continuing. Persist quota/rate-limit blockers without retry
storms, silent provider changes, or letting dependent work proceed on guesses.

An exposed permission question is separate from a lifecycle checkpoint. Answer
only when the host permits delegated approval and the explicit user mandate
covers the exact request; prefer allow_once and record why. A text message does
not approve a tool request. A denial is not an invitation to bypass the gate.
Keep briefs in accessible authorized locations; do not broaden global access.
