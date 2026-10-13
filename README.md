# Specadoc

An explicit engineering lifecycle for coding agents: **explore → propose →
apply → archive**. Specadoc keeps a stable behavioral contract (`spec.md`) apart
from mutable execution state (`plan.md`), gates each phase with deterministic
checks, and routes work to three bounded roles:

| Role | Level | Job |
|---|---|---|
| `scout` | EASY | One bounded, read-only investigation; returns a fixed report. |
| `worker` | MEDIUM | One fully specified, low-decision task, test-first. |
| `reviewer` | HIGH | Independent read-only review of the final diff against the spec. |

The controller (your main agent session) owns requirements, architecture,
approvals and final verification. Specadoc runs only when you invoke it
explicitly; it never takes over ordinary coding work.

## Modes

- `specadoc explore <request>`: facts and stress-testing, no files.
- `specadoc propose <request|slug>`: writes `docs/specadoc/<slug>/spec.md` and
  `plan.md` and stops at the model and plan checkpoints.
- `specadoc apply <slug>`: TDD implementation, bounded workers, controller
  verification, final reviewer.
- `specadoc archive <slug>`: compacts a finished change into
  `docs/specadoc/archive/<slug>/record.md` (≤ 16 KiB).

## Install

### Claude Code (plugin)

```bash
claude plugin marketplace add <git-url-or-local-path-of-this-repo>
claude plugin install specadoc@specadoc
```

The skill is invoked as `/specadoc:specadoc`. The roles are available as
`specadoc:scout`, `specadoc:worker` and `specadoc:reviewer`. For a single
session from a checkout, run `claude --plugin-dir <path>`.

### Codex plugin (local marketplace)

This checkout includes a portable root `plugin.json` and a repo marketplace at
`.agents/plugins/marketplace.json`. The plugin is version **0.1.1** and installs
all four skills. No MCP, authentication, lifecycle hooks, project agent files,
or automatic host configuration is required. Python 3.9+ is needed to run the
lifecycle helpers. Installing a plugin does not install Python.

From an isolated test project, with a separate `CODEX_HOME` for a pilot:

```bash
codex plugin marketplace add /absolute/path/to/specadoc
codex plugin add specadoc@specadoc
codex plugin list
```

You can also select Specadoc in the desktop plugin directory after adding the
marketplace. Start a new chat and explicitly select the installed
`specadoc:specadoc` skill (`$specadoc:specadoc` when supported); plain skill
installations use `specadoc`. Ask for `explore`, `propose`, `apply` or `archive`.
Specadoc has `allow_implicit_invocation: false`; companion skills keep their
own discovery rules and are optional within the lifecycle.

Do not install alongside a symlink/copy of the same skills in a pilot project.
The installed cache copy, not the source checkout, supplies runtime resources.
An embedded role contract is not a registered agent or a model configuration:
project profiles win; otherwise pass the contract to an available, permitted
subagent. With no independent reviewer, managed review remains incomplete —
the controller cannot claim an independent PASS.

After changing the local source, remove and reinstall in the isolated pilot,
then start a new chat and check the cache copy:

```bash
codex plugin remove specadoc@specadoc
codex plugin add specadoc@specadoc
```

`codex plugin marketplace upgrade` refreshes Git-backed sources only; it does not
refresh a local directory. After checking the reinstalled cache, clean up with:

```bash
codex plugin remove specadoc@specadoc
codex plugin marketplace remove specadoc
```

CLI/plugin availability varies by host version. Apply your repository's command
prefix to these examples when required; do not change global configuration just
to perform a smoke test.

### Plain skills (Codex CLI and OpenCode)

Both read Agent Skills folders. Link or copy the skill folder:

```bash
ln -s <repo>/skills/specadoc <project>/.agents/skills/specadoc     # Codex
ln -s <repo>/skills/specadoc <project>/.opencode/skills/specadoc   # OpenCode
```

Link companion skills (below) the same way, one folder per skill.

The portable role contracts are in `skills/specadoc/references/roles/`. Existing
Codex/OpenCode project roles take precedence; otherwise include the relevant
contract in a permitted subagent's prompt. Scout/worker work may fall back to
the controller, but independent review cannot. No agent configuration is
written automatically.

## Companion skills

Standalone, opt-in skills that Specadoc uses when installed and that also work
without it:

| Skill | Use |
|---|---|
| `tidy` | Behavior-preserving cleanup in REFACTOR, before final verification and review. |
| `codebase-design` | Controller decision on an unresolved interface or seam. |
| `domain-modeling` | Ambiguous terms, states and invariants during clarification. |

