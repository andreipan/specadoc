# Design gate

Load this reference when a plan adds new non-test files, before plan approval.

Run 3.5 mirrored an existing feature with about seven ports, and nobody counted
classes before code. The gate makes that count and its reasons explicit, and
checks them before the first task.

1. In `## Class inventory`, list every new non-test file the change adds: one
   backticked path or glob per row, its layer, the requirement or boundary it
   serves, and its kind (`port`, `concrete`, or `file` for config, migrations
   and route files). Tests and prose need no row. A port needs a real boundary
   or a second implementation; "the neighbouring feature has one" is not a
   reason. Delete the example row when nothing new is added.
2. `validate_change.py <slug> --phase plan` checks the rows. It warns when tasks
   name new files but the plan has no inventory.
3. `specadoc_step.py design-brief <slug>` writes `runs/design-brief.md` from the
   requirements, decisions, approach, files and inventory. Run the strongest
   available `reviewer` binding on it (for example an opus reviewer), read-only
   and independent of the controller that wrote the plan.
4. `specadoc_step.py design-review <slug> --result-file <json>` records the
   verdict in `## Design review`, bound to the inventory hash. Resolve BLOCKER
   and IMPORTANT findings by changing the approach or the inventory, then review
   again. Changing the inventory later invalidates the PASS.
5. Present the plan for approval with the design verdict. `dispatch` requires a
   current PASS.

Answer the brief's whole-design questions (data states, platform requirements,
input edge cases, error codes) in spec `Constraints` first; 3.8 met them in review.

During apply, `accept` and `report` fail on a new non-test file outside the
inventory. Pre-review and the final gate check every file added since the first
dispatch (`runs/apply-start.json`). A file you did not foresee is a design
change: add its row with a reason, rerun the design review, then continue.
