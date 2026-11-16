#!/usr/bin/env python3
"""The BA register: one numbered file of questions for the business analyst,
divergences from the sources, and decisions taken without the analyst.

    ba_register.py add <file> --title T --step S --type T --status S [--section H] [--file -|path]
    ba_register.py status <file> <n> --status S [--note TEXT]
    ba_register.py list <file> [--status TEXT]

An item is `## <n>. <title> (<step>)` followed by one line
`**<Type>:** <type> · **<Status>:** <status>`; the labels are taken from the
file's existing items (English for a new file). A number is never reused: the
next one is the largest + 1. `status` rewrites the status in place and keeps the
item; a note is appended to it with the date. Run 6.11-6.15 kept two files
whose items shared the numbers 21-24.
"""
from __future__ import annotations

import argparse
import fcntl
import re
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ITEM = re.compile(r"^## (?P<number>\d+)\. (?P<title>.*)$", re.M)
STATE = re.compile(r"^\*\*(?P<type_label>[^*]+):\*\* (?P<type>.*?) · \*\*(?P<status_label>[^*]+):\*\* (?P<status>.*)$")
BODY_LIMIT = 4096


@contextmanager
def locked(path: Path):
    # The lock lives outside the repository: a `ba-questions.md.lock` beside the register would be an
    # untracked file a `git add -A` can sweep into a commit.
    import hashlib
    key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
    # A fixed directory: a sandboxed session's TMPDIR differs per session and would not exclude the others.
    directory = Path.home() / ".cache" / "ba-register"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{key}.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    temporary.replace(path)


def labels(text: str) -> tuple[str, str]:
    for line in text.splitlines():
        if match := STATE.match(line):
            return match["type_label"], match["status_label"]
    return "Type", "Status"


def items(text: str) -> list[tuple[int, int, int]]:
    """(number, start, end) of each item; an item ends at the next heading of level 1 or 2."""
    found = []
    for match in ITEM.finditer(text):
        following = re.compile(r"^#{1,2} ", re.M).search(text, match.end())
        found.append((int(match["number"]), match.start(), following.start() if following else len(text)))
    return found


def one_line(value: str, name: str) -> str:
    flat = " ".join(value.split())
    if not flat:
        raise ValueError(f"{name} is empty")
    return flat


def add(path: Path, title: str, step: str, kind: str, status: str, section: str | None, body: str) -> int:
    text = path.read_text(encoding="utf-8")
    number = max((n for n, _, _ in items(text)), default=0) + 1
    type_label, status_label = labels(text)
    block = [f"## {number}. {one_line(title, '--title')} ({one_line(step, '--step')})", "",
             f"**{type_label}:** {one_line(kind, '--type')} · **{status_label}:** {one_line(status, '--status')}"]
    if body.strip():
        block += ["", body.strip()]
    entry = "\n".join(block) + "\n"
    if section:
        heading = re.compile(rf"^# {re.escape(section)}\s*$", re.M).search(text)
        if not heading:
            raise ValueError(f"no `# {section}` section in {path}")
        following = re.compile(r"^# ", re.M).search(text, heading.end())
        at = following.start() if following else len(text)
        before = text[:at].rstrip("\n")
        text = before + "\n\n" + entry + ("\n" + text[at:] if following else "")
    else:
        text = text.rstrip("\n") + "\n\n" + entry
    write(path, text)
    return number


def set_status(path: Path, number: int, status: str, note: str | None) -> None:
    text = path.read_text(encoding="utf-8")
    found = next(((start, end) for n, start, end in items(text) if n == number), None)
    if not found:
        raise ValueError(f"no item {number} in {path}")
    start, end = found
    block = text[start:end].rstrip("\n").split("\n")
    index = next((i for i, line in enumerate(block) if STATE.match(line)), None)
    if index is None:
        raise ValueError(f"item {number} has no type and status line")
    match = STATE.match(block[index])
    block[index] = (f"**{match['type_label']}:** {match['type']} · "
                    f"**{match['status_label']}:** {one_line(status, '--status')}")
    if note:
        tail = []
        while block and block[-1].strip() in ("", "---"):  # keep a closing rule after the note
            tail.insert(0, block.pop())
        block += ["", f"- {date.today().isoformat()}: {one_line(note, '--note')}", *tail]
    replacement = "\n".join(block) + "\n" + ("\n" if end < len(text) else "")
    write(path, text[:start] + replacement + text[end:])


def listing(path: Path, status: str | None) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = []
    for number, start, end in items(text):
        block = text[start:end]
        title = ITEM.match(block)["title"]
        state = next((m for line in block.splitlines() if (m := STATE.match(line))), None)
        current = state["status"] if state else "?"
        if status and status.lower() not in current.lower():
            continue
        lines.append(f"{number}. {title} — {current}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    added = sub.add_parser("add")
    added.add_argument("file", type=Path)
    added.add_argument("--title", required=True)
    added.add_argument("--step", required=True)
    added.add_argument("--type", required=True, dest="kind")
    added.add_argument("--status", required=True)
    added.add_argument("--section", help="Top-level `# ` heading to add the item under (default: end of file)")
    added.add_argument("--file", dest="body", help="Item text: a path or - for stdin")
    changed = sub.add_parser("status")
    changed.add_argument("file", type=Path)
    changed.add_argument("number", type=int)
    changed.add_argument("--status", required=True)
    changed.add_argument("--note")
    listed = sub.add_parser("list")
    listed.add_argument("file", type=Path)
    listed.add_argument("--status")
    args = parser.parse_args(argv)
    try:
        if not args.file.is_file():
            raise ValueError(f"no register at {args.file}")
        if args.action == "list":
            print("\n".join(listing(args.file, args.status)) or "no items")
            return 0
        with locked(args.file):
            if args.action == "add":
                body = ""
                if args.body:
                    body = sys.stdin.read() if args.body == "-" else Path(args.body).read_text(encoding="utf-8")
                if len(body.encode("utf-8")) > BODY_LIMIT:
                    raise ValueError(f"item text is over {BODY_LIMIT} bytes; keep the register short")
                number = add(args.file, args.title, args.step, args.kind, args.status, args.section, body)
                print(f"added {number}")
            else:
                set_status(args.file, args.number, args.status, args.note)
                print(f"updated {args.number}")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
