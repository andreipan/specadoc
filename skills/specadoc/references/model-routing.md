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
`role_routing.py --controller-runtime <runtime> --dry-run --compact --check-cli`,
or name the registered or embedded role when nothing is routed. Record the line
in `## Plan approval` → `Bindings shown`. It is evidence of what would run, not
an approval of a profile. Direct shows the same line in chat.

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
A fresh session can lose useful cache, so it is not mandatory at every phase:

- At plan approval, offer a fresh `apply <slug>` session if accumulated context
  warrants it, starting from `### Read before continuing`, not discussion logs.
- For another slug, archive, or branch work, prefer a bounded handoff from
  `plan.md` or `record.md`; do not split short clarifications mechanically.
- In `apply`, record each accepted task's result in `plan.md` before the next
  task. When the controller context exceeds roughly 150k tokens, stop at a task
  boundary and recommend resuming in a new session from `plan.md`.
- Use an observed host context count, never token-volume totals as an estimate
  of the current window. Pass `--context-tokens` to dispatch when available.
  A boundary handoff lists accepted interfaces, the next ready task, relevant
  decisions and exact evidence; do not copy the discussion or raw logs.

Role boundaries, routing policy, dispatch contracts, and escalation live in
`subagent-routing.md`. This file owns risk, binding resolution, binding advice,
and session boundaries only.
