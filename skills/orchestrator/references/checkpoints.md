# Authority and checkpoints

## An explicit user mandate

Choosing Orchestrator authorizes coordination, not blanket approval of local
plans or tools. State and record whether the user delegates ordinary local plan
checkpoints within a defined goal, repositories, contracts, and risk boundary.
Without that explicit user mandate, relay required plan approvals to the user.
Follow stricter host/repository requirements; a mandate does not create permission
to waive them or to impersonate a human approver.

A mandate recorded earlier in the coordination record stays in force for later
steps of the same roadmap while the step stays inside its goal, repositories,
contracts and risk boundary. Cite it (`inherited from <record> D<n>`) instead of
asking again, and ask only when no record exists or the step falls outside it.
Per-step permissions (a test database run, archive, commit, push) do not carry
over to the next step unless the user granted them for named steps. In 3.6 the
orchestrator missed the standing mandate, recorded "no delegation" and brought
ordinary approvals to the user; in 5.1 and 5.2 each mandate named one step, so
every run asked again.

Suggested bounded question:

> May I accept local plans within this goal and these contracts, returning to you
> for changed requirements, risk, external effects, or scope? Otherwise I will
> bring the required checkpoints to you, grouped when they share one decision.
> Does this hold for this step only, or for every step of `<stage or roadmap
> range>`, each within its own sweep answers? The same for archiving each
> accepted step and recording it as a stack patch.
> May controllers and the integration verifier use `<dedicated test database>`
> for integration runs without asking each time?

Offer the range of steps the user named or the current stage as the
recommended scope; each later step still asks when it falls outside it.

### Plan approval under a mandate

With that mandate, approve an ordinary local plan without asking the user when
all of these hold, and record the provenance line below:

- the plan's design gate is a current PASS (`## Design review` bound to the
  current Class inventory; `ACCEPTED` after the round cap counts), or the plan
  adds no new non-test file;
- `validate_change.py --phase plan` passes;
- no escalation trigger: no row of Decision boundaries that belongs to the user
  (new behavior, incompatible contract, added repository, material risk or
  scope change, production, destructive or external effects, routing), and no
  open decision the controller marked for the user;
- every exception the plan makes to a repository architecture rule (module
  boundaries, allowed bridges or consumers) is allowed by that rule. Decide an
  exception at approval, not after review: in 4.3 the orchestrator reversed one
  after G1, which cost a design re-review and three more code rounds.

Otherwise bring the checkpoint to the user. A design FAIL is never approved by
the orchestrator; return it to the controller. Past Specadoc's design round cap
the orchestrator decides the round itself (Extra review rounds).

### Standing test-database permission

The mandate may name one dedicated, disposable test database and its connection
name. Controllers and the integration verifier may then run integration tests
and test migrations against it repeatedly without asking each time. Record it
once, with its exact name, in the coordination brief; controller briefs cite
that entry. It never covers the working, shared or production database, a
copied production configuration, or creating another database.

When permitted, local controllers record the original mandate and the actual
orchestrator decision with its artifact revision. Do not fabricate a user quote
or mark an approval as directly given by the user when it was delegated. Use
existing Specadoc approval fields; if their validation cannot represent the
delegation faithfully, stop and obtain direct approval rather than bypassing a gate.
The controller records it with `specadoc_step.py approve <slug> --by
orchestrator --source 'mandate D<n>, decision D<m>'` (a direct user decision:
`--by user --source '<the user's words>'`). It writes a plain `**Status:**
Approved`, an `**Approval provenance:**` line and the approved spec/design
hashes; never write
these lines or hashes by hand. Give controllers this command in the brief so
they never record an orchestrator decision as an explicit user instruction.

### Extra review rounds

Specadoc allows three initial (new-diff) rounds and one targeted re-review
after each; a stale round (code or approval changed while it ran) uses neither.
Under a plan mandate the orchestrator grants extra rounds itself and records
each with `coordination_log.py decision --by orchestrator`: a code review round
with `--review-decision 'orchestrator D<n> under mandate D<m>: one extra round
for <scope>'`; a design round past Specadoc's cap (four recorded rounds) with
`design-brief <slug> --attempt-decision 'continue: orchestrator D<n> under
mandate D<m>'` (the open IMPORTANT items become apply obligations and the round
checks the BLOCKER items), or `'accept: …'` to carry the open IMPORTANT items
into apply as obligations. Accept when the open items are test cases or spec
wording, continue when one changes behaviour; a BLOCKER is never accepted. A
BLOCKER on test design, spec wording or an internal rule is yours as well; when
it comes back in a new form after a round, choose a simpler check or drop the
claim with its residual risk recorded instead of ordering the same round again
(7.1, 8.1, 8.2: 8, 11 and 7 design rounds, and 4 h 15 min waiting for the user on a
race-test BLOCKER). From design round 3 Specadoc itself turns findings of class
`other` into apply obligations (`R3.1`) and accepts a round with no must-not-ship
finding left (data, money, access, user path, silently wrong result); a round past
2 with must-not-ship items open needs `design-brief --verify-by '<method or owner>'`.
Choose that method under the mandate (a spike test, a simpler check, the user as
owner of a contract question), never the same review again. Name every such round
in the final report. Without a mandate the round is the user's. Never write
"user-approved" without the user's words (6.12-6.15 asked the user for rounds
the mandate covered and waited up to 14 hours).

