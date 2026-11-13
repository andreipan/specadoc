# Design gate

Load when a plan adds new non-test files, before plan approval.

1. In `## Class inventory`, list every new non-test file the change adds: one
   backticked path or glob per row, its layer, the requirement or boundary it
   serves, and its kind (`port`, `concrete`, or `file` for config, migrations
   and route files). Tests and prose need no row. A port needs a real boundary
   or a second implementation; "the neighbouring feature has one" is not a
   reason. Delete the example row when nothing new is added. The propose scout
   returns each row's folder and naming rule with file:line.
2. `validate_change.py <slug> --phase plan` checks the rows.
3. `specadoc_step.py design-brief <slug>` writes `runs/design-brief.md` from the
   requirements, decisions, approach, files and inventory. Run the strongest
   available `reviewer` binding on it, read-only and independent of the
   controller that wrote the plan; a fresh agent per round. After a recorded
   round it is a re-review of that round's findings and the diff since
   (`--full`: whole review).
4. `specadoc_step.py design-review <slug> --from-agent <id>` (or `--result-file`)
   records the verdict in `## Design review`, bound to the inventory hash.
   A FAIL lists each blocking finding's items (`F1.2`): close them all in one
   pass, answer each with `design-resolve <slug> --file -` (`F1.2: resolved:
   <where>` or `rejected: <why>`), then `design-brief` (it refuses an
   unanswered item). A later inventory change invalidates the PASS.
5. Present the plan for approval with the design verdict. `dispatch` requires a
   current PASS.

Answer the brief's whole-design questions (data states, platform requirements,
input edge cases, error codes) in spec `Constraints` first.

In apply, `accept` and `report` fail on a new non-test file outside the
inventory. Pre-review and the final gate check every file added since the first
dispatch. A file you did not foresee is a design
change: add its row with a reason, rerun the design review.
