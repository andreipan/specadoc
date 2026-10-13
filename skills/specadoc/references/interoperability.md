# Interoperability and conflict resolution

Load this reference only when repository instructions or another active skill overlap this workflow.

## Role of this skill

Treat this skill as an engineering lifecycle orchestrator. It owns sequencing, artifact state, model checkpoints, task boundaries, and completion evidence. It does not override a more specific skill's concrete operational rules.

Examples:

- A security-review skill owns its security analysis method.
- A database-migration skill owns migration safety commands and rollback rules.
- A document or PDF skill owns artifact-specific manipulation.
- Repository CI and testing policy owns required commands.

This skill may wrap those operations in a broader explore-propose-apply-archive lifecycle.
It is standalone: OpenSpec may be consulted as external design inspiration, but
must not be installed, invoked, or maintained as a parallel artifact engine.

## Optional companion skills

Specadoc works alone. When the host installs any of these, use them for the
step they own and record which one ran:

- **Grilling** — stress-tests a proposal after reconnaissance (explore, propose).
  Without it, the controller asks the material questions itself.
- **Review checklist** — a repository review skill the `reviewer` follows.
  Without it, the reviewer role's own order applies.
- **Implementation discipline** — rules for surgical, minimal diffs that the
  `worker` and controller follow during apply.
- **Tool router** — the host's policy for symbol-aware (IDE/LSP) and code-graph
  tools, including fallbacks. Without it, use `rg`/file inspection and state the
  limitation.

## Host conventions

Hosts often add rules Specadoc must honor without naming them: a required
command prefix or proxy, a persistent memory protocol, a project landscape map,
or a harness instruction file. Treat these as repository instructions under the
conflict order below. Specadoc's examples show bare commands; apply the host's
prefix or wrapper when one is required.

## Conflict resolution order

When instructions conflict:

1. Follow system, platform, and explicit user instructions.
2. Follow repository-local instructions closest to the changed files.
3. Follow the more specific domain skill for its owned operation.
4. Use this skill for lifecycle decisions not defined above.
5. Ask the user only when two same-priority instructions remain materially incompatible.

Do not merge incompatible workflows silently.

This skill never grants itself an exception to a higher-priority instruction. A
needed exception must be recorded in the higher-priority document and cited here,
not asserted here.

## Common conflicts

### Artifact location or naming

If another workflow requires `tasks.md`, `.specify/`, `openspec/`, issue files, or another directory, follow that higher-priority repository convention. Avoid duplicating the same state in both formats. Record the chosen source of truth in the plan.

### Approval gates

If another skill requires approval before planning, implementation, migration, or deployment, honor the stricter gate. Do not add a second equivalent approval unless it changes the decision.

### TDD policy

If repository policy defines a different test order or test framework, follow it while preserving the core evidence requirement: observe a meaningful failure before claiming the test proves new behavior whenever practical.

### Agent routing

If another skill or runtime owns subagent selection, supply the task risk and execution level and let that mechanism bind the concrete agent. Do not invent model names and do not reason about model price. Where a role registry exists, read it; `model-routing.md` names the registry path per runtime.

### Review policy

If another skill requires deeper or per-task review, use the stricter review. If it already provides equivalent completeness, correctness, coherence, and regression checks, do not duplicate the same review.

### Commits, branches, and deployment

Do not commit, push, open a pull request, deploy, or modify external trackers unless the user or a higher-priority workflow explicitly requests it.

### Autonomous execution

An explicit user request for uninterrupted autonomous execution waives both the
manual model checkpoint and the manual plan checkpoint, but not specification,
testing, or completion evidence unless the user explicitly waives those too.

## Source-of-truth rule

For each concern, keep one source of truth:

- Behavior: specification or repository-required equivalent.
- Execution state: plan or repository-required task system.
- Test policy: repository instructions.
- Specialized operation: domain skill.
- Final evidence: plan or repository-required report.

Prefer adapting this skill to an existing source of truth over creating parallel documents.
