# Configuration

[Русский](../../ru/reference/config.md)

This page describes the project file `.specadoc.json`, the artifact root
resolution and the configuration that external role runs read. To route roles to
runtimes step by step, read [Routing](../guides/routing.md).

In the commands below, `<skill-root>` is the installed `skills/specadoc` folder.

## .specadoc.json

`.specadoc.json` is a JSON file in the repository root. The project owns it.
Commit it: its configuration applies to everyone who runs Specadoc in the repository.
The file is optional. Without it, all defaults below apply.

The JSON schema is
[`assets/project-config.schema.json`](../../../skills/specadoc/assets/project-config.schema.json).
The scripts read the file from the current directory, so run them from the
repository root.

An update of the plugin never rewrites this file. A reinstall of the plugin
does not overwrite it.

A full example:

```json
{
  "version": 1,
  "root": "docs/specadoc",
  "roles": {
    "controller": {"runtime": "claude"},
    "scout": {"runtime": "claude"},
    "worker": {"runtime": "codex"},
    "reviewer": {"runtime": "claude"}
  },
  "verification": {
    "environment": ["PATH", "APP_*"],
    "external_only": ["<integration suite config>"],
    "final": ["<suite command>", "<gates command>"],
    "probe": ["<command that reaches the test database>"]
  },
  "review": {"tidy": "required"}
}
```

The values in angle brackets are placeholders. Replace them with the commands
of your project.

### Keys

