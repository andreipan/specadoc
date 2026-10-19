# Archive mode

Load this reference only for explicit `specadoc archive`.

The target is `docs/specadoc/archive/<slug>/record.md`, schema
`specadoc.archive/v1`, with a hard 16 KiB budget. It retains the durable outcome,
capability delta, decisions, review, token totals, forced exceptions, and a
SHA-256 source manifest. It intentionally drops raw progress and logs.

Archive consumes the PASS recorded by `apply`; it never dispatches a `reviewer`,
invokes a review skill, or rebuilds a code graph. Confirm that the recorded PASS applies
to the current executable diff by running `review_snapshot.py verify <slug>
--stored <manifest from the latest ### G<n> block>` (also run automatically by
`archive_change.py`'s own gate). A manifest mismatch always means executable
code, tests, migrations, executable configuration, a public contract, or
approved requirements changed
after PASS: stop and return the change to final `apply`. Archive does not
start a reviewer to resolve that condition. A `plan.md` with no `### G<n>`
round-log entry predates this mechanism: fall back to confirming this by
manual judgment instead.

`Snapshot waiver` covers only a technical read failure after a valid Review
scope was declared; it never accepts an invalid scope or a computed manifest
mismatch. The only explicit bypass for those failures is user-authorized
`archive --force`, whose compact record retains the unmet gates.

Normal archive:

1. Confirm the existing PASS and closed lifecycle gates.
2. Run `python3 <skill-root>/scripts/archive_change.py <slug> --dry-run`.
3. Clear every deterministic gate, unknown-attachment, collision, and size
   violation without dispatching a reviewer.
4. Run the same command without `--dry-run`.

Files under the change's `runs/` are transient role handoff: archive never
reports them as unknown attachments, collapses them into one source-manifest
row, and removes them with the source; clean nothing by hand.

Forced archive:

1. Always show `--force --dry-run` first.
2. Only an explicit `--force` request authorizes the real compaction.
3. Force bypasses lifecycle and capability-provenance gates, but cannot
   overwrite a target, skip record validation, or remove the source before the
   record is published and read back.

Legacy archives are separate. Run `migrate_archive.py` without `--apply` to
produce the inventory and projected-size report. Any legacy file beyond
`spec.md` and `plan.md` — including design, research, and logs — requires a
human-written `migration-summary.md`. Apply only after the user approves the
dry-run; the migrator creates and verifies a timestamped compressed backup and
never deletes it automatically.

## Memory handoff (optional)

When the runtime exposes a persistent memory tool, leave a session handoff
after the record is published and read back, so the next session re-orients
without reading the full plan. Follow the host's memory conventions for tool
names and keys.

- The handoff summary covers goal, discoveries, accomplished work, next steps,
  and files; next steps must name `docs/specadoc/archive/<slug>/record.md`.
- Durable cross-session facts go under a stable topic key, one fact per entry,
  stating what, why, where, and what was learned. Progress and logs stay out.
- Never record secrets; the host's memory conventions own the full rule.
- Scope is the current repository. Never write another repository's facts
  into this scope; cross-repo impact notes belong to the consumer's session.
