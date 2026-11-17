# Development

[Русский](../../ru/maintainers/development.md)

This page is for contributors who change Specadoc itself. To use Specadoc on
your own repository, start at the [documentation map](../index.md). For the
version, the ZIP and the release steps, see [Packaging](packaging.md).

## Repository layout

| Path | Contents | In the release ZIP |
|---|---|---|
| `skills/specadoc/` | The lifecycle skill: `SKILL.md`, `references/`, `scripts/`, `assets/` and `agents/openai.yaml` | yes |
| `skills/tidy/`, `skills/codebase-design/`, `skills/domain-modeling/` | Companion skills | yes |
| `skills/foreman/`, `skills/orchestrator/` | Management skills with their `evals/` cases. The orchestrator also has `scripts/coordination_log.py` and `scripts/ba_register.py` | yes |
| `agents/` | Claude Code role adapters, generated from the portable role contracts | no |
| `scripts/` | Check and build tools for the checkout | no |
| `tests/` | Unit tests and the `tests/evals/` behavioral eval cases | no |
| `plugin.json` | Portable plugin manifest | yes |
| `.claude-plugin/` | Claude Code manifest and marketplace | no |
| `.agents/plugins/marketplace.json` | Codex marketplace for a local source | no |
| `docs/en/`, `docs/ru/` | This documentation | yes |
| `dist/` | Build output. Git ignores this folder | no |

The tools in `scripts/`:

| File | Purpose |
|---|---|
| `check.sh` | Runs all checks of the checkout. Use it before each commit |
| `render_roles.py` | Writes `agents/*.md` from the portable role contracts. With `--check`, it only compares |
| `claude-roles.json` | Claude Code frontmatter for each generated adapter |
| `package_plugin.py` | Checks the package and builds the ZIP. See [Packaging](packaging.md) |
| `smoke_codex.py` | Opt-in offline Codex pilot. See [Packaging](packaging.md) |
| `docs_sync.py` | Reports each English document without a current Russian translation. With `--stamp`, it records the source hash in a Russian document |

## Python version

The scripts use only the Python standard library. Three version limits apply:

| What | Minimum | Where the limit is |
|---|---|---|
| Skill scripts in `skills/*/scripts/` | Python 3.10 | `specadoc_config.py` stops with an error on an older interpreter |
| Codex TOML role registries in `role_routing.py` | Python 3.11 | `tomllib` |
| `scripts/check.sh` | Python 3.11 | The routing tests need `tomllib` |

The release ZIP does not install Python. A user with Python 3.10 can run the
lifecycle scripts but not the Codex registry resolution.

## Run the checks

Run the full check from the repository root:

```bash
scripts/check.sh
```

If `check.sh` selects the wrong interpreter, give it one explicitly:

```bash
PYTHON=/path/to/python3.11 scripts/check.sh
```

Without `PYTHON`, the script tries `python3`, then `python3.14` down to
`python3.11`, then `/opt/homebrew/bin/python3` and `/usr/local/bin/python3`. It
uses the first interpreter that is 3.11 or newer. If it finds none, it stops
with `error: routing checks require Python 3.11+`.

`check.sh` runs these steps in sequence and stops at the first failure:

1. `scripts/render_roles.py --check`: the Claude Code adapters match the role contracts.
2. `scripts/package_plugin.py --check`: the manifests, the skills and the ZIP contents are valid.
3. `python -m unittest discover -s tests -p 'test_*.py' -q`: all unit tests.
4. If the `claude` CLI is on `PATH`, `claude plugin validate . --strict` and
   `claude plugin validate .claude-plugin/plugin.json --strict`.

All Python steps run with `PYTHONDONTWRITEBYTECODE=1`.

To run one test module, give its file name as the pattern:

```bash
python3 -m unittest discover -s tests -p 'test_validate_change.py' -q
```

## Unit tests

All tests use `unittest`. The tests work in temporary folders and do not
start a model. A test that runs a role CLI puts a fake `codex` or `opencode`
script first on `PATH`.

