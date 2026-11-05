# Controller brief

Load this before sending a controller its first brief. Runs 3.7 and 3.8 sent
7–8k-character briefs that repeated the same prohibitions every time and glued
words together ("idle186k", "hashes2integrationfiles"); controllers had to
decode them, and every message stays in their context for the whole session.

Rules:

- Standing constraints live once in the coordination `brief.md`: forbidden
  operations (commit, stash or stack edits, push, archive, the next step),
  integration runs by the parent only, no DDL or migrations on shared databases,
  the test database, preserved files. The brief cites them by path and decision
  id; it does not restate them.
- Write full sentences in the user's language with ordinary spacing. No
  abbreviations the controller must decode.
- Context thresholds are not yours to set: the controller follows `status`
  (Specadoc `model-routing.md` → Session boundaries).
- Send it through a file or stdin (host notes), not as a shell argument.
- A replacement controller gets the same shape: what is done, the checkpoint it
  starts from (`status` and `runs/handoff.md`), and what changed since.

Shape (keep under about 2,000 characters):

```markdown
# <step> <slug>: <one-line outcome>

Standing constraints: `<coordination dir>/brief.md` (mandate D<n>, test database D<m>).
Use Specadoc for this change. Start from `specadoc_step.py status <slug>`.

## Outcome and why
<two or three sentences; the roadmap row quoted verbatim>

## This step only
<what differs from the standing constraints: allowed dependency, external run,
files the parent will run, anything newly authorized, with its D<n>>

## Authority
<decisions you may take; decisions that return to the parent; plan approval
under mandate D<n> is recorded with `specadoc_step.py approve`>

## Return
The envelope from `controllers.md` at: plan approval, locally-ready,
review-ready with the external run pending, or a blocker.
```
