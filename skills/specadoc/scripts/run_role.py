#!/usr/bin/env python3
"""Run a Specadoc role on another runtime's CLI and collect its result.

The controller (or a thin role wrapper) uses this when a role's runtime is not
the harness it runs in, for example a Claude controller delegating a worker
task to Codex. See `references/runners.md` for the contract.

    run_role.py start  --role worker --runtime codex --model M --effort E \\
                       --prompt-file runs/T1-brief.md --name T1
    run_role.py wait   runs/T1.worker.run.json --timeout 540
    run_role.py result runs/T1.worker.run.json

`start` launches the CLI in the background and returns at once; `wait` blocks
for at most `--timeout` seconds (exit 3 while still running), so a caller with
a per-command time limit can wait in slices; `result` validates the final JSON
against the role's schema. No model names live here: the caller passes them.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import wraps
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ROLES = ("scout", "worker", "reviewer")
RUNTIMES = ("codex", "claude", "opencode")
WRITERS = {"worker"}
READ_TOOLS = "Read,Grep,Glob,Bash"
WRITE_TOOLS = "Read,Edit,Write,Grep,Glob,Bash"
# OpenCode checks every command of a shell line separately against its full text.
READ_SHELL = ("git diff", "git log", "git show", "git status")
# Later rules win: these re-deny writes a read-only git command could still make.
SHELL_WRITES = ("*>*", "*--output*", "*--ext-diff*")
STILL_RUNNING = 3
# A successful run keeps only this much of its log; usage moves into the run file.
LOG_TAIL = 8192
NO_PROGRESS_TIMEOUT = 900.0


class RunError(RuntimeError):
    pass


@contextmanager
def _record_lock(run_file: str):
    """One advisory lock per run directory; no per-poll files or stale writes."""
    parent = Path(run_file).parent
    parent.mkdir(parents=True, exist_ok=True)
    with (parent / ".specadoc-run.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _locked_action(action):
    @wraps(action)
    def locked(args):
        if action.__name__ == "start":
            if args.dry_run:
                return action(args)
            cwd = Path(args.cwd).resolve()
            prompt = cwd / args.prompt_file
            if not prompt.is_file():
                raise RunError(f"no prompt file at {prompt}")
            directory = cwd / args.out_dir if args.out_dir else prompt.parent
            run_file = str(_paths(directory, args.name, args.role)["run"])
        else:
            run_file = args.run_file
            if not Path(run_file).is_file():
                raise RunError(f"no run record at {run_file}")
        # The action loads its record only after acquiring the shared lock.
        with _record_lock(run_file):
            return action(args)
    return locked


def _write_record(run_file: str, record: dict[str, Any]) -> None:
    path = Path(run_file)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)


def _persist_completion(run_file: str) -> None:
    # A wait loop may have loaded its copy before result settled and cut the log.
    with _record_lock(run_file):
        current = _load(run_file)
        _completion(current)
        _write_record(run_file, current)


def schema_path(role: str) -> Path:
    return ASSETS / f"{role}-result.schema.json"


def build_command(runtime: str, role: str, model: str, effort: str | None, cwd: Path, result: Path) -> list[str]:
    schema = schema_path(role)
    writes = role in WRITERS
    if runtime == "codex":
        command = [
            "codex", "exec", "--json", "--ephemeral",
            "-C", str(cwd),
            "-s", "workspace-write" if writes else "read-only",
            "-m", model,
            "--output-schema", str(schema),
            "-o", str(result),
        ]
        if effort:
            command += ["-c", f'model_reasoning_effort="{effort}"']
        if writes:
            # Tests against a local database or service need loopback network.
            command += ["-c", "sandbox_workspace_write.network_access=true"]
        return command + ["-"]
    if runtime == "claude":
        tools = WRITE_TOOLS if writes else READ_TOOLS
        command = [
            "claude", "-p",
            "--model", model,
            "--output-format", "json",
            "--json-schema", schema.read_text(encoding="utf-8"),
            "--tools", tools,
            "--allowedTools", *tools.split(","),
            "--permission-mode", "acceptEdits" if writes else "dontAsk",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
        if effort:
            command += ["--effort", effort]
        return command
    if runtime == "opencode":
        # A dedicated primary agent avoids recursively invoking installed wrappers.
        base, separator, variant = model.partition("#")
        if effort and separator and variant != effort:
            raise RunError("model variant conflicts with --effort")
        selected = f"{base}#{effort or variant}" if effort or variant else base
        return ["opencode", "run", "--standalone", "--format", "json", "--auto",
                "--agent", "specadoc-external", "--model", selected]
    raise RunError(f"unsupported runtime {runtime!r}")


def opencode_config(role: str) -> str:
    config = json.loads(os.environ.get("OPENCODE_CONFIG_CONTENT") or "{}")
    actions = ["read", "glob", "grep", "webfetch", "websearch", "skill"]
    if role in WRITERS:
        actions += ["edit", "shell"]
    rules = [{"action": "*", "resource": "*", "effect": "deny"}]
    rules += [{"action": action, "resource": "*", "effect": "allow"} for action in actions]
    if role not in WRITERS:
        rules += [{"action": "shell", "resource": pattern, "effect": "allow"}
                  for command in READ_SHELL for pattern in (command, f"{command} *")]
        rules += [{"action": "shell", "resource": pattern, "effect": "deny"} for pattern in SHELL_WRITES]
    config.setdefault("agents", {})["specadoc-external"] = {
        "mode": "primary", "system": f"Execute only the Specadoc {role} dispatch. No nested agents or git mutations.",
        "permissions": rules,
    }
    return json.dumps(config)


def _check_opencode_log() -> None:
    """OpenCode exits at once when its log file is not writable (for example inside a sandbox)."""
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    log = base / "opencode" / "log" / "opencode.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.open("ab").close()
    except OSError as exc:
        raise RunError(
            f"OpenCode cannot write its log {log} ({exc.strerror}); this shell is likely sandboxed. "
            "Start the run from a shell with write access to that path, with the approved escalation"
        ) from exc


def _paths(out_dir: Path, name: str, role: str) -> dict[str, Path]:
    stem = f"{name}.{role}"
    return {
        "run": out_dir / f"{stem}.run.json",
        "log": out_dir / f"{stem}.log",
        "result": out_dir / f"{stem}.result.json",
        "exit": out_dir / f"{stem}.exit",
    }


@_locked_action
def start(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    from specadoc_config import load_config

    config = load_config(cwd)
    controller = getattr(args, "controller_runtime", None)
    route = None
    if "roles" in config or controller:
        if not controller:
            raise RunError("project routing requires --controller-runtime; do not infer the controller from the worker")
        from role_routing import resolve_role

        route = resolve_role(cwd, args.role, controller)
        for flag, selected in (("runtime", route["runtime"]), ("model", route["model"]), ("effort", route["effort"])):
            explicit = getattr(args, flag)
            if explicit is not None and explicit != selected:
                raise RunError(f"--{flag} conflicts with the resolved binding")
            setattr(args, flag, selected)
    if not args.runtime or not args.model:
        raise RunError("provide --runtime and --model, or --controller-runtime to resolve the role")
    prompt_path = cwd / args.prompt_file
    if not prompt_path.is_file():
        raise RunError(f"no prompt file at {prompt_path}")
    out_dir = cwd / args.out_dir if args.out_dir else prompt_path.parent
    paths = _paths(out_dir, args.name, args.role)
    invocation = {
        "role": args.role, "runtime": args.runtime, "model": args.model, "effort": args.effort,
        "cwd": str(cwd), "binding": route, "controller_runtime": controller,
    }
    prompt_digest = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    command = build_command(args.runtime, args.role, args.model, args.effort, cwd, paths["result"].resolve())
    if args.dry_run:
        print(json.dumps(command))
        return 0
    if paths["run"].exists():
        existing = _load(str(paths["run"]))
        if existing.get("prompt_sha256") != prompt_digest or existing.get("invocation") != invocation:
            raise RunError(f"existing run {paths['run']} has a conflicting or unverifiable dispatch; "
                           "inspect it with status and choose a new --name for new work")
        state = _status(existing)
        print(f"existing {state['status']} run; use status or result; no work relaunched", file=sys.stderr)
        print(paths["run"])
        return 0
    if any(paths[key].exists() for key in ("result", "exit", "log")):
        raise RunError("existing run artifacts without a record; preserve them and choose a new --name")
    if shutil.which(command[0]) is None:
        raise RunError(f"{command[0]} CLI is not on PATH for role {args.role}")
    if args.runtime == "opencode":
        _check_opencode_log()
    if out_dir.name == "runs":
        from specadoc_root import ensure_runs

        ensure_runs(out_dir)
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
    # Reserve the name exclusively before launching. A concurrent dispatch or a
    # failed launch must never overwrite a run (including a partially written one).
    try:
        reservation = paths["run"].open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RunError("run name was claimed concurrently; inspect status or choose a new --name") from exc

    # A small supervisor shell records the exit code, so `wait` works after the
    # caller's own process is gone. The prompt file itself goes on stdin, with an
    # optional suffix instead of a rewritten copy.
    script = '{ cat "$SPECADOC_PROMPT"; printf %s "$SPECADOC_SUFFIX"; } | "$@" > "$SPECADOC_LOG" 2>&1; echo $? > "$SPECADOC_EXIT"'
    env = dict(os.environ)
    suffix = ""
    if args.runtime == "opencode":
        env["OPENCODE_CONFIG_CONTENT"] = opencode_config(args.role)
        suffix = "\nReturn only a JSON object matching this schema as your final message:\n"
        suffix += schema_path(args.role).read_text(encoding="utf-8")
    env.update(
        SPECADOC_PROMPT=str(prompt_path.resolve()),
        SPECADOC_SUFFIX=suffix,
        SPECADOC_LOG=str(paths["log"].resolve()),
        SPECADOC_EXIT=str(paths["exit"].resolve()),
    )
    started = time.time()
    try:
        process = subprocess.Popen(
            ["sh", "-c", script, "specadoc-run", *command],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except BaseException:
        reservation.close()
        raise
    record = {
        "role": args.role,
        "runtime": args.runtime,
        "model": args.model,
        "effort": args.effort,
        "binding": route,
        "prompt_sha256": prompt_digest,
        "prompt_file": str(prompt_path.resolve()),
        "invocation": invocation,
        "no_progress_timeout": getattr(args, "no_progress_timeout", NO_PROGRESS_TIMEOUT),
        "pid": process.pid,
        "started": started,
        "cwd": str(cwd),
        "command": [part if len(part) < 200 else part[:40] + "…" for part in command],
        **{key: str(path.resolve()) for key, path in paths.items() if key != "run"},
    }
    with reservation:
        reservation.write(json.dumps(record, indent=1) + "\n")
    print(paths["run"])
    return 0


def _load(run_file: str) -> dict[str, Any]:
    path = Path(run_file)
    if not path.is_file():
        raise RunError(f"no run record at {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunError(f"incomplete run record at {path}; inspect it before retrying, or choose a new --name") from exc


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _completion(record: dict[str, Any]) -> bool:
    """Use the supervisor's timestamp, not the time result was first requested."""
    exit_file = Path(record["exit"])
    if not exit_file.is_file() or not exit_file.read_text().strip():
        return False
    record.setdefault("completed", max(record["started"], exit_file.stat().st_mtime))
    record.setdefault("elapsed_seconds", max(0.0, record["completed"] - record["started"]))
    return True