| Group | Files | What they check |
|---|---|---|
| Lifecycle scripts | `test_init_change.py`, `test_validate_change.py`, `test_specadoc_step.py`, `test_review_state.py`, `test_review_snapshot.py`, `test_final_run_and_status_json.py`, `test_task_brief.py`, `test_worker_scope.py`, `test_list_changes.py` | Change creation, the phase gates, the apply steps, review rounds, the review scope and the status output |
| Archive and artifact root | `test_archive_change.py`, `test_migrate_archive.py`, `test_migrate_root.py`, `test_specadoc_root.py`, `test_specadoc_doctor.py` | Archive records, migrations, root resolution and the read-only health check |
| End to end | `test_lifecycle_cli.py` | The packaged CLI gates from spec to normal archive, with synthetic approval and review input |
| Roles and routing | `test_agents.py`, `test_role_routing.py`, `test_run_role.py` | Adapter format, role binding resolution and role runs on another runtime |
| Token accounting | `test_collect_tokens.py` | The collector for Claude Code, Codex and OpenCode transcripts |
| Skill text | `test_mode_budget.py`, `test_specadoc_explore.py`, `test_engineering_companions.py`, `test_management_skills.py`, `test_coordination_log.py`, `test_ba_register.py` | Size limits, required rules in the skill text, the companion and management skills and the orchestrator scripts |
| Package | `test_plugin_package.py` | Manifest checks, ZIP contents, a reproducible build and the eval case list |
| Neutrality | `test_neutrality.py` | Host-specific words in public text |
| Documentation | `test_docs.py` | Translation state, relative links, language switch links, and a reference entry for each script and mode |
| Audit regressions | `test_apply_reliability.py`, `test_apply_efficiency.py` | Failures found in two workflow audits |
| Pilot regressions | `test_run<id>_regressions.py` | Failures found in pilot runs. See the next section |

`test_lifecycle_cli.py` tests the artifact mechanics. It does not prove model
behavior or a real independent PASS.

### Regression tests named after pilot runs

Many Specadoc fixes come from pilot runs. In a pilot run, Specadoc makes real
changes in a repository, and the maintainer reviews the run after it. Each
failure from that review gets a regression test.

The tests for one pilot run, or for one group of runs, go into one file. The
file name carries the run id, for example `test_run35_regressions.py` or
`test_run611_regressions.py`. These rules apply:

- The module docstring names the runs that the file covers.
- Each test class covers one failure. Its docstring says what went wrong in the run.
- The test fails on the old behavior and passes on the fix.
- The tests use synthetic fixtures. Many files import the shared plan and
  helpers from `test_specadoc_step.py` and `test_apply_reliability.py`.

When a new pilot run shows a failure, add the test to the file of that run.
If the run has no file, make a new one with the same name pattern.

### Neutrality test

`tests/test_neutrality.py` keeps public text free of host-specific vocabulary.
It has two tests:

- `test_skill_text_names_no_host_apps` reads `skills/**/*.md`. It refuses names
  of concrete host applications and host environment variables.
- `test_no_host_specific_terms` reads the `.md`, `.py`, `.yaml`, `.json` and
  `.toml` files in `skills/`, `agents/`, `scripts/` and `docs/`. It also reads
  `README.md`, `README.ru.md`, `CHANGELOG.md` and `CHANGELOG.ru.md`. It refuses
  personal tool names, stack-specific commands and private project paths.

The patterns are in the test file. If the test fails, write the text in
neutral words. Skill text names a host capability, for example "a symbol-aware
tool". Concrete host tools and commands belong in the instructions of the
host or of the repository.

### Documentation checks

`tests/test_docs.py` checks the documentation in `README.md`, `CHANGELOG.md`
and `docs/`, and the Russian files of each:

- Each relative link points to a file that exists.
- Each document has a link to its other language in the first six lines.
- `docs/en/reference/scripts.md` has a `## <name>.py` section for each script
  in `skills/specadoc/scripts/` and `skills/orchestrator/scripts/`.
- `README.md` and `docs/en/reference/modes.md` name each mode from
  `skills/specadoc/SKILL.md`.
- Each English document has a Russian document at the same path, and the
  Russian document is current.

The first line of each Russian document records the SHA-256 of its English
source: `<!-- source-sha256: <hex> -->`. If the English document changes, the
check reports the Russian document as stale. To make it current, do these
steps:

1. Update the Russian translation.
2. Run `python3 scripts/docs_sync.py --stamp <russian file>`.

`python3 scripts/docs_sync.py` without options only reports problems. It
prints `Documentation EN/RU: OK` when there are none.

## Portable role contracts and adapters

The role contracts in `skills/specadoc/references/roles/` are the source:
`scout.md`, `worker.md` and `reviewer.md`. The files `agents/scout.md`,
`agents/worker.md` and `agents/reviewer.md` are Claude Code adapters.
`render_roles.py` makes each adapter from three parts:

1. Frontmatter from the role entry in `scripts/claude-roles.json`.
2. A comment line that says the file is generated.
3. The full text of the role contract.

To change a role, do these steps:

1. Edit the contract in `skills/specadoc/references/roles/`.
2. If the Claude Code frontmatter must change, edit `scripts/claude-roles.json`.
3. Run `python3 scripts/render_roles.py`.
4. Commit the contract and the generated adapter together.

Do not edit `agents/*.md` by hand. The next render overwrites the edit, and
the check fails before that.

`python3 scripts/render_roles.py --check` writes nothing. If an adapter is
missing or different, it prints `Stale adapters: <paths>` and exits with 1.
`check.sh` runs this check first. `test_plugin_package.py` compares the
adapters again.

