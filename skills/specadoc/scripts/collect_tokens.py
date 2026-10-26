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
import contextlib
import io
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402
from validate_change import PLACEHOLDER  # noqa: E402

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
    requests: dict[str, dict[str, int]] = {}
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
            if not request_id:
                continue
            usage = (record.get("message") or {}).get("usage") or {}
            if not usage:
                continue
            counters = {
                "uncached_input": usage.get("input_tokens", 0),
                "cache_write": usage.get("cache_creation_input_tokens", 0),
                "cached_input": usage.get("cache_read_input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "reasoning": (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0),
            }
            previous = requests.setdefault(request_id, {})
            # Streaming blocks can contain partial usage before the final response.
            for key, value in counters.items():
                previous[key] = max(previous.get(key, 0), value or 0)
    for counters in requests.values():
        for key, value in counters.items():
            setattr(execution, key, getattr(execution, key) + value)
    execution.requests = len(requests)
    return bool(requests)


def collect_claude(sources: list[Path]) -> list[Execution]:
    transcripts: list[Path] = []
    for source in sources:
        if source.is_dir():
            transcripts.extend(sorted(source.glob("*.jsonl")))
        else:
            transcripts.append(source)

    # Discover all children before scanning so explicit paths (in either order),
    # repeated directories and symlinks cannot turn a child into a controller.
    discovered: dict[Path, None] = {}
    for transcript in transcripts:
        if not transcript.is_file():
            print(f"warning: not a file: {transcript}", file=sys.stderr)
            continue
        discovered[transcript.resolve()] = None
        for child in sorted(transcript.with_suffix("").glob("subagents/*.jsonl")):
            discovered[child.resolve()] = None

    executions: list[Execution] = []
    for transcript in discovered:
        is_child = transcript.parent.name == "subagents"
        role, description = ("subagent" if is_child else "controller"), ""
        if is_child:
            meta_path = transcript.with_suffix(".meta.json")
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    role = meta.get("agentType", role)
                    description = meta.get("description", "")
                except (OSError, json.JSONDecodeError):
                    pass
        execution = Execution(
            "claude", transcript.stem.removeprefix("agent-") if is_child else transcript.stem,
            role=role, parent=transcript.parent.parent.name if is_child else "-",
        )
        if _claude_scan(transcript, execution):
            if description:
                execution.notes.append(description)
            executions.append(execution)
        else:
            print(f"warning: no usage in {transcript}", file=sys.stderr)
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
        execution = Execution("codex", path.stem)
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
from {table}
where directory = ?
{authoritative}
order by time_created
"""


def collect_opencode(directory: str, db_path: Path,
                     root_sessions: list[str] | None = None) -> list[Execution]:
    if not db_path.is_file():
        raise SystemExit(f"error: no opencode database at {db_path}")
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in connection.execute(
            "select name from sqlite_master where type='table'")}
        rows_by_id = {}
        # The V2 snapshot replaces, rather than adds to, its legacy copy.
        for table in ("session", "session_v2"):
            if table in tables:
                authoritative = ("and not exists (select 1 from session_v2 "
                                 "where session_v2.id = session.id)"
                                 if table == "session" and "session_v2" in tables else "")
                for row in connection.execute(OPENCODE_QUERY.format(
                        table=table, authoritative=authoritative), (directory,)):
                    rows_by_id[row[0]] = row
        if not tables.intersection({"session", "session_v2"}):
            raise SystemExit("error: no supported OpenCode session table")
    finally:
        connection.close()

    if root_sessions:
        selected = set(root_sessions).intersection(rows_by_id)
        for missing in sorted(set(root_sessions) - selected):
            print(f"warning: session {missing} not found in {directory}", file=sys.stderr)
        while True:
            descendants = {ident for ident, row in rows_by_id.items() if row[1] in selected}
            if descendants <= selected:
                break
            selected.update(descendants)
        rows_by_id = {ident: row for ident, row in rows_by_id.items() if ident in selected}
    else:
        print("warning: no --session filter; counting all sessions in the directory", file=sys.stderr)

    executions = []
    for (session_id, parent_id, agent, sess_dir, tin, tout, treason,
         tcache_read, tcache_write, cost) in rows_by_id.values():
        executions.append(Execution(
            "opencode",
            session_id,
            role=agent or ("subagent" if parent_id else "controller"),
            parent=parent_id or "-",
            directory=sess_dir,
            uncached_input=tin or 0,
            cached_input=tcache_read or 0,
            cache_write=tcache_write or 0,
            output=tout or 0,
            reasoning=treason or 0,
            cost=cost or None,
        ))
    return executions


# --------------------------------------------------------------- external runs

def collect_external_runs(sources: list[Path]) -> list[Execution]:
    """Read settled run_role records; their logs may already have been truncated.

    Identity includes the full log/result location and start marker, not a short
    task basename. Copies of the same record therefore count only once.
    """
    executions = []
    seen = set()
    for source in sources:
        try:
            record = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("expected a run object")

            def run_path(key: str) -> Path:
                path = Path(record[key])
                return path.resolve() if path.is_absolute() else (source.parent / path).resolve()

            runtime = record.get("runtime")
            if runtime not in {"codex", "claude", "opencode"}:
                raise ValueError(f"unsupported runtime {runtime!r}")
            if run_path("exit").read_text(encoding="utf-8").strip() != "0":
                raise ValueError("run did not exit successfully")
            if not run_path("result").is_file():
                raise ValueError("missing run result")
            usage = record.get("usage")
            input_key = "input" if runtime == "opencode" else "input_tokens"
            if (not isinstance(usage, dict) or not isinstance(usage.get(input_key), int)
                    or isinstance(usage[input_key], bool)):
                raise ValueError("missing or unrecognized usage counters")
            counter_keys = {
                "input", "output", "reasoning", "cache.read", "cache.write",
                "input_tokens", "output_tokens", "cached_input_tokens",
                "cache_read_input_tokens", "cache_creation_input_tokens",
                "cache_write_input_tokens", "reasoning_output_tokens",
                "output_tokens_details.thinking_tokens",
            }
            for key in counter_keys.intersection(usage):
                value = usage[key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"invalid usage counter {key}")
            if runtime == "codex" and usage.get("cached_input_tokens", 0) > usage["input_tokens"]:
                raise ValueError("cached input exceeds total input")
            identity = (runtime, str(run_path("log") if record.get("log") else run_path("result")),
                        record.get("started"), record.get("pid"))
            if identity in seen:
                continue
            seen.add(identity)
            execution = Execution(
                runtime, f"external:{identity[1]}@{identity[2]}:{identity[3]}",
                role=record.get("role") or "subagent", parent=record.get("parent_id") or "external",
                directory=record.get("cwd", ""),
            )
            if runtime == "opencode":
                # OpenCode input is already uncached, just like native DB counters.
                execution.uncached_input = usage["input"]
                execution.cached_input = usage.get("cache.read", 0)
                execution.cache_write = usage.get("cache.write", 0)
                execution.output = usage.get("output", 0)
                execution.reasoning = usage.get("reasoning", 0)
            else:
                execution.cached_input = usage.get(
                    "cached_input_tokens" if runtime == "codex" else "cache_read_input_tokens", 0)
                execution.uncached_input = usage["input_tokens"] - (
                    execution.cached_input if runtime == "codex" else 0)
                execution.cache_write = usage.get(
                    "cache_write_input_tokens" if runtime == "codex" else "cache_creation_input_tokens", 0)
                execution.output = usage.get("output_tokens", 0)
                execution.reasoning = usage.get(
                    "reasoning_output_tokens" if runtime == "codex"
                    else "output_tokens_details.thinking_tokens", 0)
            executions.append(execution)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"warning: external run {source}: {exc}", file=sys.stderr)
    return executions


# ----------------------------------------------------------------------- main

def append_to_plan(plan: Path, rows: list[str], mode: str,
                   harness: str | None = None) -> None:
    if "archive" in plan.resolve().parts:
        raise SystemExit("error: refusing to rewrite archived token history")
    if harness is None:
        # Older callers pass only mode; infer the owner from normal row shapes.
        for row in rows:
            match = re.match(r"(?:total )?mode=\S+ (claude|codex|opencode)(?: |$)", row)
            if match:
                harness = match.group(1)
                break
    lines = plan.read_text(encoding="utf-8").splitlines()
    try:
        label = next(i for i, line in enumerate(lines) if line.strip() == "Execution tokens:")
    except StopIteration:
        raise SystemExit(f"error: {plan} has no `Execution tokens:` block")
    end = label + 1
    while end < len(lines) and lines[end].strip():
        end += 1
    def replaces(line: str) -> bool:
        if not (line.startswith(f"mode={mode} ") or line.startswith(f"total mode={mode} ")):
            return False
        if harness is None:  # Compatibility for callers using the original API.
            return True
        ledger = re.search(r"(?:^| )ledger=(\S+)", line)
        if ledger:
            return ledger.group(1) == harness
        prefix = f"total mode={mode} " if line.startswith("total ") else f"mode={mode} "
        return line[len(prefix):].split(" ", 1)[0] == harness

    existing = [
        line
        for line in lines[label + 1 : end]
        if not replaces(line)
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
    parser.add_argument("--session", "--root-session", action="append", default=[],
                        help="opencode: include this session and descendants; repeat for resumed roots")
    parser.add_argument("--external-run", type=Path, action="append", default=[],
                        help="settled run_role .run.json record; repeat for each external execution")
    status = parser.add_mutually_exclusive_group()
    status.add_argument("--final", action="store_true", help="mark the collection final")
    status.add_argument("--provisional", action="store_true", help="mark provisional (default)")
    parser.add_argument("--root", help="Artifact root relative to the current repository (default: resolved, see specadoc_root.py)")
    parser.add_argument("--project", default=str(Path.cwd()),
                        help="warn about executions recorded outside this directory")
    parser.add_argument("--append", action="store_true",
                        help="write the rows into the change's evidence block")
    return parser


def current_claude_transcript() -> Path | None:
    """The transcript of the Claude Code session running this command, if any."""
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not re.fullmatch(r"[0-9A-Za-z-]+", session):
        return None
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    return next(iter(sorted((home / "projects").glob(f"*/{session}.jsonl"))), None)


def claude_context_tokens(path: Path) -> int | None:
    """Input context of the latest main-thread request: uncached + cache write + cache read."""
    latest = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if '"usage"' not in line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "assistant" or record.get("isSidechain"):
                continue
            usage = (record.get("message") or {}).get("usage") or {}
            if usage:
                latest = sum(usage.get(key) or 0 for key in
                             ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return latest


def latest_claude_transcript(project: str) -> Path | None:
    """This session's transcript, else the newest one recorded for this project directory."""
    if (current := current_claude_transcript()) is not None:
        return current
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    directory = home / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path(project).resolve()))
    transcripts = sorted(directory.glob("*.jsonl"), key=lambda path: path.stat().st_mtime) if directory.is_dir() else []
    return transcripts[-1] if transcripts else None