A decision that changes the approved design (a port, an adapter, an exception)
says whether it also authorizes re-approving that change; the controller then
re-approves before the next review round, never during one.

An explicit uninterrupted-execution request is handled by existing Specadoc
rules. It does not waive specifications, testing, review, or completion evidence.

## Decision boundaries

| Decision | Owner |
|---|---|
| Local implementation mechanism within the accepted contract | Local controller |
| Dependency scheduling and compatible shared-contract details inside the mandate | Orchestrator, recorded and sent to affected owners |
| Ordinary local plan checkpoint | User unless explicitly delegated and accepted by host/repository rules |
| New product behavior, incompatible contract, added repository, or material risk/scope change | User unless that exact choice was already explicitly authorized |
| Production, destructive migration, secrets, money, system changes, external publication, push/deployment | User's explicit authorization for the action; never inferred from a plan mandate |
| Network access, dependency install or update, a sandbox bypass, or any command a runtime denied | User, for that exact command; the orchestrator never runs it for a controller, and nobody calls it approved without a recorded approval. Exception: starting a role on the runtime `.specadoc.json` routes it to, also outside the sandbox (Specadoc `runners.md`); the routing is the user's authorization |
| Runtime/model routing, role files, `.specadoc.json`, or a controller's runtime | User; show the mismatch and ask, never edit to make a launch fit |
| Independent review result | Independent reviewer; neither controller nor orchestrator may invent PASS |
| Review rounds past the limits, under a plan mandate | Orchestrator, recorded `--by orchestrator` and reported |
| A choice that leaves contract, response codes, data, security and money as the sources state them | Orchestrator under a plan mandate (Deciding without the user) |

Use the simplest reversible option within the mandate. For an escalation, give
context, viable options including deferral, costs/risks, and a recommendation.

### Relaying options

When a controller returns options for the user, pass them on verbatim: its
option table with the controller's labels, its recommendation, and what each
choice changes. Ask one structured question (the host's question tool when it
has one) whose answers are those labels. Open it with one sentence in the user's
language on the situation and what is being decided (6.8: a bare option stem was
answered "I do not understand the question" after 112 minutes). Do not reword, re-letter, merge or
reorder options, and do not add your own preference unless labelled as yours.
An answer that picks no option ("go", "ok") is not a choice: ask again. In 3.5
the orchestrator reframed a controller's A/B/C, the user answered "go", and the
choice had to be made again inside the controller. Never carry out an action
that none of the offered options names (5.2: "go" to "you write in the
controller thread / you run it" became the orchestrator running it).

Pause affected work; independent authorized work may continue when the host
supports it. Do not repeatedly ask equivalent approval questions.

### Deciding without the user

Under a plan mandate decide yourself, with the controller's recommendation as
the default, every question that keeps the external contract, response codes,
irreversible data, security, money and production as the sources state them:
spec wording, test cases, internal rules, the order of local steps, a choice
among the controller's options. Record it as `D<n>`. When the answer departs
from Confluence, the ERD or a producer's code, or settles an ambiguity in them,
also add it to the BA register (`references/research.md` → BA register) with
the register's default-applied status and the `D<n>`; nothing that differs
from a source may live only in the decision log.

A question that changes the external contract, response codes, data, security
or money stops only its step. While any child runs, do not open the host's
question tool (it blocks child reports): write the question to the block's
`questions.md`, state it to the user in plain text at the end of the turn with
the options and your recommendation, and continue the independent steps. The
user answers in an ordinary message; record the answer as `D<n>` and resume
the step. When every child is idle, ask with the question tool, never in plain
text (8.2: a plain-text question waited 520 minutes and no user-wait count saw it).

## Acceptance is not authorization

Inspect plan/diff revisions and proof before accepting a checkpoint. Do not
approve dependent implementation just because a producer says it is nearly done.
Contract readiness needs a named revision and observable compatibility evidence.

If requirements or contracts change, identify all affected controllers, invalidate
stale readiness, and route changes into their existing lifecycle records. Obtain
any renewed approvals before dependent implementation. Local executable changes
invalidate the relevant old review evidence; metadata-only coordination notes do
not automatically require another code review.
