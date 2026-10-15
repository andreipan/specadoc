#!/usr/bin/env python3
"""Validate and compact a Specadoc change into one immutable record.md."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402
from validate_change import (  # noqa: E402
    PENDING,
    Document,
    capability_deltas,
    capability_requirements,
    check_final,
    check_plan,
    check_spec,
)
from review_snapshot import (  # noqa: E402
    latest_round,
    verify_latest,
)


RECORD_BUDGET = 16 * 1024
KNOWN_ARTIFACTS = {"spec.md", "plan.md", "design.md", "research.md"}
NOISE_NAMES = {".DS_Store", "Thumbs.db"}
NOISE_DIR_NAMES = {"__pycache__"}
ARTIFACT_SIZE_WARNING = 512 * 1024


class ArchiveError(RuntimeError):
    pass


class SourceFile(NamedTuple):
    name: str
    size: int
    sha256: str


class ArchiveResult(NamedTuple):
    source: Path
    target: Path
    record_size: int
    source_size: int
    forced: bool
    violations: tuple[str, ...]
    unknown_attachments: tuple[str, ...]


def capability_findings(spec: Document, root: str, change_slug: str) -> tuple[list[str], list[str]]:
    declared: list[str] = []
    messages: list[str] = []
    for _, capability, is_new, operations in capability_deltas(spec, root):
        if capability not in declared:
            declared.append(capability)
        path = Path(capability)
        if not path.is_file():
            messages.append(f"{capability}:1: declared capability file does not exist")
            continue
        if change_slug not in path.read_text(encoding="utf-8"):
            messages.append(f"{capability}:1: provenance table does not record {change_slug}")
        present = capability_requirements(path)
        for _, operation, identifier, _ in operations:
            if operation in ("ADDED", "MODIFIED", "RENAMED") and identifier not in present:
                messages.append(
                    f"{capability}:1: {operation} {identifier} declared in spec.md "
                    "but absent from the capability file"
                )
            if operation == "REMOVED" and identifier in present:
                messages.append(
                    f"{capability}:1: REMOVED {identifier} declared in spec.md "
                    "but still present in the capability file"
                )
        if is_new and not present:
            messages.append(f"{capability}:1: new capability file defines no `### C<n>`")
    return declared, messages


def validate_change_gates(root: Path, change_slug: str) -> list[str]:
    change = root / change_slug
    missing = [name for name in ("spec.md", "plan.md") if not (change / name).is_file()]
    if missing:
        return [f"{change / name}: missing artifact" for name in missing]
    root_label = root.as_posix().rstrip("/")
    spec = Document(change / "spec.md", str(change / "spec.md"))
    plan = Document(change / "plan.md", str(change / "plan.md"))
    requirement_ids = [identifier for identifier, _, _ in spec.blocks("Requirements", "R")]
    violations = (
        check_spec(spec, root_label, expect_capabilities_applied=True)
        + check_plan(plan, requirement_ids)
        + check_final(spec, plan)
    )
    _, capability_messages = capability_findings(spec, root_label, change_slug)
    messages = {violation.render() for violation in violations} | set(capability_messages)
    messages |= set(_snapshot_messages(plan, change, Path.cwd()))
    return sorted(messages)


def _snapshot_messages(
    plan: Document,
    change: Path,
    repo_root: Path | None = None,
) -> list[str]:
    """Confirm the latest recorded PASS still applies to the current diff.

    Mirrors `references/archive.md`'s "confirm the recorded PASS applies to
    the current executable diff" rule mechanically, via a content-hash
    snapshot rather than manual judgment. A `plan.md` with no `### G<n>`
    round-log entry at all (every change created before this mechanism
    existed) is a silent no-op.
    """
    entry = latest_round(plan)
    if entry is None:
        return []
    return [
        f"{plan.display}:1: {message}"
        for message in verify_latest(plan, change, repo_root or Path.cwd())
    ]


RUNS_PREFIX = "runs/"


def source_manifest(change: Path) -> list[SourceFile]:
    paths = [
        path
        for path in change.rglob("*")
        if path.is_file()
        and path.name not in NOISE_NAMES
        and not (NOISE_DIR_NAMES & set(path.relative_to(change).parts[:-1]))
    ]
    result: list[SourceFile] = []
    for path in sorted(paths):
        content = path.read_bytes()
        result.append(
            SourceFile(
                name=path.relative_to(change).as_posix(),
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    return result


def unknown_attachments(manifest: Sequence[SourceFile]) -> list[str]:
    return [
        item.name
        for item in manifest
        if item.name not in KNOWN_ARTIFACTS and not item.name.startswith(RUNS_PREFIX)
    ]


def oversized_artifacts(manifest: Sequence[SourceFile]) -> list[str]:
    """Soft check: a known artifact file far larger than expected usually means
    a log or trace got pasted into spec.md/plan.md by mistake."""
    return [
        f"{item.name}: {item.size} bytes exceeds the expected artifact size; "
        f"check for accidentally pasted logs"
        for item in manifest
        if item.name in KNOWN_ARTIFACTS and item.size > ARTIFACT_SIZE_WARNING
    ]


def section(path: Path, heading: str) -> str:
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    marker = f"## {heading}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return ""
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


ROUND_MANIFEST_FENCE = re.compile(r"```json\n(.*?)\n```\n?", re.DOTALL)


def _strip_round_manifests(text: str) -> str:
    """Replace each fenced round manifest with a one-line stand-in.

    A `### G<n>` manifest is gate input, not durable outcome: both
    `validate_change.py --phase final` and this script verify it against the
    working tree before anything is published, and the `Snapshot:` hash beside
    it is the checkable form that survives. Its size scales with the change's
    file count, so keeping it would spend most of RECORD_BUDGET on per-file
    digests — a ~100-file change alone produces ~13 KiB and cannot be archived
    without force, which is what this strip exists to prevent.
    """

    def replace(match: re.Match[str]) -> str:
        try:
            entries = len(json.loads(match.group(1)))
        except (json.JSONDecodeError, TypeError):
            return "(manifest elided for the record; see the Snapshot hash above)\n"
        return (
            f"({entries} manifest entries elided for the record; "
            "see the Snapshot hash above)\n"
        )

    return ROUND_MANIFEST_FENCE.sub(replace, text)


def _truncate(text: str, byte_limit: int) -> str:
    value = text.strip() or "Not recorded."
    encoded = value.encode("utf-8")
    if len(encoded) <= byte_limit:
        return value
    suffix = "\n\n_[truncated during forced compaction]_"
    available = max(0, byte_limit - len(suffix.encode("utf-8")))
    shortened = encoded[:available].decode("utf-8", errors="ignore").rstrip()
    return shortened + suffix


def _manifest_markdown(manifest: Sequence[SourceFile]) -> str:
    rows = ["| File | Bytes | SHA-256 |", "|---|---:|---|"]
    entries = [
        (item.name, f"| `{item.name}` | {item.size} | `{item.sha256}` |")
        for item in manifest
        if not item.name.startswith(RUNS_PREFIX)
    ]
    runs = [item for item in manifest if item.name.startswith(RUNS_PREFIX)]
    if runs:
        total = sum(item.size for item in runs)
        entries.append(
            (RUNS_PREFIX, f"| `{RUNS_PREFIX}` ({len(runs)} files) | {total} | — |")
        )
    rows.extend(row for _, row in sorted(entries, key=lambda entry: entry[0].split("/")))
    return "\n".join(rows)


def render_record(
    change: Path,
    change_slug: str,
    *,
    forced: bool,
    violations: Sequence[str],
    migration_summary: str = "",
) -> str:
    manifest = source_manifest(change)
    spec = change / "spec.md"
    plan = change / "plan.md"
    limits = {
        "goal": 1200,
        "capabilities": 1800,
        "decisions": 1600,
        "summary": 2200,
        "verification": 1400,
        "review": 700,
        "measurement": 900,
    }
    values = {
        "goal": section(spec, "Goal"),
        "capabilities": section(spec, "Affected capabilities"),
        "decisions": section(plan, "Confirmed decisions"),
        "summary": section(plan, "Archive summary"),
        "verification": section(plan, "Final verification"),
        "review": section(plan, "Review result"),
        "measurement": section(plan, "Completion evidence"),
    }
    values["review"] = _strip_round_manifests(values["review"])
    if migration_summary.strip():
        values["summary"] = "\n\n".join(
            value for value in (values["summary"], migration_summary.strip()) if value
        )
    if forced:
        values = {key: _truncate(value, limits[key]) for key, value in values.items()}
    else:
        values = {key: value.strip() or "Not recorded." for key, value in values.items()}

    forced_findings = "\n".join(f"- {message}" for message in violations) or "- None."
    status = "forced" if forced else "archived"
    archived_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    record = f"""---
