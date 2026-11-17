# Roles

[Русский](../../ru/concepts/roles.md)

Specadoc splits the work of one change between a controller and three bounded
roles: `scout`, `worker` and `reviewer`. The controller is the main agent
session that you talk to. The roles are subagents that the controller starts
for one narrow job each.

## Who decides what

| Role | Decides | Writes files | Report limit |
|---|---|---|---|
| controller | requirements, architecture, routing, escalation and acceptance | spec, plan, controller tasks | none |
| `scout` | which facts are relevant to one question | no | 500 words |
| `worker` | how to execute one defined task inside fixed boundaries | only the task's files | 600 words |
| `reviewer` | whether the implementation satisfies the contract | no | 1,200 words |

The controller owns all final verification. It also owns every decision that
the plan leaves open. A role never makes a material decision for it.

### scout

A scout answers one concrete question with evidence. It reads the repository
instructions first, then the smallest relevant set of files. It returns
relevant files, existing patterns, exact verification commands, constraints and
at most three material unknowns. It does not edit files, design the solution or
ask you questions.

The controller sends a scout when it expects to read more than about five files
or 400 lines, or when the area is unfamiliar.

### worker

A worker implements exactly one task that is ready for it. A task is ready
when all of these hold:

- The task is fully specified and has low decision risk.
- The relevant files and interfaces are known.
- The expected behavior is explicit.
- An exact deterministic Verification command exists.
- No behavior, architecture, authorization, schema, ownership or compatibility
  decision remains.

The worker uses RED-GREEN-REFACTOR and edits only the files the task allows. It
ends with one of four statuses:

| Status | Meaning | What the controller does |
|---|---|---|
| `DONE` | complete, all listed checks passed | runs `accept` |
| `DONE_WITH_CONCERNS` | complete, with something to look at | resolves or records each concern, then accepts |
| `NEEDS_CONTEXT` | the task needs a file, fact or interface that it does not give | adds exactly that context and dispatches again |
| `BLOCKED` | the task needs a decision that it does not make | makes the decision or asks you, updates the plan, then dispatches again |

`NEEDS_CONTEXT` is not a failed attempt. `BLOCKED` keeps the task with the
controller until the decision is made.

A worker also does two jobs outside the task list: the archive run and, when
the change uses one, the tidy pass before the first review.

### reviewer

A reviewer is a fresh read-only agent that judges evidence, not the
implementer's narrative. It checks completeness, correctness, test quality,
coherence and risk, and returns PASS or FAIL. Any BLOCKER or IMPORTANT finding
makes the verdict FAIL.

