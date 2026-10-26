# Propose mode

Load this reference only for `specadoc propose`.

1. Reuse accepted explore evidence; do not repeat reconnaissance.
2. Initialize `docs/specadoc/<slug>/spec.md` and `plan.md` with
   `scripts/init_change.py`. Add design/research only when the artifact rules
   require them.
3. Resolve behavior-changing questions and fill observable requirements,
   acceptance scenarios, non-goals, constraints, assumptions, and capability
   operations in `spec.md`.
4. Run `validate_change.py <slug> --phase spec` and clear violations. Record
   the risk. Do not stop for model approval: Specadoc fixes no model level.
5. Complete a small ordered set of independently verifiable tasks (usually
   three to eight, a heuristic rather than a hard limit) and the
   requirement-to-check matrix in `plan.md`.
   Use an installed architecture-design companion only for unresolved interface
   choices; use domain modeling when meanings or invariants need sharpening.
   The controller decides; bounded workers do not choose architecture. Preserve
   repository artifact locations and keep one source of truth per concern.
6. Run `validate_change.py <slug> --phase plan`, present a compact plan preview
   with the role bindings line and any binding advice (`model-routing.md` →
   Bindings at plan approval, Binding advice), and stop for plan approval. If accumulated context warrants it, offer running
   `apply <slug>` in a new controller session that starts from the plan's
   `### Read before continuing` list (`model-routing.md` → Session boundaries).

Plan approval is the only approval stop. An explicit uninterrupted execution
request may waive it, but not specification or validation.

Read `artifacts.md` and `model-routing.md` while preparing the proposal.
