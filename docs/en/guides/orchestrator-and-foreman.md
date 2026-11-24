# Orchestrator and foreman

[Русский](../../ru/guides/orchestrator-and-foreman.md)

Specadoc ships two management skills: `foreman` and `orchestrator`. They are
not lifecycle modes and they are not roles. Each one starts only when you name
it in your request. An installed management skill does not change role
bindings and does not start on its own.

In Claude Code the skills are `specadoc:foreman` and `specadoc:orchestrator`.
Plain skill installations use `foreman` and `orchestrator`.

## Which one to use

| Situation | Use |
|---|---|
| One local change, with or without several workers | An ordinary Specadoc controller. Use neither skill. |
| A long coding, research, browser or data task that one persistent executor can do | `foreman` |
| Several Specadoc controllers in different repositories or isolated changes, for one outcome | `orchestrator` |

Foreman does not need Specadoc. Orchestrator coordinates Specadoc controllers
and needs Specadoc in each repository.

Do not put foreman inside a Specadoc controller, and do not put foreman inside
an orchestrator controller. The task boundaries, approvals, verification and
independent review of Specadoc stay in force.

If a plan that you approve will start two or more Specadoc controllers in
different repositories, name the orchestrator in your request. Without it, the
session coordinates without a recorded mandate and without a coordination
record.

## Foreman

The foreman keeps your goal, the decisions and the acceptance in the main
session. One persistent executor does the hands-on work across related steps.

Example request:

> Use foreman: investigate the intermittent import failure through one persistent
> executor. Preserve the public error format and verify the original failure case.

### Who does what

| Foreman (main session) | Executor |
|---|---|
| Requirements, decisions, briefs, corrections, acceptance, communication with you | Commands, investigation, experiments, implementation, evidence |

The foreman does not do the executor's task in parallel. It can inspect
results, run short acceptance checks and keep notes.

Each brief to the executor contains:

- the purpose and your requirements, word for word
- the facts and the assumptions, kept apart
- the allowed scope and the forbidden actions
- the completion evidence and a depth budget.

The executor selects the
mechanism. The brief asks it to challenge a plan that is too large or that the
evidence contradicts.

### Preflight of capabilities

Before the first launch, the foreman checks what the host really exposes. A
file that exists or a product feature that you expect is not proof.

| Capability | What the foreman checks |
|---|---|
| Launch and continuation | A stable session or thread identifier, and that the same executor can take another task |
| Binding | The configured model and effort, if observable. Otherwise it labels them unverified. |
| Scope | The executor can read its brief, write its work area and use the authorized access |
| Delivery | How completion, questions, errors and permission requests reach the main session |
| Status and interruption | Observable status, queued messages, acknowledged messages and real cancellation |
| Scheduling | Whether a durable timer and notifications really exist |

If the host cannot continue an executor, the foreman stops before the task. It
explains that a persistent foreman is not available. It offers a normal bounded
worker or a supported persistent thread, and you select one.

The foreman uses the installed model bindings. It does not select a model,
change role settings, or use another model in place of an unavailable one that
you requested.

### Supervision and correction

The executor ends each turn with a question, a blocker or a completed result.
The foreman reads detailed logs only for a concrete concern or for acceptance.
It forwards your corrections word for word.

A correction has this form: observed fact, suspected cause, next action, and
what must stay untouched. Reasons to intervene are repeated failure, scope
growth, substituted test cases, no progress, and facts invented after
compaction.

The foreman replaces the executor only for a dead session, a changed
environment, stale context that obstructs the work, or repeated fabrication or
boundary violations. Before a new writer starts, it stops the old executor or
checks that it is inactive. Then it transfers the brief and the evidence.

### Acceptance

The foreman treats the executor's report as a hypothesis. It inspects the
artifact and reproduces the proof in the authorized environment. A short check
must cover the original failure case, not an easier substitute.

Each management step ends in one of four states: `working`, `waiting-user`
(a named decision from you), `blocked` or `accepted`.