The reviewer role has two jobs. Before plan approval, it reviews the design
(the plan's class inventory) when the plan adds new non-test files. After
implementation, it reviews the stable diff. Each round uses a new reviewer
agent.

## Why the roles are bounded

The controller's context is the scarce budget. Each task that the controller
implements itself grows its session. When the session gets too large, a new
session must replace it, and that session reads the plan again. In measured
runs, controllers that read everything themselves reached 160k to 236k tokens
before any code was written.

Bounded roles keep the reading and the editing out of the controller's context.
The controller gets a short report and a deterministic result instead.

Decisions do not move with the work. A task with an open decision stays with
the controller, even when this costs context. Specadoc never moves
decision-heavy work to a worker to save context. A new session is the remedy
for a large context.

The controller keeps a task that is ready for a worker only with a recorded
`Controller justification`. Valid reasons are an edit smaller than its brief,
or a decision that the controller must make while it edits.

Dispatch is not acceptance. A worker's report is a claim. `accept` turns it
into evidence: it validates the report, runs the task's Verification and checks
that no file outside the task changed.

## Why review cannot fall back to the controller

The controller wrote the spec and the plan, made the open decisions and
accepted every task. A review by the same session checks its own work. Such a
check is not independent, so Specadoc does not accept it as a PASS.

If no subagent can start, the controller can still do scout and worker work
itself. It cannot supply the reviewer's PASS. It reports the incomplete review
gate and stops before it claims completion or runs a normal archive. This rule
also applies in `light` mode.

Two more rules protect independence:

- Each review round goes to a fresh reviewer agent. Reusing the previous
  reviewer needs a recorded reason (`--same-reviewer-reason`).
- We recommend that the final reviewer runs on a runtime other than the
  worker's. Two models from the same vendor share blind spots. `doctor.py` warns when
  `worker` and `reviewer` share a runtime.

## How a role is resolved

Specadoc names no models and keeps no approval for a role binding. Each
dispatch resolves the role again. An edited role file or `.specadoc.json`
applies to the next dispatch.

The runtime of a role (`claude`, `codex` or `opencode`) comes from the first
match:

1. `roles.<role>.runtime` in the project's `.specadoc.json`.
2. The default of an installed legacy wrapper role.
3. The controller's own runtime.

The model and the effort come only from the role file of the target runtime:
`.claude/agents/<role>.md`, `.codex/agents/<role>.toml` or
`.opencode/agents/<role>.md`.

Without routing configuration, Specadoc uses the first role that exists:

1. A project role in the runtime's registry.
2. A registered plugin role, such as `specadoc:<role>` in Claude Code.
3. A generic subagent. The controller adds the portable role contract from
   `references/roles/<role>.md` to its prompt.
4. No subagent capability. The controller does scout and worker work and
   reports the review gate as incomplete.

A role on a runtime other than the controller's runs through `run_role.py`.
The plan preview shows one binding line per role and can add one advice line
when a binding does not fit the risk. Specadoc never edits role files itself.

See [Routing](../guides/routing.md) for configuration and external runtimes.

## Session boundaries

Long sessions make every later call more expensive, because each call reads the
whole context again. Specadoc keeps one active change and decides about a new
session at phase boundaries:

- At a phase boundary such as plan approval, check the context size. If it is
  120k tokens or more and the next phase dispatches workers, start a fresh
  session. Below that, or when only the final gate is left, continue.
- Inside `apply`, `dispatch` blocks near 200k. The controller writes a handoff
  with `specadoc_step.py handoff` and you continue in a new session.
- Never split `explore` from `propose`.
- A fresh `apply` session starts from the plan's `### Read before continuing`
  list and from `specadoc_step.py status`, not from discussion logs.

`status` prints the observed context size and the advice. Specadoc uses an
observed context count from the host, never an estimate.

The handoff goes to `runs/handoff.md`, at most 4 KiB, and each handoff
overwrites the previous one. It lists accepted interfaces, the next ready task,
relevant decisions and exact evidence. It never copies the discussion or raw
logs.

Some hosts can fork a session. There, a fork of a small base session costs
less than a fresh session that reads the same context again. The base loads only
the skill, repository rules and tooling notes, then stops.

## Context discipline

These rules keep the controller's context small:

- No repeated reads, raw success logs, duplicate code-graph calls or repository
  tours.
- Reports give one line per successful command. A failing step shows only
  the tail of its output.
- Every role report has a word limit (see the table above).
- Each step of `specadoc_step.py` prints the same five fields: `checked`,
  `result`, `changed files`, `blocking reason` and `next`.
- Each scout, worker and reviewer runs in the foreground. The controller does
  no parallel work and never polls an agent's output in a sleep loop. When the
  host starts an agent asynchronously, `specadoc_step.py wait` waits for the
  worker's report.
- One writer at a time. Nobody edits the working tree while a worker runs.

## Related pages

- [Lifecycle](lifecycle.md)
- [Artifacts and gates](artifacts-and-gates.md)
- [Orchestrator and Foreman](../guides/orchestrator-and-foreman.md)
- Agent-facing detail:
  [subagent-routing.md](../../../skills/specadoc/references/subagent-routing.md),
  [model-routing.md](../../../skills/specadoc/references/model-routing.md),
  [roles/](../../../skills/specadoc/references/roles/)
