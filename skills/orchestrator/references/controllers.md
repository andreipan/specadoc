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

- **BB or another thread host:** each controller is an independent resumable
  thread in its assigned repository. Use installed host instructions, not hardcoded
  command guesses. Confirm the underlying runtime's tools and delivery too.
- **Native child sessions:** verify nesting depth and delegation tools. A
  resumable child alone does not prove it can act as a controller.
- **ACP:** obey foreground requirements for sequential dependent work. Do not
  end a parent turn while a required result is pending if delivery stops then.
  Use background work only when independent, supported, and observable.

Prefer completion events. With a supported durable timer, keep at most one future
coordination tick for the whole orchestration; inspect only controllers that need
attention. Cancel it when finished or waiting solely for the user. Without one,
use supported event/foreground waiting and state the limitation. Never improvise
durable monitoring with shell sleep or duplicate watcher processes.

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
