#!/usr/bin/env python3
"""Every active change's `status --json` in one read-only call, for a dashboard or driver.

  python3 list_changes.py [--root DIR]     # run from the repository root

Prints one JSON object: `{root, active: [<status object> + updated_at], archived: N}`.
An active change is a directory under the root with a `plan.md` (not `archive/`,
`specs/`, `contracts/`). A change whose status fails is listed with `result: "error"`;
the others are still printed. No controller transcript is read (`context.tokens` is 0),
and nothing is written.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from specadoc_root import resolve_root  # noqa: E402

RESERVED = ("archive", "specs", "contracts")


def newest_mtime(directory: Path) -> int:
    times = [p.stat().st_mtime for p in directory.rglob("*") if p.is_file()]
    return int(max(times, default=directory.stat().st_mtime))


def change_status(slug: str, root: str) -> dict:
    from specadoc_step import status

    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            status(slug, root, None, 0, as_json=True)
        return json.loads(out.getvalue())
    except Exception as exc:  # one broken change must not hide the others
        return {"change": slug, "result": "error", "error": f"{type(exc).__name__}: {exc}"}


def list_changes(root_arg: str | None = None) -> dict:
    root = resolve_root(root_arg).path
    base = Path(root)
    active = []
    if base.is_dir():
        for change in sorted(p for p in base.iterdir() if p.is_dir() and p.name not in RESERVED):
            if not (change / "plan.md").is_file():
                continue
            active.append({**change_status(change.name, root), "updated_at": newest_mtime(change)})
    archive = base / "archive"
    archived = sum(1 for p in archive.glob("*/record.md")) if archive.is_dir() else 0
    return {"root": root, "active": active, "archived": archived}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Specadoc root (default: the usual root resolution)")
    args = parser.parse_args(argv)
    print(json.dumps(list_changes(args.root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