For work that crosses turns or compaction, the foreman keeps one small handoff
file in an authorized work area. The file holds:

- the goal, the invariants and the acceptance criterion
- the executor identifier, its binding and its continuation mechanism
- the current step and its state
- the last accepted evidence, open questions and the next action.

It holds no secrets and no full logs.

### What the foreman does not do

- It does not grant permissions. Choosing foreman does not authorize a commit,
  a push, a deploy, a publication or a change to an external system.
- It does not answer a permission request with a text message to the executor.
- It does not create a second manager under the executor or start helpers by default.
- It does not simulate monitoring with shell `sleep` or promise to return later.
- It does not retry a launch blindly after a timeout or a lost reply. It
  inspects the session, the artifacts and the diff first.

## Orchestrator

The orchestrator owns the shared outcome across independent Specadoc
controllers. Each controller owns its local lifecycle: spec, plan, approvals,
workers, final verification and reviewer. The orchestrator owns the shared
contracts, the dependencies and the end-to-end acceptance. It talks to
controllers, not to their workers.

Example request:

> Use orchestrator: coordinate separate Specadoc controllers for the service,
> SDK, and portal. Agree the API contract before dependent implementation and
> verify the whole flow. You may accept ordinary local plans within this scope;
> ask me about changed requirements or external effects. Do not deploy or publish.

In the commands below, `<orchestrator-root>` is the installed
`skills/orchestrator` folder and `<skill-root>` is the installed
`skills/specadoc` folder.

### The mandate

A request for the orchestrator authorizes coordination only. It does not
approve local plans or tools. The orchestrator asks whether you delegate the
ordinary plan checkpoints within a defined goal, set of repositories, contracts
and risk boundary. The suggested question:

> May I accept local plans within this goal and these contracts, returning to you
> for changed requirements, risk, external effects, or scope? Otherwise I will
> bring the required checkpoints to you, grouped when they share one decision.

The orchestrator also asks whether the mandate holds for one step or for a
range of roadmap steps. A mandate in the coordination record stays in force for
later steps of the same roadmap inside its boundary. Permissions for one step,
such as an archive, a commit or a push, do not apply to the next step.

The mandate can name one dedicated, disposable test database. Controllers and
the integration verifier can then run integration tests and test migrations on
it without a new question each time. The mandate never covers a working, shared
or production database.

Under a mandate, the orchestrator approves an ordinary local plan when all of
these conditions are true:

- The design gate of the plan is a current PASS, or the plan adds no new
  non-test file.
- `validate_change.py --phase plan` passes.
- No decision in the plan belongs to you (see the table below).
- Each exception to a repository architecture rule is allowed by that rule.

The controller then records the approval:

```text
python3 <skill-root>/scripts/specadoc_step.py approve <slug> --by orchestrator --source 'mandate D<n>, decision D<m>' --bindings '<role runtime/model/effort, ...>'
```

A design FAIL never goes to approval by the orchestrator. Past the review round
limits of Specadoc, the orchestrator can grant extra rounds under the mandate
and names each one in the final report.

### Decision boundaries

| Decision | Owner |
|---|---|
| Local implementation mechanism within the accepted contract | Local controller |
| Dependency schedule and compatible shared-contract details inside the mandate | Orchestrator, recorded and sent to the affected owners |
| Ordinary local plan checkpoint | You, unless you delegated it explicitly |
| New product behavior, incompatible contract, added repository, material change of risk or scope | You |
| Production, destructive migration, secrets, money, system changes, publication, push, deploy | You, for that action |
| Network access, a dependency install or update, a sandbox bypass, a command that a runtime denied | You, for that exact command |
| Runtime and model routing, role files, `.specadoc.json` | You |
| Independent review result | The independent reviewer |

A role start on the runtime that `.specadoc.json` routes it to is not a denied
command. The routing is your authorization, also outside the sandbox.

