#!/usr/bin/env python3
"""Append-only coordination log: numbered decisions and one current-state block.

    coordination_log.py decision <file> --title '<title>' --file <path|->
    coordination_log.py state <file> --file <path|->

`decision` appends `### D<n> — <title> (<UTC time>)` after the highest existing
D<n>; earlier entries are never rewritten. `state` replaces only the block
between the current-state markers, created under the first heading when absent.
Both refuse oversized text: the log records verdicts and references, not logs.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DECISION = re.compile(r"^### D(\d+)\b", re.M)
BEGIN, END = "<!-- current-state:begin -->", "<!-- current-state:end -->"
DECISION_LIMIT = 2048
STATE_LIMIT = 1536


def read_text(source: str) -> str:
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    text = "\n".join(line.rstrip() for line in text.strip().splitlines())
    if not text:
        raise ValueError("empty entry")
    return text


def bullets(text: str) -> str:
    return "\n".join(line if line.startswith(("- ", "  ")) or not line else f"- {line}"
                     for line in text.splitlines())


def write(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def decision(path: Path, title: str, body: str) -> str:
    if len(body.encode("utf-8")) > DECISION_LIMIT:
        raise ValueError(f"decision is over {DECISION_LIMIT} bytes; cite artifacts instead of pasting evidence")
    title = " ".join(title.split())
    if not title:
        raise ValueError("decision needs a title")
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    number = max((int(n) for n in DECISION.findall(current)), default=0) + 1
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"### D{number} — {title} ({stamp})\n{bullets(body)}\n"
    write(path, (current.rstrip("\n") + "\n\n" if current.strip() else "") + entry)
    return f"D{number}"


def state(path: Path, body: str) -> None:
    if len(body.encode("utf-8")) > STATE_LIMIT:
        raise ValueError(f"current state is over {STATE_LIMIT} bytes; keep only state, blockers and next action")
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    block = f"{BEGIN}\n{bullets(body)}\n{END}"
    if BEGIN in current and END in current:
        head, rest = current.split(BEGIN, 1)
        updated = head + block + rest.split(END, 1)[1]
    else:
        lines = current.splitlines()
        at = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
        updated = "\n".join(lines[:at] + ["", "## Current state", "", block, ""] + lines[at:]).lstrip("\n")
    write(path, updated.rstrip("\n") + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("decision", "state"):
        action = actions.add_parser(name)
        action.add_argument("log", type=Path)
        action.add_argument("--file", required=True, help="Entry text file, or - for stdin")
        if name == "decision":
            action.add_argument("--title", required=True)
    args = parser.parse_args()
    try:
        body = read_text(args.file)
        if args.action == "decision":
            print(f"{decision(args.log, args.title, body)} appended to {args.log}")
        else:
            state(args.log, body)
            print(f"current state replaced in {args.log}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
