# Changelog

[Русский](CHANGELOG.ru.md)

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-11-17

### Changed

- The install guide uses the GitHub marketplace (`andreipan/specadoc`) for
  Claude Code and Codex, with an optional release tag. It also covers a project
  scope for teams and how to move to another tag.
- `tests/test_docs.py` checks that the example release tag in the README files
  and install guides matches the version in `plugin.json`. The release steps
  in the packaging guide now include it and the GitHub release.

### Fixed

- The `.DS_Store` scope test no longer depends on a global gitignore, so
  `scripts/check.sh` passes on machines that ignore `.DS_Store` globally.

## [0.1.2] - 2026-11-17

### Changed

- The documentation is rewritten in English and Russian. The `docs/` folder,
  `README.ru.md` and both changelogs ship in the release ZIP.
- `tests/test_docs.py` checks the documentation. Each English page must have a
  current Russian translation. Every script and mode must be documented.
  Relative links and heading anchors must resolve. `scripts/docs_sync.py`
  stamps a translation after an update.
- The neutrality test also scans the documentation.

### Fixed

- Implicit mode selection now asks for the plan approval. The old text asked
  for "both approvals", but plan approval is the only approval stop.
- `scripts/smoke_codex.py` gives `init_change.py` the required `--no-scout`
  reason and counts the installed helpers.
- `apply.md` step 6 no longer reads as an unconditional tidy pass. The pass is
  mandatory only with `review.tidy: required`, as `pre-review` enforces.
- `artifacts.md` no longer says that capability specs are written at archive
  time. The controller writes them after the review PASS. The final gate and
  `archive_change.py` check them.
- `interoperability.md` now states the role tooling block rule: a host that
  generates its own role files replaces only that block.

## [0.1.1] - 2026-11-17

First tagged release. There is no earlier tag, so this section lists what the
plugin contains at this version.

### Lifecycle and modes

- Five modes: `explore`, `propose`, `apply`, `light` and `archive`. Specadoc runs only on an explicit request.
- `spec.md` holds the stable behavioral contract of a change. `plan.md` holds tasks, approvals and evidence.
- `light` mode for a change that stays in one repository and one session. It updates capability specs in place and creates no change folder.
- `archive` compacts a closed change into one bounded `record.md`. `migrate_archive.py` converts older archives and keeps a verified backup.
- The artifact root is configurable. The default is `docs/specadoc`. `migrate_root.py` moves an old `docs/agent` root.
- The controller implements tasks by default. A worker gets only a task with low decision risk, known files and an exact verification.
- `init_change.py` requires `--scout <report>` or `--no-scout <reason>` and records it in the plan.
- Companion skills `tidy`, `codebase-design` and `domain-modeling`. They are opt-in and also work without Specadoc.

### Gates and review

- `validate_change.py` gates the phases `spec`, `plan`, `pre-review` and `final`.
- `specadoc_step.py` runs each apply step with one command and prints a five-field result. Steps include `approve`, `dispatch`, `report`, `accept`, `refresh`, `pre-review`, `finalize` and `status`.
- Design gate: the plan lists each new non-test file in a class inventory. A design review must PASS before the first dispatch. After four recorded rounds, the controller must decide explicitly.
- `review_snapshot.py` hashes the review scope. If the diff changes after a PASS, `status` asks for a re-review.
- One `tidy` pass over the review scope runs before the first review.
- The reviewer can mark a requirement UNVERIFIABLE and ends its reply with a result JSON.
- A MINOR finding is deferred only by a decision of the parent session or the user.
- `finalize --run` records the final verification against the review scope and refuses a stale run.
- A check reserved for the user or another executor goes into `External verification` and is recorded with `external-result`.
- `report` refuses a completion that admits a test written after the code, unless mutation evidence is given.
- Accepted evidence is reused only while its inputs are unchanged. Environment values are never stored.

### Roles and routing

- Three bounded roles: `scout`, `worker` and `reviewer`. Portable contracts ship with the skill. Claude Code adapters are generated from them.
- Role resolution order: a project role, a registered plugin role, a permitted subagent with the portable contract, then the controller. Without an independent reviewer, the review gate stays incomplete.
- Optional `.specadoc.json` routes each role to `claude`, `codex` or `opencode`. Model and effort come from the installed role file of the target runtime, at each dispatch.
- Specadoc fixes no model and no model level. The plan preview shows each role binding.
- `run_role.py` runs a role on another runtime with a file-based handoff. Worker statuses are `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT` and `BLOCKED`.
- `wait` reports host sleep as host sleep, not as a stalled role.
- OpenCode read-only roles take shell allow rules from the installed role file.

### Management skills

- `foreman`: the main session keeps decisions and acceptance, and one persistent executor does the work. It stops if the host cannot continue an executor.
- `orchestrator`: coordinates several Specadoc controllers. It owns shared contracts, dependencies and end-to-end acceptance.
- The orchestrator accepts local plan checkpoints only under an explicit user mandate. A mandate can cover a range of steps.
- An integration verifier runs the cross-project checks for the orchestrator. It reports failures and never fixes them.
- `coordination_log.py` appends orchestrator decisions. `ba_register.py` keeps one numbered register of analyst questions, divergences and decisions.
- Both skills run only on an explicit request and include simulation eval cases.

### Tooling and packaging

- Claude Code plugin and marketplace. A portable `plugin.json` and a Codex marketplace install all six skills.
- `package_plugin.py` checks the manifests and builds a deterministic ZIP. `smoke_codex.py` is an opt-in offline Codex pilot.
- `doctor.py` checks capability specs and archives. `doctor.py --probe` checks the run environment before work starts.
- `collect_tokens.py` collects token counts from Claude Code, Codex and OpenCode transcripts and from external role runs.
- `list_changes.py` prints the status of every active change in one call.
- Skill scripts stop with a clear error on Python older than 3.10.
- Tests limit the size of the skill text that each mode loads and keep host-specific words out of public text.
