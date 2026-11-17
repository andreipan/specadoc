# Specadoc documentation

[Русский](../ru/index.md)

This is the map of the Specadoc documentation. For a short introduction, read
the [README](../../README.md) first.

The agent-facing instructions live in `skills/specadoc/SKILL.md` and
`skills/specadoc/references/`. These pages explain the same system to a
person. If a page and the skill disagree, the skill is the source of truth.
Report the difference as a documentation bug.

## Where to start

| You want to | Read |
|---|---|
| Install Specadoc | [Install](guides/install.md) |
| Run your first change from start to end | [Your first change](guides/first-change.md) |
| Decide between `light`, `propose` and `explore` | [Light or propose](guides/light-or-propose.md) |
| Fix a refused step or a failed gate | [Troubleshooting](guides/troubleshooting.md) |
| Understand why Specadoc works this way | [Concepts](#concepts) |
| Find an exact flag, key or section name | [Reference](#reference) |

## Concepts

- [Lifecycle](concepts/lifecycle.md): the modes, how Specadoc picks one, and
  how an active change continues.
- [Roles](concepts/roles.md): the controller, `scout`, `worker` and
  `reviewer`, and what each one owns.
- [Artifacts and gates](concepts/artifacts-and-gates.md): spec, plan,
  capability specs and archive records, and the checks between phases.

## Guides

- [Install](guides/install.md): Claude Code, Codex and OpenCode.
- [Your first change](guides/first-change.md): `propose`, `apply` and
  `archive` on an example.
- [Light or propose](guides/light-or-propose.md): pick the right mode.
- [Routing](guides/routing.md): run roles on Claude, Codex or OpenCode with
  `.specadoc.json`.
- [Orchestrator and Foreman](guides/orchestrator-and-foreman.md): long tasks
  and several controllers.
- [Companion skills](guides/companion-skills.md): `tidy`, `codebase-design`,
  `domain-modeling` and `grilling`.
- [Troubleshooting](guides/troubleshooting.md): typical refusals and fixes.

## Reference

- [Modes](reference/modes.md): syntax, inputs, outputs and stop points.
- [Scripts](reference/scripts.md): every script, its subcommands and flags.
- [Configuration](reference/config.md): `.specadoc.json` and the artifact
  root.
- [Plan structure](reference/plan-structure.md): the sections of `spec.md`,
  `plan.md` and `record.md`.
- [Glossary](reference/glossary.md): the terms these pages use.

## For maintainers

- [Development](maintainers/development.md): repository layout, tests and
  role contracts.
- [Packaging and release](maintainers/packaging.md): manifests, the release
  ZIP, the Codex pilot and tagging.
- [CHANGELOG](../../CHANGELOG.md)
