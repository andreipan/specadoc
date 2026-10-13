#!/usr/bin/env python3
"""Compact legacy Specadoc archive directories after a recoverable dry-run."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402
from archive_change import (  # noqa: E402
    ArchiveError,
    render_record,
    section,
    source_manifest,
    validate_record,
)


class MigrationError(RuntimeError):
    pass


class MigrationReport(NamedTuple):
    pending_count: int
    compact_count: int
    source_size: int
    projected_size: int
    backup_path: Path | None
    backup_sha256: str | None
    issues: tuple[str, ...]
    previews: tuple[tuple[str, str], ...]


def _entries(archive: Path) -> list[Path]:
    return sorted(path for path in archive.iterdir() if path.is_dir() and not path.name.startswith("."))


def _is_compact(path: Path) -> bool:
    return path.joinpath("record.md").is_file() and [item.name for item in path.iterdir()] == ["record.md"]


def _unknown(path: Path) -> list[str]:
    compact_without_summary = {"spec.md", "plan.md", "migration-summary.md"}
    return [item.name for item in source_manifest(path) if item.name not in compact_without_summary]


def _render_legacy(path: Path) -> str:
    unknown = _unknown(path)
    summary_path = path / "migration-summary.md"
    archive_summary = section(path / "plan.md", "Archive summary")
    if (unknown or not archive_summary) and not summary_path.is_file():
        reasons = []
        if unknown:
            reasons.append(f"unknown attachment(s) {', '.join(unknown)}")
        if not archive_summary:
            reasons.append("plan has no Archive summary")
        raise MigrationError(
            f"{path}: {'; '.join(reasons)}; "
            "add migration-summary.md before --apply"
        )
    summary = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else ""
    try:
        record = render_record(
            path,
            path.name,
            forced=True,
            violations=("legacy archive compacted outside current lifecycle gates",),
            migration_summary=summary,
        )
        validate_record(record, path.name)
        return record
    except ArchiveError as exc:
        raise MigrationError(str(exc)) from exc


def _backup(archive: Path, backup_root: Path) -> tuple[Path, str]:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = backup_root / f"archive-{stamp}-{uuid.uuid4().hex[:8]}.tar.gz"
    with tarfile.open(path, "w:gz") as handle:
        handle.add(archive, arcname="archive")
    expected = {item.name: item for item in source_manifest(archive)}
    with tarfile.open(path, "r:gz") as handle:
        members = {
            member.name.removeprefix("archive/"): member
            for member in handle.getmembers()
            if member.isfile() and member.name.startswith("archive/")
        }
        if set(members) != set(expected):
            raise MigrationError(f"backup file manifest mismatch: {path}")
        for name, source in expected.items():
            member = members[name]
            extracted = handle.extractfile(member)
            if extracted is None:
                raise MigrationError(f"backup member is unreadable: archive/{name}")
            content = extracted.read()
            if len(content) != source.size or hashlib.sha256(content).hexdigest() != source.sha256:
                raise MigrationError(f"backup checksum mismatch: archive/{name}")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def migrate_archive(
    root: Path,
    *,
    apply: bool,
    backup_root: Path | None = None,
) -> MigrationReport:
    root = Path(root)
    archive = root / "archive"
    if not archive.is_dir():
        raise MigrationError(f"archive directory does not exist: {archive}")

    entries = _entries(archive)
    pending = [path for path in entries if not _is_compact(path)]
    compact = [path for path in entries if _is_compact(path)]
    source_size = sum(item.stat().st_size for path in entries for item in path.rglob("*") if item.is_file())
    issues: list[str] = []
    projected_size = sum((path / "record.md").stat().st_size for path in compact)
    rendered: dict[str, str] = {}
    for path in pending:
        unknown = _unknown(path)
        has_summary = path.joinpath("migration-summary.md").is_file()
        missing_archive_summary = not section(path / "plan.md", "Archive summary")
        if (unknown or missing_archive_summary) and not has_summary:
            reasons = []
            if unknown:
                reasons.append(", ".join(unknown))
            if missing_archive_summary:
                reasons.append("missing Archive summary")
            issues.append(f"{path.name}: needs migration-summary.md for {'; '.join(reasons)}")
            if apply:
                raise MigrationError(issues[-1])
        try:
            record = _render_legacy(path) if not (unknown or missing_archive_summary) or has_summary else ""
        except MigrationError as exc:
            issues.append(str(exc))
            if apply:
                raise
            record = ""
        if record:
            rendered[path.name] = record
            projected_size += len(record.encode("utf-8"))

    if not apply or not pending:
        return MigrationReport(
            len(pending),
            len(compact),
            source_size,
            projected_size,
            None,
            None,
            tuple(issues),
            tuple(sorted(rendered.items())),
        )

    backup_path, backup_sha256 = _backup(
        archive,
        Path(backup_root) if backup_root else root / ".archive-backups",
    )
    staging = Path(tempfile.mkdtemp(prefix=".archive.compact-", dir=root))
    previous = root / f".archive.previous-{uuid.uuid4().hex}"
    try:
        for path in compact:
            shutil.copytree(path, staging / path.name)
        for path in pending:
            target = staging / path.name
            target.mkdir()
            target.joinpath("record.md").write_text(rendered[path.name], encoding="utf-8")
            validate_record(target.joinpath("record.md").read_text(encoding="utf-8"), path.name)
        archive.rename(previous)
        try:
            staging.rename(archive)
        except Exception:
            previous.rename(archive)
            raise
        shutil.rmtree(previous)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return MigrationReport(
        len(pending),
        len(compact),
        source_size,
        projected_size,
        backup_path,
        backup_sha256,
        tuple(issues),
        tuple(sorted(rendered.items())),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Artifact root relative to the current repository (default: resolved, see specadoc_root.py)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path)
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
        report = migrate_archive(Path(choice.path), apply=args.apply, backup_root=args.backup_root)
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    action = "migrated" if args.apply else "would migrate"
    print(f"{action}: {report.pending_count}; already compact: {report.compact_count}")
    print(f"projected size: {report.source_size} -> {report.projected_size} bytes")
    for issue in report.issues:
        print(f"warning: {issue}")
    if not args.apply:
        for slug, record in report.previews:
            print(f"--- archive/{slug}/record.md ---")
            print(record.rstrip())
    if report.backup_path:
        print(f"backup: {report.backup_path}")
        print(f"backup sha256: {report.backup_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
