# Artifact formats

Read only when writing an authorized glossary/ADR and the project has no format.
Do not write these files during no-file exploration or from a read-only role.

Use GLOSSARY.md at the project/context location. One term per heading:

```markdown
## Term
Meaning in this domain. Distinction from a commonly confused term.
Not: what it does not mean here (including another context's meaning).
Relationships or valid domain states when needed to explain its meaning.
```

When one word has different rules in different contexts, qualify the heading
(`Booking (catalog)`, `Booking (reservations)`) or use each context's glossary.

Avoid class paths, framework details, operational commands, and SHALL requirements.
If multiple contexts already exist, follow GLOSSARY-MAP.md; do not introduce
contexts merely to justify another document.

For a qualifying decision, use the existing ADR directory/numbering. Otherwise
create docs/adr lazily and choose the next available number, never overwrite:

```markdown
# NNNN — Decision title
## Status
Accepted (only after the decision is accepted), proposed, or superseded.
## Context
Problem, constraints, and why the choice is non-obvious.
## Decision
Chosen option and reasons; relevant alternatives rejected.
## Consequences
Benefits, costs, risks, and conditions for revisiting.
```

Link the existing specification or technical plan for details rather than copying
its behavior contract or task list. A rejected architecture candidate merits an
ADR only when its enduring reason would prevent future repeated proposals.
