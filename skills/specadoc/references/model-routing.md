# Model routing and handoff

Load this reference only when classifying risk, delegating work, or showing role bindings.

## Risk classification

### Low risk

All or nearly all are true:

- Existing implementation pattern is clear.
- No public contract, schema, migration, permissions, sensitive data, money, concurrency, or distributed behavior changes.
- Scope is local and reversible.
- Deterministic tests exist.

### Medium risk

One or more are true:

- Several modules are involved.
- A new internal interface or integration is introduced.
- Error handling is complex.
- Some technical ambiguity remains, but the change is reversible.

### High risk

Any is true:

- Authentication, authorization, payments, privacy, or sensitive data.
- Persistent schema, migration, or irreversible data effects.
- Concurrency or distributed behavior.
- Public API or compatibility obligations.
- Operationally dangerous changes.
- Major architectural tradeoffs.

## Binding resolution

Specadoc fixes no model level and keeps no approval for a binding. Each
dispatch resolves the role again, so an edited role file or `.specadoc.json`
applies to the next dispatch.

- **Runtime:** with `.specadoc.json` `roles`, read `project-config.md` and
  resolve with `scripts/role_routing.py`. Use `.specadoc.json`
  `roles.<role>.runtime`, then an installed legacy wrapper's default binding,
  then the controller's runtime.
- **Model and effort:** only from the target runtime's role file:
  `.claude/agents/<role>.md`, `.codex/agents/<role>.toml`, or
  `.opencode/agents/<role>.md`.

Without routing configuration, use the first role that exists:

1. A project role in the runtime's registry (paths above).
2. A registered plugin role, such as `specadoc:<role>` in Claude Code.
3. An available subagent without a registered role. Pass this skill's
   `references/roles/<role>.md` contract in its bounded dispatch prompt. A
   bundled contract defines behavior, not a model.
4. No subagent capability. The controller may do scout and worker work, but it
   cannot supply an independent reviewer PASS. Report the incomplete review gate
   and stop before claiming managed completion or normal archive. Never silently
   substitute self-review.

A role whose runtime is not the controller's runs through `run_role.py`; see
`runners.md`. Do not install project agents or change runtime configuration.
All dispatches remain subject to the host's delegation policy and capabilities.

## Bindings at plan approval

The plan preview shows one line per role: controller, scout, worker and
reviewer, each with runtime/model/effort and its source file. Read them with
`role_routing.py --controller-runtime <runtime> --change <slug> --dry-run --compact
--check-cli`: only roles the plan uses (reviewer; worker when a task names one)
fail it; a broken unused role file is a warning. When nothing is routed, name
the registered or embedded role. Record the line in `## Plan approval` →
`Bindings shown`. It is evidence of what would run, not
an approval of a profile. Light shows the controller and reviewer in chat.

## Binding advice

Use the risk classification above to judge whether a binding fits the change.
For example, a high-risk change whose reviewer resolves to a low effort or a
small model does not fit. In that case, add one advice line to the plan preview.
The line names the exact file and key to change: a role file's `model` or
`effort`, or a `.specadoc.json` runtime. Specadoc never edits that file, blocks
on the advice, or records it as an approval. The user edits the file, or
continues as is. A model switch for the controller is cheapest at a session
boundary, because the prompt cache belongs to one model.

## Session boundaries

Long histories increase later input, often cached. Keep one active change;
use a compact handoff when switching tasks or when the history becomes large.
A fresh session is not mandatory at every phase. Each call re-reads the whole
context; a fresh controller re-orients to 70–90k in about ten calls, so in 3.6 a
switch paid back after about 30 calls at 120k and 10 at 200k (apply: 75–105).

- Decide at a phase boundary (plan approved; locally-ready before a fix);
  within a phase the 200k task-boundary guard decides.
- Start fresh at 120k or more when the next phase dispatches workers; below
  that, or with only the final gate left, continue. `status` prints the
  observed context and this advice. Never split explore from propose.
- A fresh `apply <slug>` session starts from `### Read before continuing`, not
  discussion logs.
- For another slug, archive, or branch work, prefer a bounded handoff from
  `plan.md` or `record.md`; do not split short clarifications mechanically.
- In `apply`, record each accepted task's result in `plan.md` before the next
  task. When the controller context exceeds roughly 200k tokens, stop at a task
  boundary, write session notes with `specadoc_step.py handoff`, and recommend
  resuming in a new session from `specadoc_step.py status <slug>`.
- Use an observed host context count, never token-volume totals as an estimate
  of the current window. Pass `--context-tokens` to dispatch when available.
  A boundary handoff lists accepted interfaces, the next ready task, relevant
  decisions and exact evidence in `runs/handoff.md`, overwritten each time; do
  not copy the discussion or raw logs, and never append it to plan.md.
- When the host can fork a session, a fork of a small base session is cheaper
  than a fresh session that re-reads the same context. The base loads only
  change-independent context (this skill, repository rules, tooling notes) and
  stops; each phase starts as a fork with its handoff as the first prompt. A fork
  inherits the base's context size, so keep the base small and never fork a long
  session to escape the context guard.

Role boundaries, routing policy, dispatch contracts, and escalation live in
`subagent-routing.md`. This file owns risk, binding resolution, binding advice,
and session boundaries only.
