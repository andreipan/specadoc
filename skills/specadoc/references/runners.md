# Role runtimes and external runners

Load this reference only when a role's runtime differs from the harness the
controller runs in.

## Runtime binding

Each role (`scout`, `worker`, `reviewer`) runs on a **runtime**: the agent CLI
that executes it (`claude`, `codex`, or `opencode`). The controller's runtime
is the harness that invoked Specadoc. A role whose runtime equals the
controller's runs natively as a subagent; any other runtime runs as an
**external** role through `scripts/run_role.py`.

Resolve each role's runtime and model in this order, first match wins:

1. Project `.specadoc.json` routing, resolved by `scripts/role_routing.py`.
   Read `project-config.md` when `roles` is present. Model and effort come from
   the selected runtime's registry, not the current harness's wrapper model.
2. The role registry (`model-routing.md` → Binding resolution). A host may install a
   thin wrapper role that already calls `run_role.py` for its configured
   runtime; a `Runtime:` line in the dispatch prompt overrides the wrapper's
   default.
3. The controller's own runtime.

Specadoc names no models: the registry or the user supplies them. Nothing is
frozen or approved. Each dispatch resolves again, and with project routing it
uses `run_role.py --controller-runtime ...` (`project-config.md`). The explicit
flags below remain for projects without routing.

## Independence

The final reviewer should not run on the worker's runtime, because two models
from the same vendor share blind spots. This is a project-level choice in
`.specadoc.json`. The doctor warns once when `worker` and `reviewer` share a
runtime, and no review round records a waiver.

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
python3 <skill-root>/scripts/run_role.py wait <run-file> --timeout 540 --follow   # exit 3: still running, wait again
python3 <skill-root>/scripts/run_role.py result <run-file>
```

`start` returns immediately with the run file; `wait` blocks for at most the
timeout, so a shell tool with a per-command limit waits in slices. `result`
exits 1 when the CLI failed or the JSON breaks the schema; read the log named
in the run file before retrying, and never resend an unchanged prompt. Use
`stop <run-file>` to abandon a run.

Use `--follow` for every wait: it prints one progress line every `--interval`
seconds (default 45): elapsed time, and for OpenCode the tool-call count and last
tool; for the other runtimes the log size. Relay each line to the user as a short
progress note, so a long run never looks stopped.

A launched run is not a result. The controller stays in its turn and keeps calling
`wait --follow` until the run finishes, or ends the turn only with a real blocker or
a necessary user decision. Claude Code can run `wait --follow` with
`run_in_background` and is woken when it exits; Codex and OpenCode have no such
wake-up, so they must keep waiting in the foreground.

Routing a role to an external runtime in the committed `.specadoc.json` is the
project's consent to send it code. Do not ask for each change or task. A
confirmation prompt from the host itself (for example the Codex approval policy)
is not controlled by Specadoc.

For a worker, wrap the run in the file-based handoff of `subagent-routing.md`:
`specadoc_step.py dispatch` before `start`, `specadoc_step.py accept --verify`
after `result`. Status handling is the same as for a native worker.

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
  prompt and the final text JSON is validated locally, not by the provider. A reply
  wrapped in a code fence or surrounded by prose is accepted: the last JSON object
  is used. `start` fails at once with a clear error when OpenCode cannot write its log
  (`~/.local/share/opencode/log`), which happens inside a sandboxed shell; start it
  from a shell with write access to that path.
  An OpenCode session title may be junk (result-like JSON or reasoning text), because a
  title request runs on the same agent. Never read a status from a session title:
  the run result is only the validated JSON from `run_role.py result`.

An external role does not share the controller's MCP servers or its context.
Name exact files in the brief; it falls back to its own tools and `rg`.
