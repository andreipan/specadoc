# Install Specadoc

[Русский](../../ru/guides/install.md)

Specadoc is one plugin with six skills: `specadoc` and five optional skills. You can install it in three ways:

| Host | Method | Skill name |
|---|---|---|
| Claude Code | plugin from a marketplace | `specadoc:specadoc` |
| Codex | plugin from a local marketplace | `specadoc:specadoc` |
| Codex CLI, OpenCode | plain skill folders | `specadoc` |

The plugin version is 0.1.1. Specadoc needs no MCP server, no authentication and no lifecycle hooks. The install does not change your host configuration or write agent files to your project.

## Requirements

- Python 3.10 or newer on `PATH`. The plugin does not install Python.
- Python 3.11 or newer, if your project has Codex role files (`.codex/agents/<role>.toml`). Specadoc reads these TOML files with `tomllib`, which Python 3.11 added.
- Git in the project. The `scope` step measures the diff against `HEAD`.

The scripts use only the Python standard library. Every lifecycle script checks the version first. An older interpreter stops with a message like this one:

```text
error: Specadoc scripts need Python 3.10+; this is 3.9.6 at /usr/bin/python3. Put a newer python3 first on PATH (a terminal started without your login PATH) or call it explicitly.
```

`run_role.py` starts a role on another runtime and uses `fcntl`. For this reason it does not run on Windows. The other scripts are not tested on Windows.

## Get the source

Clone the repository once. All install methods below use this checkout.

```bash
git clone https://github.com/andreipan/specadoc
```

In this guide, `<repo>` is the absolute path of the checkout.

## Claude Code plugin

1. Add the repository as a marketplace:

   ```bash
   claude plugin marketplace add <repo>
   ```

   The command also accepts a Git URL instead of a local path.

2. Install the plugin:

   ```bash
   claude plugin install specadoc@specadoc
   ```

3. Start a new Claude Code session.

The plugin gives you these names:

- The skill `/specadoc:specadoc`. Add the mode after it, for example `/specadoc:specadoc explore <request>`.
- The roles `specadoc:scout`, `specadoc:worker` and `specadoc:reviewer`.
- The other skills as `specadoc:<name>`, for example `specadoc:tidy`.

A skill loads only when a task matches its description. The `specadoc` skill runs only when you name it.

To try the plugin for one session without an install, load it from the checkout:

```bash
claude --plugin-dir <repo>
```

## Codex plugin

The checkout has a plugin manifest (`plugin.json`) and a local marketplace file (`.agents/plugins/marketplace.json`). The plugin installs all six skills.

1. Add the checkout as a marketplace. Use an absolute path.

   ```bash
   codex plugin marketplace add <repo>
   ```

2. Install the plugin:

   ```bash
   codex plugin add specadoc@specadoc
   ```

3. Check that the plugin is in the list:

   ```bash
   codex plugin list
   ```

4. Start a new chat.
5. Select the `specadoc:specadoc` skill. If your host supports it, type `$specadoc:specadoc`.
6. Ask for a mode: `explore`, `propose`, `apply`, `light` or `archive`.

You can also select Specadoc in the desktop plugin directory after you add the marketplace.

The `specadoc` skill has `allow_implicit_invocation: false`. Codex does not start it on its own. The other skills keep their own discovery rules.

Codex runs the skills from its installed cache copy, not from your checkout. Do not install the plugin in a project that also has a linked or copied copy of the same skills.

For packaging, the offline pilot and a separate `CODEX_HOME`, see [Packaging](../maintainers/packaging.md).

## Plain skills for Codex CLI and OpenCode

Both hosts read Agent Skills folders. Link or copy each skill folder into the project.

1. Link the `specadoc` skill:

   ```bash
   # Codex
   ln -s <repo>/skills/specadoc <project>/.agents/skills/specadoc
   # OpenCode
   ln -s <repo>/skills/specadoc <project>/.opencode/skills/specadoc
   ```

2. Link each optional skill that you need in the same folder. See the next section.
3. Start a new session.
4. Ask for the skill by its plain name, `specadoc`, and a mode.

