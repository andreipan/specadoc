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
| completion/failure event | prefer the host's wake on a finished, failed or interrupted controller turn; otherwise one bounded wait per active controller (see Waiting) |
| observed context | the controller's current context size, for session boundaries |
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

A question to the user blocks your turn; a host delivers child wakes only after
it ends. Ask before launching a controller or when every child is idle, never
while one runs (4.9: a blocked controller waited 24 minutes behind a question).

Every wake re-reads the orchestrator's whole context. In 3.6 about 25 of 38
three-minute waits timed out, and the wakes, not the wait output, made the cost.
Prefer a host event that fires when a controller turn finishes, fails or is
interrupted: end your turn and continue when it arrives. Only when the host has
no such event, or your turn must not end, wait in bounded intervals of about
fifteen minutes. After each timeout read only the controller's status and its
last error, not its log. A failed provider call can leave a controller errored
while a wait for completion keeps waiting (3.5: a 30-minute wait returned after
46 minutes): an errored turn needs a supported retry or a decision, not another
wait. A wait that returns late is not evidence of progress.

Resume a controller from `specadoc_step.py status <slug>` and its
`runs/handoff.md`, not by re-reading spec, plan and design: in 3.5 the
orchestrator re-read plan.md five times.

## Keep sessions few and small

- Continue the controller that finished a change for its integration fix and
  final gate. It hands the archive run to a worker (Specadoc `archive.md`), so
  archive is no reason to keep or replace a session.
- Decide a fresh controller session only at a phase boundary, by the rule in
  Specadoc `model-routing.md` → Session boundaries, using the `Context` line
  of the envelope and the advice `status` prints. Do not set thresholds of your
  own in briefs (3.7/3.8 briefs invented "hand off at 120–140k at a task
  boundary", which contradicts that rule).
- A controller ends its turn only in an envelope state: checkpoint, blocked,
  failed or locally-ready, and with none of its own background jobs still
  running (3.8: three controllers went idle with a run pending). Starting a
  worker is not a reason to end the turn.
- When that rule calls for a fresh session and the host can fork, fork one
  prepared base controller session with only step-independent context (skills,
  repository rules, tooling notes) and send the brief as the fork's first
  prompt. Without a fork, start fresh from a compact handoff.
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
controller. The verifier owns the run's evidence (row counts before and after,
log, hash); the orchestrator reads its report instead of repeating the queries.
Take the run command from the controller's checkpoint or the project notes, not
from memory (4.10: a hand-written flag failed a round). Neither reads secret
values: `.env` is read by key names only, never with `grep '^DB_'` into the
transcript.

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
    Undo (locally-ready): revert is enough | <manual step or data repair>
    Tidy (before the first review): fixed N / skipped (reason) / not required
    Context: <observed tokens, or unknown>
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
A turn that failed on authentication (an expired or time-limited login) is not
retried: no retry succeeds until the user signs in again. Record it, dispatch
nothing new, and give the user the exact sign-in step; after it, retry the failed
turns once and reconcile from status (4.5: the orchestrator and a controller both
failed and waited 16 minutes for an unprompted "go").

An exposed permission question is separate from a lifecycle checkpoint. Answer
only when the host permits delegated approval and the explicit user mandate
covers the exact request; prefer allow_once and record why. A text message does
not approve a tool request. A denial is not an invitation to bypass the gate.
When a controller reports that its runtime denied a command (network, a
dependency update, a write outside its sandbox), bring that exact command to the
user; do not run it yourself in your own, wider sandbox, and never call it
approved without a recorded user approval (3.8: the orchestrator ran a
dependency lock update with network after the controller's denial and told it
"approved"). Keep briefs in accessible authorized locations; do not broaden
global access.
