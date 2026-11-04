---
name: specadoc
description: Explicit engineering lifecycle with explore, propose, apply, and compact archive modes. Use only when the user names specadoc, invokes one of its modes, or requests this complete lifecycle; do not auto-apply it to ordinary coding work.
---

# Specadoc

Specadoc owns this lifecycle; do not install or mirror OpenSpec beside it.

Repository instructions, user decisions and domain skills remain authoritative.
An installed implementation skill owns coding discipline; Specadoc owns state,
approvals, routing and evidence.

## Route the request

Explicit modes win:

- `explore <request>` — establish facts and stress-test the idea without files;
  read `references/explore.md`.
- `propose <request|slug>` — produce and validate `spec.md` plus `plan.md`; read
  `references/propose.md`.
- `apply <slug>` — implement an approved plan and collect final evidence; read
  `references/apply.md`.
- `light <request>` — one-session change that updates capability specs without
  a change folder; read `references/light.md`.
- `archive <slug> [--dry-run] [--force]` — close a change into one bounded
  `record.md`; read `references/archive.md`. Never select archive implicitly.

Without an explicit mode:

1. Select `apply` only for an existing slug whose plan records both approvals.
2. Select `explore` when material requirements are unresolved or the area is
   unfamiliar.
3. Select `propose` when any `light` eligibility condition fails: another
   repository or external consumers, more than one session, money or the
   permission model, or an irreversible data effect.
4. Otherwise select `light`, including small local fixes.

## Shared invariants

- Explicit invocation only; never create a second artifact tree.
- `spec.md` is the stable behavioral contract. `plan.md` owns mutable technical
  state, approvals, evidence, and the compact archive summary.
- The controller implements by default. A `scout` or `worker` is optional and
  bounded, used only when its handoff pays for itself; one final read-only
  `reviewer` covers each stable executable diff. The controller owns all final
  verification.
- Role startup, symbol-aware tools and code graphs are independent capabilities.
  Distinguish absence after discovery from a failed exposed call; cite a call
  and error only when actually attempted.
- Keep contexts narrow: no repeated reads, raw success logs, duplicate graph
  calls or repository tours. One active change;
  see `references/model-routing.md` → Session boundaries.
- Dispatch is not acceptance: `accept` validates reports, runs Verification and
  records acceptance before the next task. Save reviews before user questions;
  do not relabel corrective rounds or hide follow-ups in completed tasks.
- Failed gates do not authorize baseline rewrites, weaker frozen Verification,
  hidden completed work or altered approvals. Use amendment, reopen or an
  authorized exception; otherwise report the blocker.
- When a required check is reserved for the user, keep its task unaccepted until
  the user supplies the result. Static checks do not replace that evidence.
  Give the command/prerequisites and resume this change with the observed result;
  do not claim completion while it is pending.
- Follow the host's command conventions (for example a required command prefix
  in repository or harness instructions) for every shell command shown or run.
- `<skill-root>` in references means this skill's directory
  (`${CLAUDE_SKILL_DIR}` in Claude Code).

## Continuity of an active change

Once explicitly selected, keep follow-ups in this lifecycle, including small
visual/verification fixes and resumed implementation. Reuse accepted spec/plan,
scout evidence and approvals while behavioral requirements are unchanged; append
evidence to the existing plan.

A bounded controller follow-up may replace a worker under the routing rules,
not final verification or independent review of a new executable diff. PASS
remains valid for `archive` after only plan, capability, archive-summary,
accounting or archive-record edits. Production code, tests, migrations,
executable config, public contracts or approved requirements changing requires
final `apply`. Start a new lifecycle only for a changed behavioral contract or
a different change.

## Progressive references

- Artifacts and deterministic gates: `references/artifacts.md`
- Risk, role bindings and binding advice: `references/model-routing.md`
- Role dispatch and fallbacks: `references/subagent-routing.md`
- Roles on another runtime (`run_role.py`): `references/runners.md`
- Project-owned routing (`.specadoc.json`): `references/project-config.md`
- Portable role contracts: `references/roles/scout.md`,
  `references/roles/worker.md`, `references/roles/reviewer.md`; load only the
  dispatched role, when no project or registered plugin role supplies it.
- TDD and review: `references/tdd-and-review.md`
- Token accounting: `references/measurement.md`
- Conflicts, optional companion skills, and source-of-truth rules:
  `references/interoperability.md`

Load only the selected mode reference and the shared reference it explicitly
requires.
