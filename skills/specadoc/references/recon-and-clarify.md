# Reconnaissance and clarification

Load this reference only for repository discovery and requirement clarification.

## Repository reconnaissance

Inspect the cheapest authoritative sources in this order:

1. Repository instructions and local policy.
2. Up to three capability specifications selected by `explore.md` from
   `docs/specadoc/specs/`. They state intended current behavior in one place; the
   code remains authoritative where the two disagree. Do not search or read
   `docs/specadoc/archive/` during reconnaissance.
3. Current implementation and public interfaces.
4. Existing tests and fixtures.
5. Similar features or fixes in the same repository.
6. Domain documentation, ADRs, schemas, and build configuration.
7. User clarification.

Do not ask the user for information that can be established from the repository.

Capture only decision-relevant evidence:

- Relevant files or symbols: maximum 8.
- Existing patterns to reuse: maximum 5.
- Exact build, test, lint, and type-check commands.
- Public contracts and compatibility constraints.
- Material unknowns: maximum 3.

For a mechanical namespace, path, symbol, or type migration, also capture a
compact migration matrix before any broad replacement:

```text
Legacy contract | Target contract | Consumer category | Semantic differences | Verification
```

Group equivalent consumers; do not list every file when one category and a
source search define the scope. Resolve incompatible constructors, fields,
ownership, and layer boundaries before implementation.

Avoid a general repository tour.

## Scout dispatch contract

Scout policy — one attempt, at most one running scout, and non-blocking — lives
in `explore.md`. This
section defines only what a scout is given and what it returns.

Give the scout one bounded question and the smallest useful scope. Require the
standard scout report defined by the runtime's role profile (`model-routing.md`
→ Role registry); if the runtime has no `scout` profile, paste that profile's
response contract into the dispatch prompt.

When `explore.md` selected capability specifications, include their paths in
the scout's `Read` list and require it to compare their relevant `C<n>`
requirements with the current code. The scout reports a conflict as capability
drift, with code authoritative; it does not repair the document or infer that
the specification overrides current behavior. When no capability specification
matched, state that in the prompt and continue normally.

The scout must not edit files, choose the final architecture, or produce a broad summary.

After reconnaissance, stress-test the idea with a grilling skill when one is
installed (see `interoperability.md` → Optional companion skills). Pass it the
settled facts and material decisions; do not let it repeat repository
discovery or persist `spec.md`/`plan.md` during explore mode.

When terminology, states, or invariants remain ambiguous, an installed domain
modeling companion may sharpen them within that same clarification round.
Keep no-file/read-only exploration intact: return proposed terms and scenarios,
not glossary/ADR edits. Consult only relevant existing definitions and decisions.

## Unknown classification

Classify every unknown as one of:

- `REPOSITORY_ANSWER`: resolve from code, tests, or documentation.
- `SAFE_DEFAULT`: choose a reasonable default and record it as an assumption.
- `MATERIAL_USER_DECISION`: ask the user.
- `TECHNICAL_PLANNING`: defer until the behavioral specification is stable.

A user decision is material only when different answers change one or more of:

- Observable behavior.
- Scope or non-goals.
- Data ownership, persistence, or migration.
- Authentication, authorization, privacy, or safety.
- Public API or compatibility.
- Acceptance tests.
- Architecture or task boundaries.

## Question protocol

Ask no more than three material questions by default. Ask every question whose
prerequisites are settled in one numbered round, and keep a dependent question
for a later round. Ask one at a time only when the harness has no sub-agents. An
installed grilling skill may refine this delivery; follow it when present.

Each question must contain:

```text
Question: <one decision>
Why it matters: <one sentence>
Recommendation: <preferred answer and reason>
Options: <2-4 mutually distinct options when useful>
```

Treat `recommended` as acceptance of the recommendation.

Stop questioning when behavior-changing uncertainty is resolved or safe defaults remain. Do not ask about internal names, libraries, or file placement already established by repository conventions.