Under a mandate, the orchestrator decides some questions itself. Each of these
questions keeps the external contract, response codes, irreversible data,
security, money and production as the sources state them. Examples are spec wording, test cases,
internal rules, the order of local steps, and a choice among the controller's
options. The controller's recommendation is the default.

A question that changes one of those things stops only its step. While a
controller runs, the orchestrator writes such a question at the end of its turn
in plain text and continues the independent steps.

### Preflight

Before the launch, the orchestrator checks the capabilities of the host:

- persistent controller sessions with stable identifiers, and continuation
- the ability of each controller to run its own workers and reviewer
- delivery of completion, questions and errors, and observable status
- permission boundaries, foreground and background rules
- the model bindings, which it shows next to the runtime and model that it will start

A generic child agent that cannot start workers is not a full Specadoc
controller. If the host has no such capability, the orchestrator reports the
limit. It offers controllers that you manage or one controller with bounded
workers.

Before the mandate question, it runs the probe in each repository:

```text
python3 <skill-root>/scripts/doctor.py --probe --baseline
```

`--baseline` runs the final gate on the untouched checkout. If the host gives a
child another environment, the orchestrator also runs
`doctor.py --probe --expect-head <sha>` through the host's launch. An error
stops the run while you are present. Keep the machine awake for the run: idle
sleep looks like stalled roles.

### Coordination record

The orchestrator keeps a small coordination directory in an authorized work
area, for example `orchestration/<task>/`. A later step of the same roadmap
appends to the existing record.

| File | Contents |
|---|---|
| `brief.md` | Shared goal, your invariants word for word, boundaries, mandate, acceptance scenario, contract owners and revisions |
| `status.md` | Controller identifiers and work areas, links to local plans, observed bindings, dependencies, last checkpoint, blockers, next action |
| `decisions.md` | Numbered cross-project decisions `D<n>`, with rationale and authorization |

The record links to local Specadoc records. It holds no copies of specs,
plans or verification logs.

### Research before a block of steps

For a block of roadmap steps, the orchestrator runs research before the first
controller. It skips research for a single step whose sources you already
settled.

1. One read-only research session per step runs a full Specadoc `explore`, three at a time.
2. Each session writes only `<coordination dir>/research/<step>.md` and source copies under `sources/`.
3. One worker merges the questions into `questions.md`.
4. The orchestrator asks you every class A question in one batch.
5. It decides every class B question itself and records it as `D<n>`.

A class A question changes the external contract, response codes,
irreversible data, security or money. All other questions are class B. A
conclusion that depends on code from an earlier step of the block carries the
mark `depends on <step>`.

Divergences between sources (wiki, data model, producer code, repository
rules) and decisions taken without the business analyst go to the BA register.

### Controller briefs

The orchestrator writes each brief from
[controller-brief.md](../../../skills/orchestrator/references/controller-brief.md).
A brief is under about 2,000 characters. It cites standing constraints in
`brief.md` by decision number and does not repeat them. It names every file by
its repository-relative path. It tells the controller to use Specadoc for the
local change, and it lets the controller select its local plan.

The controller ends its turn only in a checkpoint state and returns this envelope:

```text
Controller / repository / change slug:
Event ID or checkpoint key / phase:
State: working | checkpoint | blocked | failed | locally-ready
Result and artifact references:
Diff/contract revision and verification/review evidence:
Undo (locally-ready): revert is enough | <manual step or data repair>
Tidy (before the first review): fixed N / skipped (reason) / not required
Context: <observed tokens, or unknown>
Question, recommendation, and next action:
```

### Checkpoints

At a checkpoint, the orchestrator reads `specadoc_step.py status <slug>` and
the handoff of the controller. It opens only the plan section that the decision
needs. Its message to the controller is about 150 words: the decision, the
checkpoint key and the `D<n>`. The rationale stays in the coordination record.

If a controller returns options for you, the orchestrator gives them to you word
for word, with the controller's labels and recommendation. An answer such as
"go" or "ok" picks no option, and the orchestrator asks again.

### Integration verifier

