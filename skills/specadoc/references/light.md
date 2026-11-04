# Light mode

Load this reference only for `specadoc light` or when routing selects it.

Light keeps capability specs as the durable record and keeps the plan,
approval and evidence in conversation. It creates no change folder, `plan.md`,
`runs/` or archive record, and dispatches no scout or worker.

## Eligibility

All must hold; recheck whenever new facts appear:

- one repository, and the work fits one session;
- requirements are clear and no material domain question is open;
- no contract with consumers outside this repository changes (a published
  API, SDK, event or shared schema);
- no change to money handling or to the permission model;
- no irreversible data effect beyond an ordinary additive migration.

If any fails, stop and switch to `propose`, or to `explore` for open questions.
Carry the approved spec delta and accepted evidence forward: propose records
them in `spec.md` instead of restarting.

## Steps

1. Read mandatory repository rules. Find the affected capability files in
   `docs/specadoc/specs/` by filename, heading and `C<n>`; read at most three.
   Investigate with targeted reads only. Where specs and code disagree, code is
   authoritative: report the drift.
2. Draft the spec delta in place. Change only the affected `C<n>` statements,
   invariants and key paths, or create the capability from
   `<skill-root>/assets/capability-template.md`. Statements stay observable and
   testable, without classes or implementation order. A change without an
   observable behavior delta leaves specs untouched.
3. Present one compact preview in chat: the spec delta, files to touch, ordered
   steps, exact verification commands including the repository's static and
   style gates for those files, risk, and the controller and reviewer bindings.
   Stop for one approval that covers both spec and plan. An explicit
   uninterrupted request waives the stop, not the spec delta.
4. Implement as the controller with RED-GREEN-REFACTOR per changed `C<n>`; an
   installed implementation skill owns coding discipline. Run only focused
   tests while iterating.
5. Run final verification once: affected tests, static analysis and lint.
   Report exact commands and results, not raw logs.
6. Unless the diff is trivial (one file, no behavior change), dispatch one
   independent read-only `reviewer` with the spec delta, the diff and the
   verification evidence; read `tdd-and-review.md` before it. Fix confirmed
   findings, rerun only affected checks, and re-review only the changed files
   once. New BLOCKER or IMPORTANT findings after that: stop and ask. Without a
   subagent capability, report the incomplete review gate; never self-review.
7. Close: add a provenance row `<slug> | <date> | <effect>` to each touched
   capability file, update its **Last updated**, run
   `python3 <skill-root>/scripts/doctor.py` once, and commit only on request.
   There is no archive step.

## Interruption

An unfinished light change consists of the edited specs and the working tree.
Resume from `git diff` and the spec delta. If the remaining work no longer fits
one session, escalate to `propose`.
