# Companion skills

[Русский](../../ru/guides/companion-skills.md)

A companion skill does one step of the Specadoc lifecycle well, and it also
works without Specadoc. Specadoc works without any of them. When the host has
one installed, Specadoc uses it for the step that it owns and records which one
ran. An equivalent skill of your host can take the place of a bundled one.

| Skill | Source | Specadoc step | Who runs it |
|---|---|---|---|
| `grilling` | External, installed separately | `explore` and `propose` | Controller |
| `domain-modeling` | Bundled | Clarification round in `explore` and `propose` | Controller |
| `codebase-design` | Bundled | Technical planning in `propose` | Controller |
| `tidy` | Bundled | REFACTOR in `apply`, before final verification and review | Worker or controller |

In Claude Code, every folder in the plugin's `skills/` is available as
`specadoc:<name>`. For a plain skill installation, link or copy one folder per
skill (see [Install](install.md)). Install only the skills that the project
needs.

Each bundled skill grants no permission. A skill does not authorize edits,
commits or a redesign that the current step does not authorize.

## grilling

`grilling` is not part of this plugin. It stress-tests an idea or a proposal
with questions: it clarifies requirements, challenges hidden assumptions and
resolves design decisions. Install it with the normal skill installation method
of your host. The source is the `skills/productivity/grilling` folder of
[mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling). The same repository has
[`grill-me`](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me): the same interview, but the agent never starts it
on its own.

### Standalone use

We recommend that you invoke `grilling` explicitly before `specadoc propose`.
It is optional, and no lifecycle gate requires it.

### When Specadoc calls it

In `explore`, after the facts are stable, the controller uses `grilling` when
at least one of these conditions is true:

- More than one material open question remains.
- The change touches a public contract, schema, security, concurrency or money.
- The reconnaissance found conflicting evidence.

If the request is narrow, low-risk and has no open questions, the controller
skips it. It records `Grilling: skipped — <reason>` in the decision log.

Without a grilling skill, the controller asks the same questions directly in the
decision log. Grilling does not restart the repository exploration and creates
no artifacts. An installed grilling skill can change how the controller asks
the questions of the round. By default the round has at most three material
questions.

## domain-modeling

`domain-modeling` makes the meaning of domain concepts exact before they go
into interfaces or data. Use it for ambiguous terms, states, relationships and
invariants. It is most useful for access, money, retries, irreversible
outcomes, and a term that means different things in different areas.

The skill first reads the glossary, the ADRs, the spec and the code. It keeps
three things apart: what the code does, what the accepted spec says, and what
you want. A current bug does not become a desired rule.

It sets the depth for the area. A core area of the product gets a precise model
with edge cases. Supporting CRUD and reporting get clear terms only. It asks
these questions where they matter:

| Question | What it decides |
|---|---|
| Same word, different meaning? | Two context-qualified terms, each with what it does not mean |
| Invariant or corrective policy? | Whether a rule holds at once and atomically, or a later repair is acceptable |
| What changes together? | The boundary of atomic change |
| What is identity? | When two instances are the same, and how a consumer detects a duplicate event |

It tests the model with edge cases: delayed or duplicate events, unknown
outcomes, partial completion and changes of ownership. For unclear states or an
integration with another model, it loads
[discovery heuristics](../../../skills/domain-modeling/references/discovery-heuristics.md).

### What it writes

In a no-file `explore` or a read-only role, the skill returns proposed terms
and decisions only. It writes no file. In authorized design work, it can write:

| Location | Contents |
|---|---|
| Glossary (`GLOSSARY.md` if the project has no format) | Meanings and domain relationships only |
| ADR (existing ADR directory, else `docs/adr`) | A hard-to-reverse, unexpected choice made through a real trade-off |

Observable behavior stays in the spec. The technical design stays in the plan.
The skill uses existing project locations and formats first. If
`GLOSSARY-MAP.md` exists, the skill uses its context mapping.

### When Specadoc calls it

In `explore` and `propose`, the controller uses `domain-modeling` when terms,
states or invariants stay ambiguous. It runs inside the existing clarification
round, not as a second questionnaire.

## codebase-design

`codebase-design` designs or reshapes a module interface. Use it in these cases:

- The architecture is not settled.
- Ports or wrappers multiply for one need.
- One change spreads across many callers.
- Tests depend on internal plumbing.

