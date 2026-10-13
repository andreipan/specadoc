---
name: specadoc
description: Explicit engineering lifecycle with explore, propose, apply, and compact archive modes. Use only when the user names specadoc, invokes one of its modes, or requests this complete lifecycle; do not auto-apply it to ordinary coding work.
---

# Specadoc

Specadoc is the single lifecycle tool for this workflow. It does not install,
invoke, mirror, or maintain an OpenSpec workflow beside its own artifacts.

Repository instructions, explicit user decisions, and specialized domain skills
remain authoritative. An implementation-discipline skill, when installed, owns
how code is written; Specadoc owns lifecycle state, approvals, routing, and
evidence.

## Route the request

An explicit mode always wins:

- `explore <request>` — establish facts and stress-test the idea without files;
  read `references/explore.md`.
- `propose <request|slug>` — produce and validate `spec.md` plus `plan.md`; read
  `references/propose.md`.
- `apply <slug>` — implement an approved plan and collect final evidence; read
  `references/apply.md`.
- `archive <slug> [--dry-run] [--force]` — close a change into one bounded
  `record.md`; read `references/archive.md`. Never select archive implicitly.

Without an explicit mode:

1. Select `apply` only for an existing slug whose plan records both approvals.
2. Select `explore` when material requirements are unresolved or the area is
   unfamiliar.
3. Select `propose` when behavior is clear but the change is non-trivial.
4. Use the internal direct path only when the change is local, reversible, free
   of contract/schema/permission/money/concurrency risk, and has one exact
   check. Direct still stops for model and plan approval but creates no files.

## Shared invariants

- Explicit invocation only; never create a second artifact tree.
- `spec.md` is the stable behavioral contract. `plan.md` owns mutable technical
  state, approvals, evidence, and the compact archive summary.
- Keep one bounded `scout`, fully specified low-decision `worker` tasks, and one
  final read-only `reviewer` per stable executable diff in `apply`. The
  controller owns all final verification.
- Treat role startup, symbol-aware tooling availability, and code-graph
  availability as independent capabilities. Failure of one never implies failure of the others. Distinguish
  absence after tool discovery from a failed exposed call; cite the exact call
  and error only for a call that was actually attempted.
- Keep contexts narrow: no repeated reads, raw successful logs, equivalent graph
  calls, or broad repository summaries.
- Follow the host's command conventions (for example a required command prefix
  in repository or harness instructions) for every shell command shown or run.
- `<skill-root>` in references means this skill's directory
  (`${CLAUDE_SKILL_DIR}` in Claude Code).

## Continuity of an active change

Once Specadoc has been explicitly selected for a change, follow-up work on the
same change remains inside that lifecycle, including small visual corrections,
verification fixes, and resumed implementation. Reuse the accepted `spec.md`,
`plan.md`, scout evidence, and approvals while the behavioral requirements stay
unchanged. Record the follow-up evidence in the existing plan.

Controller execution of a bounded follow-up may replace a worker dispatch when
the routing rules favour it, but it does not remove the required final
verification or independent review for a new executable diff. A recorded PASS
remains valid for `archive`: changes only to `plan.md`, capability documents,
archive summary, execution-accounting evidence, or the archive record do not need another
reviewer. Return to final `apply` when production code, tests, migrations,
executable configuration, a public contract, or the approved requirements
change. Start a new lifecycle only when the follow-up changes the behavioral
contract or belongs to a different change.

## Progressive references

- Artifacts and deterministic gates: `references/artifacts.md`
- Risk and model checkpoint: `references/model-routing.md`
- Role dispatch and fallbacks: `references/subagent-routing.md`
- TDD and review: `references/tdd-and-review.md`
- Token accounting: `references/measurement.md`
- Conflicts, optional companion skills, and source-of-truth rules:
  `references/interoperability.md`

Load only the selected mode reference and the shared reference it explicitly
requires.
