#!/usr/bin/env python3
"""Append-only coordination log: numbered decisions and one current-state block.

    coordination_log.py decision <file> --by user|orchestrator --title '<title>' --file <path|->
        [--quote '<the user's words>' [--confirms '<the one proposal a bare go/ok accepted>']]
    coordination_log.py state <file> --file <path|->
    coordination_log.py last <file>
    coordination_log.py get <file> D<n>
    coordination_log.py capsule <file> [--status <status.md>] [--max-lines 60]

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
`capsule` prints a short role reminder for the orchestrator to re-read after a
compaction (week 47: orchestrator sessions compacted at 202-274k and lost their
role): the mandate, the current state, the newest decisions and fixed rules. A
host hook may inject it; without one the orchestrator runs it itself.
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


CAPSULE_BYTES = 4096
MANDATE = re.compile(r"mandat|мандат", re.I)
UNDER = re.compile(r"\b(?:under|по|в рамках) (?:the )?(?:mandate|мандат)", re.I)
CAPSULE_RULES = [
    "## Rules",
    "- You coordinate controllers: do not read repository code, tests or skills and do not run quality tools or "
    "tests yourself; a scout or the integration verifier does, and you read verdicts and cited lines.",
    "- Decide only what the mandate covers (references/checkpoints.md, Decision boundaries); a changed contract, "
    "response code, data, security, money, production, a dependency install or routing goes to the user.",
    "- Record each decision with `coordination_log.py decision <record> --by orchestrator` and cite the D<n> that "
    "`last` or `get` prints, never one from memory.",
    "- One writer per checkout; never edit a controller's active diff or direct its workers.",
    "- Relay a controller's options verbatim; use the question tool only while every child is idle.",
    "- Keep each message to a controller near 150 words: the decision, the checkpoint key and D<n>.",
    "- Next: run `specadoc_step.py status <slug>` for every live controller and reconcile before acting.",
]


def current_block(path: Path) -> list[str]:
    """Lines of the current-state block, or []."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if BEGIN not in text or END not in text:
        return []
    return [line for line in text.split(BEGIN, 1)[1].split(END, 1)[0].strip().splitlines() if line.strip()]


def capsule(path: Path, status: Path | None = None, max_lines: int = 60) -> str:
    """The orchestrator's role reminder: at most `max_lines` lines and CAPSULE_BYTES bytes."""
    if not path.is_file():
        raise ValueError(f"{path} does not exist")
    found = entries(path)
    state_lines = current_block(path)
    if not found and not state_lines:
        raise ValueError(f"{path} has neither decisions nor a current-state block; it is not a coordination record")
    # The mandate is the user's decision that grants it, not the later ones taken "under mandate D<n>"
    # (stage 6: D118 grants it; D125-D150 cite it).
    headers = [(text, text.splitlines()[0]) for _, text in reversed(found)]
    granted = [text for text, header in headers if MANDATE.search(header) and not UNDER.search(header)]
    mandate = next((text for text in granted if "[by user]" in text.splitlines()[0]), None) \
        or next(iter(granted), None) \
        or next((text for text, header in headers if MANDATE.search(header) and "[by user]" in header), None)
    status = status if status is not None else path.with_name("status.md")
    status_lines = current_block(status) if status != path else []
    head = ["# Orchestrator capsule — re-read after a compaction", "",
            f"You are the orchestrator of this run. Record: `{path}`.", ""]
    sections: list[list[str]] = []
    if mandate:
        lines = mandate.splitlines()
        sections.append(["## Mandate", lines[0].removeprefix("### "), *lines[1:7]])
    if state_lines:
        sections.append(["## Current state", *state_lines])
    if status_lines:
        sections.append([f"## Status ({status.name})", *status_lines])
    if found:
        sections.append(["## Newest decisions", *(f"- {text.splitlines()[0].removeprefix('### ')}"
                                                  for _, text in found[-5:])])
    tail = ["", *CAPSULE_RULES]
    budget = max_lines - len(head) - len(tail)

    def render(parts: list[list[str]]) -> list[str]:
        lines: list[str] = []
        for part in parts:
            lines += [*part, ""]
        return lines

    body = render(sections)
    # Trim from the bottom of each long section until the capsule fits: rules and the mandate header stay.
    while (len(body) > budget or len("\n".join(head + body + tail).encode("utf-8")) > CAPSULE_BYTES) and \
            any(len(part) > 2 for part in sections):
        longest = max(sections, key=len)
        longest.pop()
        body = render(sections)
    return "\n".join(head + body + tail).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("decision", "state", "last", "get", "capsule"):
        action = actions.add_parser(name)
        action.add_argument("log", type=Path)
        if name == "capsule":
            action.add_argument("--status", type=Path, help="status.md with its own current-state block "
                                                           "(default: status.md beside the record)")
            action.add_argument("--max-lines", type=int, default=60)
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
        if args.action == "capsule":
            print(capsule(args.log, args.status, args.max_lines), end="")
            return 0
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
