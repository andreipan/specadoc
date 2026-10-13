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
- `specadoc propose <request|slug>`: writes `docs/agent/<slug>/spec.md` and
  `plan.md` and stops at the model and plan checkpoints.
- `specadoc apply <slug>`: TDD implementation, bounded workers, controller
  verification, final reviewer.
- `specadoc archive <slug>`: compacts a finished change into
  `docs/agent/archive/<slug>/record.md` (≤ 16 KiB).

## Install

### Claude Code (plugin)

```bash
claude plugin marketplace add <git-url-or-local-path-of-this-repo>
claude plugin install specadoc@specadoc
```

The skill is invoked as `/specadoc:specadoc`. The roles are available as
`specadoc:scout`, `specadoc:worker` and `specadoc:reviewer`. For a single
session from a checkout, run `claude --plugin-dir <path>`.

### Codex CLI and OpenCode

Both read Agent Skills folders. Link or copy the skill folder:

```bash
ln -s <repo>/skills/specadoc <project>/.agents/skills/specadoc     # Codex
ln -s <repo>/skills/specadoc <project>/.opencode/skills/specadoc   # OpenCode
```

The roles in `agents/*.md` are written in Claude Code agent format. For Codex,
convert each one into `.codex/agents/<role>.toml` (`name`, `description`,
`model`, `developer_instructions` = the Markdown body). For OpenCode, copy it
to `.opencode/agents/<role>.md` with `mode: subagent`. Without roles, Specadoc
falls back to running every step in the controller.

## Roles and overrides

Specadoc resolves each role in this order (see
`skills/specadoc/references/model-routing.md`):

1. a project role: `.claude/agents/<role>.md`, `.codex/agents/<role>.toml`, or
   `.opencode/agents/<role>.md`;
2. the role shipped with this plugin;
3. no role: the controller does the work and records `Role registry: none`.

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

All scripts use only the Python standard library (Python 3.9 or newer) and
write only under the project's `--root` (default `docs/agent`):

| Script | Purpose |
|---|---|
| `init_change.py` | Create `spec.md` and `plan.md` from templates. |
| `validate_change.py` | Phase gates: `spec`, `plan`, `pre-review`, `final`. |
| `review_snapshot.py` | Hash the review scope and verify a recorded PASS. |
| `archive_change.py` | Compact a closed change into one bounded record. |
| `migrate_archive.py` | Migrate legacy archives, with a verified backup. |
| `doctor.py` | Read-only health check of capability specs and archives. |
| `collect_tokens.py` | Token accounting from Claude Code, Codex, or OpenCode logs. |

## Development

```bash
scripts/check.sh            # unit tests + plugin manifest validation
PYTHON=python3.14 scripts/check.sh
```

`tests/test_neutrality.py` keeps host-specific vocabulary out of the shipped
skill and roles.

## License

MIT
