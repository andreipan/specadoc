# Model routing and handoff

Load this reference only when classifying risk, delegating work, or evaluating a model-switch checkpoint.

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

## Execution levels

Task risk and execution level are separate axes. Risk describes consequences;
execution level describes the capability needed to make the remaining
decisions. A medium-risk migration can still need `HIGH` execution when its
architecture is ambiguous, while a bounded task inside a high-risk change can
use `EASY` or `MEDIUM` after the decisions are fixed.

Use three levels:

- `EASY`: bounded read-only research, test discovery, or mechanical work with
  no material decisions.
- `MEDIUM`: normal implementation with clear requirements, known patterns, and
  reversible technical decisions.
- `HIGH`: architecture, migrations, public contracts, security, concurrency,
  distributed systems, or unresolved high-impact ambiguity.

## Profile binding

Recommend and record an execution level, never a bare model name. Plans and
checkpoints carry only `EASY`, `MEDIUM`, or `HIGH`. Bind the level to a concrete
profile through the runtime in use, and state both values in the checkpoint.

| Level | Model tier | Reasoning effort | Claude Code default |
|---|---|---|---|
| `EASY` | small, fast | low | `model: haiku` + `effort: low` |
| `MEDIUM` | balanced | medium | `model: sonnet` + `effort: medium` |
| `HIGH` | most capable | high | `model: opus` + `effort: high` |

For other runtimes, bind each level to the equivalent tier of the provider in
use through the role registry below; Specadoc does not name those models.

Family and effort are both binding. A `HIGH` recommendation is not satisfied by
the right family at a lower effort. A higher effort or a newer top-tier family is
an upgrade above `HIGH`, not a substitute for user approval of the level.

Fixed role levels are `scout` = `EASY`, `worker` = `MEDIUM`, and `reviewer` =
`HIGH`, unless the user approves another mapping. A host may raise one
runtime's reasoning effort inside a level (for example a worker at `MEDIUM`
tier with `high` effort); record such an override in that host's role
registry, not here.

## Role registry

If `.specadoc.json` contains `roles`, first read `project-config.md` and resolve
the selected runtime using `scripts/role_routing.py`. Its target-runtime project
registry supplies model/effort; the controller's host wrapper frontmatter does
not. Record and approve the resolved binding snapshot before dispatch. The
lookup below remains the fallback for projects without routing configuration.

The runtime's role registry is the authoritative binding, not the table above.
Resolve each role in this order and use the first that exists:

1. Project role: `.claude/agents/<role>.md` (Claude Code),
   `.codex/agents/<role>.toml` (Codex), or `.opencode/agents/<role>.md`
   (OpenCode).
2. A registered plugin role, such as `specadoc:<role>` in Claude Code.
3. An available subagent without a registered role: pass this skill's
   `references/roles/<role>.md` contract in its bounded dispatch prompt.
   Record `Role registry: embedded contract` in the plan (or direct chat).
   A bundled contract is not a registered agent or a model configuration.
4. No subagent capability: record `Role registry: none`. The controller may
   perform scout/worker work; it cannot supply an independent reviewer PASS.
   Report the incomplete review gate and stop before claiming managed completion
   or normal archive. Never silently substitute self-review.

A role's runtime (which agent CLI executes it) is part of its binding. A
per-change runtime in the plan's `## Model handoff` takes precedence over the
registry; a role whose runtime is not the controller's runs through
`run_role.py`. See `runners.md`.

Do not install project agents or change runtime configuration automatically.
All dispatches remain subject to the host's delegation policy and capabilities.

Read the registry file for the runtime in use rather than assuming a model name.
If the registry and the table disagree, the registry wins; report the mismatch
instead of silently following either. If the runtime has no registry, state that
the level could not be bound and ask which profile to use. Embedded contracts
define behavior, not models; do not invent or silently override a host profile.

## Model Checkpoint

After analysis (and behavioral specification on the managed path), but before
technical planning, always stop for the user to confirm or change the execution
profile. Do this on both direct and managed paths, even when the current profile
exactly matches the recommendation. Skip the stop only when the user explicitly
requested uninterrupted execution or disabled the model checkpoint.

The checkpoint message must state:

- task risk and execution level as separate values;
- current model/reasoning profile when known;
- recommended model/reasoning profile and concise reasons;
- what the recommended profile will decide and produce next;
- fixed subagent profiles expected later;
- choices to continue with the recommendation, choose another profile, or
  revise scope.

On the managed path, before stopping, fill the `## Model handoff` block that `plan.md` already contains
from `assets/plan-template.md`. Do not restate the block here. Set
`**Model checkpoint:**` to `Awaiting user confirmation`, tick the phases completed
so far, and under `### Read before continuing` list `spec.md`, `plan.md`, any
`design.md` or `research.md` that exists, and at most five critical repository paths.

On direct, put the same decision-relevant handoff in chat, without creating
files: risk, execution level, known current profile, recommendation, reasons,
and the next action. After model approval, present a short plan with the bounded
edit and exact check, stop for plan approval, then implement and report evidence.
Artifact initialization, file-based handoffs and artifact gates apply only to
the managed path. An explicit uninterrupted request may waive both manual
stops, but not the bounded plan or verification.

Then output a concise recommendation and stop. Do not continue planning, write
tests, or edit production code until the user confirms or changes the profile.

Record the user's selection as approved, not merely "satisfied" or "waived".
Do not ask again for the same model checkpoint unless scope changes materially.

Role boundaries, routing policy, dispatch contracts, and escalation live in
`subagent-routing.md`. This file owns risk, execution level, and profile binding only.
