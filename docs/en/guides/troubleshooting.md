# Troubleshooting

[Русский](../../ru/guides/troubleshooting.md)

This page lists the usual gate refusals and errors, with their cause and fix. The message texts come from the scripts. Parts in angle brackets, for example `<slug>` or `<path>`, change from run to run.

`<skill-root>` is the installed `skills/specadoc` folder. See [Install Specadoc](install.md#check-the-install).

## Read the output first

`specadoc_step.py` prints five fields for each step:

```text
checked: <what ran>
result: PASS | FAIL | BLOCKED | ...
changed files: <paths or ->
blocking reason: <reason or ->
next: <the next allowed step>
```

The exit code is 0 for PASS, ACCEPTED, CHECKED and EXTERNAL-PENDING. It is 1 for FAIL, a finding that you can fix. It is 2 for BLOCKED (the step cannot evaluate) and for NEEDS_DECISION. Read `blocking reason` for the cause and `next` for the fix. If a step raises an error, the result is `BLOCKED` and `next` is `inspect the plan and handoff files, then retry`.

`validate_change.py` prints one line per violation, `<file>:<line>: <message>`, and then `<n> violation(s) in phase <phase>`. It exits with 1 when it finds violations, and with 2 when it cannot read the change. Warnings start with `warning:` and do not block.

If you do not know which step comes next, run `python3 <skill-root>/scripts/specadoc_step.py status <slug>`. Its `next:` line names the next allowed step.

## Python version

| Message | Cause | Fix |
|---|---|---|
| `error: Specadoc scripts need Python 3.10+; this is <version> at <path>. ...` | `python3` on `PATH` is older than 3.10. A terminal without your login `PATH` often finds the system Python | Put Python 3.10 or newer first on `PATH`, or call that interpreter by its full path |
| `Codex registry resolution requires Python 3.11+; select a supported interpreter` | The project has Codex role files (`.codex/agents/<role>.toml`). Python 3.10 cannot read TOML | Use Python 3.11 or newer |

## validate_change refusals

The controller runs `validate_change.py <slug> --phase <spec|plan|pre-review|final>` before each checkpoint. A passing script checks only structure. It does not prove that a requirement is correct.

| Message | Cause | Fix |
|---|---|---|
| `error: no change directory: <path>` | Wrong slug, or the artifact root is different | Check the slug with `list_changes.py`. Check the root that `doctor.py` prints |
| `unfilled template placeholder: <text>; wrap code such as list<T> in backticks if it is not a placeholder` | Template text in `<...>` stays in the file | Replace the placeholder. If the text is code, put it in backticks |
| `missing required section: ## <name>` | A template section was deleted | Restore the section from `assets/plan-template.md` or `assets/spec-template.md` |
| `<R>: no acceptance scenario covers it` | A requirement has no scenario | Add a scenario with `**Covers:** <R>` |
| `<A>: missing Given` (or `When`, `Then`) | A scenario is incomplete | Add the missing line |
| `no capability file declared under <root>/specs/` | `## Affected capabilities` lists no capability spec | Add the operations, for example `ADDED C1 (R1) — <effect>` |
| `Owner: worker needs Decision risk: low; close the decision and set low, or set Owner: controller with a Controller justification` | A worker task still has an open decision | Close the decision, or give the task to the controller with a reason |
| `<T>: Evidence predates a later change (<reason>); re-verify with specadoc_step.py refresh` | A later edit touched the files of an accepted task | Run `specadoc_step.py refresh <slug>` |
| `final verification unchecked: <label>` | A box in `## Final verification` has no proof | Run `specadoc_step.py finalize <slug>`. Do not tick boxes by hand |
| `` verification.final: no `finalize --run` record; run specadoc_step.py finalize <slug> --run `` | `.specadoc.json` sets `verification.final`, but the full suite did not run through `finalize` | Run `finalize <slug> --run` |
| `Review result: latest round <G> outcome is FAIL, not PASS` | The last review round did not pass | Fix the findings and run a re-review |

## Approval

| Message | Cause | Fix |
|---|---|---|
| `plan approval is required before apply or dispatch` | The plan has no recorded approval | Approve the plan in chat. The controller runs `specadoc_step.py approve` |
| `plan.md has no Bindings shown; pass --bindings` | The preview did not record the role bindings | Show the bindings in `next` to the approver, then run `approve` with `--bindings` |
| `<G> is recorded but not reviewed; an approval change now would make it stale` | A review round is open | Run `pre-review <slug> --withdraw`, then `approve`, then `pre-review` again |
| `<files> changed since approval; a round recorded now would settle stale` | `spec.md` or `design.md` changed after the approval | Approve again: `approve <slug> --by user --source '<decision>'`. Then run `pre-review` |

## dispatch and accept

| Message | Cause | Fix |
|---|---|---|
| `controller context is <n> tokens, at least 200k` | The controller session is too large for the next task | Save notes with `specadoc_step.py handoff <slug> --file -`. Continue in a fresh session from `status <slug>` |
| `design review missing: run specadoc_step.py design-brief, an independent reviewer, then design-review` | The plan has a `## Class inventory` without a design review | Run the design gate. See the [design gate reference](../../../skills/specadoc/references/design-gate.md) |
| `design review predates the current Class inventory; review the changed inventory again` | The inventory changed after the design PASS | Run the design review again |
| `Verification must contain only exact backticked commands separated by semicolons; ...` | The `Verification` field has prose or a manual check | Keep only commands. Move a manual check to `External verification:` |
| `<T>: dependency <T> accepted evidence is stale (<reason>); run specadoc_step.py refresh <slug>; reopen only for code fixes` | A later edit made the evidence of a finished task old | Run `refresh <slug>`. For changed files, `dispatch` runs this refresh itself |
| `changes outside the task scope` | The worker changed a file that the task does not list | Revert the file. Or run `amend <slug> <T> --allow <path> --reason '<decision>'`, or `--derived <path>` for a generated file |
| `Class inventory files not created` | A planned file does not exist | Create the file, or change the inventory and run a new design review |
| `` `<command>` exited <code> `` | A `Verification` command failed | Fix the code, or send the task back to the worker with the failure |
| `worker report is missing: <path>` | The worker did not run `report` | Ask the worker to finish with `specadoc_step.py report` |
| `worker status <status> is not completion; ...` | The report says BLOCKED or NEEDS_CONTEXT | Remove the blocker. Then run `accept` with `--resolved '<who removed it and how>'`. Never edit the worker report |
| `worker concerns require a controller disposition` (result `NEEDS_DECISION`) | The worker reported concerns | Decide, then run `accept` again with `--note '<decision>'`. The verification result is reused |
| `verification timed out after 600s` | A command ran longer than `--verification-timeout` (600 seconds by default) | Find the cause in the log first. Keep the same baseline when you retry |
| `environment changed: <names>; list only verifier-relevant variables in .specadoc.json verification.environment` | An environment variable changed between sessions, so the evidence is old | Add `verification.environment` to `.specadoc.json`. See [Configuration](../reference/config.md) |

## pre-review and Review scope

| Message | Cause | Fix |
|---|---|---|
| `no tidy pass recorded (.specadoc.json review.tidy: required)` | The project needs a tidy pass before the first review | Run `tidy <slug>`, give the brief to one worker, then run `refresh <slug>` |
| `tidy skill not installed at <path>` | The `tidy` skill is not next to the `specadoc` folder | Install `tidy` in the same skills folder, or run `tidy <slug> --skip '<reason>'` |
| `files added during apply are missing from Review scope` | New files are not in `## Review scope` | Run `scope <slug>`, then `pre-review` |
| `line <n>: Review scope lists a Specadoc artifact: <path>; ...` | `## Review scope` names a file of the change folder | Remove that line. The scope lists only the executable diff |
| `line <n>: Review scope file does not exist: <path>` | A listed file was deleted or renamed | Run `scope <slug>`. A deleted file is written as `` `!path` `` |
| `Review result: <n> new-diff review rounds recorded; add a **Round cap override:** reason to the latest round, or stop and ask whether to consolidate or split the change` | Three `initial` rounds are done | Ask the user. Pass the user's decision with `--review-decision`, or split the change |

## Stale review snapshot

A review round stores a hash manifest of the files in `## Review scope` and of the spec contract. If one of them changes, the verdict no longer covers the current diff.

| Message | Cause | Fix |
|---|---|---|
| `<G> recorded FAIL against a stale snapshot (content changed: ...); a stale round uses no review allowance; ...` | The code changed while the reviewer worked | Correct `## Review scope`, then run `pre-review --review-type re-review` |
| `<G> recorded FAIL against a stale snapshot (approval or review policy changed ...)` | The approval changed during the round | Settle the approval. Run the same round type again on the same diff |
| `Review result: diff changed since <G>'s snapshot (changed=[...], added=[...], removed=[...]); return to apply for a new review` | The code changed after the PASS (final gate or archive) | Go back to `apply` and run a new review round |
| `Review result: diff changed since <G>'s snapshot (...); run pre-review --review-type re-review --reason minor-fixes for the executable MINOR fixes` | Executable MINOR fixes after a PASS | Run that re-review |

A stale round does not count toward the round limit. A change only in tests or prose after a PASS with only MINOR findings keeps the PASS. The gate prints a warning and asks you to name these fixes in `## Archive summary`.

## finalize

| Message | Cause | Fix |
|---|---|---|
| `result: CHECKED` with `left to the controller: ...` | Some boxes have no recorded proof | Run the commands that `next` names. Do not edit `plan.md` by hand |
| `rows still Pending: <R>; finalize <slug> --requirements '<the evidence that proves them>'` | The requirement-to-check matrix has open rows | Run `finalize` with `--requirements` |
| `.specadoc.json sets no verification.final` | `--run` has no commands to run | Run the full suite yourself. Record it with `finalize <slug> --observed '<command, result>'` |
| `the whole suite runs once over accepted code; ...` | A task is not accepted yet | Run `accept` or `refresh` first, then `finalize --run` |
| result `FAIL` with `` `<command>` exit <code> `` | A command of `verification.final` failed | Fix the failure. A worker makes executable fixes. Then run `finalize --run` again |

## Role bindings

Specadoc stores no approval for a binding. Each dispatch reads the role files and `.specadoc.json` again, so an edited role file applies to the next dispatch. The `Bindings shown` line in `plan.md` records what you saw at approval. A later edit of a role file does not need a new approval.

These errors appear when the project uses routing (`.specadoc.json` with `roles`) or when the controller passes `--controller-runtime`:

| Message | Cause | Fix |
|---|---|---|
| `controller runtime is <x>, binding expects <y>; restart in <y> or edit .specadoc.json` | The session runs on a different runtime than `roles.controller.runtime` | Start the controller on `<y>`, or change `.specadoc.json` |
| `no valid <runtime>/<role> model/effort binding; install a target role file` | The target runtime has no role file with a model and an effort | Add the role file in `.claude/agents/`, `.codex/agents/` or `.opencode/agents/` |
| `routed dispatch requires --controller-runtime or roles.controller.runtime` | The project routes roles, but the controller runtime is unknown | Pass `--controller-runtime`, or set `roles.controller.runtime` |
| `<path>: wrapper points to <x>, not <y>; migrate to native roles` | An old wrapper role file disagrees with `.specadoc.json` | Replace the wrapper with a native role file |

To see the bindings, run `python3 <skill-root>/scripts/role_routing.py --controller-runtime <runtime> --change <slug> --dry-run --compact --check-cli`. See [Routing](routing.md).

## Oversized plan

These are warnings. No gate, worker or archive step waits for them.

- `plan.md is <n> bytes (> 49152): keep only decisions, tasks, one-line evidence and current state; ...`. The warning names the four largest parts. Move long evidence to `research.md`, or delete it.
- `plan.md Handoff is <n> bytes (> 2048): ...`. Keep the checkpoint and one `Continue` line in `## Handoff`. Put session notes in `runs/handoff.md` with `specadoc_step.py handoff`.
- `<n> tasks: inspect change size and dependency boundaries; ...`. The plan has more than eight tasks. Keep corrective tasks as new tasks. Do not merge them into finished tasks.

## Missing reviewer

The controller never reviews its own diff. If no subagent can start, the controller can still do scout and worker work. It reports that the review gate is incomplete and stops before it claims completion or a normal archive. Install or permit a reviewer role, then run `pre-review` again. See [Roles](../concepts/roles.md).

| Message | Cause | Fix |
|---|---|---|
| `record a pending round and manifest before review dispatch` | `review-result` ran before `pre-review` | Run `pre-review <slug>`, then start the reviewer |
| `agent <id> already reviewed an earlier round; dispatch a fresh reviewer or pass --same-reviewer-reason` | The same reviewer agent got a second round | Start a fresh reviewer agent |
| `invalid reviewer result: <errors>` | The reply has no valid result JSON | Run the reviewer again. Do not copy or edit its reply |
| `reviewer PASS contradicts open BLOCKER/IMPORTANT findings` | The verdict and the findings disagree. The round stays open | Start a fresh reviewer for the open round |
| `reviewer process did not exit successfully` | An external reviewer run failed | Read its run file, then start the reviewer again |

## Archive refusals

| Message | Cause | Fix |
|---|---|---|
| `error: refusing to archive <slug>: <n> unmet condition(s)` | Gates are open. The lines below list each one | Fix each listed condition. Run `--dry-run` again |
| `<path>:1: provenance table does not record <slug>` | A capability spec has no row for this change | Add the provenance row to that capability spec |
| `<path>:1: declared capability file does not exist` | `spec.md` names a capability spec that is not there | Create it from `assets/capability-template.md` |

`--force` bypasses the lifecycle gates. Use it only on an explicit request from the user, and show `--force --dry-run` first.
