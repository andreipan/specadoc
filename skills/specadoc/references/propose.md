# Propose mode

Load this reference only for `specadoc propose`.

1. Reuse accepted explore evidence; do not repeat reconnaissance. A scout reads
   the code and returns a map; the controller opens only the files a decision
   turns on (4.9–4.11: self-reading controllers ended propose at 144–188k).
2. Initialize `docs/specadoc/<slug>/spec.md` and `plan.md` with
   `scripts/init_change.py` from the repository root. Add design/research only
   when the artifact rules require them.
3. Resolve behavior-changing questions; fill requirements, acceptance
   scenarios, non-goals, constraints, assumptions and capability operations
   in `spec.md`.
4. Run `validate_change.py <slug> --phase spec` and clear violations. Record
   one risk in the spec, design and plan headers. Never stop for model
   approval: Specadoc fixes no model level.
5. Complete a small ordered set of independently verifiable tasks (usually
    three to eight) and the requirement-to-check matrix in `plan.md`.
    A task with low decision risk (left to the implementer, not task risk),
    known Files and exact Verification gets `Owner: worker` (`--phase plan`
    requires `low`); else the controller keeps it with a `Controller
    justification`. Merge adjacent mechanical steps with shared files/checks.
    Keep `plan.md` to decisions, tasks, one-line evidence and current state
    (warning above 48 KiB). Reuse exact verifier commands, project configs,
    baseline failures and DB/live permission limits in each task's `Test
    context`. Before the preview, close what would stop a worker (BLOCKED or
    NEEDS_CONTEXT):
    - check each requirement against its acceptance scenarios and the
      contracts it touches; record every conflict and its choice in
      `Decisions`;
    - give each task's `Files`/`Derived files` the registration and wiring
      its new code needs (container bindings, providers of contextual
      bindings, mappers, exports), asking the scout to list them;
    - copy each `External verification` command from the project notes or a
      recorded run, never from memory (4.10: an invented flag failed a run);
    - put the repository's static and style gates for the task's files in
      its `Verification`, so step 6 does not find them late.
   Use an architecture-design companion only for unresolved interface choices,
   domain modeling when meanings or invariants need sharpening. The controller
   decides; workers do not choose architecture. Keep one source of truth per
   concern and the repository's artifact locations.
6. List every new non-test file in `## Class inventory` and pass the design
   gate (`design-gate.md`) before approval.
7. Run `validate_change.py <slug> --phase plan`, present a compact plan preview
   with the role bindings line, any binding advice (`model-routing.md` →
   Bindings at plan approval, Binding advice) and the context figure from
   `status`, never an estimate, and stop for plan approval;
   record it with `specadoc_step.py approve`, never by hand. When `status`
   advises it, offer `apply <slug>` in a new controller session that starts
   from the plan's `### Read before continuing` list (`model-routing.md`).

Plan approval is the only approval stop; an explicit uninterrupted execution
request may waive it, never specification or validation.

Read `artifacts.md`, `model-routing.md` and `design-gate.md` to propose.
