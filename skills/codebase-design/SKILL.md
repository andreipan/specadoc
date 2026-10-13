---
name: codebase-design
description: Design or reshape a module interface when architecture is unresolved, ports/wrappers multiply for one need, changes scatter across callers, or tests depend on internal plumbing. Not routine implementation of an approved design or a cosmetic refactor.
---

# Codebase Design

Design deep modules: substantial behavior behind a small interface. The goal is
leverage for callers, locality of change, and tests of observable behavior.
The controller owns architecture; scouts gather bounded evidence and workers
implement the accepted design. This skill does not authorize a redesign or edits.

## Vocabulary

- **Module:** something with an interface and implementation, from a function
  to a package or a cross-tier slice.
- **Interface:** everything callers must know: types, invariants, ordering,
  errors, configuration, and performance constraints, not just public methods.
- **Depth / leverage:** useful behavior per unit of interface a caller learns.
- **Locality:** knowledge, change, bugs, and verification concentrate in one place.
- **Seam:** where behavior can be substituted without editing its caller.
- **Adapter:** a concrete participant satisfying the interface at a seam.

Use domain glossary terms when present, but retain repository vocabulary and
mandatory layers. Do not rename services, APIs, or components just to fit this list.

## Make a bounded design decision

1. Start with the actual scenario, known callers, repository rules, relevant ADRs,
   and current tests. Use existing scout evidence; do not repeat a repository tour.
2. Ask what callers currently need to know and what changes together. Apply the
   deletion test: does removing the module remove needless indirection, or scatter
   essential complexity across callers? Prefer concentrating real complexity.
3. Compare the simplest viable existing shape with a deeper interface. State
   inputs/results, errors, invariants, ordering, and what implementation is hidden.
4. Justify seams with actual variation or an explicit contract/test-isolation need.
   Two useful adapters are evidence, not a rigid quota. Preserve required ports,
   ownership, trust boundaries, and dependency direction.
5. Specify behavioral tests through the chosen interface and compatibility checks.
   Do not delete tests automatically; demonstrate preserved scenario coverage
   before replacing redundant implementation-coupled tests.
6. Recommend one shape and explain trade-offs. In a managed lifecycle, record it
   in the existing technical plan after the required approvals. In no-file
   exploration, return the proposal without edits.

For complex dependency/test questions, load [deepening](references/deepening.md).
For an explicitly requested comparison of alternative interfaces, load
[design alternatives](references/design-alternatives.md), not for ordinary design.

Return: scenario/constraints, evidence paths, proposed interface, hidden behavior,
dependency strategy, tests, trade-offs, and unresolved material decisions. No
parallel agents or new artifact tree by default.
