#!/usr/bin/env python3
"""Initialize Specadoc proposal artifacts in a target repository."""

from __future__ import annotations

import argparse
import errno
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402

VALID_RISKS = ("low", "medium", "high")
# Errors from filesystems that cannot create hard links (FAT/exFAT, some SMB/FUSE).
NO_HARDLINK_ERRNOS = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS}


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("change slug must contain at least one letter or digit")
    return slug


def title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))


def render(template: str, title: str, risk: str) -> str:
    return (
        template.replace("__CHANGE_TITLE__", title)
        .replace("__RISK__", risk.capitalize())
        .replace("__DATE__", date.today().isoformat())
    )


def publish_exclusive(source: Path, destination: Path) -> None:
    """Publish without clobbering: hard link, else exclusive create where links are unsupported."""
    try:
        os.link(source, destination)
        return
    except OSError as error:
        if error.errno not in NO_HARDLINK_ERRNOS:
            raise
    # Exclusive create still refuses an existing file; only the write is not atomic.
    handle = destination.open("xb")
    try:
        with handle:
            handle.write(source.read_bytes())
    except OSError:
        destination.unlink(missing_ok=True)
        raise


def publish_templates(
    files: list[tuple[Path, Path]],
    title: str,
    risk: str,
    force: bool,
) -> None:
    """Preflight the complete set, stage, then publish with handled-error rollback.

    This is not a multi-file transaction across process crashes. If rollback
    itself fails, retain staged backups and report their location for recovery.
    """
    contents = []
    for template, destination in files:
        if not template.is_file():
            raise FileNotFoundError(f"missing bundled template: {template}")
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise OSError(f"refusing non-regular artifact: {destination}")
        if destination.exists() and not force:
            raise FileExistsError(f"refusing to overwrite existing file: {destination}")
        contents.append(render(template.read_text(encoding="utf-8"), title, risk))

    target = files[0][1].parent
    created_dirs = []
    ancestor = target
    while not ancestor.exists():
        created_dirs.append(ancestor)
        ancestor = ancestor.parent
    stage = None
    published = []
    backups = {}
    try:
        target.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".specadoc-init-", dir=target))
        for index, ((_, destination), content) in enumerate(zip(files, contents)):
            (stage / f"new-{index}").write_text(content, encoding="utf-8")
            if destination.exists():
                backup = stage / f"old-{index}"
                shutil.copy2(destination, backup)
                backups[destination] = backup
        for index, (_, destination) in enumerate(files):
            staged = stage / f"new-{index}"
            if force:
                os.replace(staged, destination)
            else:
                # No-clobber publication, including a post-preflight race.
                publish_exclusive(staged, destination)
            published.append(destination)
    except OSError as error:
        try:
            for destination in reversed(published):
                if destination in backups:
                    os.replace(backups[destination], destination)
                else:
                    destination.unlink()
        except OSError as rollback_error:
            raise OSError(
                f"{error}; rollback failed: {rollback_error}; recovery files: {stage}"
            ) from rollback_error
        if stage is not None:
            shutil.rmtree(stage)
        for directory in created_dirs:
            try:
                directory.rmdir()
            except OSError:
                # Another process may have populated a newly created directory.
                # Preserve its files and do not obscure the publication error.
                break
        raise
    else:
        shutil.rmtree(stage)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create spec.md and plan.md for a Specadoc proposal."
    )
    parser.add_argument("change_slug", help="Change name, normalized to kebab-case")
    parser.add_argument(
        "--root",
        help="Artifact root relative to the current repository (default: resolved, see specadoc_root.py)",
    )
    parser.add_argument("--risk", choices=VALID_RISKS, default="medium")
    parser.add_argument("--with-design", action="store_true")
    parser.add_argument("--with-research", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        slug = normalize_slug(args.change_slug)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        choice = resolve_root(args.root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if warning := legacy_warning(choice):
        print(warning, file=sys.stderr)

    skill_root = Path(__file__).resolve().parent.parent
    assets = skill_root / "assets"
    target = Path(choice.path).resolve() / slug
    title = title_from_slug(slug)

    files = [
        (assets / "spec-template.md", target / "spec.md"),
        (assets / "plan-template.md", target / "plan.md"),
    ]
    if args.with_design:
        files.append((assets / "design-template.md", target / "design.md"))
    if args.with_research:
        files.append((assets / "research-template.md", target / "research.md"))

    try:
        publish_templates(files, title, args.risk, args.force)
    except (FileExistsError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"root: {choice.path} ({choice.source})")
    print(f"created change artifacts in {target}")
    for _, destination in files:
        print(f"- {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
