#!/usr/bin/env python3
"""Append-only coordination log: numbered decisions and one current-state block.

    coordination_log.py decision <file> --by user|orchestrator --title '<title>' --file <path|->
        [--quote '<the user's words>' [--confirms '<the one proposal a bare go/ok accepted>']]
    coordination_log.py state <file> --file <path|->
    coordination_log.py last <file>
    coordination_log.py get <file> D<n>

`decision` appends `### D<n> — <title> [by <author>] (<UTC time>)` after the
highest existing D<n>; earlier entries are never rewritten. `--by user` needs
`--quote` with the user's own words; a bare go/ok picks no option, so it needs
`--confirms` naming the single proposal it accepted (5.2: "go" to two options
was logged as a user decision for a third). `--by orchestrator` is a decision
under the mandate.
`last` prints the newest decision's header and `get` one entry, so a message to
a controller cites the number the log assigned (4.1/4.2: D12 sent for D11). `state` replaces only the block
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
BARE = re.compile(r"^(?:go|ok|okay|ок|окей|да|yes|y|ага|угу|давай|го|\+|continue|proceed|продолжай|дальше)$")


def user_words(quote: str | None, confirms: str | None) -> str:
    """The first bullet of a user decision: the user's words, and what a bare go/ok accepted."""
    quote = " ".join((quote or "").split())
    if not quote:
        raise ValueError("--by user needs --quote with the user's own words")
    if BARE.match(quote.lower().strip(" .!«»\"'")):
        confirms = " ".join((confirms or "").split())
        if not confirms:
            raise ValueError(f"«{quote}» picks no option: ask again with the options, or pass --confirms naming "
                             "the single proposal it accepted")
        return f"User: «{quote}» to: {confirms}"
    return f"User: «{quote}»"


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


def decision(path: Path, title: str, body: str, by: str) -> str:
    if len(body.encode("utf-8")) > DECISION_LIMIT:
        raise ValueError(f"decision is over {DECISION_LIMIT} bytes; cite artifacts instead of pasting evidence")
    title = " ".join(title.split())
    if not title:
        raise ValueError("decision needs a title")
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    number = max((int(n) for n in DECISION.findall(current)), default=0) + 1
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"### D{number} — {title} [by {by}] ({stamp})\n{bullets(body)}\n"
    write(path, (current.rstrip("\n") + "\n\n" if current.strip() else "") + entry)
    return f"D{number}"


def entries(path: Path) -> list[tuple[str, str]]:
    """(`D<n>`, entry text) in file order."""
    text = path.read_text(encoding="utf-8")
    starts = [match.start() for match in DECISION.finditer(text)] + [len(text)]
    found = []
    for begin, end in zip(starts, starts[1:]):
        chunk = text[begin:end]
        # An entry ends at the next heading of any level.
        cut = re.search(r"^#{1,3} ", chunk[4:], re.M)
        chunk = chunk[:cut.start() + 4] if cut else chunk
        found.append((f"D{DECISION.match(chunk)[1]}", chunk.rstrip()))
    return found


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
    for name in ("decision", "state", "last", "get"):
        action = actions.add_parser(name)
        action.add_argument("log", type=Path)
        if name in ("decision", "state"):
            action.add_argument("--file", required=True, help="Entry text file, or - for stdin")
        if name == "decision":
            action.add_argument("--title", required=True)
            action.add_argument("--by", required=True, choices=("user", "orchestrator"),
                                help="user: the user's own decision; orchestrator: decided under the mandate")
            action.add_argument("--quote", help="With --by user: the user's own words, verbatim")
            action.add_argument("--confirms", help="With a bare go/ok quote: the single proposal it accepted")
        if name == "get":
            action.add_argument("id", help="Decision id such as D12")
    args = parser.parse_args()
    try:
        if args.action in ("last", "get"):
            found = entries(args.log)
            if args.action == "last":
                if not found:
                    raise ValueError(f"no decisions in {args.log}")
                print(found[-1][1].splitlines()[0].removeprefix("### "))
                return 0
            match = next((text for key, text in found if key == args.id.upper()), None)
            if match is None:
                raise ValueError(f"{args.id} is not in {args.log}; the newest is "
                                 f"{found[-1][0] if found else 'none'}")
            print(match)
            return 0
        body = read_text(args.file)
        if args.action == "decision":
            if args.by == "user":
                body = f"- {user_words(args.quote, args.confirms)}\n{body}"
            print(f"{decision(args.log, args.title, body, args.by)} appended to {args.log}")
        else:
            state(args.log, body)
            print(f"current state replaced in {args.log}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
