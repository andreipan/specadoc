#!/usr/bin/env python3
"""Move the Specadoc artifact root and rewrite root references inside it.

Dry-run by default. With ``--apply`` the directory is moved (``git mv`` inside a
git work tree, a plain move otherwise) and every literal ``<from>/`` in the moved
Markdown files becomes ``<to>/``. Archive record hashes describe the source
artifacts at archive time, so rewriting record text does not invalidate them.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import DEFAULT_ROOT, LEGACY_ROOT  # noqa: E402


class MigrationError(Exception):
    pass


class RootMigration(NamedTuple):
    source: Path
    target: Path
    rewrites: tuple[tuple[Path, int], ...]
    moved_with_git: bool


def _in_git(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _rewrites(directory: Path, old: str, new: str) -> list[tuple[Path, str, int]]:
    changes = []
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count:
            changes.append((path, text.replace(old, new), count))
    return changes


def migrate_root(source: str, target: str, *, apply: bool = False, cwd: Path | None = None) -> RootMigration:
    base = cwd or Path.cwd()
    source = source.strip().rstrip("/")
    target = target.strip().rstrip("/")
    src = base / source
    dst = base / target
    if not src.is_dir():
        raise MigrationError(f"nothing to migrate: `{source}` is not a directory")
    if dst.exists():
        raise MigrationError(f"target `{target}` already exists; merge it manually")

    old, new = f"{source}/", f"{target}/"
    planned = _rewrites(src, old, new)
    use_git = _in_git(base)
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if use_git:
            # Untracked files stay behind under `git mv`; -k skips them, so move the rest after.
            subprocess.run(["git", "-C", str(base), "mv", "-k", source, target], check=True)
        if src.exists():
            dst.mkdir(parents=True, exist_ok=True)
            for item in sorted(src.rglob("*"), reverse=True):
                relative = item.relative_to(src)
                if item.is_file() or item.is_symlink():
                    (dst / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(dst / relative))
            shutil.rmtree(src)
        for path, text, _ in planned:
            (dst / path.relative_to(src)).write_text(text, encoding="utf-8")

    return RootMigration(
        src,
        dst,
        tuple((dst / path.relative_to(src) if apply else path, count) for path, _, count in planned),
        use_git,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", default=LEGACY_ROOT, help=f"current root (default: {LEGACY_ROOT})")
    parser.add_argument("--to", dest="target", default=DEFAULT_ROOT, help=f"new root (default: {DEFAULT_ROOT})")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_root(args.source, args.target, apply=args.apply)
    except (MigrationError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    verb = "moved" if args.apply else "would move"
    how = "git mv" if result.moved_with_git else "move"
    print(f"{verb} ({how}): {args.source} -> {args.target}")
    for path, count in result.rewrites:
        print(f"- rewrote {count} reference(s) in {path}")
    print(f"files with rewritten references: {len(result.rewrites)}")
    if not args.apply:
        print("dry run: re-run with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