DIAGNOSTIC_MARKERS = ("api error:", "connection reset", "connection refused", "authentication failed",
                      "stream disconnected", "stream error")


def _transport_diagnostics(record: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Return (terminal error, warnings).

    Only an event that ends the turn (`turn.failed`, an error result) is terminal.
    Every other error line is a warning: CLIs retry and reconnect on their own,
    so a live process with such a line is still running, and the exit code
    decides a finished one.
    """
    log = Path(record["log"])
    if not log.is_file():
        return None, []
    text = log.read_text(encoding="utf-8", errors="replace")
    # Claude's JSON envelope can be pretty-printed rather than JSONL.
    try:
        envelope = json.loads(text)
        if isinstance(envelope, dict) and envelope.get("is_error") is True:
            return json.dumps(envelope, ensure_ascii=False)[-2000:], []
    except json.JSONDecodeError:
        pass
    terminal = None
    warnings: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Do not mistake tool output or a role's JSON report about an error for
            # a transport failure. Plain CLI diagnostics are separate from events.
            lower = line.strip().lower()
            if not lower.startswith(('"', '{', '[')) and (
                    lower.startswith(("error:", "fatal:")) or any(m in lower for m in DIAGNOSTIC_MARKERS)):
                warnings.append(line[-2000:])
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "turn.failed" or (event.get("type") == "result" and event.get("is_error") is True):
            terminal = json.dumps(event, ensure_ascii=False)[-2000:]
        elif event.get("type") == "error" or event.get("is_error") is True:
            warnings.append(json.dumps(event, ensure_ascii=False)[-2000:])
    return terminal, warnings


def _status(record: dict[str, Any], no_progress_timeout: float | None = None) -> dict[str, Any]:
    now = time.time()
    finished = _completion(record)
    alive = not finished and _alive(record["pid"])
    log = Path(record["log"])
    stat = log.stat() if log.is_file() else None
    observable = record["runtime"] != "claude"
    silence = max(0.0, now - max(record["started"], stat.st_mtime if stat else record["started"]))
    threshold = no_progress_timeout if no_progress_timeout is not None else record.get("no_progress_timeout", NO_PROGRESS_TIMEOUT)
    error, warnings = _transport_diagnostics(record)
    exit_code = int(Path(record["exit"]).read_text().strip()) if finished else None
    if finished:
        state = "completed" if exit_code == 0 and not error else "failed"
        if state == "failed" and not error and warnings:
            error = warnings[-1]
    else:
        state = "failed" if error or not alive else "running"
    if state == "running" and observable and threshold > 0 and silence >= threshold:
        state = "no-progress"
    role_status = None
    if finished:
        try:
            payload = _final_json(record)
            if isinstance(payload, dict):
                role_status = payload.get("status")
        except (RunError, ValueError, OSError):
            pass
    return {
        "status": state, "role_status": role_status, "exit": exit_code, "pid": record["pid"],
        "alive": alive, "completed": record.get("completed"),
        "elapsed_seconds": record.get("elapsed_seconds", max(0.0, now - record["started"])),
        "progress": {"observable": observable, "log_bytes": stat.st_size if stat else 0,
                     "last_activity": stat.st_mtime if stat else None,
                     "silence_seconds": silence, "no_progress_timeout": threshold,
                     "note": "stream activity only; no automatic stop" if observable else "unobservable: buffered JSON; silence is not stall evidence"},
        "transport_error": error,
        "warnings": warnings,
        "retry": {"safe": not alive and state == "failed" and role_status is None, "automatic": False,
                  "instruction": "inspect log/result; use a new --name for any approved retry; never rerun completed work"},
    }


@_locked_action
def status(args: argparse.Namespace) -> int:
    record = _load(args.run_file)
    before = dict(record)
    state = _status(record, getattr(args, "no_progress_timeout", None))
    if record != before:
        _write_record(args.run_file, record)
    print(json.dumps(state, indent=2))
    return 0


def _progress(record: dict[str, Any], state: dict[str, Any]) -> str:
    """One status line from the run log; OpenCode logs add step and last-tool counts."""
    elapsed = int(time.time() - record["started"])
    line = f"{record['role']} {record['runtime']} running {elapsed // 60}m{elapsed % 60:02d}s"
    log = Path(record["log"])
    if not log.is_file():
        return line
    size = log.stat().st_size
    if record["runtime"] == "opencode":
        with log.open("rb") as handle:
            handle.seek(state.get("offset", 0))
            chunk = handle.read()
        cut = chunk.rfind(b"\n") + 1  # keep a partially written last line for the next call
        state["offset"] = state.get("offset", 0) + cut
        for raw in chunk[:cut].splitlines():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "tool_use":
                state["tools"] = state.get("tools", 0) + 1
                part = event.get("part")
                state["last"] = part.get("tool", "?") if isinstance(part, dict) else "?"
        return f"{line}, {state.get('tools', 0)} tool calls, last: {state.get('last', '-')}"
    return f"{line}, log {size // 1024} KiB"


def wait(args: argparse.Namespace) -> int:
    record = _load(args.run_file)
    exit_file = Path(record["exit"])
    budget = getattr(args, "shell_budget", 120.0)
    if budget <= 0 or args.timeout < 0:
        raise RunError("--shell-budget must be positive and --timeout nonnegative")
    # Leave room for startup, persistence, and reporting before the host kills us.
    deadline = time.monotonic() + min(args.timeout, max(0.0, budget - min(5.0, budget * 0.1)))
    follow = getattr(args, "follow", False)
    interval = getattr(args, "interval", 45.0)
    next_report = time.monotonic() + interval
    state: dict[str, Any] = {}
    while True:
        if _completion(record):
            _persist_completion(args.run_file)
            print(f"finished: exit {exit_file.read_text().strip()}")
            return 0
        if not _alive(record["pid"]):
            print("finished: supervisor exited without an exit code")
            return 0
        snapshot = _status(record, getattr(args, "no_progress_timeout", None))
        if snapshot["status"] == "failed":
            print(f"failed: pid {record['pid']} reported a terminal transport error; role not stopped; "
                  "inspect status/log and any existing diff before an explicit stop or retry")
            return 1
        if snapshot["status"] == "no-progress":
            print(f"no-progress: pid {record['pid']}; role not stopped; "
                  "inspect status/log before deciding whether to keep waiting or stop explicitly")
            return STILL_RUNNING
        if time.monotonic() >= deadline:
            break
        if follow and time.monotonic() >= next_report:
            print(_progress(record, state), flush=True)
            next_report = time.monotonic() + interval
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    snapshot = _status(record, getattr(args, "no_progress_timeout", None))
    line = f"{snapshot['status']}: pid {record['pid']}" if not follow else _progress(record, state)
    print(line + "; wait timed out (not a role result); call wait again")
    return STILL_RUNNING


def stop(args: argparse.Namespace) -> int:
    record = _load(args.run_file)
    try:
        os.killpg(record["pid"], signal.SIGTERM)
    except ProcessLookupError:
        pass
    print("stopped")
    return 0


def _parse_json_text(text: str) -> Any:
    """Parse a final message that may wrap the JSON in a code fence or prose.

    Strict JSON wins; otherwise the last top-level JSON object in the text is used.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    found = None
    index = 0
    while (index := text.find("{", index)) != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        if isinstance(value, dict):
            found = value
        index = end
    if found is None:
        raise ValueError("no JSON object in the final message")
    return found


def _final_json(record: dict[str, Any]) -> Any:
    result = Path(record["result"])
    if result.is_file() and result.read_text(encoding="utf-8").strip():
        return _parse_json_text(result.read_text(encoding="utf-8"))
    log = Path(record["log"])
    if record["runtime"] == "opencode" and log.is_file():
        messages: dict[str, list[str]] = {}
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # CLI diagnostics are not result data.
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                raise RunError(f"OpenCode error; inspect {record['log']}")
            part = event.get("part", {})
            if event.get("type") == "text" and isinstance(part, dict) and isinstance(part.get("text"), str):
                messages.setdefault(part.get("messageID", "final"), []).append(part["text"])
        if messages:
            return _parse_json_text("".join(list(messages.values())[-1]))
    if record["runtime"] == "claude" and log.is_file():
        envelope = json.loads(log.read_text(encoding="utf-8"))
        if isinstance(envelope, dict) and "structured_output" in envelope:
            return envelope["structured_output"]
        if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
            return _parse_json_text(envelope["result"])
    raise RunError(f"no final result; inspect {record['log']}")


def schema_errors(value: Any, schema: dict[str, Any], where: str = "$") -> list[str]:
    """A minimal validator for the bundled result schemas (object/array/string/enum)."""
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return [f"{where}: expected object"]
        errors = [f"{where}.{key}: missing" for key in schema.get("required", []) if key not in value]
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors += [f"{where}.{key}: unexpected" for key in value if key not in properties]
        for key, child in properties.items():
            if key in value:
                errors += schema_errors(value[key], child, f"{where}.{key}")
        return errors
    if kind == "array":
        if not isinstance(value, list):
            return [f"{where}: expected array"]
        return [error for index, item in enumerate(value) for error in schema_errors(item, schema["items"], f"{where}[{index}]")]
    if kind == "string":
        if not isinstance(value, str):
            return [f"{where}: expected string"]
        if "enum" in schema and value not in schema["enum"]:
            return [f"{where}: {value!r} not in {schema['enum']}"]
    return []


def _add_usage(total: dict[str, int], value: Any, prefix: str = "") -> None:
    for key, item in value.items():
        if isinstance(item, dict):
            _add_usage(total, item, f"{prefix}{key}.")
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            total[prefix + key] = total.get(prefix + key, 0) + item


def _usage(record: dict[str, Any]) -> dict[str, int]:
    """Token totals from the log: Claude's envelope `usage`, Codex `turn.completed`
    usage, OpenCode `step_finish` part tokens. Unknown shapes contribute nothing."""
    log = Path(record["log"])
    if not log.is_file():
        return {}
    text = log.read_text(encoding="utf-8", errors="replace")
    events = []
    for chunk in [text] if record["runtime"] == "claude" else text.splitlines():
        try:
            events.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    total: dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        if record["runtime"] == "opencode":
            part = event.get("part")
            usage = part.get("tokens") if isinstance(part, dict) else None
        else:
            usage = event.get("usage")
        if isinstance(usage, dict):
            _add_usage(total, usage)
    return total


def _settle(run_file: str, record: dict[str, Any], payload: Any) -> None:
    """After a successful run keep the result, record usage, and cut the log to its tail."""
    if "settled" in record:
        return
    Path(record["result"]).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    log = Path(record["log"])
    _completion(record)
    if "usage" not in record:
        record["usage"] = _usage(record)
        record["log_bytes"] = log.stat().st_size if log.is_file() else 0
    record["settled"] = time.time()
    _write_record(run_file, record)
    if log.is_file() and record.get("log_bytes", 0) > LOG_TAIL:
        with log.open("rb") as handle:
            handle.seek(-LOG_TAIL, os.SEEK_END)
            tail = handle.read()
        note = f"[specadoc: log cut to its last {LOG_TAIL} bytes of {record['log_bytes']} after a successful result; usage is in the run file]\n"
        log.write_bytes(note.encode() + tail)


@_locked_action
def result(args: argparse.Namespace) -> int:
    record = _load(args.run_file)
    before = dict(record)
    if not _completion(record):
        raise RunError("run has not finished; call wait first")
    if record != before:
        _write_record(args.run_file, record)
    exit_file = Path(record["exit"])
    payload = _final_json(record)
    schema = json.loads(schema_path(record["role"]).read_text(encoding="utf-8"))
    errors = schema_errors(payload, schema)
    output = {"exit": int(exit_file.read_text().strip() or 1), "result": payload, "schema_errors": errors}
    if not errors and output["exit"] == 0:
        _settle(args.run_file, record, payload)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if not errors and output["exit"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    begin = sub.add_parser("start")
    begin.add_argument("--role", choices=ROLES, required=True)
    begin.add_argument("--runtime", choices=RUNTIMES)
    begin.add_argument("--model")
    begin.add_argument("--effort")
    begin.add_argument("--controller-runtime", choices=RUNTIMES, help="resolve project routing and target model registry")
    begin.add_argument("--prompt-file", required=True, help="Brief or full dispatch prompt")
    begin.add_argument("--name", required=True, help="Run name, usually the task id")
    begin.add_argument("--cwd", default=".", help="Repository root the role works in")
    begin.add_argument("--out-dir", help="Where run files go (default: the prompt file's directory)")
    begin.add_argument("--dry-run", action="store_true", help="Print the command instead of running it")
    begin.add_argument("--no-progress-timeout", type=_nonnegative, default=NO_PROGRESS_TIMEOUT,
                       help="stream silence deadline in seconds; 0 disables; buffered JSON is unobservable")
    for name in ("wait", "result", "stop", "status"):
        child = sub.add_parser(name)
        child.add_argument("run_file")
        if name in ("wait", "status"):
            child.add_argument("--no-progress-timeout", type=_nonnegative,
                               help="override stream silence deadline; never automatically stops the role")
        if name == "wait":
            child.add_argument("--timeout", type=_nonnegative, default=120.0)
            child.add_argument("--shell-budget", type=_positive, default=120.0,
                               help="host shell limit in seconds; wait leaves a safety margin below it")
            child.add_argument("--follow", action="store_true", help="print a progress line every --interval seconds")
            child.add_argument("--interval", type=float, default=45.0)
    return parser


def _nonnegative(value: str) -> float:
    import math

    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be finite and nonnegative")
    return number


def _positive(value: str) -> float:
    number = _nonnegative(value)
    if number == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main() -> int:
    args = build_parser().parse_args()
    handler = {"start": start, "wait": wait, "result": result, "stop": stop, "status": status}[args.action]
    try:
        return handler(args)
    except (RunError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