| Key | Type | Default | Meaning |
|---|---|---|---|
| `$schema` | string | none | A schema reference for editors. The scripts ignore it. |
| `version` | integer, only `1` | none | The config version. Required when `roles` is present. |
| `root` | non-empty string | resolved, see [Artifact root](#artifact-root) | The artifact root, relative to the repository root. |
| `roles` | object | none | The runtime of each role. |
| `roles.<role>.runtime` | `claude`, `codex` or `opencode` | see [Role binding resolution](#role-binding-resolution) | The runtime that runs the role. `<role>` is `controller`, `scout`, `worker` or `reviewer`. |
| `verification.environment` | list of strings | all variables except a fixed list | Names or globs of the variables that verification depends on. |
| `verification.external_only` | list of strings | none | Command fragments that only an external executor runs. |
| `verification.final` | list of strings | none | The whole suite and gates, run once before the first review. |
| `verification.probe` | list of strings | none | Quick commands that `doctor.py --probe` runs. |
| `review.tidy` | `required` or `optional` | `optional` | Whether a tidy pass is mandatory before the first initial review. |
| `context.phase_boundary` | integer, at least 20000 | `120000` | Context at which `status` advises a fresh session before worker dispatch. |
| `context.review_boundary` | integer, at least 20000 | `160000` | Context at which `status` advises a fresh session before a review round. |
| `context.dispatch_guard` | integer, at least 20000 | `200000` | Context at which `dispatch` and `design-brief` refuse. |

Each list item must be a non-empty string. Each role object has only the key
`runtime`. Models, effort, permissions and tools do not go in this file. They
belong to the installed role files (see
[Role files](#role-files)).

### Validation rules

- An unknown key, role, version or runtime is an error. The scripts do not fall
  back to a default.
- `roles` without `"version": 1` is an error.
- A file with `root` only needs no `version`.
- The schema has no layers. There is no global or local config file.

A script that cannot read the file stops with the message
`.specadoc.json: cannot read Specadoc config: <reason>`.

### roles

Each role gets a runtime. Partial roles are allowed: a role without an entry
uses the next source in the resolution order.

`roles.controller.runtime` does not start a controller. It only checks the
runtime of the controller that runs. If they differ, routing stops with
`controller runtime is <actual>, binding expects <expected>`.

A committed route to a runtime other than the controller's is the project's
consent. Specadoc then sends that role's prompt and the repository to that
runtime without a new question for each change or task. A confirmation prompt
of the host itself is outside the control of Specadoc.

Install the CLI of each routed runtime wherever the project runs. The doctor
reports a missing CLI as an error. Specadoc never falls back to another
provider. When `worker` and `reviewer` use the same runtime, the doctor gives
one warning.

### verification.environment

Accepted evidence is reused only while the environment digest is the same.
The digest stores a short hash of each variable, never the value.

Without this key, the digest covers every variable except a fixed list. The
list contains these patterns:
`PWD`, `OLDPWD`, `SHLVL`, `_`, `TMPDIR`, `*_TMPDIR`, `TMPPREFIX`,
`SSH_AUTH_SOCK`, `XPC_SERVICE_NAME`, `XPC_FLAGS`, `*PROXY*`, `*SESSION_ID`,
`*SESSIONID`, `*_THREAD_ID`, `*_PID`, `*_SOCKET`, `*_TOKEN`.

With this key, only the listed names and globs count. Other variables never
make evidence stale. If a new session reports `environment changed: <names>`,
list only the variables that verification depends on.

```json
{"version": 1, "verification": {"environment": ["PATH", "APP_*"]}}
```

### verification.external_only

List a fragment that identifies each command that only an external executor
can run, for example the config file name of an integration suite.

`validate_change.py --phase plan` and `dispatch` refuse a task whose
`Verification` contains such a fragment. Put a local static check in
`Verification` and name the real run in `External verification:`.

```json
{"version": 1, "verification": {"external_only": ["<integration suite config>"]}}
```

### verification.final

The commands that the controller runs once before the first review: the whole
suite and the repository gates.

With this key, `specadoc_step.py finalize <slug> --run` runs the commands and
records the exit codes with the Review scope snapshot.
`validate_change.py --phase final` then refuses a missing, failed or stale
record. A record is stale when code changed after the run.

Without this key, the controller runs the commands itself and records them with
`finalize <slug> --observed '<run>'`.

```json
{"version": 1, "verification": {"final": ["<suite command>", "<gates command>"]}}
```

### verification.probe

Quick commands that prove that the shell reaches what verification needs, for
example one query against the test database. `doctor.py --probe` runs each
command. Each command must exit with 0 within 60 seconds.

```json
{"version": 1, "verification": {"probe": ["<command that reaches the test database>"]}}
```

### review.tidy

With `required`, `pre-review` refuses the first `initial` round until
`specadoc_step.py tidy <slug>` records one pass over the Review scope.
Re-reviews never need another pass. With `optional`, the tidy pass is an
opt-in REFACTOR companion.

```json
{"version": 1, "review": {"tidy": "required"}}
```

### context

The controller context boundaries, in tokens. The defaults weigh the cost of
re-reading a long context on every call against a fresh session, which needs
60–100k before its first step. Set them for a model with another window or
price; each key is optional.

```json
{"version": 1, "context": {"phase_boundary": 120000, "review_boundary": 160000, "dispatch_guard": 200000}}
```

### Host configuration in Verification

Do not put a host or sandbox setting in a task's `Verification`. A command that
starts with `NAME=value` or `env` fixes one session's runtime into the plan.
Another session, sandbox or the validator then runs it differently.

Configure the runtime once for every session, for example in an interpreter
config file that the runtime always loads. Then write the bare command.
`validate_change.py --phase plan` warns about such a prefix.

## Artifact root

The artifact root holds all Specadoc files of a repository. The default is
`docs/specadoc`.

The scripts resolve the root in this order. The first match wins.

1. The `--root <path>` flag of the script.
2. The `SPECADOC_ROOT` environment variable.
3. The `root` key of `.specadoc.json`.
4. The legacy root `docs/agent`, when it exists and `docs/specadoc` does not.
5. The default `docs/specadoc`.

`doctor.py` and `init_change.py` print the resolved root and its source.

### --root

Most scripts accept `--root`. The value is relative to the repository root. For
`specadoc_step.py`, put `--root` before the step name:

```bash
python3 <skill-root>/scripts/specadoc_step.py --root docs/changes status my-change
```

### SPECADOC_ROOT

Set this variable to change the root for one shell without a change to the
repository. A blank value is ignored.

```bash
SPECADOC_ROOT=docs/changes python3 <skill-root>/scripts/doctor.py
```

### Legacy docs/agent

Older projects used `docs/agent`. A script uses it only when `docs/specadoc`
does not exist. Each script then prints a warning on stderr.

To move the legacy root:

1. Run `python3 <skill-root>/scripts/migrate_root.py` and read the dry-run
   output.
2. Run `python3 <skill-root>/scripts/migrate_root.py --apply`.

The script moves the folder with `git mv` in a git work tree. It rewrites each
literal `docs/agent/` in the moved Markdown files to `docs/specadoc/`. Use
`--from` and `--to` for other paths. See
[Scripts](scripts.md#migrate_rootpy).

## Role binding resolution

A role binding is the runtime, model and effort that serve a role. Each
dispatch resolves the binding again. Specadoc keeps no snapshot and no approval
of a binding. If you edit a role file or `.specadoc.json`, the next dispatch
uses the new binding.

The runtime of each role comes from the first source that applies:

1. `roles.<role>.runtime` in `.specadoc.json`.
2. An installed legacy wrapper in the controller's role file (see
   [Legacy wrappers](#legacy-wrappers)).
3. The runtime of the invoking controller.

The model and effort always come from the role file of the selected runtime.
A missing or invalid target role file is an error.

To show the bindings of a change, run:

```text
python3 <skill-root>/scripts/role_routing.py --controller-runtime <runtime> --change <slug> --dry-run --compact --check-cli
```

Always give the runtime of the invoking controller explicitly.

When no routing config exists and no project role file exists, the controller
uses a registered plugin role (for example `specadoc:<role>` in Claude Code).
If that also does not exist, it uses a subagent with the portable role contract
from `references/roles/<role>.md`.

## External runner settings

A role whose runtime differs from the controller's runtime runs through
`run_role.py`. This section lists the files and variables that it reads. The
command flags are in [Scripts](scripts.md#run_rolepy).

### Role files

| Runtime | Role file | Model key | Effort key |
|---|---|---|---|
| `claude` | `.claude/agents/<role>.md` (front matter) | `model` | `effort` |
| `codex` | `.codex/agents/<role>.toml` | `model` | `model_reasoning_effort` |
| `opencode` | `.opencode/agents/<role>.md` (front matter) | `model` | `variant` |

The effort value must be one of these values:

| Runtime | Allowed effort values |
|---|---|
| `claude` | `low`, `medium`, `high`, `max` |
| `codex`, `opencode` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra` |

A model value that is empty or starts with `<` is invalid. A Codex role file
needs Python 3.11 or newer, because the resolver reads TOML.

### Legacy wrappers

A legacy role file can contain this line:

```text
Default binding: runtime `<runtime>`, model `<model>`, effort `<effort>`
```

The resolver reads it only when `.specadoc.json` has no route for the role. It
refuses a wrapper that points to a runtime other than the resolved one. When you
change to project routing, move wrappers and `.specadoc.json` together.

### OpenCode read permissions

For `scout` and `reviewer` on OpenCode, the runner allows read, search, web and
skill tools. It also allows the shell commands `git diff`, `git log`,
`git show` and `git status`.

To allow more shell commands, add entries to the `permissions` list in the
front matter of `.opencode/agents/<role>.md`. Use one `key: value` per line:

```yaml
permissions:
  - action: shell
    resource: <command> *
    effect: allow
```

The runner takes only entries with `action: shell` and `effect: allow`. A
resource must start with a command word. A resource that starts with `*` is
ignored. Redirection, `--output`, `--ext-diff` and `--pre` stay denied.

If a host plugin adds a prefix to shell commands, list the prefixed forms.
OpenCode checks a command after plugins rewrite it.

### Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `SPECADOC_ROOT` | all artifact scripts | The artifact root. |
| `CODEX_HOME` | `run_role.py` | The Codex home. Default: `~/.codex`. `start` exits with 4 if it cannot write there. |
| `XDG_DATA_HOME` | `run_role.py` | The base of the OpenCode log, `opencode/log/opencode.log`. Default: `~/.local/share`. `start` exits with 4 if it cannot write the log. |
| `OPENCODE_CONFIG_CONTENT` | `run_role.py` | An existing OpenCode config. The runner adds its own agent `specadoc-external` to it. |
| `CLAUDE_CONFIG_DIR` | `collect_tokens.py`, `reviewer_reply.py` | The Claude Code config folder with the transcripts. Default: `~/.claude`. |
| `CLAUDE_CODE_SESSION_ID` | `specadoc_step.py`, `collect_tokens.py` | The current Claude Code session. Steps record it in `runs/sessions.json` for token collection. |

`run_role.py` removes `CLAUDE_CODE_SESSION_ID` from the environment of the role
process. The role is a separate session.

### Runtime commands

| Runtime | Command | Writer (`worker`) | Read-only roles |
|---|---|---|---|
| `codex` | `codex exec --json --ephemeral` with `--output-schema` | `-s workspace-write`, loopback network on | `-s read-only` |
| `claude` | `claude -p` with `--json-schema`, `--strict-mcp-config`, `--no-session-persistence` | edit tools, `acceptEdits` | `Read, Grep, Glob, Bash`, `dontAsk` |
| `opencode` | `opencode run --standalone --format json --auto` with model `provider/model#effort` | edit and any shell command | the read permissions above |

An external role does not share the controller's MCP servers or context. Name
the exact files in the brief.
