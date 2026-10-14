# Role runtimes and external runners

Load this reference only when a role's runtime differs from the harness the
controller runs in, or when the plan records a per-change runtime override.

## Runtime binding

Each role (`scout`, `worker`, `reviewer`) runs on a **runtime**: the agent CLI
that executes it (`claude`, `codex`, or `opencode`). The controller's runtime
is the harness that invoked Specadoc. A role whose runtime equals the
controller's runs natively as a subagent; any other runtime runs as an
**external** role through `scripts/run_role.py`.

Resolve each role's runtime and model in this order, first match wins:

1. The plan's `## Model handoff` → `Scout runtime`, `Worker runtime`,
   `Reviewer runtime` (`<runtime>/<model>`), approved at the model checkpoint.
2. The role registry (`model-routing.md` → Role registry). A host may install a
   thin wrapper role that already calls `run_role.py` for its configured
   runtime; a `Runtime:` line in the dispatch prompt overrides the wrapper's
   default.
3. The controller's own runtime.

Record the resolved values in `## Model handoff` before the first dispatch.
Specadoc names no models: the registry or the user supplies them.

## Independence

The final reviewer should not run on the worker's runtime: two models from the
same vendor share blind spots. When they match, the latest `### G<n>` block
needs `**Independence waiver:** <reason>`; `validate_change.py --phase
pre-review` enforces this when both runtimes are recorded.

## External run contract

Input, all paths repository-relative:

- the prompt file: `runs/T<n>-brief.md` from `task_brief.py` for a worker, or a
  written dispatch prompt (`runs/G<n>-review.md`, `runs/S<n>-scout.md`) for the
  other roles, following the examples in `subagent-routing.md`;
- the role's result schema `assets/<role>-result.schema.json`;
- the working directory: the repository root of the current checkout.

Rules the prompt and the runner enforce:

- one external writer at a time, and no controller edits while it runs;
- scout and reviewer run read-only; the worker may write the working tree;
- no commits, branch switches, stashes, resets, or nested agents;
- nothing under the artifact root changes except files in the change's `runs/`.

Output: the final message is JSON matching the role's schema; a worker also
writes its full report to `runs/T<n>-report.md`.

## Running it

```text
python3 <skill-root>/scripts/run_role.py start --role worker --runtime <runtime> \
  --model <model> --effort <effort> --prompt-file <root>/<slug>/runs/T<n>-brief.md --name T<n>
python3 <skill-root>/scripts/run_role.py wait <run-file> --timeout 540   # exit 3: still running, wait again
python3 <skill-root>/scripts/run_role.py result <run-file>
```

`start` returns immediately with the run file; `wait` blocks for at most the
timeout, so a shell tool with a per-command limit waits in slices. `result`
exits 1 when the CLI failed or the JSON breaks the schema; read the log named
in the run file before retrying, and never resend an unchanged prompt. Use
`stop <run-file>` to abandon a run.

For a worker, wrap the run in the file-based handoff of `subagent-routing.md`:
`baseline` before `start`, `check-scope` and your own Verification after
`result`. Status handling is the same as for a native worker.

## Runtime notes

- `codex`: `codex exec` with `-s workspace-write` for the worker (loopback
  network enabled so tests can reach a local database) and `-s read-only` for
  scout and reviewer; `--output-schema` enforces the result shape.
- `claude`: `claude -p` with `--json-schema`; the worker gets edit tools with
  `acceptEdits`, read-only roles get `Read, Grep, Glob, Bash` with `dontAsk`.
- `opencode`: V2 `opencode run --standalone --format json --auto`, with
  `provider/model#effort` and a dedicated primary agent (not the installed role
  wrapper). Scout/reviewer permit only read/search/web/skill tools and the shell
  commands `git diff|log|show|status`, without redirection, `--output` or
  `--ext-diff`; edits, other commands, MCP tools and nested agents are denied.
  Worker additionally permits edit and any shell command.
  These are tool permissions, not an OS sandbox. The schema is appended to the
  prompt and the final text JSON is validated locally, not by the provider.

An external role does not share the controller's MCP servers or its context.
Name exact files in the brief; it falls back to its own tools and `rg`.