def _collect(args: argparse.Namespace) -> list[Execution]:
    if args.harness == "opencode":
        if not args.directory and not args.external_run:
            raise SystemExit("error: --harness opencode requires --directory")
        executions = (collect_opencode(args.directory, args.db, args.session)
                      if args.directory else [])
    else:
        if not args.sources and not args.external_run and args.harness == "claude":
            if transcript := latest_claude_transcript(args.project):
                print(f"warning: no transcript given; using the newest session {transcript} and its subagents",
                      file=sys.stderr)
                args.sources = [str(transcript)]
        if not args.sources and not args.external_run:
            raise SystemExit(f"error: --harness {args.harness} requires transcript paths")
        paths = [Path(source) for source in args.sources]
        executions = (collect_claude(paths) if args.harness == "claude"
                       else collect_codex(paths))
    executions.extend(collect_external_runs(args.external_run))
    return executions


def main() -> int:
    args = build_parser().parse_args()
    diagnostics = io.StringIO()
    try:
        with contextlib.redirect_stderr(diagnostics):
            executions = _collect(args)
    finally:
        sys.stderr.write(diagnostics.getvalue())
    if args.final and "warning:" in diagnostics.getvalue():
        print("error: final collection has missing, unscoped or incomplete inputs; inspect warnings or collect provisionally", file=sys.stderr)
        return 2

    if not executions:
        print("error: no execution with a token counter", file=sys.stderr)
        return 1

    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = (f"ledger={args.harness} collected_at={collected_at} "
                f"status={'final' if args.final else 'provisional'}")
    rows = []
    for execution in sorted(executions, key=lambda item: item.unique, reverse=True):
        if execution.directory and Path(execution.directory) != Path(args.project):
            print(f"warning: {execution.execution_id} ran in {execution.directory}, "
                  f"not {args.project}", file=sys.stderr)
        rows.append(f"mode={args.mode} {execution.row()} {metadata}")

    unique = sum(execution.unique for execution in executions)
    read = sum(execution.read for execution in executions)
    controllers = [e for e in executions if e.parent == "-" and not e.execution_id.startswith("external:")]
    controller_unique = sum(e.unique for e in controllers)
    share = f" controller={controller_unique * 100 // unique}%" if unique else ""
    rows.append(f"total mode={args.mode} {args.harness} {len(executions)} run(s) "
                f"unique={unique} read={read}{share} {metadata}")

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
        append_to_plan(plan, rows, args.mode, args.harness)
        print(f"written to {plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
