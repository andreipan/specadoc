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
over to the next step. In 3.6 the orchestrator missed the standing mandate,
recorded "no delegation" and brought ordinary approvals to the user.

Suggested bounded question:

> May I accept local plans within this goal and these contracts, returning to you
> for changed requirements, risk, external effects, or scope? Otherwise I will
> bring the required checkpoints to you, grouped when they share one decision.
> May controllers and the integration verifier use `<dedicated test database>`
> for integration runs without asking each time?

### Plan approval under a mandate

With that mandate, approve an ordinary local plan without asking the user when
all of these hold, and record the provenance line below:

- the plan's design gate is a current PASS (`## Design review` bound to the
  current Class inventory), or the plan adds no new non-test file;
- `validate_change.py --phase plan` passes;
- no escalation trigger: no row of Decision boundaries that belongs to the user
  (new behavior, incompatible contract, added repository, material risk or
  scope change, production, destructive or external effects, routing), and no
  open decision the controller marked for the user.

Otherwise bring the checkpoint to the user. A design FAIL is never approved by
the orchestrator; return it to the controller.

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

Specadoc caps new-diff review rounds at three. Under a plan mandate the
orchestrator may grant one extra round per change: record it with
`coordination_log.py decision --by orchestrator`, give the controller
`--review-decision 'orchestrator D<n> under mandate D<m>: one extra round for
<scope>'`, and name it in the final report. A second extra round, or one without
a mandate, is the user's decision. Never write "user-approved" without the
user's words.

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
| Network access, dependency install or update, a sandbox bypass, or any command a runtime denied | User, for that exact command; the orchestrator never runs it for a controller, and nobody calls it approved without a recorded approval |
| Runtime/model routing, role files, `.specadoc.json`, or a controller's runtime | User; show the mismatch and ask, never edit to make a launch fit |
| Independent review result | Independent reviewer; neither controller nor orchestrator may invent PASS |
| One extra review round past the cap, under a plan mandate | Orchestrator, recorded `--by orchestrator` and reported; a second one is the user's |

Use the simplest reversible option within the mandate. For an escalation, give
context, viable options including deferral, costs/risks, and a recommendation.

### Relaying options

When a controller returns options for the user, pass them on verbatim: its
option table with the controller's labels, its recommendation, and what each
choice changes. Ask one structured question (the host's question tool when it
has one) whose answers are those labels. Do not reword, re-letter, merge or
reorder options, and do not add your own preference unless labelled as yours.
An answer that picks no option ("go", "ok") is not a choice: ask again. In 3.5
the orchestrator reframed a controller's A/B/C, the user answered "go", and the
choice had to be made again inside the controller.

Pause affected work; independent authorized work may continue when the host
supports it. Do not repeatedly ask equivalent approval questions.

## Acceptance is not authorization

Inspect plan/diff revisions and proof before accepting a checkpoint. Do not
approve dependent implementation just because a producer says it is nearly done.
Contract readiness needs a named revision and observable compatibility evidence.

If requirements or contracts change, identify all affected controllers, invalidate
stale readiness, and route changes into their existing lifecycle records. Obtain
any renewed approvals before dependent implementation. Local executable changes
invalidate the relevant old review evidence; metadata-only coordination notes do
not automatically require another code review.
