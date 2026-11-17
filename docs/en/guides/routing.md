# Role routing

[Русский](../../ru/guides/routing.md)

Specadoc gives work to three roles: `scout`, `worker` and `reviewer` (see
[Roles](../concepts/roles.md)). This guide tells how each role gets its
runtime, model and effort, and how you change that choice.

A role binding has four parts: the runtime, the model, the effort and the file
that supplies them. The runtime is the agent CLI that runs the role: `claude`,
`codex` or `opencode`. The workflow fixes no model. The model and the effort
always come from a role file: a project role file, or a role that the plugin
ships.

The controller runtime is the host where you started Specadoc. A role on the
controller runtime runs as a native subagent. A role on another runtime runs as
an external role through `run_role.py`.

In the commands below, `<skill-root>` is the installed `skills/specadoc`
folder. Run the commands from the root of the checkout.

## Resolution without `.specadoc.json`

If the project has no `.specadoc.json` with a `roles` key, the controller uses
the first role that exists:

1. A project role in the registry of the controller runtime:
   `.claude/agents/<role>.md`, `.codex/agents/<role>.toml` or
   `.opencode/agents/<role>.md`.
2. A registered plugin role, for example `specadoc:<role>` in Claude Code.
3. An available subagent without a registered role. The controller puts the
   portable role contract (`references/roles/<role>.md`) into the dispatch
   prompt. The contract sets the behavior, not a model.
4. No subagent capability. The controller can do scout and worker work itself.

In case 4 the controller cannot supply an independent reviewer PASS. It reports
the incomplete review gate and stops before managed completion or a normal
archive. It never uses self-review in place of the reviewer.

The Claude Code plugin ships the three roles as `agents/*.md`. Their
frontmatter sets the model alias: `haiku` for scout, `sonnet` for worker and
`opus` for reviewer. The source of these values is `scripts/claude-roles.json`.
A project role with the same name has priority.

