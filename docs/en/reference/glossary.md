# Glossary

[Русский](../../ru/reference/glossary.md)

This page defines the terms of the Specadoc documentation. Each term has one
meaning, and the documentation uses one term for each concept. The last column
links to the page that explains the term.

Role names (`scout`, `worker`, `reviewer`), verdicts (`PASS`, `FAIL`), finding
severities and statuses are fixed English identifiers.

| Term | Definition | Explained in |
|---|---|---|
| acceptance | The `specadoc_step.py accept` step. It checks the task scope, validates the report, runs the task Verification and records the Evidence. A dispatch is not an acceptance. | [Roles](../concepts/roles.md#worker) |
| acceptance scenario | A `### A<n>` block in `spec.md` with `Given`, `When` and `Then`. Each requirement maps to at least one scenario. | [Plan structure](plan-structure.md#specmd) |
| amendment | A recorded change to the scope or frozen Verification of a dispatched task, made with `specadoc_step.py amend` and a reason. | [Artifacts and gates](../concepts/artifacts-and-gates.md#amendment-reopen-and-exception) |
| approval | A user decision recorded in `plan.md` with `specadoc_step.py approve`. An orchestrator can approve under a recorded user mandate. | [Artifacts and gates](../concepts/artifacts-and-gates.md#approvals) |
| artifact root | The folder that holds all Specadoc files of a repository. The default is `docs/specadoc`. | [Configuration](config.md#artifact-root) |
| baseline | The content manifest of the working tree that `dispatch` records in `runs/T<n>-baseline.json` before a task starts. A retry keeps the first baseline. | [Scripts](scripts.md#review_snapshotpy) |
| BLOCKED | A worker status: the worker cannot continue without a decision. Also a `specadoc_step.py` result: the step cannot evaluate. | [Roles](../concepts/roles.md#worker) |
| capability operation | One line under a capability spec in `## Affected capabilities`: `ADDED`, `MODIFIED`, `REMOVED` or `RENAMED` of a `C<n>` requirement, with the cited `R<n>` ids. | [Artifacts and gates](../concepts/artifacts-and-gates.md#capability-operations) |
| capability spec | A long-lived file `<root>/specs/<capability>.md` that describes the current observable behavior of one capability with `C<n>` statements. | [Artifacts and gates](../concepts/artifacts-and-gates.md) |
| change | One unit of work with a slug. A full-lifecycle change has a change folder. A light change has none. | [Lifecycle](../concepts/lifecycle.md) |
| change folder | The folder `<root>/<slug>/` with `spec.md`, `plan.md`, optional `design.md` and `research.md`, and `runs/`. | [Plan structure](plan-structure.md#layout-of-the-artifact-root) |
| class inventory | The `## Class inventory` table in `plan.md`. It lists each new non-test file with its layer, reason and kind (`port`, `concrete` or `file`). | [Artifacts and gates](../concepts/artifacts-and-gates.md#design-gate) |
| companion skill | An optional skill that Specadoc uses for one step: `tidy`, `codebase-design` or `domain-modeling`, or an equivalent host skill. | [Companion skills](../guides/companion-skills.md) |
| context discipline | The rules that keep the controller's context small: no repeated reads, raw success logs or repository tours, and compact step output. | [Roles](../concepts/roles.md#context-discipline) |
| context guard | The limit of about 200k tokens of controller context. At this limit, `dispatch` stops and the controller writes a handoff. | [Roles](../concepts/roles.md#session-boundaries) |
| contract file | A file `<root>/contracts/<contract>.md` in the repository of a shared package. It describes a cross-service contract change and its consumers. | [Plan structure](plan-structure.md#contract-file) |
| controller | The main agent session. It owns decisions, approvals, final verification and the artifacts. | [Roles](../concepts/roles.md#who-decides-what) |
| controller justification | The task field that says why a task that is ready for a worker stays with the controller. | [Roles](../concepts/roles.md#worker) |
| decision risk | The task field `low`, `medium` or `high`: the risk of the decisions left to the implementer. `Owner: worker` needs `low`. | [Plan structure](plan-structure.md#task-fields) |
| derived files | The task field with generated or wiring paths that a task can also change, for example lockfiles. Changes there are listed, not violations. | [Plan structure](plan-structure.md#task-fields) |
| design gate | The check before plan approval: an independent `reviewer` checks the class inventory. `dispatch` needs a current PASS. | [Artifacts and gates](../concepts/artifacts-and-gates.md#design-gate) |
| design obligation | An open IMPORTANT item of a FAIL design round that the controller accepts after the round cap. It goes to `## Global constraints` and binds `apply`. | [Artifacts and gates](../concepts/artifacts-and-gates.md#design-gate) |
| dispatch | The `specadoc_step.py dispatch` step. It checks a task, writes its baseline and brief, and hands the task to a worker or the controller. | [Roles](../concepts/roles.md#worker) |
| DONE | A worker status: the task is complete. | [Roles](../concepts/roles.md#worker) |
| DONE_WITH_CONCERNS | A worker status: the task is complete, but the worker reports concerns. The controller decides on each concern before acceptance. | [Roles](../concepts/roles.md#worker) |
| drift | A difference between a capability spec and the code. The code is authoritative. The controller reports the drift. | [Lifecycle](../concepts/lifecycle.md#explore) |
| evidence | The one- or two-line record of the commands and results that prove a task. `accept` writes it. | [Plan structure](plan-structure.md#task-fields) |
| execution | One run for token accounting: one controller transcript or one child agent. | [Scripts](scripts.md#collect_tokenspy) |
| executor | The one persistent agent that a foreman delegates hands-on work to. | [Orchestrator and foreman](../guides/orchestrator-and-foreman.md#foreman) |
| EXTERNAL-PENDING | The `accept` result for a task with `External verification:`. Dependent tasks and review can start. The final gate needs the recorded PASS. | [Artifacts and gates](../concepts/artifacts-and-gates.md#external-verification) |
| external dispatch | A role run on a runtime other than the controller's, through `run_role.py`. | [Routing](../guides/routing.md) |
| external verification | A required check that only the user or another executor can run. The task names it in `External verification:`, and `external-result` records its result. | [Artifacts and gates](../concepts/artifacts-and-gates.md#external-verification) |
| final verification | The one run of the whole suite and the repository gates before the first review, and the `## Final verification` checklist. The controller owns it. | [Lifecycle](../concepts/lifecycle.md#apply) |
| finding | One problem that a reviewer reports, with a severity `BLOCKER`, `IMPORTANT` or `MINOR`, a location and a summary. | [Artifacts and gates](../concepts/artifacts-and-gates.md#review-rounds) |
| gate | A deterministic check between phases, for example `validate_change.py --phase plan`, the design gate or the archive gates. A failed gate blocks the next step. | [Artifacts and gates](../concepts/artifacts-and-gates.md#gates) |
| handoff | The compact session notes in `runs/handoff.md` (at most 4 KiB) that let a new session continue a change. `specadoc_step.py handoff` overwrites it. | [Roles](../concepts/roles.md#session-boundaries) |
| light change | A change made in `light` mode: one session, capability specs only, no change folder. | [Light or propose](../guides/light-or-propose.md) |
| management skill | A skill that manages other agents: `foreman` or `orchestrator`. The user starts it explicitly. | [Orchestrator and foreman](../guides/orchestrator-and-foreman.md) |
| mandate | The authority that the user explicitly grants to an orchestrator, for example to approve ordinary local plans. | [Orchestrator and foreman](../guides/orchestrator-and-foreman.md#the-mandate) |
| mode | One of the five Specadoc phases: `explore`, `propose`, `apply`, `light` or `archive`. | [Modes](modes.md) |
| native dispatch | A role run as a subagent of the controller, on the controller's runtime. | [Roles](../concepts/roles.md#how-a-role-is-resolved) |
| NEEDS_CONTEXT | A worker status: the worker needs named context. The controller adds it and dispatches again. This is not a failed attempt. | [Roles](../concepts/roles.md#worker) |
| plan (`plan.md`) | The mutable technical state of a change: tasks, decisions, approvals, evidence and the archive summary. | [Plan structure](plan-structure.md#planmd) |
| plan checkpoint | The stop after `propose`, where the user approves the plan. It is the only approval stop of `propose`. | [Lifecycle](../concepts/lifecycle.md#propose) |
| portable role contract | A role instruction file `references/roles/<role>.md`. The controller passes it to a subagent when no project or plugin role exists. It defines behavior, not a model. | [Roles](../concepts/roles.md#how-a-role-is-resolved) |
| probe | The `doctor.py --probe` check of the shell that a session runs in. | [Configuration](config.md#verificationprobe) |
| provenance row | A row `<slug> \| <date> \| <effect>` in the `## Provenance` table of a capability spec, one for each contributing change. | [Plan structure](plan-structure.md#capability-spec) |
| record (`record.md`) | The compact, immutable archive of a closed change, `<root>/archive/<slug>/record.md`, at most 16 KiB. | [Plan structure](plan-structure.md#recordmd) |
| reopen | A new attempt of an earlier task from the current tree, started with `dispatch --reopen '<reason>'`. Use it for code fixes only. | [Artifacts and gates](../concepts/artifacts-and-gates.md#amendment-reopen-and-exception) |
| requirement | A `### R<n>` block in `spec.md` with observable, testable behavior. | [Plan structure](plan-structure.md#specmd) |
| review | One independent read-only check of a stable diff by a `reviewer`. | [Artifacts and gates](../concepts/artifacts-and-gates.md#review-rounds) |
| re-review | A targeted review of the earlier findings and the changed files after a fix. It does not count against the round cap. | [Artifacts and gates](../concepts/artifacts-and-gates.md#review-rounds) |
| review round | One `### G<n>` block in the round log of `plan.md`. `pre-review` records it and `review-result` settles it. | [Artifacts and gates](../concepts/artifacts-and-gates.md#review-rounds) |
| review scope | The `## Review scope` list of repository-relative file paths of the executable diff. `specadoc_step.py scope` writes it. | [Plan structure](plan-structure.md#planmd) |
| review snapshot | The sorted `{path: sha256}` manifest of the Review scope plus the spec contract sections. A PASS applies only while the snapshot is the same. | [Artifacts and gates](../concepts/artifacts-and-gates.md#when-a-pass-stays-valid) |
| reviewer | The read-only role that reviews a stable diff, or the class inventory in the design gate, and returns a verdict. | [Roles](../concepts/roles.md#reviewer) |
| risk | The `low`, `medium` or `high` value in the spec, plan and design headers. The three headers must agree. | [Plan structure](plan-structure.md#specmd) |
| role | A bounded agent job with a fixed contract: `scout`, `worker` or `reviewer`. | [Roles](../concepts/roles.md) |
| role binding | The runtime, model and effort that serve a role. Each dispatch resolves it again. | [Configuration](config.md#role-binding-resolution) |
| round cap | The limit on review rounds: three `initial` review rounds (a fourth needs `--review-decision`) and four design rounds (the next needs `--attempt-decision`). | [Artifacts and gates](../concepts/artifacts-and-gates.md#review-rounds) |
| runtime | The agent CLI that runs a role: `claude`, `codex` or `opencode`. | [Routing](../guides/routing.md) |
| scout | The read-only role that answers one bounded question about the code and returns a short report. | [Roles](../concepts/roles.md#scout) |
| skill | A packaged set of instructions that a host loads, for example `specadoc` or `orchestrator`. | [Install](../guides/install.md) |
| slug | The short kebab-case id of a change. It is also the name of the change folder. | [Plan structure](plan-structure.md#layout-of-the-artifact-root) |
| spec (`spec.md`) | The stable behavioral contract of a change: goal, requirements, acceptance scenarios, constraints and capability operations. | [Plan structure](plan-structure.md#specmd) |
| spec delta | The change to capability specs that a light change writes in place: the affected `C<n>` statements, invariants and key paths. | [Lifecycle](../concepts/lifecycle.md#light) |
| stale evidence | Accepted evidence whose files, commands or environment changed after acceptance. `specadoc_step.py refresh` accepts the task again. | [Configuration](config.md#verificationenvironment) |
| task brief | The self-contained file `runs/T<n>-brief.md` that a worker reads. `dispatch` writes it. | [Scripts](scripts.md#task_briefpy) |
| tidy pass | One behavior-preserving cleanup pass of a worker over the Review scope before the first initial review. | [Companion skills](../guides/companion-skills.md) |
| verdict | The result of a review: `PASS` or `FAIL`. | [Artifacts and gates](../concepts/artifacts-and-gates.md#review-rounds) |
| Verification | The task field with the exact commands that `accept` runs. It is frozen at dispatch. | [Plan structure](plan-structure.md#task-fields) |
| worker | The role that implements one ready task inside its Files and returns a report with a status. | [Roles](../concepts/roles.md#worker) |
