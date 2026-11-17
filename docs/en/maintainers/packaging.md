# Packaging and release

[Русский](../../ru/maintainers/packaging.md)

This page tells maintainers how the plugin version, the manifests and the
release ZIP work, and how to make a release. For tests and role adapters, see
[Development](development.md).

A release is local only. The maintainer makes a git tag and a ZIP. Nobody
uploads the package to a public plugin directory or submits it for review. A
valid package is not an approval from a public directory.

## Version and manifests

The repository has four manifest files:

| File | Host | Contents |
|---|---|---|
| `plugin.json` | Portable package, Codex | Name, version, description, author, license, keywords and the `com.openai` interface |
| `.claude-plugin/plugin.json` | Claude Code | The same name, version, description, author, license and keywords |
| `.claude-plugin/marketplace.json` | Claude Code | One plugin entry, `specadoc`, with the source `./` |
| `.agents/plugins/marketplace.json` | Codex | One plugin entry, `specadoc`, with a local source `./` |

The version is in the two `plugin.json` files only. The marketplace files have
no version. The ZIP name comes from the version in `plugin.json`.

`python3 scripts/package_plugin.py --check` refuses the package for these
errors:

- `plugin.json` and `.claude-plugin/plugin.json` have a different or empty
  `name`, `version`, `description`, `author`, `license` or `keywords`.
- The version is not in the form `X.Y.Z`.
- `plugin.json` has a `$schema` other than
  `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`.
- The `com.openai` extension declares `hooks`, `apps` or `mcpServers`. The
  package contains skills only.
- The `com.openai` interface has no `displayName`, `shortDescription`,
  `developerName` or `category`.
- `.agents/plugins/marketplace.json` does not have exactly one `specadoc` entry
  with the source `{"source": "local", "path": "./"}`, the policy
  `{"installation": "AVAILABLE", "authentication": "ON_USE"}` and the category
  `Productivity`.

The same command also checks the skills:

- `skills/` holds exactly six folders: `specadoc`, `tidy`, `codebase-design`,
  `domain-modeling`, `foreman` and `orchestrator`.
- The `SKILL.md` frontmatter of each skill has a `name` equal to the folder
  name and a `description`.
- Each path in backticks that starts with `references/`, `scripts/`, `assets/`
  or `roles/` points to a file that exists.
- `skills/specadoc`, `skills/foreman` and `skills/orchestrator` have
  `allow_implicit_invocation: false` in `agents/openai.yaml`. These skills run
  only on an explicit request.
- The three portable role contracts exist in `skills/specadoc/references/roles/`.
- Each file of the ZIP exists, and no file is a symbolic link.

`package_plugin.py` does not read `.claude-plugin/marketplace.json`. If the
`claude` CLI is on `PATH`, `check.sh` runs `claude plugin validate . --strict`
for the Claude Code files.

## Build the ZIP

To build the ZIP, run:

```bash
python3 scripts/package_plugin.py
```

The script checks the package first. If the check passes, it writes
`dist/specadoc-<version>.zip` and prints the path and `sha256:<digest>`. To
write the ZIP to another path, add `--output <path>`. Git ignores `dist/`.

### ZIP contents

| In the ZIP | Not in the ZIP |
|---|---|
| `plugin.json` | `.claude-plugin/` |
| `README.md`, `README.ru.md` | `.agents/` |
| `CHANGELOG.md`, `CHANGELOG.ru.md` | `agents/` (Claude Code adapters) |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | `scripts/` |
| Each `.md` file in `docs/en/` and `docs/ru/` | `tests/` |
| All files of the six skill folders, `evals/` included | `.git`, `__pycache__/`, `*.pyc`, `.DS_Store` |

All the files in the left column must exist. If a top-level file, `docs/en/`
or `docs/ru/` does not exist, the build stops with an error.

The ZIP has no marketplace file. The ZIP also has no Claude Code manifest or
role adapters. Claude Code installs the plugin from the repository through
`.claude-plugin/marketplace.json`.

### Deterministic build

The build gives the same bytes for the same source tree:

- The entries are sorted by path.
- Each entry has the timestamp 1980-01-01 00:00:00 and the mode `0644`.
- All entries use deflate compression at level 9.

`test_plugin_package.py` builds the ZIP two times and compares the bytes. A
different Python or zlib version can compress differently. Thus, compare
digests only from builds in the same environment.

