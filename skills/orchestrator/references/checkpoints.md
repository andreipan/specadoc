# Authority and checkpoints

## An explicit user mandate

Choosing Orchestrator authorizes coordination, not blanket approval of local
plans or tools. State and record whether the user delegates ordinary local plan
checkpoints within a defined goal, repositories, contracts, and risk boundary.
Without that explicit user mandate, relay required plan approvals to the user.
Follow stricter host/repository requirements; a mandate does not create permission
to waive them or to impersonate a human approver.

Suggested bounded question:

> May I accept local plans within this goal and these contracts, returning to you
> for changed requirements, risk, external effects, or scope? Otherwise I will
> bring the required checkpoints to you, grouped when they share one decision.

When permitted, local controllers record the original mandate and the actual
orchestrator decision with its artifact revision. Do not fabricate a user quote
or mark an approval as directly given by the user when it was delegated. Use
existing Specadoc approval fields; if their validation cannot represent the
delegation faithfully, stop and obtain direct approval rather than bypassing a gate.
Keep `**Status:**` a plain `Approved`: the gate rejects negations there, such as
"not a direct user approval". Put provenance on its own line, for example
`**Approval provenance:** orchestrator decision under user mandate D<n>, artifact
revision <ref>`. Give controllers this wording in the brief so they never record
an orchestrator decision as an explicit user instruction.

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
| Runtime/model routing, role files, `.specadoc.json`, or a controller's runtime | User; show the mismatch and ask, never edit to make a launch fit |
| Independent review result | Independent reviewer; neither controller nor orchestrator may invent PASS |

Use the simplest reversible option within the mandate. For an escalation, give
context, viable options including deferral, costs/risks, and a recommendation.
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
