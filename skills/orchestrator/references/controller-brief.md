# Controller brief

Load this before sending a controller its first brief. Runs 3.7 and 3.8 sent
7–8k-character briefs that repeated the same prohibitions every time and glued
words together ("idle186k", "hashes2integrationfiles"); controllers had to
decode them, and every message stays in their context for the whole session.

Rules:

- Standing constraints live once in the coordination `brief.md`: forbidden
  operations (commit, stash or stack edits, push, archive, the next step),
  integration runs by the integration verifier only, no DDL or migrations on shared databases,
  the test database, preserved files. The brief cites them by path and decision
  id; it does not restate them.
- Write full sentences in the user's language with ordinary spacing. No
  abbreviations the controller must decode.
- Limits are not yours to invent: no context threshold and no token, time or
  step budget the user did not set. The controller follows `status` for context
  (Specadoc `model-routing.md` → Session boundaries) and does not stop early or
  skip work for a limit nobody set.
- Send it through a file or stdin (host notes), not as a shell argument.
- A replacement controller gets the same shape: what is done, the checkpoint it
  starts from (`status` and `runs/handoff.md`), and what changed since.
- Mandate, test database and routing are `brief.md D<n>` citations, never
  retold; 4.1/4.2 propose briefs were 2.7–2.8k because they retold them.
- Decision numbers come from `coordination_log.py` output (`last`, `get`).
- The step's source excerpt (roadmap row, sweep section) lives in a step file in
  the coordination directory; the brief cites it instead of quoting it. Name the
  decisions the step relies on; the controller reads each one, never the whole
  decision log (4.3–4.5 propose briefs were 2.8–3.6k characters and controllers
  read the 25 KB log whole).
- Name every file by its repository-relative path, the skill references too
  (`.claude/skills/orchestrator/references/controllers.md`, `roadmap.md` at the
  root). 4.6–4.8 controllers searched for an unnamed file with `find /`, which
  ran into the 120 s command timeout each time.
- The plan checkpoint carries the bindings `role_routing.py` resolved; the
  approval message repeats them as `--bindings '<...>'` (4.6: `approve` without
  them was refused once).

Shape (keep under about 2,000 characters):

```markdown
# <step> <slug>: <one-line outcome>

Standing constraints: `<coordination dir>/brief.md` (mandate D<n>, test database D<m>).
Use Specadoc for this change. Start from `specadoc_step.py status <slug>`.

## Outcome and why
<two or three sentences; the roadmap row quoted verbatim>

## This step only
<what differs from the standing constraints: allowed dependency, external run,
files the integration verifier will run, anything newly authorized, with its D<n>>

## Authority
<decisions you may take; decisions that return to the parent; plan approval
under mandate D<n> is recorded with `specadoc_step.py approve --bindings`>

## Return
The envelope from `.claude/skills/orchestrator/references/controllers.md` at:
plan approval, locally-ready, review-ready with the external run pending, or a
blocker.
```