`claude-roles.json` has one entry for each role, with the keys `name`,
`description`, `tools` and `model`. These values apply only to the Claude Code
adapters. They do not bind a Codex or OpenCode model.

`tests/test_agents.py` checks each adapter:

- The frontmatter has `name`, `description`, `tools` and `model`.
- The text has exactly one block between `<!-- specadoc:tooling:begin -->` and
  `<!-- specadoc:tooling:end -->`. This block holds the neutral tool guidance.
- The text has the report headings of the role.
- Only the worker has the `Edit` or `Write` tool.

The orchestrator has one more contract,
`skills/orchestrator/references/roles/integration-verifier.md`. It has no
generated adapter. `test_management_skills.py` checks its tooling block and
report headings.

## Behavioral eval cases

Two sets of eval cases describe the expected model behavior in words:

| Location | Format | Contents |
|---|---|---|
| `tests/evals/specadoc.json` | A list of cases with `id`, `request` and `expected_behavior` | 14 lifecycle cases, for example the direct path, a MINOR re-review and an unavailable reviewer |
| `tests/evals/tidy.json`, `codebase-design.json`, `domain-modeling.json` | `skill_name` and `evals`. Each eval has `id`, `prompt`, `expected_output` and `files` | Cases for the companion skills |
| `skills/foreman/evals/<case>/`, `skills/orchestrator/evals/<case>/` | `case.yaml`, `prompt.md` and `graders/*.md` | Simulation cases with trace graders: 3 for Foreman, 4 for Orchestrator |

In a management skill case, `case.yaml` has `schema_version: "1.1"`, the
case `name` and an `expected_outcome`. The frontmatter of `prompt.md` sets
`max_turns`, `timeout_seconds` and `allowed_tools` for an eval runner. Each
grader starts with `type: llm`, `focus: trace` and `weight: 1`.

The management skill cases are in the release ZIP. The `tests/evals/` cases are
not.

The unit tests check only the presence and the format of these cases:

- `test_plugin_package.py` compares the case ids in `tests/evals/specadoc.json`
  with the approved list. It also checks that each case has a request and an
  expected behavior.
- `test_management_skills.py` checks the folder names, the `case.yaml` fields,
  the `prompt.md` frontmatter and the grader headers.
- No test reads the companion skill files in `tests/evals/`.

The repository has no script that runs these cases with a model. A passing
`check.sh` is not the result of a behavioral evaluation. If you run the cases
with a model, record the model, the host and each result. Record each case
that did not run as a gap.

## Token accounting

Use token accounting to compare the cost of a skill change across pilot runs.
The full rules are in
[measurement.md](../../../skills/specadoc/references/measurement.md). The
script is `skills/specadoc/scripts/collect_tokens.py`.

An execution is one run: one controller transcript or one child agent. The
collector reads each counter once, at its final value. A resumed session
writes a new transcript, so it is a separate execution.

The collector gives two totals:

| Total | Contents |
|---|---|
| `unique` | Uncached input, cache writes and output: new tokens that entered a transcript |
| `read` | Cached input: the same context sent again on each turn. It follows the turn count more than the content |

Collect every execution of a change, the controller included. A total of only
the child agents is incomplete. Run the collector once for each mode, for
example:

```bash
python3 skills/specadoc/scripts/collect_tokens.py <slug> --mode apply --harness claude <session.jsonl> --append
python3 skills/specadoc/scripts/collect_tokens.py <slug> --mode apply --harness codex <rollout.jsonl> --append
python3 skills/specadoc/scripts/collect_tokens.py <slug> --mode apply --harness opencode --directory <repo path> --session <controller-id> --append
```

- If a role ran through `run_role.py`, add its record with
  `--external-run runs/<name>.<role>.run.json`.
- With `--append`, the totals go to `plan.md` and the rows for each execution go
  to `runs/tokens.md`.
- A collection is provisional by default. Use `--final` only for the completed
  set of executions.

Read the numbers with these limits:

- Do not compare absolute numbers across harnesses. Cache rules, models and
  system prompts are different. Keep the harness next to each total.
- The totals are context volume from transcripts. They are not provider billing.
  Do not convert them to money.
- Codex `input_tokens` includes the cached input. In Claude Code transcripts the
  two fields are separate. The collector handles this difference.

### Context budget of the skill

`test_mode_budget.py` limits the size of the skill text that a mode loads. The
limits are in `skills/specadoc/assets/mode-budget.json`:

- `SKILL.md` larger than 5632 bytes is an error.
- A file in `references/` larger than 15360 bytes is an error.
- For each mode, `SKILL.md` plus the files in `always` above the mode `limit`
  gives a warning.
- A mode reference that names a reference file not in the manifest is drift.
  The test fails on drift.

When you make a mode reference name a new reference file, add that file to
the mode in `mode-budget.json`, under `always` or `conditional`.
