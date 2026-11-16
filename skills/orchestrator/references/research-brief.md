# Research brief

Copy the block below into `<coordination dir>/research/<step>-brief.md`, fill the angle
brackets, and send it like a controller brief (host notes). One brief per step; keep it under
about 2,000 characters. The step excerpt and the decisions are cited, never retold.

```markdown
# Research <step> <slug>: <one-line outcome>

Standing constraints: `<coordination dir>/brief.md` (mandate D<n>). Step excerpt:
`<coordination dir>/step-<step>.md`. Decisions already taken: D<n>, D<m> (read each with
`coordination_log.py get`, never the whole log). BA register: `<path>`.

## Task
Run Specadoc `explore` for this step on the current checkout. Read-only research: write only
`<coordination dir>/research/<step>.md` and source copies under `<coordination dir>/sources/`
(title, page id, URL, fetch date; reuse a copy that is already there). This file is a report to
the parent, not a repository artifact: create no change folder, spec or plan, run no
`init_change.py`, edit no code, use no git, start no workers.

Earlier steps of the block, <steps>, are not built yet. Mark every conclusion that rests on code
they will write `depends on <step>`. Facts from Confluence, the ERD, producer code (<paths>) and
framework behaviour carry no such mark.

## Research file (<language>, compact, every claim with file:line or page id)
1. Facts: endpoint (method, path, profile), request and response fields, error codes, the
   connector operation that covers it or none, tables and columns used, what is missing.
2. Divergences: Confluence vs ERD vs producer code vs repository rules (`AGENTS.md`), each with
   the quoted source line.
3. Defaults without a question, one line each with the reason.
4. Questions `Q<step>-<n>` (`QX-<name>` when another step shares it): options A/B(/C), a
   recommendation and why, and a class. A: changes the external contract, response codes,
   irreversible data, security or money. B: everything else.
5. A question that waits for a third party carries the decision that holds until it answers.
6. Risks and blockers (a producer endpoint missing means the step cannot be done).
Only facts that change a decision; about 8-15 KB.

## Return
Write the file, then run `<report command> "<coordination dir>/research/<step>.md"` and end
the turn. Do not ask the user anything: questions go into the file.
```

Notes:

- The research session uses the controller launch line of the host notes, so it gets the same
  model, tools and permissions. Three run at a time; start the next when one reports.
- `explore` alone writes no files; the Task paragraph is what allows this one report file.
- Name the producer repositories and the saved sources of earlier stages in `<paths>`, so the
  session does not refetch a wiki page another step already saved.