The integration verifier is one persistent session beside the controllers. It
runs the agreed end-to-end scenario and compares shared contracts field by
field with their source of truth. It reports PASS, FAIL or BLOCKED and never
fixes a defect. The orchestrator sends each failure to the owning controller.

The verifier runs in the harness of the orchestrator. `.specadoc.json` does not
route it. Its contract is
[integration-verifier.md](../../../skills/orchestrator/references/roles/integration-verifier.md).

A task whose integration run belongs to the verifier has
`External verification:`. Its controller can open review before the run. The
controller records the verifier's result with `specadoc_step.py external-result`.

### Acceptance

Each local handoff gives:

- the repository, the change slug and the phase
- the diff or commit identifier
- the verification evidence and the review result for that diff
- the open limits and an `Undo:` line.

An undo that needs more than a revert goes to you if the approved plan did not
name it.

A local review PASS does not prove integration. The orchestrator calls the task
complete only after the integration verifier proves the shared acceptance.

The orchestrator reads verdicts and the lines that they cite. It does not read
repository code or run tests, `validate_change.py` or quality tools itself.
The owning controller, a scout or the integration verifier does that work.

### Recovery

- After a timeout or a lost event, the orchestrator inspects the session, work
  area, artifacts and diff first.
- Before it replaces a controller, it stops the old one or checks that it is
  inactive. Then it transfers the local plan and the accepted evidence.
- After compaction, it reads the coordination record and the current local
  checkpoints again, and checks the dependencies again.
- After an authentication failure, it dispatches nothing new and gives you the
  exact sign-in step. After you sign in, it retries the failed turns once.
- On a quota or rate limit, it records the blocker and does not retry in a loop.
- A `host slept N s` line means that the machine slept, not that a role stalled.

A controller resumes from `specadoc_step.py status <slug>` and `runs/handoff.md`.

### What the orchestrator does not do

- It does not invent an approval or write "user-approved" without your words.
- It does not edit routing, role files or `.specadoc.json` to make a launch fit.
- It does not run a command that a controller's runtime denied.
- It does not direct the controllers' workers or edit their active diff.
- It does not archive, commit, push, deploy or publish without the authorization
  for that action.
- It does not open your question tool while a controller runs, because the tool
  blocks child reports.

## Orchestrator scripts

The coordination log and the BA register are append-only files. Write them only
through these scripts.

| Command | What it does |
|---|---|
| `coordination_log.py decision <file> --by user\|orchestrator --title '<t>' --file -` | Appends the next `### D<n>` entry, at most 2 KiB |
| `coordination_log.py state <file> --file -` | Replaces the current-state block, at most 1,536 bytes |
| `coordination_log.py last <file>` | Prints the header of the newest decision |
| `coordination_log.py get <file> D<n>` | Prints one decision |
| `coordination_log.py capsule <file>` | Prints the role reminder to read after a compaction, at most 60 lines |
| `ba_register.py add <file> --title T --step S --type T --status S` | Adds an item with the next free number |
| `ba_register.py status <file> <n> --status S [--note TEXT]` | Changes the status of an item and keeps the item |
| `ba_register.py list <file> [--status TEXT]` | Lists the items |

Run them as `python3 <orchestrator-root>/scripts/<name>.py`.

`decision --by user` needs `--quote` with your own words. A bare "go" or "ok"
also needs `--confirms` with the one proposal that it accepted. Messages to a
controller cite the decision number that `last` or `get` printed.

The BA register starts with these types: `divergence from the wiki`,
`divergence from the ERD`, `divergence from producer code`, `ambiguity in a
source`, `decision without the analyst`. Its statuses are `open`,
`default applied, awaiting analyst`, `closed by analyst (<date>)` and
`moved to stage <N>`. A number is never reused.

For the agent-facing detail, see
[orchestrator SKILL.md](../../../skills/orchestrator/SKILL.md) and
[foreman SKILL.md](../../../skills/foreman/SKILL.md).
