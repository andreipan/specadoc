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

## Resolve, approve, dispatch

Use a verified Python 3.11+ interpreter when routes read Codex TOML registries;
record its command once in the handoff. Do not rediscover the same version error
per task or hard-code a machine-specific interpreter in this plugin.
Follow the host's shell prefix convention for all commands below.

Before the model checkpoint run this read-only command from the checkout root:

```text
python3 <skill-root>/scripts/role_routing.py --controller-runtime <invoking-runtime> --dry-run --check-cli
```

For an existing approved change, add `--plan <root>/<slug>/plan.md`. The invoking
controller runtime must be supplied explicitly, never inferred from the worker
or an environment heuristic. `roles.controller.runtime` validates it, not starts
another controller. An approved `**Controller runtime:** <runtime>` in Model
handoff can override this expectation; it still must match the invoking host.

Per-role runtime precedence: approved plan override → project JSON → existing
installed binding → invoking controller. Read model/effort from the selected
runtime's project registry, not from a cheap wrapper in the controller registry.
Installed registries are `.claude/agents/<role>.md`, `.codex/agents/<role>.toml`,
and `.opencode/agents/<role>.md`. Runtime/model in the approved handoff overrides
that model; optional `**Worker effort:** <effort>` (likewise Scout/Reviewer)
overrides effort. Missing target bindings fail; a complete approved plan binding
can supply model and effort when no file-backed registry exists. The resolver
does not inspect live host plugin registries: a plugin-only binding must be
recorded and approved in the plan, not invented. Without this configuration,
the existing host/plugin registry fallback remains supported by the controller.

The JSON result includes source paths, registry hashes and binding fingerprints.
Present the resolved runtime/model/effort and their sources at the checkpoint.
After user approval, save that exact result to
`<root>/<slug>/runs/model-bindings.json` (or a temporary file for direct). Do not
regenerate an approved snapshot silently. Record the selected runtime/model,
effort, sources and snapshot path in Model handoff (direct: chat). Merely running
the resolver or creating a snapshot is not user approval.

- Native dispatch: use the installed native role. For managed workers/reviewers,
  pass `--controller-runtime` and `--binding-file` to `specadoc_step.py dispatch`
  or `pre-review`; it checks the fresh fingerprint before writing a baseline.
  For direct/scout dispatch use `role_routing.py --role <role> --binding-file
  <approved-json> --compact --check-cli` with the same controller/plan arguments.
  Changed bindings require new approval. Delegation remains subject to host policy.
- External dispatch: use the runner directly, not a host wrapper:

```text
python3 <skill-root>/scripts/run_role.py start --role worker --controller-runtime <invoking-runtime> --plan <root>/<slug>/plan.md --binding-file <root>/<slug>/runs/model-bindings.json --prompt-file <root>/<slug>/runs/T1-brief.md --name T1
```

Omit `--plan` for direct. The runner re-resolves and checks the fingerprint,
rejects conflicting explicit runtime/model/effort flags, requires the approved
snapshot for a real routed launch, and records the binding in its run metadata.
`--dry-run` prints the resolved external command without writing or deleting
anything; it does not launch or approve a role. `--prompt-file`, `--out-dir`,
`--plan` and `--binding-file` are relative to `--cwd` (default: the current
directory), not to the caller's shell.

Resolve full JSON once for the checkpoint; use `--compact` for human-facing
revalidation, not repeated configuration dumps. The runner already checks
external bindings at launch: do not precede each launch with a full dry-run.
No cache may replace fresh validation. Keep full resolver JSON as the approval
artifact; a successful check is not authentication evidence.

The fingerprint covers the whole project config and the target registry, so it
includes personal models. An approved snapshot belongs to whoever approved it.
Another checkout or teammate with different installed roles gets a mismatch and
must resolve the binding and get approval again. That mismatch is intended, not
corruption.

`.specadoc.json` is committed and shared, so its routes apply to everyone. Each
routed runtime's CLI must be installed wherever the project runs; the doctor
reports a missing CLI as an error.

Missing CLIs are explicit failures. Never fall back to another provider.
Reviewer independence, waiver validation, one-writer ownership, bounded briefs,
scope checks, read-only roles and controller verification are unchanged.
For read-only diagnostics, run `doctor.py --controller-runtime <runtime>`;
add `--plan` for per-change overrides. CLI presence is not proof of successful
startup, authentication or model availability.

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
