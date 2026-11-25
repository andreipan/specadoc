# Scripts

[Русский](../../ru/reference/scripts.md)

This page lists every Python script of the `specadoc` and `orchestrator`
skills: its purpose, subcommands, flags and exit codes. The flags come from the
`--help` output and the argparse code. `tests/test_docs.py` checks that every
script has a section here.

## Conventions

- `<skill-root>` is the installed `skills/specadoc` folder. In Claude Code it is
  `${CLAUDE_SKILL_DIR}`.
- `<orchestrator-root>` is the installed `skills/orchestrator` folder.
- Run each command from the repository root. The scripts resolve relative paths
  against the current directory.
- `<root>` is the artifact root. See [Artifact root resolution](#artifact-root-resolution).
- If the host requires a command prefix or wrapper, add it to each command.

## Python version

The scripts use only the Python standard library. Every lifecycle script imports
`specadoc_config.py` first. That module stops with exit code 2 on Python older
than 3.10. The resolution of Codex role files (TOML) needs Python 3.11 or newer.

The supported minimum is Python 3.10. The maintainer checks in
`scripts/check.sh` need Python 3.11 or newer.

The runtime flags (`--controller-runtime`) accept `claude`, `codex` and
`opencode`. They also accept `claude-code` as an alias of `claude`.

## Artifact root resolution

Every script that reads or writes artifacts resolves the root in this order.
The first match wins.

1. The `--root <path>` flag.
2. The `SPECADOC_ROOT` environment variable.
3. The `root` key of `.specadoc.json` in the current directory.
4. The legacy root `docs/agent`, when it exists and `docs/specadoc` does not.
5. The default root `docs/specadoc`.

A legacy root gives a warning on stderr. To move it, run
[`migrate_root.py`](#migrate_rootpy). `doctor.py` and `init_change.py` print the
resolved root and its source (`cli`, `env`, `config`, `legacy` or `default`).

## Index

| Script | Kind | Purpose |
|---|---|---|
| [`archive_change.py`](#archive_changepy) | command | Compact a closed change into `record.md` |
| [`collect_tokens.py`](#collect_tokenspy) | command | Sum token counters of one change |
| [`doctor.py`](#doctorpy) | command | Check capability specs, archives, routing and the shell |
| [`init_change.py`](#init_changepy) | command | Create `spec.md` and `plan.md` of a change |
| [`list_changes.py`](#list_changespy) | command | Print the status of all active changes as JSON |
| [`migrate_archive.py`](#migrate_archivepy) | command | Compact legacy archive folders |
| [`migrate_root.py`](#migrate_rootpy) | command | Move the artifact root |
| [`pr_description.py`](#pr_descriptionpy) | command | Pull or merge request description from archive records and the diff |
| [`review_snapshot.py`](#review_snapshotpy) | command | Content hash of the Review scope, task scope checks |
| [`role_routing.py`](#role_routingpy) | command | Resolve role bindings |
| [`run_role.py`](#run_rolepy) | command | Run a role on another runtime's CLI |
| [`specadoc_step.py`](#specadoc_steppy) | command | One call per lifecycle step of `propose` and `apply` |
| [`task_brief.py`](#task_briefpy) | command | Write the brief of one worker task |
| [`validate_change.py`](#validate_changepy) | command | Structural validation of `spec.md` and `plan.md` |
| [`design_gate.py`](#design_gatepy) | internal module | Class inventory and design review |
| [`host_clock.py`](#host_clockpy) | internal module | Detect host sleep during a wait |
| [`mode_budget.py`](#mode_budgetpy) | internal module | Size limits of the skill text |
| [`review_state.py`](#review_statepy) | internal module | Record and settle review rounds |
| [`reviewer_reply.py`](#reviewer_replypy) | internal module | Save a native reviewer reply |
| [`specadoc_config.py`](#specadoc_configpy) | internal module | Read and validate `.specadoc.json` |
| [`specadoc_root.py`](#specadoc_rootpy) | internal module | Resolve the artifact root |
| [`task_state.py`](#task_statepy) | internal module | Task state in the baseline file |
| [`verification_inputs.py`](#verification_inputspy) | internal module | Inputs and environment digest for evidence reuse |
| [`ba_register.py`](#ba_registerpy) | orchestrator command | Numbered register of questions for the business analyst |
| [`coordination_log.py`](#coordination_logpy) | orchestrator command | Append-only log of orchestrator decisions |

An internal module has no command line. Other scripts import it.

## archive_change.py

Validates a change and compacts it into one immutable `record.md`. See
[archive](modes.md#archive).

```text
python3 <skill-root>/scripts/archive_change.py [--root ROOT] [--dry-run] [--force] change_slug
```

| Flag | Meaning |
|---|---|
| `change_slug` | The slug of the change. |
| `--root ROOT` | The artifact root. Default: resolved. |
| `--dry-run` | Run all checks and print the result. Write nothing. |
| `--force` | Compact although gates fail. The record lists the unmet gates. |

The script refuses to archive when one of these conditions is true:

- a lifecycle gate is open, or the review result is not PASS
- `review_snapshot.py verify` finds a change after the latest PASS
- a declared capability spec is missing
- a capability spec has no provenance row for the slug
- an `ADDED`, `MODIFIED` or `RENAMED` id is absent from the capability spec, or a
  `REMOVED` id is still present
- an unknown attachment is in the change folder
- `<root>/archive/<slug>/` already exists
- the record is larger than 16 KiB.

`--force` bypasses the lifecycle and provenance gates. It never overwrites a
target and never skips the record validation. The script removes the change
folder only after it reads the record back. Files in `runs/` are not unknown
attachments. They become one row of the source manifest.

Exit codes: 0 success, 1 an archive error (the reason is on stderr), 2 the root
cannot be resolved.

## collect_tokens.py

Sums the token counters of all executions of one change. An execution is one
run: a controller transcript or one child agent.

```text
python3 <skill-root>/scripts/collect_tokens.py change_slug [sources ...] --harness {claude,codex,opencode}
    --mode {explore,light,propose,apply,archive} [--directory DIR] [--db DB] [--session ID]
    [--external-run RUN_JSON] [--final | --provisional] [--root ROOT] [--project DIR] [--append]
```

| Flag | Meaning |
|---|---|
| `sources` | Transcripts or folders, for `claude` and `codex`. |
| `--harness` | The harness that recorded the transcripts. Required. |
| `--mode` | The Specadoc mode of these executions. Required. |
| `--directory DIR` | OpenCode: the repository path where a session ran. |
| `--db DB` | OpenCode: the database location. |
| `--session ID`, `--root-session ID` | OpenCode: include this session and its descendants. Repeat for resumed roots. |
| `--external-run RUN_JSON` | A settled `run_role.py` record. Repeat for each external execution. |
| `--final` | Mark the collection final. |
| `--provisional` | Mark the collection provisional. This is the default. |
| `--root ROOT` | The artifact root. Default: resolved. |
| `--project DIR` | Warn about executions recorded outside this folder. |
| `--append` | Write the totals to `plan.md` and the rows to `runs/tokens.md`. |

Each row gives two numbers. `unique` is uncached input plus cache writes plus
output. `read` is cached input. The numbers are context volume, not provider
billing. Do not compare them across harnesses.

Without a source path, the `claude` backend uses the sessions that
`specadoc_step.py` recorded in `runs/sessions.json`. If that file is missing,
it uses the newest session of the project and says which one.

`--append` replaces only the ledger of this mode and harness. Other ledgers
stay.

Exit codes: 0 success, 1 no execution with a token counter, 2 `--final` with
warnings about missing, unscoped or incomplete inputs, or an unresolved root.

## doctor.py

Reports integrity problems of the capability specs and archive records. With
`--probe`, it checks the shell that a session runs in. The command is read-only.

```text
python3 <skill-root>/scripts/doctor.py [--root ROOT] [--strict]
    [--controller-runtime {claude,codex,opencode}] [--probe] [--expect-head SHA] [--baseline]
```

| Flag | Meaning |
|---|---|
| `--root ROOT` | The artifact root. Default: resolved. |
| `--strict` | Return non-zero for warnings too. |
| `--controller-runtime` | Also inspect role routing, CLI presence and reviewer independence. |
| `--probe` | Check the run environment instead of the specs. |
| `--expect-head SHA` | With `--probe`: the revision the parent session works on. |
| `--baseline` | With `--probe`: also run every `verification.final` command on the checkout. |

Without `--probe`, the doctor reports:

- duplicate `C<n>` ids
- repeated provenance rows
- exact duplicate requirement text across capability specs
- duplicate archive slugs
- archive references that no longer resolve to a capability spec or its
  provenance
- key paths that do not exist in the repository.

The doctor never changes artifacts. With `--controller-runtime`, it reports a
missing runtime CLI as an error. It gives one warning when `worker` and
`reviewer` use the same runtime.

With `--probe`, the doctor checks:

- the executables of `verification.final` and the interpreter of their `#!` line
- the CLI and writable home of each routed runtime
- the checkout, and the revision when `--expect-head` is set
- each `verification.probe` command (exit 0 within 60 seconds).

Exit codes without `--probe`: 0 no errors, 1 errors (or warnings with
`--strict`), 2 an unresolved root. With `--probe`: 0 PASS, 1 an error. A use of
`--expect-head` or `--baseline` without `--probe` gives exit code 2.

## init_change.py

Creates `spec.md` and `plan.md` of a change from the templates in
`<skill-root>/assets/`.

```text
python3 <skill-root>/scripts/init_change.py change_slug [--root ROOT] [--risk {low,medium,high}]
    [--with-design] [--with-research] [--force] (--scout REF | --no-scout REASON)
```

| Flag | Meaning |
|---|---|
| `change_slug` | The change name. The script converts it to kebab-case. |
| `--root ROOT` | The artifact root. Default: resolved. |
| `--risk` | The risk written into the headers. |
| `--with-design` | Also create `design.md`. |
| `--with-research` | Also create `research.md`. |
| `--force` | Overwrite existing files. |
| `--scout REF` | The scout report or agent id that mapped the code. |
| `--no-scout REASON` | Why no scout ran, for example the reused explore evidence. |

You must give `--scout` or `--no-scout`. The script fills the title, risk,
date and scout fields of the headers.

Exit codes: 0 success, 1 a file error (for example an existing file without
`--force`), 2 an invalid slug, an empty scout value or an unresolved root.

## list_changes.py

Prints the `status --json` object of every active change in one read-only call.
A dashboard or a driver script can use it.

```text
python3 <skill-root>/scripts/list_changes.py [--root ROOT]
```

The output is one JSON object: `{root, active: [<status object> + updated_at], archived: N}`.
An active change is a folder under the root with a `plan.md`. The folders
`archive/`, `specs/` and `contracts/` are not changes. A change whose status
fails has `result: "error"`. The script reads no controller transcript, so
`context.tokens` is 0.

Exit code: 0.

## migrate_archive.py

Compacts legacy archive folders into `record.md` files. Without `--apply`, it
writes nothing.

```text
python3 <skill-root>/scripts/migrate_archive.py [--root ROOT] [--apply] [--backup-root DIR]
```

| Flag | Meaning |
|---|---|
| `--root ROOT` | The artifact root. Default: resolved. |
| `--apply` | Do the migration. |
| `--backup-root DIR` | Where the backup goes. Default: `<root>/.archive-backups`. |

The dry run prints the inventory, the projected size and a preview of each
record. Each legacy file other than `spec.md` and `plan.md` needs a
`migration-summary.md` written by a person. With `--apply`, the script first
writes a timestamped `.tar.gz` backup and checks it. It never deletes the
backup.

Exit codes: 0 success, 1 a migration error, 2 an unresolved root.

## migrate_root.py

Moves the artifact root and rewrites root references in the moved Markdown
files. Without `--apply`, it writes nothing.

```text
python3 <skill-root>/scripts/migrate_root.py [--from SOURCE] [--to TARGET] [--apply]
```

| Flag | Meaning |
|---|---|
| `--from SOURCE` | The current root. Default: `docs/agent`. |
| `--to TARGET` | The new root. Default: `docs/specadoc`. |
| `--apply` | Move the folder. |

In a git work tree, the move uses `git mv`. Each literal `<from>/` in the moved
Markdown files becomes `<to>/`. The hashes in archive records stay valid,
because they describe the source artifacts at archive time.

Exit codes: 0 success, 1 a migration or git error.

## pr_description.py

Writes the description of a pull or merge request from archive records and
the diff. It only reads; posting the text is the caller's step. See
[archive](modes.md#archive).

```text
python3 <skill-root>/scripts/pr_description.py (--range BASE..HEAD | --slug SLUG ...) [--root ROOT] [--output FILE]
```

| Flag | Meaning |
|---|---|
| `--range BASE..HEAD` | The commits of the request. The records are the `<root>/archive/<slug>/record.md` files that the range adds or changes, read at `HEAD`. |
| `--slug SLUG` | Read this record from the working tree instead. Repeat for more records. |
| `--root ROOT` | The artifact root. Default: resolved. |
| `--output FILE` | Write the description to the file. Default: standard output. |

For each record the description gives the goal, the first paragraph of the
outcome, the verification (the commands, the requirement mapping with the
requirements that have no recorded result, the test commands, the design and
review rounds, the final review result), the residual risks and the record
path. Several records get one heading each.

With `--range` a last block adds facts from the diff: the number of files and
lines, the migration files (a path with a `migrations/`, `migration/` or
`migrate/` folder), the lock files, the configuration files (a `config/`,
`conf/` or `settings/` folder, or `.env.*`) and the rollback note. When there
is a migration, the note says that a revert does not undo it.

Exit codes: 0 success, 1 the range has no archive record or git failed, 2 bad
arguments.

## review_snapshot.py

Computes a content hash of the Review scope and checks the scope of one worker
task. It needs no git commit or ref.

```text
python3 <skill-root>/scripts/review_snapshot.py {compute,verify,diff,baseline,check-scope} change_slug
    [--task T<n>] [--root ROOT] [--stored MANIFEST] [--previous G<n>|MANIFEST]
```

| Action | Meaning |
|---|---|
| `compute` | Print the snapshot: `{hash, manifest}`. |
| `verify` | Compare the current snapshot with `--stored`. Print `match`, or the differences. |
| `diff` | Print the changes since `--previous` (a round id `G<n>` or a manifest). |
| `baseline` | Record a manifest of the whole working tree in `runs/T<n>-baseline.json` before dispatch. |
| `check-scope` | Fail when a file changed outside the task's `Files:` or under the artifact root. |

| Flag | Meaning |
|---|---|
| `--task T<n>` | The task, for `baseline` and `check-scope`. |
| `--root ROOT` | The artifact root. Default: resolved. |
| `--stored MANIFEST` | For `verify`: a JSON file path or inline JSON. |
| `--previous` | For `diff`: a round id or a manifest. |

A snapshot is the sorted `{path: sha256}` manifest of each path in
`## Review scope`. It also has one entry `spec.md#contract` for the spec
sections Requirements, Acceptance scenarios, Constraints and Affected
capabilities. Files in the change folder are not allowed in the Review scope.

A second `baseline` for the same task keeps the first baseline. A retry never
replaces it.

Exit codes:

- 0: success, or `match`.
- 1: a mismatch (`verify`) or a scope violation (`check-scope`).
- 2: an unresolvable scope, a missing flag or an unresolved root.

## role_routing.py

Resolves the runtime, model and effort of each role. It never starts an agent.
See [Configuration](config.md#role-binding-resolution).

```text
python3 <skill-root>/scripts/role_routing.py --controller-runtime {claude,codex,opencode}
    [--cwd DIR] [--role {scout,worker,reviewer}] [--change SLUG] [--root ROOT]
    [--dry-run] [--check-cli] [--compact]
```

| Flag | Meaning |
|---|---|
| `--controller-runtime` | The runtime of the invoking controller. Required. |
| `--cwd DIR` | The repository root. Default: the current directory. |
| `--role` | Resolve one role only. |
| `--change SLUG` | Check only the roles that this plan uses. Errors of other roles become warnings. |
| `--root ROOT` | The artifact root for `--change`. Default: resolved. |
| `--dry-run` | Read-only. The command never starts agents in any case. |
| `--check-cli` | Also check that each runtime CLI is on `PATH`. |
| `--compact` | A short JSON summary without source details. |

The output is JSON: `{routes, findings}`. A plan uses the `reviewer`, and the
`worker` when a task has `Owner: worker`. Show the result at plan approval with
`--change <slug> --dry-run --compact --check-cli`.

Exit codes: 0 no errors, 1 a finding of level ERROR, 2 an unreadable plan, or
the only requested role cannot be resolved.

## run_role.py

Runs a Specadoc role on another runtime's CLI and collects its result. When the
runtime of a role is not the controller's runtime, use this script. See
[Configuration](config.md#external-runner-settings) and
[`references/runners.md`](../../../skills/specadoc/references/runners.md).

```text
python3 <skill-root>/scripts/run_role.py start --role {scout,worker,reviewer} --prompt-file FILE --name NAME
    [--controller-runtime RT | --runtime RT --model MODEL [--effort EFFORT]]
    [--cwd DIR] [--out-dir DIR] [--dry-run] [--no-progress-timeout SECONDS]
python3 <skill-root>/scripts/run_role.py wait RUN_FILE [--timeout S] [--shell-budget S] [--follow]
    [--interval S] [--no-progress-timeout S]
python3 <skill-root>/scripts/run_role.py status RUN_FILE [--no-progress-timeout S]
python3 <skill-root>/scripts/run_role.py result RUN_FILE
python3 <skill-root>/scripts/run_role.py stop RUN_FILE
```

| Subcommand | Meaning |
|---|---|
| `start` | Start the CLI in the background and print the run file. |
| `wait` | Wait for the run, at most `--timeout` seconds. |
| `status` | Show running, completed, failed or no-progress, with diagnostics. |
| `result` | Validate the final JSON against the role schema and save it. |
| `stop` | Stop the run. |

Flags of `start`:

| Flag | Meaning |
|---|---|
| `--role` | The role. Required. |
| `--controller-runtime` | Resolve the role from project routing and the target role file. |
| `--runtime`, `--model`, `--effort` | Explicit binding, for projects without routing. |
| `--prompt-file FILE` | The brief or the full dispatch prompt. Required. |
| `--name NAME` | The run name, usually the task id. Required. |
| `--cwd DIR` | The repository root the role works in. Default: `.`. |
| `--out-dir DIR` | Where the run files go. Default: the folder of the prompt file. |
| `--dry-run` | Print the CLI command. Do not start it. |
| `--no-progress-timeout S` | Stream silence limit in seconds. Default: 900. 0 disables it. |

Flags of `wait`:

| Flag | Default | Meaning |
|---|---|---|
| `--timeout S` | 120 | The longest wait in seconds. |
| `--shell-budget S` | 120 | The shell time limit of the host. The wait ends a few seconds before it. |
| `--follow` | off | Print a progress line every `--interval` seconds. |
| `--interval S` | 45 | The interval of progress lines. |
| `--no-progress-timeout S` | from the run | Override the stream silence limit. The role is never stopped automatically. |

The prompt file, `--out-dir` and the run files are relative to `--cwd`. The run
files are `<name>.<role>.run.json`, `.log`, `.result.json` and an exit file.
If you start the same name with the same prompt and binding, the existing run
is reused. A conflicting prompt or binding needs a new `--name`.

With `--controller-runtime`, explicit `--runtime`, `--model` or `--effort`
flags that conflict with the resolved binding are refused.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Success. For `wait`: the run finished. |
| 1 | `wait`: a terminal transport error. `result`: the CLI failed or the JSON does not match the schema. |
| 2 | An error, for example a missing prompt file, a missing CLI or a conflicting run name. |
| 3 | `wait`: the run is still running, or no progress was seen. This is not a role failure. |
| 4 | `start`: the runtime cannot write its home or log in this shell (`sandboxed:`). |

## specadoc_step.py

Runs one lifecycle step and prints a compact result. Each step uses the logic
of `review_snapshot.py`, `task_brief.py` and `validate_change.py`.

```text
python3 <skill-root>/scripts/specadoc_step.py [--root ROOT] <step> <arguments>
```

`--root` goes before the step name. Every step prints five fields:

```text
checked: <what ran>
result: PASS | FAIL | BLOCKED | ...
changed files: <paths or ->
blocking reason: <reason or ->
next: <the next allowed step>
```

| Result | Exit code |
|---|---|
| PASS, CHECKED, ACCEPTED, EXTERNAL-PENDING | 0 |
| FAIL | 1 |
| BLOCKED, NEEDS_DECISION, WAITING | 2 |

FAIL is a finding that you can fix. BLOCKED means that the step cannot
evaluate. An unexpected error of a step gives BLOCKED.

Every step accepts `--controller-runtime {codex,claude,opencode}`. The steps
`preflight`, `dispatch`, `wait`, `pre-review`, `design-brief`, `design-review`
and `status` use it. The other steps accept it and ignore it.

### Steps of propose

| Step | Arguments and flags | Meaning |
|---|---|---|
| `design-brief` | `<slug> [--full] [--attempt-decision 'continue: <source>' \| 'accept: <source>'] [--verify-by METHOD] [--context-tokens N]` | Validate the plan, then write `runs/design-brief.md` for the design reviewer. Refuse at the context guard (200k by default, `context.dispatch_guard`): hand off and run the round from a fresh session. `--full` asks for a whole review after a redesign. `--verify-by` names how a round past the second checks the open must-not-ship items differently, or who owns them. |
| `design-review` | `<slug> (--result-file FILE \| --from-agent ID) [--same-reviewer-reason TEXT]` | Record the design verdict in `## Design review`, bound to the inventory hash. |
| `design-resolve` | `<slug> --file FILE\|-` | Answer each item of a FAIL design round: `F1.2: resolved: <where>` or `F1.2: rejected: <why>`. |
| `approve` | `<slug> --by {user,orchestrator} --source TEXT [--bindings TEXT]` | Record the plan approval and its source. Hash `spec.md` and `design.md` into `runs/approval.json`. |

After four design rounds, a new round after a FAIL needs `--attempt-decision`.
`continue: <source>` allows one more round: each open IMPORTANT item becomes a
design obligation in `## Global constraints`, and the round checks the BLOCKER
items and the changes. `accept: <source>` closes the gate, and each open
IMPORTANT item becomes a design obligation. A BLOCKER item is never accepted.

In a re-review every finding carries `origin`: `previous` (an earlier item is
still open), `change` (a defect in the changed lines) or `new`. A `new`
IMPORTANT or MINOR finding lies outside the changes: `design-review` records it
under `### Notes outside the re-review scope` and it does not fail the round.
The recorded round removes `runs/design-brief.md`, so a reviewer cannot start on
it again.

Every BLOCKER and IMPORTANT finding carries `class`: `data`, `money`, `access`,
`user-path` and `wrong-result` are must-not-ship; `other` is test design, spec
wording, internal rules or structure. A must-not-ship class needs a state that
can occur (a code path, existing rows, an input the spec admits); a hypothetical
state is `other` until shown. From design round 3 a BLOCKER or IMPORTANT
of class `other` becomes a design obligation `R<round>.<n>` in
`## Global constraints` and is listed under `### Deferred to apply (not
must-not-ship)`. When no must-not-ship finding is left, the round is
`ACCEPTED` by the must-not-ship rule. A finding without `class` is never
deferred. A round after the second with must-not-ship items open needs
`--verify-by '<method or owner>'`, recorded in `## Confirmed decisions` as
`Design round method`; the same method twice is refused. Each round's counts
go to `runs/design-round.json` and, at archive, to one `Design rounds:` line of
`record.md`.

`approve` refuses when the design review is not current, a review round is
pending, a design obligation is named by no task's `**Obligations:**` field, or
`validate_change.py --phase plan` fails. It also refuses when no bindings line
is recorded and `--bindings` is not given. The worker brief lists the
obligations its task names; `pre-review` writes `runs/G<n>-obligations.md` for
the code reviewer, and an unmet obligation is an IMPORTANT finding.

### Steps of apply: tasks

| Step | Arguments and flags | Meaning |
|---|---|---|
| `status` | `<slug> [--context-tokens N] [--json]` | Print task states, the latest review and the next allowed step. `--json` prints one object with `next.kind`. |
| `preflight` | `<slug> T<n>` | Check the task without a change to files. It runs no Verification. |
| `dispatch` | `<slug> T<n> [--context-tokens N] [--reopen REASON]` | Preflight, then write the task baseline and `runs/T<n>-brief.md`. |
| `wait` | `<slug> T<n>\|tidy [--timeout S] [--shell-budget S]` | Wait for a new task report of any status, or for the tidy record. Default timeout: 540 seconds. |
| `report` | `<slug> T<n> --status STATUS --summary TEXT --red TEXT --green TEXT [--mutation TEXT] [--concern TEXT] [--deviation 'ID: kept\|reverted: WHY'] [--body-file FILE]` | Write the task report and its result JSON from the actual changes. A DONE report needs a decision for every recorded deviation; a kept one becomes a concern. |
| `deviation` | `<slug> T<n> --text TEXT` | The worker records one departure from its brief as it happens, in `runs/T<n>-deviations.md` (id `T<n>.d<k>`, at most 400 characters). The file survives the worker's own compaction; `accept` refuses an entry recorded after the report, a reopen archives the file with the report, and `pre-review` writes the decided entries to `runs/G<n>-deviations.md` for the code reviewer. |
| `accept` | `<slug> T<n> [--scope-only] [--result-file FILE] [--note TEXT] [--resolved HOW] [--verification-timeout S]` | Check the scope, validate the report, run the Verification commands, check the scope again, record Evidence. |
| `external-result` | `<slug> T<n> --outcome {PASS,FAIL} --evidence TEXT [--log PATH] [--supersede REASON]` | Record the result of the task's `External verification:`. |
| `amend` | `<slug> T<n> [--allow PATH] [--derived PATH] [--controller-path PATH] --reason TEXT` | Add a worker path, a derived path or a controller edit to the task scope. |
| `manifest` | `<slug> T<n>` | Print the changed paths and the suggested Review scope bullets as JSON. |
| `refresh` | `<slug> [--verification-timeout S] [--controller-path PATH] [--reason TEXT]` | Accept again every settled task with stale evidence, in dependency order. |
| `handoff` | `<slug> --file FILE\|-` | Overwrite `runs/handoff.md`. At most 4 KiB. |

The `report` statuses are `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT` and
`BLOCKED`. If a test did not fail before the code, use `--mutation`. Give each
break that you made and the test that then failed.

`dispatch` stops near 200k tokens of observed controller context. Other hosts
than Claude Code pass `--context-tokens N`. `--reopen REASON` starts a new
attempt of an earlier task from the current tree. Use it for code fixes only.

`accept` runs the Verification field with the caller's permissions. Each
command in the field must be in backticks. Separate commands with semicolons.
The default `--verification-timeout` of `accept` and `refresh` is 600 seconds.
`--resolved HOW` accepts a BLOCKED or NEEDS_CONTEXT report after the blocker
was removed.

`external-result --supersede REASON` replaces a recorded result for the same
content. The old result stays in `external_history`. A FAIL returns the task to
work.

### Steps of apply: review and completion

| Step | Arguments and flags | Meaning |
|---|---|---|
| `scope` | `<slug> [--base REV] [--dry-run] [--exclude PATH]` | Fill `## Review scope` from the diff since `--base` (default `HEAD`), plus untracked files. |
| `tidy` | `<slug> [--record --summary TEXT [--from-agent ID] \| --skip REASON]` | Without flags: write `runs/tidy-brief.md`. `--record`: record the tidy worker's result. `--skip`: record why no pass is necessary. |
| `finalize` | `<slug> [--observed RUN] [--requirements WHY] [--run] [--timeout S] [--residual TEXT]` | Tick the Final verification boxes that the recorded state proves. Fill Completion evidence. |
| `pre-review` | `<slug> [--review-type {initial,re-review}] [--reason REASON] [--review-decision TEXT] [--dry-run] [--withdraw]` | Run the pre-review gate and record a new `### G<n>` round. Write `runs/G<n>-head.diff` and `runs/G<n>-status.txt`. |
| `review-result` | `<slug> (--result-file FILE \| --from-agent ID) [--same-reviewer-reason TEXT]` | Settle the pending round. Save a native reviewer's reply under `runs/`. |

`finalize` flags:

- `--run` runs the `verification.final` commands of `.specadoc.json` once and
  records them in `runs/final-verification.json`. The default `--timeout` is
  1800 seconds for each command.
- `--observed RUN` records the whole suite and gates that the controller ran.
- `--requirements WHY` sets each Pending matrix status to PASS, with the
  evidence in one line.
- `--residual TEXT` writes the residual risks, or `none`.

`pre-review` flags:

- `--review-type` defaults to `initial`.
- `--reason` is `implementation`, `corrections`, `minor-fixes`, `requirements`
  or `polish`.
- `--review-decision` authorizes a bounded extra round. Give the author: the
  user's words, or `orchestrator D<n> under mandate D<m>: <scope>`.
- `--dry-run` runs the gate and prints the snapshot. It records no round.
- `--withdraw` removes the latest round while it is Pending.

A fourth `initial` round needs `--review-decision`. With `review.tidy: required`
in `.specadoc.json`, the first `initial` round needs a tidy record.

`review-result` and `design-review` refuse the reviewer agent of the previous
round. To allow it, give `--same-reviewer-reason`.

## task_brief.py

Writes a self-contained brief for one worker task to
`<root>/<slug>/runs/T<n>-brief.md` and prints the path. `dispatch` calls it.

```text
python3 <skill-root>/scripts/task_brief.py [--root ROOT] change_slug T<n>
```

The brief contains:

- the task block from `plan.md`, word for word
- the spec requirements that the task names
- the acceptance scenarios that cover them
- the spec Constraints
- the handoff contract: report path, result schema and scope rules
- `runs/lessons.md`, cut to 2048 bytes, when it exists.

A brief larger than 16,000 bytes gives a warning that names the largest parts.

Exit codes: 0 success, 2 an error (the reason is on stderr).

## validate_change.py

Validates the structure of `spec.md` and `plan.md` for one phase. It cannot
check meaning. See [Plan structure](plan-structure.md#what-the-validator-checks).

```text
python3 <skill-root>/scripts/validate_change.py change_slug --phase {spec,plan,pre-review,final}
    [--root ROOT] [--json] [--next-review-type {initial,re-review}] [--review-decision TEXT]
python3 <skill-root>/scripts/validate_change.py --files-hash "<Files: value>"
```

| Flag | Meaning |
|---|---|
| `--phase` | The checkpoint to validate. |
| `--root ROOT` | The artifact root. Default: resolved. |
| `--json` | Print the violations as JSON. |
| `--next-review-type` | The proposed review dispatch. Do not use it to relabel a past round. |
| `--review-decision TEXT` | The decision for a proposed extra review, with its author. |
| `--files-hash FIELD` | Print the content hash of a task's `Files:` value and stop. |

| Phase | When |
|---|---|
| `spec` | Before technical planning. |
| `plan` | Before the plan preview. |
| `pre-review` | Before the reviewer dispatch. |
| `final` | After the review PASS and before archive. |

Warnings go to stderr and do not change the exit code. Examples: a `plan.md`
over 48 KiB, more than eight tasks, a `Verification` command that starts with
`NAME=value` or `env`.

Exit codes: 0 no violations, 1 violations, 2 a missing change folder, a missing
artifact, a missing argument or an unresolved root.

## design_gate.py

Internal module. It reads the plan's `## Class inventory` and records the
independent design review in `## Design review`, bound to the inventory hash.
`specadoc_step.py` uses it for `design-brief`, `design-review`, `design-resolve`,
`approve` and `dispatch`. It keeps the round count in `runs/design-round.json`.
The round cap is four.

## host_clock.py

Internal module. It detects host sleep during a wait. On macOS the monotonic
clock stops during sleep and the wall clock does not. `run_role.py wait` and
`specadoc_step.py wait` use it to tell a sleeping host from a stalled role.

## mode_budget.py

Internal module. It checks the byte size of the skill text against
`<skill-root>/assets/mode-budget.json`. A file over its limit is an error. A
mode over its total limit is a warning. The repository tests use it. See
[Plan structure](plan-structure.md#size-limits).

## review_state.py

Internal module. It inserts a `### G<n>` round into `## Review result` before
the reviewer dispatch and settles the result. `specadoc_step.py pre-review` and
`review-result` use it. It refuses to relabel a corrective round as `initial`.

## reviewer_reply.py

Internal module. It finds a native reviewer's transcript by agent id and saves
the final reply word for word under `runs/`. This is the `--from-agent` option
of `review-result` and `design-review`. It reads transcripts under
`$CLAUDE_CONFIG_DIR/projects`, default `~/.claude/projects`.

## specadoc_config.py

Internal module. It reads and validates `.specadoc.json` in the current
directory. It also stops each script with exit code 2 on Python older than 3.10.
See [Configuration](config.md).

## specadoc_root.py

Internal module. It resolves the artifact root (see
[Artifact root resolution](#artifact-root-resolution)). It also creates the
`runs/` folder of a change with a `.gitignore` that contains `*`.

## task_state.py

Internal module. It keeps the state of a task (schema `specadoc.task/v2`) in the
task baseline file `runs/T<n>-baseline.json`. It also checks the plan approval
and the readiness of a task before dispatch.

## verification_inputs.py

Internal module. It computes the content inputs that decide whether accepted
evidence is still valid. The inputs are the task Files, Derived files, lockfiles,
`Verification inputs` and a digest of each relevant environment variable. It
never stores variable values. See
[Configuration](config.md#verificationenvironment).

## ba_register.py

Orchestrator command. It keeps one numbered register of questions for the
business analyst, divergences from the sources, and decisions taken without
the analyst.

```text
python3 <orchestrator-root>/scripts/ba_register.py add <file> --title T --step S --type T --status S
    [--section HEADING] [--file PATH|-]
python3 <orchestrator-root>/scripts/ba_register.py status <file> <n> --status S [--note TEXT]
python3 <orchestrator-root>/scripts/ba_register.py list <file> [--status TEXT]
```

| Subcommand | Meaning |
|---|---|
| `add` | Add an item with the next number. `--section` names a top-level `# ` heading. Default: the end of the file. |
| `status` | Change the status of item `<n>` in place. `--note` appends a dated note. |
| `list` | List the items, optionally only those with a status. |

An item is `## <n>. <title> (<step>)` with one line of type and status. A number
is never used again: the next number is the largest number plus one. The item
text is at most 4096 bytes. The register file must exist.

Exit codes: 0 success, 1 an error.

## coordination_log.py

Orchestrator command. It keeps an append-only log of numbered decisions and one
current-state block.

```text
python3 <orchestrator-root>/scripts/coordination_log.py decision <log> --by {user,orchestrator}
    --title TEXT --file PATH|- [--quote TEXT [--confirms TEXT]]
python3 <orchestrator-root>/scripts/coordination_log.py state <log> --file PATH|-
python3 <orchestrator-root>/scripts/coordination_log.py last <log>
python3 <orchestrator-root>/scripts/coordination_log.py get <log> D<n>
python3 <orchestrator-root>/scripts/coordination_log.py capsule <log> [--status PATH] [--max-lines N]
```

| Subcommand | Meaning |
|---|---|
| `decision` | Append `### D<n> — <title> [by <author>] (<UTC time>)` after the highest D<n>. |
| `state` | Replace the block between the current-state markers. |
| `last` | Print the header of the newest decision. |
| `get` | Print one decision. |
| `capsule` | Print the orchestrator's role reminder for after a compaction: the granting mandate (the user's decision that names the mandate, not one taken under it), the current-state block, the current state of `status.md` beside the log, the five newest decision headers and fixed rules; at most `--max-lines` (60) lines and 4096 bytes. |

`--by user` needs `--quote` with the user's own words. A bare "go" or "ok"
also needs `--confirms`, which names the one proposal it accepted.
`--by orchestrator` is a decision under the mandate. Earlier entries are never
rewritten. A decision is at most 2048 bytes and the state block at most 1536
bytes.

Exit codes: 0 success, 2 an error.