Do not use it for routine work on an approved design or for a
cosmetic refactor.

The skill aims at deep modules: much behavior behind a small interface. Its
terms:

| Term | Meaning |
|---|---|
| Module | Anything with an interface and an implementation, from a function to a package |
| Interface | Everything a caller must know: types, invariants, order, errors, configuration, performance limits |
| Depth | Useful behavior per unit of interface that a caller learns |
| Locality | Knowledge, change, bugs and verification in one place |
| Seam | A place where you can substitute behavior without an edit to its caller |
| Adapter | A concrete participant that satisfies the interface at a seam |

The skill compares the simplest existing shape with a deeper interface. It
applies the deletion test: does removal of the module remove needless
indirection, or does it spread real complexity across callers? A seam needs real
variation or an explicit need for contract or test isolation. Required ports,
ownership, trust boundaries and dependency direction stay.

It returns the scenario and constraints, evidence paths, the proposed
interface, the hidden behavior, the dependency strategy, tests, trade-offs and
open material decisions. It recommends one shape.

Two references load only on demand.
[Deepening](../../../skills/codebase-design/references/deepening.md) covers how
dependencies and tests fit behind an interface.
[Design alternatives](../../../skills/codebase-design/references/design-alternatives.md)
loads only when you explicitly ask for different interface options.

### When Specadoc calls it

In `propose`, the controller uses `codebase-design` only for interface and seam
choices that are not settled. The controller decides. Scouts supply facts, and
workers implement the accepted shape. The skill starts no parallel designers by
default and creates no second artifact tree. The result goes into the existing
plan after the required approvals.

## tidy

`tidy` improves the quality of changed code and keeps the observable behavior.
It is not a correctness or security audit and not a redesign. It does one pass
over four angles:

| Angle | What it looks for |
|---|---|
| Reuse | New code that duplicates an existing helper or pattern |
| Simplification | Stored state that can be computed, near-duplicate blocks, needless nesting or indirection, code that the change left unused |
| Efficiency | Work or I/O done twice, steps that wait without need, slow work on startup or a frequent path, queries that fetch too much |
| Altitude | A patch on one symptom where one change to the shared mechanism is simpler |

Each finding gets `file:line`, a one-line description and the cost to keep it.
The skill skips a fix that changes intended behavior, goes outside the scope,
depends on an equivalence it cannot show, or gives too little. No findings is a
valid result. Correctness and security defects go to the controller.

After the edits, the skill runs the relevant existing tests and the allowed
lint and type checks. It reports what it fixed, what it skipped and why, and
the checks that it ran.

### Standalone use

Give `tidy` a task, a diff, a commit range, a PR or a list of files. With no
scope, it uses the changes of the current task, then the staged and unstaged
changes. If these are empty, it asks you. It never audits the whole repository.

### When Specadoc calls it

In `apply`, after the controller fills Review scope from the diff, one worker
can run a tidy pass over that scope. The controller uses the pass when cleanup
helps. With `review.tidy: required`, the pass is mandatory. It happens before
final verification and before the first independent review.

1. Write the tidy brief to `runs/tidy-brief.md`:

   ```text
   python3 <skill-root>/scripts/specadoc_step.py tidy <slug>
   ```

2. Give the brief to one worker. The worker ends with
   `specadoc_step.py tidy <slug> --record --summary '<...>'`.
3. If the diff is trivial, skip the pass with
   `specadoc_step.py tidy <slug> --skip '<reason>'`.
4. Run `specadoc_step.py refresh <slug>`. It re-accepts the tasks whose evidence
   the tidy edits made stale.

`<skill-root>` is the installed `skills/specadoc` folder. If the worker answers
asynchronously, `specadoc_step.py wait <slug> tidy` waits for the tidy record.

The tidy pass records its edits, so the scope check of each task accepts them.
A reviewer never runs `tidy`, because the reviewer is read-only.

By default `review.tidy` is `optional`, and `pre-review` does not check for a
tidy record. To make the pass mandatory, set this in `.specadoc.json`:

```json
{"version": 1, "review": {"tidy": "required"}}
```

Then `pre-review` refuses the first initial review round until a tidy record
exists. A re-review never needs another pass. See
[Configuration](../reference/config.md).

An executable edit after a review PASS makes that review stale. The diff then
needs fresh verification and review.