In a project without routing, an installed legacy wrapper role can still select
another runtime (see [Migrate from older setups](#migrate-from-older-setups)).

## Project routing with `.specadoc.json`

The project owns `.specadoc.json`. You commit it, and its routes apply to
everyone who runs Specadoc in the checkout. The file selects only the runtime of
each role:

```json
{
  "version": 1,
  "roles": {
    "controller": {"runtime": "claude"},
    "scout": {"runtime": "claude"},
    "worker": {"runtime": "codex"},
    "reviewer": {"runtime": "claude"}
  }
}
```

The rules for the `roles` key:

- `roles` requires `"version": 1`.
- You can list some roles and omit others.
- Each entry has the key `runtime` only. Models, effort, permissions and tools
  belong to the role files.
- An unknown key, role, version or runtime is an error. Specadoc does not
  silently use a default in its place.
- `roles.controller.runtime` does not start a controller. It checks that you
  started Specadoc in the expected host.

For the full schema and the other keys (`root`, `verification`, `review`), see
[Configuration](../reference/config.md).

### Order of resolution

For each role, the runtime comes from the first source that gives one:

1. `roles.<role>.runtime` in `.specadoc.json`.
2. The default binding of an installed legacy wrapper role in the controller
   registry.
3. The controller runtime.

The model and the effort then come from the role file of the selected runtime:

| Runtime | Role file | Model key | Effort key | Effort values |
|---|---|---|---|---|
| `claude` | `.claude/agents/<role>.md` (frontmatter) | `model` | `effort` | `low`, `medium`, `high`, `max` |
| `codex` | `.codex/agents/<role>.toml` | `model` | `model_reasoning_effort` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra` |
| `opencode` | `.opencode/agents/<role>.md` (frontmatter) | `model` | `variant` | same as `codex` |

The resolver reads only these project files. It does not read live host plugin
registries. Thus a routed role needs a project role file in its target runtime.
A missing file, an empty or placeholder model (`<...>`), or an effort outside
the list is an error.

If the controller entry does not match the host, the resolver stops with
`controller runtime is <host>, binding expects <runtime>`. Restart in the
expected host, or edit `.specadoc.json`. The host name `claude-code` is accepted
as `claude`.

### Consent and independence

A route to a runtime other than the controller runtime is the project's consent.
Specadoc sends that role's prompt and the repository to that runtime, and it
does not ask again for each change or task. A confirmation prompt from the host
itself is outside the control of Specadoc.

Install the CLI of each routed runtime wherever the project runs. A missing
CLI is an error. Specadoc never uses another provider in its place.

We recommend a reviewer runtime that is not the worker's runtime, because two
models from the same vendor share blind spots. If `worker` and `reviewer` route to the
same runtime, the doctor prints one project-level warning.

### Python version

All Specadoc scripts need Python 3.10 or newer. The resolver needs Python 3.11
or newer to read Codex TOML role files. If `python3` on your `PATH` is older,
call a newer interpreter explicitly.

## Check the bindings

To see the bindings that a change will use, run this read-only command:

```text
python3 <skill-root>/scripts/role_routing.py --controller-runtime <runtime> --change <slug> --dry-run --compact --check-cli
```

Always give the controller runtime. Do not let anything guess it.

The output is JSON with `routes` (role, runtime, model, effort, `native` or
`external` dispatch) and `findings`. The exit code is 1 when a finding is an
`ERROR`.

`--change <slug>` limits errors to the roles that the plan uses. A plan always
uses the reviewer. It uses the worker when a task has `Owner: worker`. A broken
file of an unused role gives a warning only. `--check-cli` also checks that each
runtime's CLI is on `PATH`.

For a project-wide check, run:

```text
python3 <skill-root>/scripts/doctor.py --controller-runtime <runtime>
```

A CLI on `PATH` does not prove that it starts, that it is signed in, or that the
model is available.

### Bindings at plan approval

The plan preview shows one line per role (controller, scout, worker, reviewer)
with runtime, model, effort and source file. A design PASS writes this line to
`Bindings shown` in `plan.md`. The line is evidence of the bindings that will run. It is not
an approval of a binding. In a light change the controller shows the controller
and reviewer bindings in chat.

If a binding does not fit the risk of the change, the preview adds one advice
line. An example is a high-risk change with a reviewer on a small model or a
low effort. The line names the exact file and key to edit. Specadoc does not
edit that file, block on the advice, or record it as an approval. You edit the
file or continue as is.

## Re-resolution at every dispatch

Specadoc keeps no snapshot, fingerprint or approval of a binding. Each dispatch
resolves the role again. Thus an edit to a role file or to `.specadoc.json`
applies to the next dispatch.

In a routed project, the controller passes `--controller-runtime` to
`specadoc_step.py dispatch` and `pre-review`. These steps print
`resolved <role> <runtime>/<model>/<effort>`. A broken configuration stops them
before they write a baseline. If `--controller-runtime` is absent, the steps use
`roles.controller.runtime` and say so.

## Roles on another runtime

`run_role.py` starts a role on another runtime's CLI and collects its result.
The controller uses it when the role runtime is not the controller runtime.

In a routed project, run it with `--controller-runtime`:

```text
python3 <skill-root>/scripts/run_role.py start --role worker --controller-runtime <runtime> --prompt-file <root>/<slug>/runs/T1-brief.md --name T1
python3 <skill-root>/scripts/run_role.py wait <run-file> --timeout 540 --shell-budget 590 --follow
python3 <skill-root>/scripts/run_role.py result <run-file>
```

The runner resolves the role at launch. It refuses an explicit `--runtime`,
`--model` or `--effort` that conflicts with the resolved binding. It records
the binding in the run file. Without routing, give `--runtime`, `--model` and
`--effort` explicitly.

| Command | What it does |
|---|---|
| `start` | Starts the CLI in the background and returns the run file at once. `--dry-run` prints the command and writes nothing. |
| `status <run-file>` | Shows running, completed, failed or no-progress, with the role status and the elapsed time. |
| `wait <run-file>` | Blocks for at most `--timeout` seconds. `--follow` prints a progress line every 45 seconds by default. |
| `result <run-file>` | Checks the final JSON against the role schema and saves it. |
| `stop <run-file>` | Stops a run that you abandon. |

The run files go to the directory of the prompt file, usually `runs/` of the
change. The paths for `--prompt-file`, `--out-dir` and `--cwd` are relative to
`--cwd`.

Exit codes:

- `wait` returns 3 when the timeout expires and the role still runs. This is not
  a failure. Wait again on the same run.
- `start` returns 4 (`sandboxed:`) when the runtime cannot start inside the
  sandbox of the shell. Run the same command outside the sandbox with the host's
  escalation, and cite the routing.
- `result` returns 1 when the CLI failed or the JSON does not match the schema.
  Read the log that the run file names before you retry.
- Any command returns 2 on a usage or configuration error.

If your shell tool has a time limit, set it above `--shell-budget`. If you
cannot raise it, wait in shorter slices, for example
`--timeout 110 --shell-budget 120`.

A start with the same name and the same invocation reuses the existing run. A
changed prompt or binding needs a new name.

### What an external role gets

| Runtime | How the runner starts it |
|---|---|
| `codex` | `codex exec`. The worker gets `-s workspace-write` with loopback network. Scout and reviewer get `-s read-only`. |
| `claude` | `claude -p` with `--json-schema`. The worker gets edit tools. Scout and reviewer get `Read, Grep, Glob, Bash`. |
| `opencode` | `opencode run --standalone --format json --auto` with a dedicated primary agent. Scout and reviewer get read and search tools and read-only `git` commands. |

An OpenCode scout or reviewer also gets the shell commands that the installed
role file allows: the `action: shell`, `effect: allow` entries of its
`permissions` list. These are tool permissions, not an OS sandbox.

An external role does not share the MCP servers or the context of the
controller. Name the exact files in its brief.

For a worker, the controller wraps the run in the file-based handoff:
`specadoc_step.py dispatch` before `start`, and `specadoc_step.py accept` after
`result`. See [Scripts](../reference/scripts.md) for the full list of steps.

## The tooling block in role files

Each shipped role contract has one block between
`<!-- specadoc:tooling:begin -->` and `<!-- specadoc:tooling:end -->`. The block
holds neutral advice on lookup tools. For example, the scout uses a
symbol-aware or code-graph tool when the runtime has one, and bounded `rg`
searches otherwise.

If your host generates its own role files, you can replace only this block with
your own tool advice. Keep the rest of the role and its report format.

The portable contracts in `skills/specadoc/references/roles/` are the source.
The Claude files in `agents/*.md` are generated from them by
`scripts/render_roles.py`. The Claude metadata lives in
`scripts/claude-roles.json` and does not bind Codex models.

## Change a binding

To change the model or the effort of a role:

1. Find the source file in the bindings line or in the output of `role_routing.py`.
2. Edit `model` or the effort key in that file.
3. Run `role_routing.py` again to check the result.

The next dispatch uses the new values. A model change for the controller costs
least at a session boundary, because the prompt cache belongs to one model.

To move a role to another runtime:

1. Install the target runtime's CLI wherever the project runs.
2. Install a role file for the role in the target runtime's registry.
3. Set `roles.<role>.runtime` in `.specadoc.json`. If `version` is absent, add `"version": 1`.
4. Run `role_routing.py` with `--check-cli`.
5. Commit `.specadoc.json`, because the route applies to everyone.

## Migrate from older setups

An update of the plugin does not rewrite `.specadoc.json` or your role files.

A root-only `.specadoc.json` (`{"root": "<path>"}`) stays valid and needs no
`version`. When you add `roles`, add `"version": 1`.

A legacy wrapper role contains a line of this form:

```text
Default binding: runtime `codex`, model `<model>`, effort `<effort>`
```

Without `roles` in `.specadoc.json`, the wrapper's default binding still
applies. A `Runtime:` line in the dispatch prompt overrides the wrapper's
default.

When you move to project routing, migrate the wrappers and the configuration
together:

1. In each runtime that a route selects, replace each wrapper with a native role
   file. A native role file has the model and effort keys.
2. Add the `roles` entries to `.specadoc.json`.
3. Run `role_routing.py` to check the result.

The resolver refuses a target role file whose wrapper points to another
runtime: `wrapper points to <runtime>, not <runtime>; migrate to native roles`.

Older plans can contain fields that Specadoc no longer uses: a model
checkpoint, snapshots and fingerprints of bindings, and per-round independence
waivers. These plans still pass every gate. You do not need to edit them.

A host installer can seed routing only through an explicit migration. The
migration must keep the existing `root`, refuse conflicting routes and modified
managed roles, and keep personal model and effort overrides. It must offer a
preview and restore every written file if the apply fails. For a routed project
it installs native roles for every supported runtime.
