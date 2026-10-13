---
name: domain-modeling
description: Clarify ambiguous domain terms, states, relationships, and invariants during requirements/design, especially access, money, retry, irreversible outcomes, or a term used differently across areas or integrations. Use for glossary/ADR work; not merely reading established vocabulary or executing a settled plan.
---

# Domain Modeling

Sharpen the meaning of concepts before encoding them in interfaces or data.
The controller resolves material decisions with the user. Scouts verify facts;
workers consume agreed terms/scenarios and escalate new contradictions.

## Resolve meaning with evidence

Read the relevant glossary, ADRs, specification, and current implementation,
using accepted reconnaissance rather than repeating it. If GLOSSARY-MAP.md
exists, use its context mapping instead of assuming one global glossary.

Distinguish what code does, what the accepted specification says, and what the
user wants. Historical memory is a lead, not proof of current code or requirements.
Surface contradictions and do not silently promote current bugs into desired rules.

Calibrate depth first: a differentiating core area earns a precise model and
edge cases; supporting CRUD/reporting needs only clear terms; a generic area
conforms to its standard or product. Do not impose aggregates or events on CRUD.

Probe the model with these questions where they matter:

- **Same word, different meaning:** if a term's rules or lifecycle change
  between areas, treat it as two context-qualified terms; state what each does
  *not* mean. Do not invent contexts where the meaning is the same.
- **Invariant or corrective policy:** must the rule hold immediately and
  atomically, or may it be repaired afterwards (compensate, wait-list, notify)?
  This sets transaction scope and acceptance scenarios.
- **Change together:** what must change atomically, and does contention on one
  thing (slot, balance, stock) argue for a smaller boundary plus compensation?
  Interface and module shape belong to architecture design, not here.
- **Identity:** what makes two instances "the same"; entity or immutable value;
  which identity lets a consumer detect a duplicate or out-of-order event?

Test the model with concrete edge cases: delayed/duplicate events, unknown
outcomes, partial completion, changes of ownership, or independent state
transitions as relevant. For unclear states, missing transitions, or an
integration with another model, load [discovery heuristics](references/discovery-heuristics.md).
Ask only when the distinction affects behavior, scope, safety, or tests; label
unverified assumptions instead of filling gaps.
This is not a second questionnaire: feed settled facts and remaining material
questions into the host's existing clarification/grilling round.

## Persist only with authority

In no-file explore or a read-only role, return proposed definitions and decisions;
do not write files, including glossary or ADR files. The skill grants no new
permission to edit. During authorized proposal/design work, write resolved terms
when they become useful, not a speculative documentation tree.

- **Glossary:** meanings and domain relationships only, no implementation details,
  task state, test commands, or technical naming policy.
- **Specification:** observable behavior and acceptance scenarios.
- **Plan:** technical design, tasks, execution state, and evidence.
- **ADR:** a hard-to-reverse, surprising choice made through a genuine trade-off.
  Offer sparingly; do not record every obvious convention or temporary deferral.

Use existing project locations and formats first. When authorized and no format
exists, load [artifact formats](references/artifact-formats.md). Create files lazily
and keep one source of truth. Do not duplicate the same normative contract in
glossary, ADR, memory, and specification.

Return settled terms/invariants, current-vs-intended contradictions, concrete
acceptance scenarios, and remaining decisions; name any authorized file updates.
