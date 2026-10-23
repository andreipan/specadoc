# Project routing configuration

`.specadoc.json` is project-owned. It extends the existing optional `root`
configuration with versioned role routing; it is not the host's installer
configuration. Updating this plugin must not rewrite it or installed model
bindings. The schema is `assets/project-config.schema.json`.

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

`root` remains optional. Old root-only files need no version and retain root
precedence (`--root`, environment, config, legacy, default). `roles` requires
`version: 1`; partial roles are supported. Unknown keys, roles, versions and
runtimes fail rather than silently falling back. Models, effort, permissions
and tools belong to installed role registries, not this JSON. No global/local
configuration layering is introduced in v1.

## Resolve and dispatch

Use a verified Python 3.11+ interpreter when routes read Codex TOML registries.
Record its command once in the handoff. Do not rediscover the same version error
for each task, and do not hard-code a machine-specific interpreter in this plugin.
Follow the host's shell prefix convention for all commands below.

To show the bindings at plan approval, run this read-only command from the checkout root:

```text
python3 <skill-root>/scripts/role_routing.py --controller-runtime <invoking-runtime> --dry-run --compact --check-cli
```

Always supply the invoking controller runtime explicitly. Never infer it from the
worker or from an environment heuristic. `roles.controller.runtime` validates
it and does not start another controller.

Per-role runtime precedence: project JSON → existing installed binding → invoking
controller. Read model and effort from the selected runtime's project registry,
not from a cheap wrapper in the controller registry. Installed registries are
`.claude/agents/<role>.md`, `.codex/agents/<role>.toml`, and
`.opencode/agents/<role>.md`. A missing target binding fails. The resolver does
not inspect live host plugin registries.

Each dispatch resolves again. There is no snapshot, fingerprint or approval to
keep in sync. When the user edits a role file or `.specadoc.json`, the next
dispatch uses the new binding. If a binding looks too weak for the change's
risk, advise which file and key to edit (`model-routing.md` → Binding advice).
Do not edit the file yourself.

- Native dispatch: use the installed native role. For managed workers and
  reviewers, pass `--controller-runtime` to `specadoc_step.py dispatch` or
  `pre-review`. It resolves the role, reports `resolved <role>
  <runtime>/<model>/<effort>`, and blocks on a broken configuration before
  writing a baseline. Delegation remains subject to host policy.
- External dispatch: use the runner directly, not a host wrapper:

```text
python3 <skill-root>/scripts/run_role.py start --role worker --controller-runtime <invoking-runtime> --prompt-file <root>/<slug>/runs/T1-brief.md --name T1
```

The runner resolves the role at launch and rejects explicit
runtime/model/effort flags that conflict with the resolved binding. It records
the binding it ran with in its run metadata. `--dry-run` prints the resolved
external command without writing or deleting anything. `--prompt-file`,
`--out-dir` and `--cwd` paths are relative to `--cwd` (default: the current
directory), not to the caller's shell.

Routing a role to a non-controller runtime in the committed `.specadoc.json` is
the project's consent to send that role's prompt and the repository to that
runtime. Do not ask again for each change or task. A confirmation prompt from
the host itself is outside Specadoc's control.

`.specadoc.json` is committed and shared, so its routes apply to everyone. Each
routed runtime's CLI must be installed wherever the project runs; the doctor
reports a missing CLI as an error.

Missing CLIs are explicit failures. Never fall back to another provider.
When `worker` and `reviewer` route to the same runtime, the doctor prints one
project-level warning. No plan field records a waiver. One-writer ownership,
bounded briefs, scope checks, read-only roles and controller verification are
unchanged.
For read-only diagnostics, run `doctor.py --controller-runtime <runtime>`.
CLI presence is not proof of successful startup, authentication or model
availability.

## Installer interoperability and legacy wrappers

A host installer may seed routing only through an explicit migration. It must
preserve existing `root`, refuse conflicting routes and modified managed roles,
retain personal model/effort overrides, offer a preview, and restore every
written file if an apply fails. Undoing an applied migration needs no journal:
the installer config is under version control, and its role registries can be
reinstalled.
For routing-enabled projects, install native roles for every supported runtime;
do not derive cheap host wrappers from this project's routing. Reinstallation
does not overwrite `.specadoc.json`.

Without a routing configuration, existing wrapper defaults remain supported.
When moving to project JSON, migrate wrappers and config together. The resolver
can read legacy `Default binding` declarations but will refuse a target registry
whose wrapper actually redirects elsewhere. A role contract is separate from
its model binding; pass the bounded role instructions for external runs just as
before.
