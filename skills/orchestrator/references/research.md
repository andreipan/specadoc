# Research before a block of steps

Run 6.11-6.15 waited 1859 minutes on six user questions, three of them overnight,
while controllers sat idle. Every one could be found before the block started:
a deferred answer (`QX-7`: "the column after Hub answers" came back in 6.12),
a producer's semantics (Hub NotFound on delete, 6.13), framework behaviour
(Laravel's numeric user id in the error report context, 6.15). The stage sweep
read documents and contracts, not code. Research reads both, for every step,
before the first controller.

## When

After the environment probe and the mandate question, before the first
controller of a block of roadmap steps. Skip it for a single step whose sources
the user already settled.

## Research sessions

- One session per step, launched like a controller (host notes), with the
  Specadoc skill. Run three at a time; start the next when one ends.
- Each runs a full Specadoc explore of its step on the current checkout and is
  read-only: it writes only `<coordination dir>/research/<step>.md` and source
  copies under `<coordination dir>/sources/` (title, page id, URL, fetch date).
  No change folder, no `init_change.py`, no code edits, no git.
- Earlier steps of the block are not built yet. A conclusion that rests on code
  an earlier step will write is marked `depends on <step>`; facts from external
  sources (Confluence, ERD, producer code, framework behaviour) are not.
- Before writing a brief, search the project's memory and docs, where the host
  has them, for each topic of the step (authentication, integrations, earlier
  decisions) and cite the hits in the brief (7.2: the authentication design
  was already in project memory; a third research session found it).
- Brief each session from `references/research-brief.md`: the step's source
  excerpt and the decisions it relies on are cited as in a controller brief, and
  the brief is what allows `explore` to write its one report file. The session
  reports with the host's report command: the file path.

## Research file

Compact, in the user's language, each claim with file:line or page id:

1. Facts: endpoint, fields, codes, which connector operation covers it, tables
   and columns used, what is missing.
2. Divergences: Confluence vs ERD vs producer code vs repository rules
   (`AGENTS.md`), each with the quoted source line.
3. Defaults without a question: safe choices with their reason.
4. Questions, numbered `Q<step>-<n>`, or `QX-<name>` when another step shares
   them, each with options, a recommendation and a class:
   - **A**: changes the external contract, response codes, irreversible data,
     security or money. Only the user answers. Each carries its origin: the
     roadmap line, decision or source quote that made it open (8.2: a deferred
     code reached the user without its history and came back as a question).
   - **B**: everything else. The orchestrator decides it (`references/checkpoints.md`
     → Deciding without the user).
5. Deferred answers: a question that waits for a third party ("after Hub
   answers") always carries the decision that holds until then.

## Merge and ask once

One worker merges the research files into `<coordination dir>/questions.md`:
class A questions first, shared `QX-` questions joined, each with the steps it
blocks. Ask every class A question in one batch while no session runs (the
host's question tool, at most four per call; the stem opens with the situation
in the user's language). Record each answer as `D<n>` and copy it into the
coordination brief under Confirmed decisions. Decide every class B question
yourself, record it, and add each divergence and each class B decision that
departs from a source to the BA register. Then launch the first controller.

## Controllers read research

The step brief names its research file and the decisions that settled its
questions. The controller runs explore and propose in one session as usual,
taking the research file as evidence; it rechecks conclusions marked `depends
on <step>` against the current code and does not ask a question that already
has a decision. A new class A question found later stops only its step.

## BA register

One file for the project's open questions to the business analyst, divergences
from Confluence and the ERD, and decisions taken without the analyst. Its path
is the `BA register:` line of the coordination brief. Write it only with
`scripts/ba_register.py` (`add`, `status`, `list`): numbers never repeat, every
item has a type and a status line, and a closed item stays with its answer.
Use the types and statuses the register's header defines; a new register starts
with types `divergence from the wiki`, `divergence from the ERD`, `divergence
from producer code`, `ambiguity in a source`, `decision without the analyst`,
and statuses `open`, `default applied, awaiting analyst` (names its `D<n>`),
`closed by analyst (<date>)`, `moved to stage <N>`.
