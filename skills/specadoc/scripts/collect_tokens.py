#!/usr/bin/env python3
"""Aggregate per-execution token counters for one delivery change.

Three harnesses, one row shape. See references/measurement.md.

    collect_tokens.py <slug> --mode apply --harness claude   <session.jsonl|project-dir>...
    collect_tokens.py <slug> --mode apply --harness codex    <rollout.jsonl|dir>...
    collect_tokens.py <slug> --mode apply --harness opencode --directory <repo path>

An *execution* is one run: a controller transcript or one child agent. Its
counters are read once, at their final value, and never summed across snapshots
inside the same run.

Two aggregates are reported, and they answer different questions:

- `unique`  = uncached input + cache writes + output. New tokens that entered a
  transcript.
- `read`    = cached input. The same context re-sent turn after turn. It tracks
  turn count more than content, and it dominates provider billing.

Numbers are reported context volume, not provider billing, and they are not
comparable across harnesses: cache semantics, models, and system prompts differ.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402
from validate_change import PLACEHOLDER  # noqa: E402

CODEX_FILENAME_ID = re.compile(r"rollout-[\dT-]+-(?P<id>[0-9a-f-]{36})\.jsonl$")


@dataclass
class Execution:
    """One run. A resumed session writes a second transcript whose counter
    restarts, so the run — not the session — is the unit that gets summed."""

    harness: str
    execution_id: str
    role: str = "controller"
    parent: str = "-"
    directory: str = ""
    uncached_input: int = 0
    cached_input: int = 0
    cache_write: int = 0
    output: int = 0
    reasoning: int = 0
    requests: int = 0
    cost: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def unique(self) -> int:
        return self.uncached_input + self.cache_write + self.output

    @property
    def read(self) -> int:
        return self.cached_input

    def row(self) -> str:
        cost = f" cost={self.cost:.2f}" if self.cost else ""
        return (
            f"{self.harness} {self.execution_id} role={self.role} parent={self.parent} "
            f"unique={self.unique} read={self.read} "
            f"in={self.uncached_input} cw={self.cache_write} out={self.output} "
            f"reasoning={self.reasoning} reqs={self.requests}{cost}"
        )


# --------------------------------------------------------------------- claude

def _claude_scan(path: Path, execution: Execution) -> bool:
    """One API response is written as several lines, one per content block, each
    carrying the same usage. Deduplicating on requestId is mandatory."""
    seen: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "assistant":
                continue
            if not execution.directory:
                execution.directory = record.get("cwd", "")
            request_id = record.get("requestId")
            if not request_id or request_id in seen:
                continue
            seen.add(request_id)
            usage = (record.get("message") or {}).get("usage") or {}
            execution.uncached_input += usage.get("input_tokens", 0)
            execution.cache_write += usage.get("cache_creation_input_tokens", 0)
            execution.cached_input += usage.get("cache_read_input_tokens", 0)
            execution.output += usage.get("output_tokens", 0)
            execution.reasoning += (usage.get("output_tokens_details") or {}).get(
                "thinking_tokens", 0
            )
    execution.requests = len(seen)
    return bool(seen)


def collect_claude(sources: list[Path]) -> list[Execution]:
    transcripts: list[Path] = []
    for source in sources:
        if source.is_dir():
            transcripts.extend(sorted(source.glob("*.jsonl")))
        else:
            transcripts.append(source)

    executions: list[Execution] = []
    for transcript in transcripts:
        if not transcript.is_file():
            print(f"warning: not a file: {transcript}", file=sys.stderr)
            continue
        controller = Execution("claude", transcript.stem[:8], role="controller")
        if _claude_scan(transcript, controller):
            executions.append(controller)
        else:
            print(f"warning: no usage in {transcript}", file=sys.stderr)
            continue

        # Child agents live in a sibling directory named after the session.
        for child in sorted(transcript.with_suffix("").glob("subagents/*.jsonl")):
            meta_path = child.with_suffix(".meta.json")
            role, description = "subagent", ""
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    role = meta.get("agentType", role)
                    description = meta.get("description", "")
                except (OSError, json.JSONDecodeError):
                    pass
            agent = Execution(
                "claude",
                child.stem.removeprefix("agent-")[:9],
                role=role,
                parent=controller.execution_id,
            )
            if _claude_scan(child, agent):
                if description:
                    agent.notes.append(description)
                executions.append(agent)
    return executions


# ---------------------------------------------------------------------- codex

def collect_codex(sources: list[Path]) -> list[Execution]:
    files: list[Path] = []
    for source in sources:
        if source.is_dir():
            files.extend(sorted(source.rglob("*.jsonl")))
        else:
            files.append(source)

    executions: dict[Path, Execution] = {}
    sessions: dict[str, list[str]] = {}
    for path in files:
        if not path.is_file():
            print(f"warning: not a file: {path}", file=sys.stderr)
            continue
        resolved = path.resolve()
        if resolved in executions:
            continue
        match = CODEX_FILENAME_ID.search(path.name)
        execution = Execution("codex", (match.group("id") if match else path.stem)[:8])
        session_id = ""
        found = False
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"session_meta"' in line and not execution.directory:
                    try:
                        payload = json.loads(line).get("payload", {})
                    except json.JSONDecodeError:
                        continue
                    session_id = payload.get("session_id", "")
                    execution.directory = payload.get("cwd", "")
                    continue
                if "total_token_usage" not in line:
                    continue
                try:
                    payload = json.loads(line).get("payload", {})
                except json.JSONDecodeError:
                    continue
                usage = (payload.get("info") or {}).get("total_token_usage") or {}
                if not isinstance(usage.get("input_tokens"), int):
                    continue
                # Snapshots inside one run are the same running total: overwrite.
                # Codex `input_tokens` INCLUDES the cached part, unlike Claude Code.
                cached = usage.get("cached_input_tokens", 0)
                execution.cached_input = cached
                execution.uncached_input = usage["input_tokens"] - cached
                execution.cache_write = usage.get("cache_write_input_tokens", 0)
                execution.output = usage.get("output_tokens", 0)
                execution.reasoning = usage.get("reasoning_output_tokens", 0)
                found = True
        if not found:
            print(f"warning: no token counter in {path}", file=sys.stderr)
            continue
        executions[resolved] = execution
        if session_id:
            sessions.setdefault(session_id, []).append(execution.execution_id)

    for session_id, runs in sessions.items():
        if len(runs) > 1:
            print(
                f"note: session {session_id} was resumed; {len(runs)} runs counted "
                "separately: " + ", ".join(sorted(runs)),
                file=sys.stderr,
            )
    return list(executions.values())


# ------------------------------------------------------------------- opencode

OPENCODE_DB = Path.home() / ".local/share/opencode/opencode.db"

OPENCODE_QUERY = """
select id, parent_id, agent, directory, tokens_input, tokens_output,
       tokens_reasoning, tokens_cache_read, tokens_cache_write, cost