Install only the ones a project needs. As a Claude Code plugin, every folder in
`skills/` is available as `specadoc:<name>`; descriptions keep them from loading
until a task matches.

## Roles and overrides

Specadoc resolves each role in this order (see
`skills/specadoc/references/model-routing.md`):

1. a project role: `.claude/agents/<role>.md`, `.codex/agents/<role>.toml`, or
   `.opencode/agents/<role>.md`;
2. a registered plugin role (for example Claude's `specadoc:<role>`);
3. a permitted available subagent given the bundled portable contract;
4. no subagents: bounded controller scout/worker work, incomplete independent
   review gate (never a self-reviewed PASS).

Portable contracts are canonical; the checkout's Claude `agents/*.md` files are
generated adapters. Edit the contract, then run `python3 scripts/render_roles.py`.
The checker refuses stale adapters. Claude-specific model/tool metadata lives
separately in `scripts/claude-roles.json`; it does not bind Codex models.

Each shipped role has a block between `<!-- specadoc:tooling:begin -->` and
`<!-- specadoc:tooling:end -->`. That block holds neutral tool guidance. Hosts
that generate their own roles can replace only that block, for example with
IDE-MCP or code-graph tooling, and keep the rest of the role and its report
format unchanged.

## Host conventions

Examples use bare commands such as `python3 <skill-root>/scripts/...`.
`<skill-root>` is this skill's directory (`${CLAUDE_SKILL_DIR}` in Claude Code).
If your repository requires a command prefix, a memory protocol or a harness
instruction file, Specadoc treats it as a repository instruction (see
`references/interoperability.md`).

## Scripts

Lifecycle scripts use only the Python standard library (Python 3.9 or newer).
They use the project's artifact root: `--root`, else `$SPECADOC_ROOT`,
else `.specadoc.json` (`{"root": "<path>"}`), else `docs/specadoc` (legacy
`docs/agent` is still picked up, with a warning, until moved by
`migrate_root.py`):

`init_change.py` preflights the whole set before writing, stages the rendered
templates, and rolls back handled publication errors, including restoring
original bytes with `--force`. It refuses non-regular artifact destinations.
It is not crash-atomic across multiple files. If rollback itself fails, its
error names retained recovery files; recover those before retrying.

Direct changes keep both approvals, the short plan and verification in chat;
they do not initialize artifacts or run file-based lifecycle gates.

| Script | Purpose |
|---|---|
| `init_change.py` | Create `spec.md` and `plan.md` from templates. |
| `validate_change.py` | Phase gates: `spec`, `plan`, `pre-review`, `final`. |
| `review_snapshot.py` | Hash the review scope and verify a recorded PASS. |
| `archive_change.py` | Compact a closed change into one bounded record. |
| `migrate_archive.py` | Migrate legacy archives, with a verified backup. |
| `doctor.py` | Read-only health check of capability specs and archives. |
| `collect_tokens.py` | Token accounting from Claude Code, Codex, or OpenCode logs. |
| `migrate_root.py` | Move the artifact root (default `docs/agent` → `docs/specadoc`). |
| `specadoc_root.py` | Shared artifact-root resolution used by the scripts. |

## Development

```bash
scripts/check.sh            # unit tests + plugin manifest validation
PYTHON=python3.14 scripts/check.sh
python3 scripts/package_plugin.py --check
python3 scripts/package_plugin.py   # dist/specadoc-0.1.1.zip + SHA-256
python3 scripts/smoke_codex.py --report dist/codex-pilot.json # opt-in offline pilot
```

The checkout-only build tools are not bundled in the release ZIP. The ZIP has a
portable manifest, all four skill folders and their resources, this README,
LICENSE and third-party notices. It excludes tests, marketplace catalogs,
Claude adapters, caches and Git data. Sorted entries, fixed timestamps and modes
make repeat builds byte-identical in the same Python/zlib environment. Unpack
the ZIP and add a separate marketplace entry if testing it as a local source.

Behavioral evaluation cases live in `tests/evals/specadoc.json`. Their presence
and automatic package checks are not evidence of a model-run evaluation;
record actual runs and skipped checks separately.

This release prepares local distribution only. No OpenAI portal upload,
submission, publisher verification or public publication is performed. Package
readiness is not public directory approval. Official packaging reference:
[Package your plugin](https://developers.openai.com/plugins/build/plugins).

`tests/test_neutrality.py` keeps host-specific vocabulary out of the shipped
skill and roles.

## License

MIT. Third-party notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