Specadoc does not write agent configuration for these hosts. If the project has its own roles (`.codex/agents/<role>.toml` or `.opencode/agents/<role>.md`), Specadoc uses them. Otherwise the controller gives the portable role contract from `skills/specadoc/references/roles/` to an available subagent. For the full order, see [Roles](../concepts/roles.md).

## Companion skills

The repository has five more skills in `skills/`. Each skill works without Specadoc.

| Skill | Kind | Use |
|---|---|---|
| `tidy` | companion skill | Behavior-preserving cleanup before the final review |
| `codebase-design` | companion skill | A controller decision on an unresolved interface or seam |
| `domain-modeling` | companion skill | Ambiguous terms, states and invariants during clarification |
| `foreman` | management skill | One persistent executor under the main session |
| `orchestrator` | management skill | Several Specadoc controllers for one outcome |

The Claude Code and Codex plugins install all five. For plain skills, link only the skills that the project needs:

```bash
ln -s <repo>/skills/tidy <project>/.agents/skills/tidy
```

Put `tidy` in the same folder as `specadoc`. The `specadoc_step.py tidy` step looks for `tidy/SKILL.md` next to the `specadoc` folder. If it is not there, the step stops with `tidy skill not installed at <path>`.

The `grilling` skill is not in this repository. Specadoc uses it in explore and propose when your host has it. Install it with the normal skill method of your host.

For when to use each skill, see [Companion skills](companion-skills.md) and [Orchestrator and foreman](orchestrator-and-foreman.md).

## Check the install

In the reference docs, `<skill-root>` is the installed `skills/specadoc` folder. In Claude Code, the agent sees this folder as `${CLAUDE_SKILL_DIR}`. For a plain skill, it is the folder you linked.

1. Go to the root of a project repository.
2. Run the doctor:

   ```bash
   python3 <skill-root>/scripts/doctor.py
   ```

   The doctor is read-only. In a project without Specadoc files, the output is:

   ```text
   root: docs/specadoc (default)
   capability specs: 0
   archive records: 0
   Specadoc doctor: no findings.
   ```

3. If the doctor stops with the Python version error, put Python 3.10 or newer first on `PATH`. Then run the doctor again.
4. Start a new session and ask the agent: `specadoc explore <a small question about this repository>`. Explore writes no files, so this test is safe.

If the project has `.specadoc.json` with `roles`, also run `python3 <skill-root>/scripts/doctor.py --controller-runtime <claude|codex|opencode>`. This command checks role routing and that each runtime CLI is on `PATH`. Do not use this option in a project without `roles`. Without `roles`, Specadoc finds roles in the order that [Roles](../concepts/roles.md) gives. The routing check reads only project role files, so it reports errors for files that the project does not need. See [Routing](routing.md).

## Update

An update does not change `.specadoc.json` or your role files.

### Claude Code

1. If you added the marketplace from a local path, pull the new version into the checkout.
2. Update the marketplace and the plugin:

   ```bash
   claude plugin marketplace update specadoc
   claude plugin update specadoc@specadoc
   ```

3. Restart Claude Code. The update applies only after a restart.

### Codex plugin

`codex plugin marketplace upgrade` refreshes only Git marketplaces. It does not refresh a local folder.

1. Pull the new version into the checkout.
2. Remove the plugin and add it again:

   ```bash
   codex plugin remove specadoc@specadoc
   codex plugin add specadoc@specadoc
   ```

3. Start a new chat.

### Plain skills

- If you linked the folders, pull the new version into the checkout.
- If you copied the folders, copy them again.

Start a new session after the update.

## Uninstall

The uninstall does not remove `docs/specadoc/` from your projects. Your specs, plans and archive records stay in the repository.

Claude Code:

```bash
claude plugin uninstall specadoc@specadoc
claude plugin marketplace remove specadoc
```

Codex plugin:

```bash
codex plugin remove specadoc@specadoc
codex plugin marketplace remove specadoc
```

Plain skills: remove the links or the copied folders from `.agents/skills/` or `.opencode/skills/`.