from session
where directory = ?
order by time_created
"""


def collect_opencode(directory: str, db_path: Path) -> list[Execution]:
    if not db_path.is_file():
        raise SystemExit(f"error: no opencode database at {db_path}")
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(OPENCODE_QUERY, (directory,)).fetchall()
    finally:
        connection.close()

    executions = []
    for (session_id, parent_id, agent, sess_dir, tin, tout, treason,
         tcache_read, tcache_write, cost) in rows:
        executions.append(Execution(
            "opencode",
            session_id[:14],
            role=agent or ("subagent" if parent_id else "controller"),
            parent=(parent_id or "-")[:14],
            directory=sess_dir,
            uncached_input=tin or 0,
            cached_input=tcache_read or 0,
            cache_write=tcache_write or 0,
            output=tout or 0,
            reasoning=treason or 0,
            cost=cost or None,
        ))
    return executions


# ----------------------------------------------------------------------- main

def append_to_plan(plan: Path, rows: list[str], mode: str) -> None:
    lines = plan.read_text(encoding="utf-8").splitlines()
    try:
        label = next(i for i, line in enumerate(lines) if line.strip() == "Execution tokens:")
    except StopIteration:
        raise SystemExit(f"error: {plan} has no `Execution tokens:` block")
    end = label + 1
    while end < len(lines) and lines[end].strip():
        end += 1
    existing = [
        line
        for line in lines[label + 1 : end]
        if not line.startswith(f"mode={mode} ")
        and not line.startswith(f"total mode={mode} ")
        and not PLACEHOLDER.fullmatch(line.strip())
    ]
    plan.write_text(
        "\n".join(lines[: label + 1] + existing + rows + lines[end:]) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sum per-execution token counters for one delivery change.")
    parser.add_argument("change_slug")
    parser.add_argument("sources", nargs="*",
                        help="transcripts or directories (claude, codex)")
    parser.add_argument("--harness", required=True,
                        choices=("claude", "codex", "opencode"))
    parser.add_argument("--mode", required=True,
                        choices=("explore", "propose", "apply", "archive"))
    parser.add_argument("--directory",
                        help="opencode: the repository path a session ran in")
    parser.add_argument("--db", type=Path, default=OPENCODE_DB,
                        help="opencode: database location")
    parser.add_argument("--root", help="Artifact root relative to the current repository (default: resolved, see specadoc_root.py)")
    parser.add_argument("--project", default=str(Path.cwd()),
                        help="warn about executions recorded outside this directory")
    parser.add_argument("--append", action="store_true",
                        help="write the rows into the change's evidence block")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.harness == "opencode":
        if not args.directory:
            raise SystemExit("error: --harness opencode requires --directory")
        executions = collect_opencode(args.directory, args.db)
    else:
        if not args.sources:
            raise SystemExit(f"error: --harness {args.harness} requires transcript paths")
        paths = [Path(source) for source in args.sources]
        executions = (collect_claude(paths) if args.harness == "claude"
                      else collect_codex(paths))

    if not executions:
        print("error: no execution with a token counter", file=sys.stderr)
        return 1

    rows = []
    for execution in sorted(executions, key=lambda item: item.unique, reverse=True):
        if execution.directory and Path(execution.directory) != Path(args.project):
            print(f"warning: {execution.execution_id} ran in {execution.directory}, "
                  f"not {args.project}", file=sys.stderr)
        rows.append(f"mode={args.mode} {execution.row()}")

    unique = sum(execution.unique for execution in executions)
    read = sum(execution.read for execution in executions)
    controllers = [e for e in executions if e.parent == "-"]
    controller_unique = sum(e.unique for e in controllers)
    share = f" controller={controller_unique * 100 // unique}%" if unique else ""
    rows.append(f"total mode={args.mode} {args.harness} {len(executions)} run(s) "
                f"unique={unique} read={read}{share}")

    for row in rows:
        print(row)

    if args.append:
        try:
            choice = resolve_root(args.root)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if warning := legacy_warning(choice):
            print(warning, file=sys.stderr)
        plan = Path(choice.path) / args.change_slug / "plan.md"
        append_to_plan(plan, rows, args.mode)
        print(f"written to {plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