schema: specadoc.archive/v1
slug: {change_slug}
archived_at: {archived_at}
status: {status}
---

# {change_slug}

## Goal

{values['goal']}

## Outcome

{values['summary']}

## Affected capabilities

{values['capabilities']}

## Decisions

{values['decisions']}

## Verification

{values['verification']}

## Review

{values['review']}

## Measurement

{values['measurement']}

## Forced exceptions

{forced_findings}

## Source manifest

{_manifest_markdown(manifest)}
"""
    size = len(record.encode("utf-8"))
    if size > RECORD_BUDGET:
        mode = "forced record mandatory data" if forced else "record"
        raise ArchiveError(f"{mode} is {size} bytes; budget is {RECORD_BUDGET}")
    return record


def validate_record(record: str, change_slug: str) -> None:
    required = (
        "schema: specadoc.archive/v1",
        f"slug: {change_slug}",
        "## Goal",
        "## Outcome",
        "## Source manifest",
    )
    missing = [value for value in required if value not in record]
    if missing:
        raise ArchiveError("invalid compact record; missing: " + ", ".join(missing))
    if len(record.encode("utf-8")) > RECORD_BUDGET:
        raise ArchiveError(f"compact record exceeds {RECORD_BUDGET} bytes")


def archive_change(
    root: Path,
    change_slug: str,
    *,
    force: bool,
    dry_run: bool,
) -> ArchiveResult:
    root = Path(root)
    change = root / change_slug
    target = root / "archive" / change_slug
    if not change.is_dir():
        raise ArchiveError(f"no change directory: {change}")
    if target.exists():
        raise ArchiveError(f"archive target already exists: {target}")

    manifest = source_manifest(change)
    unknown = unknown_attachments(manifest)
    violations = validate_change_gates(root, change_slug) + oversized_artifacts(manifest)
    if not force:
        if unknown:
            raise ArchiveError("unknown attachment(s): " + ", ".join(unknown))
        if violations:
            raise ArchiveError(
                f"refusing to archive {change_slug}: {len(violations)} unmet condition(s)\n"
                + "\n".join(violations)
            )

    record = render_record(change, change_slug, forced=force, violations=violations)
    validate_record(record, change_slug)
    result = ArchiveResult(
        source=change,
        target=target,
        record_size=len(record.encode("utf-8")),
        source_size=sum(item.size for item in manifest),
        forced=force,
        violations=tuple(violations),
        unknown_attachments=tuple(unknown),
    )
    if dry_run:
        return result

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{change_slug}.archive-", dir=target.parent))
    try:
        record_path = staging / "record.md"
        record_path.write_text(record, encoding="utf-8")
        validate_record(record_path.read_text(encoding="utf-8"), change_slug)
        staging.rename(target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    shutil.rmtree(change)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_slug")
    parser.add_argument(
        "--root",
        help="Artifact root relative to the current repository (default: resolved, see specadoc_root.py)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        choice = resolve_root(args.root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if warning := legacy_warning(choice):
        print(warning, file=sys.stderr)
    try:
        result = archive_change(Path(choice.path), args.change_slug, force=args.force, dry_run=args.dry_run)
    except ArchiveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    verb = "would compact" if args.dry_run else "compacted"
    print(f"{verb} {result.source} -> {result.target / 'record.md'}")
    print(f"size: {result.source_size} -> {result.record_size} bytes")
    if result.forced:
        print(
            f"forced: {len(result.violations)} unmet condition(s), "
            f"{len(result.unknown_attachments)} unknown attachment(s)"
        )
        for violation in result.violations:
            print(f"  unmet: {violation}")
        for attachment in result.unknown_attachments:
            print(f"  unknown: {attachment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
