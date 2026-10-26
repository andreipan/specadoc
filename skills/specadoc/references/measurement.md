# Measurement: manifests and execution tokens

Load this reference when handing evidence to a controller or reviewer, or when
recording execution totals in `plan.md`.

## Compact manifest

A manifest is what a worker or controller passes upward instead of
raw output. It contains exactly:

- **Commands** - each accepted command and its result on one line. No successful
  log bodies. For a failure, the classified cause and the smallest reproducing
  command, not the full trace.
- **Diff scope** - the changed paths and a `git diff --stat` summary line.
- **Coverage** - a pointer to the plan's requirement-to-check matrix. Do not
  restate the matrix.
- **Baseline** - which failures were already present before this change.
- **Gaps** - every check that did not run, stated explicitly, such as
  `tests were not analysed` for a production-only static-analysis run.

Raw successful logs and repeated broad error output never enter the controller
or reviewer context. A reviewer still inspects critical evidence itself; a
manifest replaces re-running checks, not judgement.

The reviewer dispatch example in `subagent-routing.md` is this shape in use.

`accept` records a task's Evidence and Evidence hash. To record them by hand,
compute the hash with `validate_change.py --files-hash "<Files: value>"`.

Record execution totals by Specadoc mode: `explore`, `propose`, `apply`, and
`archive`. A mode that did not run is absent, never zero.

## Token accounting

An **execution** is one run: a controller transcript, or one child agent. Counters
are read once, at their final value; snapshots inside one run are the same running
total and are never summed. A resumed session writes a second transcript whose
counter restarts, so runs of one session are separate executions. Deduplicate by
run, not by session — keying on the session id silently drops the resumed run.

Two aggregates, answering different questions:

- **`unique`** — uncached input + cache writes + output. New tokens that entered a
  transcript.
- **`read`** — cached input: the same context re-sent turn after turn. It tracks
  turn count more than content, and it dominates provider billing.

Collect every execution of a delivery change, controller included. A child-only
sum is incomplete evidence.

```bash
python3 <skill-root>/scripts/collect_tokens.py <slug> --mode <explore|propose|apply|archive> --harness claude   <session.jsonl|project-dir>...
python3 <skill-root>/scripts/collect_tokens.py <slug> --mode <explore|propose|apply|archive> --harness codex    <rollout.jsonl|dir>...
python3 <skill-root>/scripts/collect_tokens.py <slug> --mode <explore|propose|apply|archive> --harness opencode --directory <repo path>
```

Each backend reads what its harness records:

- **claude** — `~/.claude/projects/<slug>/<session>.jsonl`; with no path the
  collector uses this project's newest session and says which. Pass only the
  session file, not its `subagents/` files. One API response is
  written as several lines, one per content block, each repeating the same usage:
  the collector deduplicates on `requestId`. Child agents are picked up from
  `<session>/subagents/`, and their role comes from the sibling `.meta.json`.
- **codex** — `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Note that Codex
  `input_tokens` *includes* `cached_input_tokens`, unlike Claude Code, where the
  fields are disjoint. Codex records no parent link; attribute child runs by `cwd`
  and time window.
- **opencode** — `~/.local/share/opencode/opencode.db`, table `session`, which
  carries legacy `session` and V2 `session_v2` tables. V2 is authoritative when
  both contain the same id. Full ids preserve controller-to-child attribution.
  Supply `--session <controller-id>` (repeat for resumed roots) to include only
  that controller and descendants. Omitting it warns and counts the whole directory,
  not necessarily this change. Use `--db <read-only-snapshot>` when auditing a live
  store that needs a backup under the host's rules.
- **external runs** (`run_role.py`) — Codex runs are `--ephemeral` and Claude runs
  keep no session, so neither leaves a transcript: read the `usage` totals that a
  successful `result` writes into `runs/<name>.<role>.run.json`, in the runtime's
   own field names.

Pass each settled external record explicitly with `--external-run <run.json>`;
it may belong to a different runtime than the controller. Keep native and
external input sets disjoint when a runtime also persisted that external session.
Repeated paths/children and streaming Claude responses are deduplicated; partial
usage blocks do not replace a later final counter. Missing external usage warns,
never masquerades as an execution with zero tokens.

Collections include `collected_at`, ledger owner and `status=provisional` by
default. Collect again after corrective reviews; use `--final` only for the
completed execution set; warnings about skipped/missing/unscoped inputs block
that label rather than silently producing a partial final. It marks an as-of snapshot, not proof that future turns
or archive work cost nothing. `--append` replaces only this mode/owner ledger,
preserving other harness ledgers; archived records are never rewritten. Keep
historical worker reports and earlier provider semantics intact.

The aggregate is reported context volume, not provider billing. Plan, pricing, and
cache-rate semantics are not available from a transcript, so do not convert it to
money.

A **review round** is one root-level read-only review of a stable diff. A
re-review counts as a round only when it follows a code change made in response
to a finding.

Absolute numbers are **not comparable across harnesses**: cache semantics, models,
and system prompts differ. Keep the harness beside every total, and do not turn
transcript counters into provider billing.
