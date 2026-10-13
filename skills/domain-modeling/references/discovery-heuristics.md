# Discovery heuristics

Load when states are unclear, transitions seem missing, or the change touches
another team's or system's model. Use only what the question needs; these are
prompts for the existing clarification round, not a workshop.

## States from a timeline

- Write business facts as past-tense events (`PaymentCaptured`, not
  `CapturePayment`), happy path first, then alternatives and failures.
- Every command needs a trigger: a user, a policy ("when X, then Y" with explicit
  criteria), a schedule, or an external system. A command with no trigger, or an
  event nobody reacts to, is a gap to ask about.
- Turn each hotspot into a question with an owner or into a corrective policy.
- State count is a signal: many states suggest an unmodeled process; one or two
  on a rule-heavy concept suggest the rules live elsewhere.
- Events that change who owns the work or which rules apply are candidate
  boundaries between meanings.

## Consistency and policies

- For each rule ask: who breaks it, when, and what must be true right after the
  change? Immediate rules bound the transaction; the rest become policies.
- Many corrective policies around one concept suggest rules leaked out of it.
- Changing another area's state usually happens by reacting to an event, so ask
  what happens on delay, redelivery, and out-of-order arrival.
- These are questions, not rules: "one transaction, one consistency boundary"
  is a heuristic to test against the real requirement.

## Events worth recording

Domain events are facts experts care about. Clarify when it happened, which
identities it concerns, who or what caused it, and the identity used to discard
duplicates. Do not promote technical notifications to domain language.

## Integration points

- Who is upstream (supplies the model) and downstream (depends on it)?
- Downstream conforms to the upstream model, or translates it at its edge
  (anti-corruption layer) when the upstream model is unstable, legacy, or
  conflicts with local meaning? A shared published contract suits many consumers.
- Name the translated terms on both sides. The translation's module design
  belongs to architecture design.
- Map only the relationships the current question needs.

## Configurable rules

When users or administrators configure the rules (tariffs, approval chains,
eligibility), model the rules as their own concepts separate from the objects
they govern, and ask who may change them and how changes apply to work in flight.
