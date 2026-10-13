# Propose mode

Load this reference only for `specadoc propose`.

1. Reuse accepted explore evidence; do not repeat reconnaissance.
2. Initialize `docs/agent/<slug>/spec.md` and `plan.md` with
   `scripts/init_change.py`. Add design/research only when the artifact rules
   require them.
3. Resolve behavior-changing questions and fill observable requirements,
   acceptance scenarios, non-goals, constraints, assumptions, and capability
   operations in `spec.md`.
4. Run `validate_change.py <slug> --phase spec`, clear violations, record the
   risk and execution-level recommendation, then stop for model approval.
5. Under the approved profile, complete three to eight independently verifiable
   tasks and the requirement-to-check matrix in `plan.md`.
6. Run `validate_change.py <slug> --phase plan`, present a compact plan preview,
   and stop for plan approval.

Model approval and plan approval are independent. An explicit uninterrupted
execution request may waive the stops, but not specification or validation.

Read `artifacts.md` and `model-routing.md` while preparing the proposal.
