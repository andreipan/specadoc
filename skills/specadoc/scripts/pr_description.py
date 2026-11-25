#!/usr/bin/env python3
"""Write a pull or merge request description from archive records and the diff.

  python3 pr_description.py --range BASE..HEAD [--root DIR] [--output FILE]
  python3 pr_description.py --slug SLUG [--slug SLUG ...] [--root DIR] [--output FILE]

Run it from the repository root. With `--range`, the records are the
`<root>/archive/<slug>/record.md` files that the range adds or changes, read
as they are at HEAD, and the description ends with diff facts: size,
migrations, lock files, configuration and how to roll back. With `--slug`,
the records are read from the working tree and there are no diff facts.

The description holds, per record: the goal, what changed, the verification
(commands, requirement mapping, review rounds), residual risks and the record
path. It reads only; it never calls a forge. Exit code 0 on success, 1 when the
range has no archive record or git fails, 2 on bad arguments.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from specadoc_root import resolve_root  # noqa: E402

MEASUREMENT_LABELS = (
    "Commands",
    "Requirement mapping",
    "Execution tokens",
    "Review rounds",
    "Design rounds",
    "Residual risks or waivers",
)
MAX_COMMANDS = 8
LOCK_FILE = re.compile(r"(?:^|/)[^/]*(?:\.lock|-lock\.json|-lock\.yaml|\.lockb)$")
CONFIG_FILE = re.compile(r"(?:^|/)(?:config|conf|settings)/|(?:^|/)\.env\.[^/]+$")
MIGRATION_PART = re.compile(r"(?:^|/)(?:migrations?|migrate)/")


class DescriptionError(RuntimeError):
    pass


class Record(NamedTuple):
    slug: str
    path: str
    text: str


class DiffFacts(NamedTuple):
    files: int
    added: int
    deleted: int
    migrations: tuple[str, ...]
    lock_files: tuple[str, ...]
    config: tuple[str, ...]


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise DescriptionError(f"git {' '.join(args)}: {result.stderr.strip() or 'failed'}")
    return result.stdout


def split_range(value: str) -> tuple[str, str]:
    if "..." in value or value.count("..") != 1:
        raise DescriptionError(f"--range must be BASE..HEAD, got {value!r}")
    base, head = value.split("..")
    if not base or not head:
        raise DescriptionError(f"--range must name both ends, got {value!r}")
    return base, head


def record_pattern(root: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(root)}/archive/([^/]+)/record\.md$")


def records_in_range(root: str, base: str, head: str) -> list[Record]:
    pattern = record_pattern(root)
    names = git("diff", "--name-only", "--diff-filter=AM", f"{base}...{head}").splitlines()
    records = []
    for name in names:
        if match := pattern.match(name):
            records.append(Record(match.group(1), name, git("show", f"{head}:{name}")))
    return records


def records_from_tree(root: str, slugs: list[str]) -> list[Record]:
    records = []
    for slug in slugs:
        path = Path(root) / "archive" / slug / "record.md"
        if not path.is_file():
            raise DescriptionError(f"{path}: no archive record")
        records.append(Record(slug, path.as_posix(), path.read_text(encoding="utf-8")))
    return records


def sections(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                found[current] = "\n".join(lines).strip()
            current, lines = line[3:].strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        found[current] = "\n".join(lines).strip()
    return found


def paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", text.strip())
    return [" ".join(line.strip() for line in block.splitlines()) for block in blocks if block.strip()]


def measurement(text: str) -> dict[str, list[str]]:
    fence = re.search(r"```[a-z]*\n(.*?)```", text, re.S)
    body = fence.group(1) if fence else text
    found: dict[str, list[str]] = {}
    current = None
    for raw in body.splitlines():
        line = raw.strip()
        label = next((name for name in MEASUREMENT_LABELS if line.startswith(f"{name}:")), None)
        if label:
            current = label
            rest = line[len(label) + 1:].strip()
            found[current] = [rest] if rest else []
        elif current and line:
            found[current].append(line)
    return found


def mapping_summary(lines: list[str]) -> str | None:
    rows = [line for line in lines if re.match(r"^R\d+\b", line)]
    if not rows:
        return None
    unresolved = [row.split()[0] for row in rows if not re.search(r":\s*PASS\s*$", row)]
    text = f"{len(rows)} requirements, {len(rows) - len(unresolved)} PASS"
    if unresolved:
        text += f"; no recorded result for {', '.join(unresolved)}"
    return text


def test_commands(lines: list[str]) -> list[str]:
    seen: list[str] = []
    for line in lines:
        for command in re.findall(r"`([^`]+)`", line):
            if command not in seen:
                seen.append(command)
    return seen


def residual_risks(parts: dict[str, str], measured: dict[str, list[str]]) -> str:
    if lines := measured.get("Residual risks or waivers"):
        return " ".join(lines)
    for paragraph in paragraphs(parts.get("Outcome", "")):
        if paragraph.startswith("Residual risks:"):
            return paragraph[len("Residual risks:"):].strip()
    return "None recorded."


def changes(parts: dict[str, str]) -> str | None:
    outcome = paragraphs(parts.get("Outcome", ""))
    if not outcome:
        return None
    first = outcome[0]
    return first[len("Outcome:"):].strip() if first.startswith("Outcome:") else first


def render_record(record: Record, heading: bool) -> list[str]:
    parts = sections(record.text)
    measured = measurement(parts.get("Measurement", ""))
    out: list[str] = []
    if heading:
        out += [f"### {record.slug}", ""]
    if goal := " ".join(paragraphs(parts.get("Goal", ""))):
        out += [f"**Goal.** {goal}", ""]
    if changed := changes(parts):
        out += [f"**Changes.** {changed}", ""]
    out.append("**Verification.**")
    out += [f"- {line}" for line in measured.get("Commands", [])]
    mapping = measured.get("Requirement mapping", [])
    if summary := mapping_summary(mapping):
        out.append(f"- Requirement mapping: {summary}.")
    commands = test_commands(mapping)
    if commands:
        shown = ", ".join(f"`{command}`" for command in commands[:MAX_COMMANDS])
        more = len(commands) - MAX_COMMANDS
        out.append(f"- Test commands: {shown}" + (f", and {more} more." if more > 0 else "."))
    for label in ("Design rounds", "Review rounds"):
        if lines := measured.get(label):
            out.append(f"- {label}: {'; '.join(lines)}.")
    if result := re.search(r"^\*\*Result:\*\*\s*(\S+)", parts.get("Review", ""), re.M):
        out.append(f"- Final review: {result.group(1)}.")
    out += ["", f"**Residual risks.** {residual_risks(parts, measured)}", ""]
    out += [f"**Record:** `{record.path}`", ""]
    return out


def diff_facts(base: str, head: str) -> DiffFacts:
    added = deleted = 0
    names: list[str] = []
    for line in git("diff", "--numstat", f"{base}...{head}").splitlines():
        plus, minus, name = line.split("\t", 2)
        names.append(name)
        if plus != "-":
            added += int(plus)
            deleted += int(minus)
    return DiffFacts(
        files=len(names),
        added=added,
        deleted=deleted,
        migrations=tuple(n for n in names if MIGRATION_PART.search(n)),
        lock_files=tuple(n for n in names if LOCK_FILE.search(n)),
        config=tuple(n for n in names if CONFIG_FILE.search(n)),
    )


def listed(names: tuple[str, ...]) -> str:
    return ", ".join(f"`{name}`" for name in names) if names else "none"


def render_diff(facts: DiffFacts) -> list[str]:
    if facts.migrations:
        rollback = ("revert the request. A revert does not undo applied migrations: "
                    "check that each one can be rolled back, and roll it back first.")
    else:
        rollback = "revert the request; it touches no migration."
    return [
        "### Deploy and rollback",
        "",
        f"- Diff: {facts.files} files, +{facts.added} −{facts.deleted} lines.",
        f"- Migrations: {listed(facts.migrations)}.",
        f"- Lock files: {listed(facts.lock_files)}.",
        f"- Configuration: {listed(facts.config)}.",
        f"- Rollback: {rollback}",
        "",
    ]


def describe(records: list[Record], facts: DiffFacts | None) -> str:
    out: list[str] = []
    for record in records:
        out += render_record(record, heading=len(records) > 1)
    if facts is not None:
        out += render_diff(facts)
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a pull or merge request description from archive records.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--range", metavar="BASE..HEAD", help="git range of the request; records it adds or changes")
    source.add_argument("--slug", action="append", help="archive record slug in the working tree (repeatable)")
    parser.add_argument("--root", help="artifact root (default: resolved)")
    parser.add_argument("--output", help="write the description to this file instead of stdout")
    args = parser.parse_args(argv)
    root = resolve_root(args.root).path
    try:
        if args.range:
            base, head = split_range(args.range)
            records = records_in_range(root, base, head)
            if not records:
                raise DescriptionError(f"{args.range}: no {root}/archive/<slug>/record.md added or changed")
            text = describe(records, diff_facts(base, head))
        else:
            text = describe(records_from_tree(root, args.slug), None)
    except DescriptionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
