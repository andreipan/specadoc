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
import json
import os
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


class RunError(RuntimeError):
    pass


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


def _paths(out_dir: Path, name: str, role: str) -> dict[str, Path]:
    stem = f"{name}.{role}"
    return {
        "run": out_dir / f"{stem}.run.json",
        "log": out_dir / f"{stem}.log",
        "result": out_dir / f"{stem}.result.json",
        "exit": out_dir / f"{stem}.exit",
    }


def start(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    from specadoc_config import load_config

    config = load_config(cwd)
    controller = getattr(args, "controller_runtime", None)
    binding_file = getattr(args, "binding_file", None)
    plan_file = getattr(args, "plan", None)
    route = None
    if "roles" in config or controller or binding_file or plan_file:
        if not controller:
            raise RunError("project routing requires --controller-runtime; do not infer the controller from the worker")
        from role_routing import resolve_role

        route = resolve_role(cwd, args.role, controller, cwd / plan_file if plan_file else None)
        if not args.dry_run and not binding_file:
            raise RunError("resolved dispatch requires --binding-file from the approved model checkpoint")
        if binding_file:
            frozen = json.loads((cwd / binding_file).read_text(encoding="utf-8"))
            routes = frozen.get("routes", []) if isinstance(frozen, dict) else None
            if not isinstance(routes, list) or not all(isinstance(row, dict) for row in routes):
                raise RunError("invalid approved binding file; expected resolver JSON")
            match = [row for row in routes if row.get("role") == args.role]
            if len(match) != 1 or match[0].get("fingerprint") != route["fingerprint"]:
                raise RunError("approved binding changed; resolve again and obtain model approval")
        for flag, selected in (("runtime", route["runtime"]), ("model", route["model"]), ("effort", route["effort"])):
            explicit = getattr(args, flag)
            if explicit is not None and explicit != selected:
                raise RunError(f"--{flag} conflicts with the resolved binding")
            setattr(args, flag, selected)
    if not args.runtime or not args.model:
        raise RunError("provide --runtime and --model, or --controller-runtime to resolve the role")
    prompt_path = cwd / args.prompt_file
    prompt = prompt_path.read_text(encoding="utf-8")
    out_dir = cwd / args.out_dir if args.out_dir else prompt_path.parent
    paths = _paths(out_dir, args.name, args.role)
    command = build_command(args.runtime, args.role, args.model, args.effort, cwd, paths["result"].resolve())
    if args.dry_run:
        print(json.dumps(command))
        return 0
    if shutil.which(command[0]) is None:
        raise RunError(f"{command[0]} is not on PATH")
    out_dir.mkdir(parents=True, exist_ok=True)
    for key in ("result", "exit"):
        paths[key].unlink(missing_ok=True)

    # A small supervisor shell records the exit code, so `wait` works after the
    # caller's own process is gone. The prompt goes on stdin.
    script = '"$@" < "$SPECADOC_PROMPT" > "$SPECADOC_LOG" 2>&1; echo $? > "$SPECADOC_EXIT"'
    prompt_file = out_dir / f"{args.name}.{args.role}.prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    env = dict(os.environ)
    if args.runtime == "opencode":
        env["OPENCODE_CONFIG_CONTENT"] = opencode_config(args.role)
        prompt += "\nReturn only a JSON object matching this schema as your final message:\n"
        prompt += schema_path(args.role).read_text(encoding="utf-8")
        prompt_file.write_text(prompt, encoding="utf-8")
    env.update(
        SPECADOC_PROMPT=str(prompt_file.resolve()),
        SPECADOC_LOG=str(paths["log"].resolve()),
        SPECADOC_EXIT=str(paths["exit"].resolve()),
    )
    process = subprocess.Popen(
        ["sh", "-c", script, "specadoc-run", *command],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    record = {
        "role": args.role,
        "runtime": args.runtime,
        "model": args.model,
        "effort": args.effort,
        "binding": route,
        "pid": process.pid,
        "started": time.time(),
        "cwd": str(cwd),
        "command": [part if len(part) < 200 else part[:40] + "…" for part in command],
        **{key: str(path.resolve()) for key, path in paths.items() if key != "run"},
    }
    paths["run"].write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(paths["run"])
    return 0


def _load(run_file: str) -> dict[str, Any]:
    path = Path(run_file)
    if not path.is_file():
        raise RunError(f"no run record at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait(args: argparse.Namespace) -> int:
    record = _load(args.run_file)
    exit_file = Path(record["exit"])
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if exit_file.is_file():
            print(f"finished: exit {exit_file.read_text().strip()}")
            return 0
        if not _alive(record["pid"]):
            print("finished: supervisor exited without an exit code")
            return 0
        time.sleep(min(1.0, max(0.1, deadline - time.monotonic())))
    print(f"running: pid {record['pid']}; call wait again")
    return STILL_RUNNING


def stop(args: argparse.Namespace) -> int:
    record = _load(args.run_file)
    try:
        os.killpg(record["pid"], signal.SIGTERM)
    except ProcessLookupError:
        pass
    print("stopped")
    return 0


def _final_json(record: dict[str, Any]) -> Any:
    result = Path(record["result"])
    if result.is_file() and result.read_text(encoding="utf-8").strip():
        return json.loads(result.read_text(encoding="utf-8"))
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
            return json.loads("".join(list(messages.values())[-1]))
    if record["runtime"] == "claude" and log.is_file():
        envelope = json.loads(log.read_text(encoding="utf-8"))
        if isinstance(envelope, dict) and "structured_output" in envelope:
            return envelope["structured_output"]
        if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
            return json.loads(envelope["result"])
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


def result(args: argparse.Namespace) -> int:
    record = _load(args.run_file)
    exit_file = Path(record["exit"])
    if not exit_file.is_file():
        raise RunError("run has not finished; call wait first")
    payload = _final_json(record)
    schema = json.loads(schema_path(record["role"]).read_text(encoding="utf-8"))
    errors = schema_errors(payload, schema)
    output = {"exit": int(exit_file.read_text().strip() or 1), "result": payload, "schema_errors": errors}
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
    begin.add_argument("--plan", type=Path, help="plan with approved Model handoff overrides")
    begin.add_argument("--binding-file", type=Path, help="saved role_routing.py JSON approved at model checkpoint")
    begin.add_argument("--prompt-file", required=True, help="Brief or full dispatch prompt")
    begin.add_argument("--name", required=True, help="Run name, usually the task id")
    begin.add_argument("--cwd", default=".", help="Repository root the role works in")
    begin.add_argument("--out-dir", help="Where run files go (default: the prompt file's directory)")
    begin.add_argument("--dry-run", action="store_true", help="Print the command instead of running it")
    for name in ("wait", "result", "stop"):
        child = sub.add_parser(name)
        child.add_argument("run_file")
        if name == "wait":
            child.add_argument("--timeout", type=float, default=540.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    handler = {"start": start, "wait": wait, "result": result, "stop": stop}[args.action]
    try:
        return handler(args)
    except (RunError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