## Offline Codex pilot

`scripts/smoke_codex.py` installs the built package into Codex and removes it
again. It is opt-in: `check.sh` does not run it. It needs the `codex` CLI on
`PATH`.

```bash
python3 scripts/smoke_codex.py --report dist/codex-pilot.json
```

The pilot uses a temporary `HOME` and `CODEX_HOME`. It removes
`OPENAI_API_KEY` and `CODEX_API_KEY` from its environment. It does not change
your Codex configuration and does not start a model turn. The pilot does
these steps:

1. It builds the ZIP into a temporary folder and unpacks it. Then it adds a
   copy of `.agents/plugins/marketplace.json`.
2. It adds the marketplace and installs `specadoc@specadoc`. The installed
   copy must be inside the temporary `CODEX_HOME`.
3. It starts `codex app-server --stdio` and opens an ephemeral thread. All six
   skills must load from the installed copy as `specadoc:<name>`.
4. It reads the installed `agents/openai.yaml` files. Specadoc, Foreman and
   Orchestrator must keep `allow_implicit_invocation: false`.
5. It runs `--help` for each installed Specadoc script. Then it runs
   `init_change.py pilot --no-scout 'pilot change'` in a temporary project.
6. It changes the unpacked source. The installed copy must stay the same until
   a remove and a new install.
7. It removes the plugin and the marketplace. The installed copy and the
   skills must be gone.

The script prints a JSON report with `checks`, `gaps`, `version`, `client` and
`skills`. With `--report <path>`, it also saves the report. The report states
one gap: the pilot has no model turns and no desktop UI actions.

## Codex local pilot by hand

Use this procedure to try the checkout in Codex before a release. Use a
separate test project. Set `CODEX_HOME` to an empty folder, so that your own
Codex configuration stays the same.

1. Add the checkout as a marketplace:

   ```bash
   codex plugin marketplace add /absolute/path/to/specadoc
   ```

2. Install the plugin:

   ```bash
   codex plugin add specadoc@specadoc
   ```

3. Start a new chat. Select the `specadoc:specadoc` skill explicitly.

Codex runs the skills from its installed copy, not from the checkout. After
you change the checkout, install the plugin again:

```bash
codex plugin remove specadoc@specadoc
codex plugin add specadoc@specadoc
```

Then start a new chat. `codex plugin marketplace upgrade` refreshes only Git
sources. It does not refresh a local folder.

After the pilot, remove the plugin and the marketplace:

```bash
codex plugin remove specadoc@specadoc
codex plugin marketplace remove specadoc
```

To try the built ZIP instead of the checkout, unpack the ZIP into a new
folder. Copy `.agents/plugins/marketplace.json` from the checkout to the same
path in that folder. Then use that folder in step 1.

## Make a release

Do these steps from the repository root:

1. Set the new version `X.Y.Z` in `plugin.json`.
2. Set the same version in `.claude-plugin/plugin.json`.
3. In `CHANGELOG.md`, move the `## [Unreleased]` entries into a new
   `## [X.Y.Z] - YYYY-MM-DD` section.
4. Make the same change in `CHANGELOG.ru.md`.
5. Set the example tag `vX.Y.Z` in `README.md`, `README.ru.md` and both
   install guides. `tests/test_docs.py` checks these examples.
6. Run `python3 scripts/docs_sync.py --stamp` on each changed Russian file.
7. Run `scripts/check.sh`. If a step fails, fix the cause and run it again.
8. Run `python3 scripts/package_plugin.py`. Keep the printed SHA-256 digest.
9. If the `codex` CLI is available, you can run
   `python3 scripts/smoke_codex.py --report dist/codex-pilot.json`.
10. Commit the version and the changelog changes.
11. Make an annotated tag: `git tag -a vX.Y.Z -m "Specadoc X.Y.Z"`.
12. Push the branch and the tag: `git push origin main vX.Y.Z`.
13. Make a GitHub release from the tag. Use the changelog section as the
    notes and attach the ZIP:
    `gh release create vX.Y.Z dist/specadoc-X.Y.Z.zip --verify-tag --notes-file <notes>`.

Do not upload the ZIP to a public plugin directory. The release is the tag and
the GitHub release with the ZIP.
