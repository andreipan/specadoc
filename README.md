# Specadoc

[Русский](README.ru.md)

Specadoc is an engineering lifecycle for coding agents in Claude Code, Codex
and OpenCode. It turns a request into a written contract, an approved plan,
test-first implementation, an independent review and a compact archive record.

Specadoc runs only when you call it by name. It never takes over ordinary
coding work.

## Why

A coding agent that works from a chat message alone forgets decisions, changes
requirements to fit its code and marks its own work as done. Specadoc keeps
three things apart:

- The spec (`spec.md`) says what the change must do. It stays stable after
  approval.
- The plan (`plan.md`) holds tasks, approvals and evidence. It changes as the
  work goes on.
- The review is done by a separate read-only `reviewer`, never by the agent
  that wrote the code.

Deterministic scripts check each phase. A failed check stops the work. It does
not let the agent rewrite the plan or weaken a test to pass.

## Modes

| Mode | What it does |
|---|---|
| `explore <request>` | Finds facts and tests the idea. Writes no files. |
| `propose <request\|slug>` | Writes `spec.md` and `plan.md`, validates them, and stops for your plan approval. |
| `apply <slug>` | Implements the approved plan test-first, runs final verification and the independent review. |
| `light <request>` | A small change in one session. Updates capability specs, keeps the plan in chat, creates no change folder. |
| `archive <slug>` | Compacts a finished change into one bounded `record.md`. Runs only on request. |

Without a mode, Specadoc picks one by fixed rules. See
[Lifecycle](docs/en/concepts/lifecycle.md).

## Roles

Your main agent session is the **controller**. It owns requirements,
architecture, approvals and final verification. It sends bounded work to
three roles:

| Role | Job |
|---|---|
| `scout` | One bounded read-only investigation with a fixed report. |
| `worker` | One fully specified, low-decision task, test-first. |
| `reviewer` | Independent read-only review of the final diff against the spec. |

Each role can run on the same host or on another runtime. A project
`.specadoc.json` file selects the runtime per role. Specadoc fixes no model:
the model and effort come from the installed role file. See
[Roles](docs/en/concepts/roles.md) and [Routing](docs/en/guides/routing.md).

## Quick start (Claude Code)

1. Add the marketplace and install the plugin:

   ```bash
   claude plugin marketplace add andreipan/specadoc
   claude plugin install specadoc@specadoc
   ```

   To stay on a release, add its tag: `andreipan/specadoc@v0.1.3`.

2. Start a new session in your project.
3. Ask for a proposal:

   ```text
   /specadoc:specadoc propose add rate limiting to the login endpoint
   ```

4. Read `docs/specadoc/<slug>/spec.md` and `plan.md`. Approve the plan or ask
   for changes.
5. Run `/specadoc:specadoc apply <slug>`.

For Codex (`codex plugin marketplace add andreipan/specadoc`), OpenCode and
plain skill folders, see [Install](docs/en/guides/install.md). For a full walkthrough, see
[Your first change](docs/en/guides/first-change.md).

## Requirements

- Python 3.10 or newer. Python 3.11 or newer for Codex TOML role files.
- Git in the project.
- No MCP server, authentication or lifecycle hooks.

## Bundled skills

The plugin also ships five skills. Each one works without Specadoc.

| Skill | Use |
|---|---|
| `tidy` | Behavior-preserving cleanup before final verification and review. |
| `codebase-design` | A controller decision on an open interface or seam. |
| `domain-modeling` | Ambiguous terms, states and invariants during clarification. |
| `foreman` | One persistent executor for a long task. |
| `orchestrator` | Several Specadoc controllers that work toward one outcome. |

See [Companion skills](docs/en/guides/companion-skills.md) and
[Orchestrator and Foreman](docs/en/guides/orchestrator-and-foreman.md).

## Documentation

All documentation is in English and Russian. Start at the
[documentation map](docs/en/index.md).

- Concepts: [lifecycle](docs/en/concepts/lifecycle.md),
  [roles](docs/en/concepts/roles.md),
  [artifacts and gates](docs/en/concepts/artifacts-and-gates.md)
- Guides: [install](docs/en/guides/install.md),
  [first change](docs/en/guides/first-change.md),
  [light or propose](docs/en/guides/light-or-propose.md),
  [troubleshooting](docs/en/guides/troubleshooting.md)
- Reference: [modes](docs/en/reference/modes.md),
  [scripts](docs/en/reference/scripts.md),
  [configuration](docs/en/reference/config.md),
  [glossary](docs/en/reference/glossary.md)
- Changes: [CHANGELOG](CHANGELOG.md)

## License

MIT. Third-party notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
