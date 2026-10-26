# Implementation plan: __CHANGE_TITLE__

**Status:** Reconnaissance  
**Mode:** Propose  
**Specification:** `spec.md`  
**Risk:** __RISK__  
**Created:** __DATE__

## Handoff

**Plan checkpoint:** Not ready

### Read before continuing

- `spec.md`
- `plan.md`
- <`design.md` or `research.md` when they exist>
- <at most five critical repository paths>

### Completed phases

- [ ] Explore evidence accepted or bounded reconnaissance complete
- [ ] Requirement clarification
- [ ] Behavioral specification
- [ ] Technical planning
- [ ] Plan approval
- [ ] TDD implementation
- [ ] Final review

### Continue with

`Continue from the plan checkpoint. Read the handoff files first and do not repeat completed reconnaissance. Do not resurrect approaches discarded in Confirmed decisions or chat summaries.`

## Reconnaissance evidence

<Decision-relevant only: at most 8 paths or symbols, 5 reusable patterns, exact
verification commands, and confirmed constraints. Not a repository tour.>

## Confirmed decisions

<One line per settled decision, with who settled it. Append as requirements
change; do not restate them elsewhere.>

## Technical approach

<Complete after the behavioral specification is ready.>

## Migration matrix

<Mechanical namespace, path, symbol, or type migrations only; delete this
section otherwise.>

| Legacy contract | Target contract | Consumer category | Semantic differences | Verification |
|---|---|---|---|---|
| Pending | Pending | Pending | Pending | Pending |

## Global constraints

- Tests precede behavior implementation unless an exception is recorded.
- Preserve existing public behavior unless the specification requires a change.
- Avoid unrelated refactoring.

## Files and interfaces

| Path or symbol | Action | Responsibility |
|---|---|---|
| Pending | Pending | Pending |

## Tasks

### T1 — <Independently testable outcome>

- [ ] Complete
- **Requirements:** R1
- **Depends on:** None
- **Decisions:** <settled technical choices needed for this task; reference only relevant design sections>
- **Interfaces:** <current contracts, exemplar paths and required wiring/exports/lockfiles/tests>
- **Open decisions:** None
- **Risk:** __RISK__
- **Decision risk:** <low|medium|high>
- **Owner:** <controller|worker>
- **Verification owner:** <worker|controller>
- **Controller justification:** <required only when Owner is controller and Decision
  risk is low — name the subagent-routing.md exception that applies (e.g. the
  one-file, one-cycle fix exception). Delete this field for any other
  Owner/Decision-risk combination.>
- **Files:** <backticked paths, directories, or globs; symbols in parentheses after a path>
- **Derived files:** None; optional — backticked generated or wiring paths the task may also
  touch (barrel exports, lockfiles of other ecosystems). Changes there are listed, not violations.
- **Test first:** <specific behavioral test>
- **Expected RED:** <why it initially fails>
- **TDD exception:** None; optional — an approved mechanical/documentation exception and its
  deterministic check. Keep None for behavior-changing work.
- **Implementation:** <minimum technical direction>
- **Verification:** `<exact command>`
- **Test context:** <optional: verified test exemplar, bootstrap/login helper,
  test-only environment and one runbook section; delete when not needed>
- **Surface:** <code|ui|mixed>
- **Delivery verification:** <For ui/mixed: final build, typecheck, and Browser URL/state check; for code: N/A>
- **Done when:** <objective condition>
- **Checkpoint:** None; optional — name an intermediate commit point after this
  task. It adds no review round; one final review still covers the diff.
- **Evidence:** Pending; keep final evidence to one or two lines.
- **Evidence hash:** Pending; optional — `validate_change.py --files-hash "<Files: value>"`
  computed when Evidence is recorded, so a later change to the same files before
  review is caught instead of trusted silently.
- **Accepted result:** None; `specadoc_step.py accept` records the delivered result.

## Requirement-to-check matrix

One row per requirement. The reviewer reads this instead of re-deriving coverage
from the diff; see `references/measurement.md`.

| Requirement | Acceptance scenarios | Exact check | Status |
|---|---|---|---|
| R1 | A1 | `<exact command or test>` | Pending |

## Plan approval

**Status:** Awaiting user approval  
**Bindings shown:** Pending  
**Approved at:** Pending

Do not begin RED or implementation until this checkpoint is approved.

## Review scope

<Populate immediately before each initial review from the actual executable
diff. Use one backticked repository-relative literal file path per bullet.
Use `!path/to/deleted-file` only for a file that no longer exists. Do not use
symbols, globs, brace expressions, directories, absolute paths, or `..`.>

- `path/to/reviewed-file`

## Final verification

- [ ] Every requirement maps to implementation.
- [ ] Every acceptance scenario has a test or deterministic verification.
- [ ] Focused tests pass.
- [ ] Relevant regression tests pass.
- [ ] Required build, lint, and type-check commands pass.
- [ ] Independent final review is complete.
- [ ] No BLOCKER findings remain.
- [ ] No IMPORTANT findings remain.

## Review result

**Result:** Pending
**Reviewed requirements:** Pending
**Reviewed tasks:** Pending

### Findings

- BLOCKER: None recorded.
- IMPORTANT: None recorded.
- MINOR: None recorded.

### Round log

<One `### G<n>` block per reviewer dispatch, oldest first. Absent entirely on a
change that predates this mechanism — that is a supported, unenforced state.
See `references/apply.md` and `references/subagent-routing.md`. Shape below is
indented so a copied template does not itself contain a live `G1` block —
un-indent it to four spaces less when you add the first real entry:

    ### G1

    - **Type:** initial|re-review
    - **Snapshot:** sha256:... (the `hash` from `review_snapshot.py compute`)
    - **Policy snapshot:** sha256:... (from `specadoc_step.py pre-review`)
    - **Previous:** none|G<n-1>
    - **Outcome:** PASS|FAIL
    - **Reason:** <one line, required on FAIL>
    - **Remaining findings:** documentation-only (only when code fixes passed and just evidence/handoff prose remains)
    - **Scope:** documentation-only (only for the one extra documentation follow-up)
    - **Round cap override:** Pending
    - **Review decision:** <only for a user-authorized extra re-review; actual decision plus bounded scope, never an inferred archive waiver>
    - **Snapshot waiver:** Pending (only for a technical read failure; never for a manifest mismatch)

    <details><summary>Manifest</summary>

    ```json
    {"...": "..."}
    ```

    </details>
>

## Archive summary

<Durable outcome, accepted decisions, capability impact, and residual risks.
Keep this concise enough for a 16 KiB compact archive record.>

## Completion evidence

```text
Commands:
Pending

Requirement mapping:
R1 -> Pending

Execution tokens:
<per-execution totals collected by collect_tokens.py>

Review rounds:
Pending

Residual risks or waivers:
Pending
```
