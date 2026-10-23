#!/usr/bin/env python3
"""Resolve role bindings from project config and role files without executing an agent (Python 3.11+)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

from specadoc_config import load_config, ROLES, RUNTIMES

WRAPPER = re.compile(r"Default binding: runtime `([^`]+)`, model `([^`]+)`, effort `([^`]+)`")
EFFORTS = {
    "claude": {"low", "medium", "high", "max"},
    "codex": {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"},
    "opencode": {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"},
}


def registry(cwd: Path, runtime: str, role: str) -> dict | None:
    extension = "toml" if runtime == "codex" else "md"
    path = cwd / f".{runtime}/agents/{role}.{extension}"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if match := WRAPPER.search(text):
        target, model, effort = match.groups()
        return {"runtime": target, "model": model, "effort": effort, "source": str(path.relative_to(cwd)), "wrapper": True}
    if runtime == "codex":
        if tomllib is None:
            raise ValueError("Codex registry resolution requires Python 3.11+; select a supported interpreter")
        fields = tomllib.loads(text)
        model, effort = fields.get("model"), fields.get("model_reasoning_effort")
    else:
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValueError(f"{path}: missing role frontmatter")
        header = text[4:].split("\n---\n", 1)[0]
        fields = {}
        for line in header.splitlines():
            if match := re.fullmatch(r"(model|effort|variant):\s*(.*?)\s*", line):
                key, value = match.groups()
                if key in fields:
                    raise ValueError(f"{path}: duplicate {key}")
                fields[key] = value.strip("\"'")
        model = fields.get("model")
        effort = fields.get("effort" if runtime == "claude" else "variant")
    return {"runtime": runtime, "model": model, "effort": effort, "source": str(path.relative_to(cwd)), "wrapper": False}


def resolve_role(cwd: Path, role: str, controller: str) -> dict:
    cwd = Path(cwd).resolve()
    if controller not in RUNTIMES or role not in ROLES:
        raise ValueError("invalid controller runtime or role")
    config = load_config(cwd)
    roles = config.get("roles", {})
    expected = roles.get("controller", {}).get("runtime")
    if expected and expected != controller:
        raise ValueError(f"controller runtime is {controller}, binding expects {expected}; restart in {expected} or edit .specadoc.json")
    configured = roles.get(role, {}).get("runtime")
    local = registry(cwd, controller, role) if not configured else None
    runtime = configured or (local["runtime"] if local else controller)
    if runtime not in RUNTIMES:
        raise ValueError(f"invalid registry runtime {runtime!r}")
    runtime_source = ".specadoc.json" if configured else local["source"] if local else "controller"
    # A legacy wrapper binding is authoritative only without a .specadoc.json entry.
    target = local if local else registry(cwd, runtime, role)
    if target and target["runtime"] != runtime:
        raise ValueError(f"{target['source']}: wrapper points to {target['runtime']}, not {runtime}; migrate to native roles")
    model = target["model"] if target else None
    effort = target["effort"] if target else None
    if not isinstance(model, str) or not model.strip() or model.startswith("<") or not isinstance(effort, str) or effort not in EFFORTS[runtime]:
        raise ValueError(f"no valid {runtime}/{role} model/effort binding; install a target role file")
    sources = {"runtime": runtime_source, "model": target["source"], "effort": target["source"]}
    return {"role": role, "controller_runtime": controller, "runtime": runtime, "model": model, "effort": effort,
            "controller_source": ".specadoc.json" if roles.get("controller") else "host",
            "dispatch": "native" if runtime == controller else "external", "sources": sources}


def inspect_routing(cwd: Path, controller: str, which=None,
                    *, resolved: list[dict] | None = None) -> list[dict]:
    which = which or shutil.which
    findings, routes = [], {}
    for role in ROLES if resolved is None else [row["role"] for row in resolved]:
        try:
            routes[role] = route = (resolve_role(cwd, role, controller) if resolved is None
                                    else next(row for row in resolved if row["role"] == role))
            if which(route["runtime"]) is None:
                findings.append({"level": "ERROR", "role": role, "message": f"{route['runtime']} CLI not on PATH"})
        except (ValueError, OSError) as exc:
            findings.append({"level": "ERROR", "role": role, "message": str(exc)})
    if "worker" in routes and "reviewer" in routes and routes["worker"]["runtime"] == routes["reviewer"]["runtime"]:
        findings.append({"level": "WARN", "role": "reviewer", "message": f"reviewer shares worker runtime {routes['reviewer']['runtime']}"})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--controller-runtime", choices=RUNTIMES, required=True)
    parser.add_argument("--dry-run", action="store_true", help="read-only; this command never launches agents")
    parser.add_argument("--check-cli", action="store_true")
    parser.add_argument("--compact", action="store_true", help="JSON summary; omit source details")
    args = parser.parse_args()
    args.cwd = args.cwd.resolve()
    try:
        roles = [args.role] if args.role else ROLES
        routes = [resolve_role(args.cwd, role, args.controller_runtime) for role in roles]
        findings = inspect_routing(args.cwd, args.controller_runtime, resolved=routes) if args.check_cli else []
        if args.compact:
            keys = ("role", "runtime", "model", "effort", "dispatch")
            routes = [{key: route[key] for key in keys} for route in routes]
        print(json.dumps({"routes": routes, "findings": findings}, indent=None if args.compact else 2))
        return int(any(row["level"] == "ERROR" for row in findings))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
