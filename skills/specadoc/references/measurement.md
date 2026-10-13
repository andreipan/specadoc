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
  `tests were not analysed` for a production-only PHPStan run.

Raw successful logs and repeated broad error output never enter the controller
or reviewer context. A reviewer still inspects critical evidence itself; a
manifest replaces re-running checks, not judgement.

The reviewer dispatch example in `subagent-routing.md` is this shape in use.

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
rtk python3 <skill-root>/scripts/collect_tokens.py <slug> --mode <explore|propose|apply|archive> --harness claude   <session.jsonl|project-dir>...
rtk python3 <skill-root>/scripts/collect_tokens.py <slug> --mode <explore|propose|apply|archive> --harness codex    <rollout.jsonl|dir>...
rtk python3 <skill-root>/scripts/collect_tokens.py <slug> --mode <explore|propose|apply|archive> --harness opencode --directory <repo path>
```

Each backend reads what its harness records:

- **claude** — `~/.claude/projects/<slug>/<session>.jsonl`. One API response is
  written as several lines, one per content block, each repeating the same usage:
  the collector deduplicates on `requestId`. Child agents are picked up from
  `<session>/subagents/`, and their role comes from the sibling `.meta.json`.
- **codex** — `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Note that Codex
  `input_tokens` *includes* `cached_input_tokens`, unlike Claude Code, where the
  fields are disjoint. Codex records no parent link; attribute child runs by `cwd`
  and time window.
- **opencode** — `~/.local/share/opencode/opencode.db`, table `session`, which
  carries `parent_id`, `agent`, and a `cost` column, so the controller-to-child
  link is native.

The aggregate is reported context volume, not provider billing. Plan, pricing, and
cache-rate semantics are not available from a transcript, so do not convert it to
money.

A **review round** is one root-level read-only review of a stable diff. A
re-review counts as a round only when it follows a code change made in response
to a finding.

Absolute numbers are **not comparable across harnesses**: cache semantics, models,
and system prompts differ. Keep the harness beside every total, and do not turn
transcript counters into provider billing.
