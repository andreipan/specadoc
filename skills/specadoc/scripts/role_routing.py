#!/usr/bin/env python3
"""Resolve approved role bindings without executing an agent (Python 3.11+)."""
from __future__ import annotations

import argparse
import hashlib
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
        return {"runtime": target, "model": model, "effort": effort, "source": str(path.relative_to(cwd)), "wrapper": True,
                "hash": hashlib.sha256(text.encode()).hexdigest()}
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
    return {"runtime": runtime, "model": model, "effort": effort, "source": str(path.relative_to(cwd)), "wrapper": False,
            "hash": hashlib.sha256(text.encode()).hexdigest()}


def plan_overrides(path: Path | None, role: str) -> dict:
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8")
    section = re.search(r"^## Model handoff\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not section:
        raise ValueError(f"{path}: missing Model handoff")
    fields = dict(re.findall(r"^\*\*([^*]+):\*\*\s*([^\n]*)", section[1], re.M))
    selected = fields.get(f"{role.title()} runtime", "").strip().strip("`")
    if not selected or selected.startswith("<") or selected.lower() in {"pending", "unknown"}:
        return {}
    checkpoint = fields.get("Model checkpoint", "").strip()
    if not re.match(r"^Approved\b", checkpoint, re.I):
        raise ValueError(f"{path}: runtime override requires an approved model checkpoint")
    runtime, slash, model = selected.partition("/")
    if runtime not in RUNTIMES or (role != "controller" and (not slash or not model.strip())):
        raise ValueError(f"{path}: invalid {role} runtime/model")
    result = {"runtime": runtime, "model": model.strip(), "source": str(path)}
    if effort := fields.get(f"{role.title()} effort", "").strip().strip("`"):
        result["effort"] = effort
    return result


def resolve_role(cwd: Path, role: str, controller: str, plan: Path | None = None) -> dict:
    cwd = Path(cwd).resolve()
    plan = (cwd / plan).resolve() if plan is not None else None
    if controller not in RUNTIMES or role not in ROLES:
        raise ValueError("invalid controller runtime or role")
    config = load_config(cwd)
    controller_override = plan_overrides(plan, "controller")
    expected = controller_override.get("runtime") or config.get("roles", {}).get("controller", {}).get("runtime")
    if expected and expected != controller:
        raise ValueError(f"controller runtime is {controller}, binding expects {expected}; restart in {expected} or approve an explicit Controller runtime override in the plan")
    override = plan_overrides(plan, role)
    for selected in (controller_override, override):
        if selected:
            selected["source"] = str(plan.relative_to(cwd)) if plan.is_relative_to(cwd) else str(plan)
    configured = config.get("roles", {}).get(role, {}).get("runtime")
    local = registry(cwd, controller, role) if not override and not configured else None
    runtime = override.get("runtime") or configured or (local["runtime"] if local else controller)
    if runtime not in RUNTIMES:
        raise ValueError(f"invalid registry runtime {runtime!r}")
    runtime_source = override.get("source") or (".specadoc.json" if configured else local["source"] if local else "controller")
    # Legacy wrapper bindings remain authoritative only without a new routing override.
    target = local if not override and not configured and local else registry(cwd, runtime, role)
    if target and target["runtime"] != runtime:
        raise ValueError(f"{target['source']}: wrapper points to {target['runtime']}, not {runtime}; migrate to native roles")
    model = override.get("model") or (target["model"] if target else None)
    effort = override.get("effort") or (target["effort"] if target else None)
    if not isinstance(model, str) or not model.strip() or model.startswith("<") or not isinstance(effort, str) or effort not in EFFORTS[runtime]:
        raise ValueError(f"no valid {runtime}/{role} model/effort binding; install a target role or approve a complete plan override")
    sources = {"runtime": runtime_source, "model": override.get("source") or target["source"],
               "effort": override.get("source") if "effort" in override else target["source"]}
    route = {"role": role, "controller_runtime": controller, "runtime": runtime, "model": model, "effort": effort,
             "controller_source": controller_override.get("source") or (".specadoc.json" if config.get("roles", {}).get("controller") else "host"),
             "dispatch": "native" if runtime == controller else "external", "sources": sources,
             "registry_hash": target["hash"] if target else None,
             "config": config}
    route["fingerprint"] = hashlib.sha256(json.dumps(route, sort_keys=True).encode()).hexdigest()
    return route


def approved_role(cwd: Path, role: str, controller: str, binding_file: Path,
                  plan: Path | None = None) -> dict:
    """Fresh validation shared by native preflight and the external runner; no cache."""
    route = resolve_role(cwd, role, controller, plan)
    check_approved_binding(route, cwd / binding_file)
    return route


def check_approved_binding(route: dict, binding_file: Path) -> None:
    frozen = json.loads(binding_file.read_text(encoding="utf-8"))
    routes = frozen.get("routes", []) if isinstance(frozen, dict) else None
    if not isinstance(routes, list) or not all(isinstance(row, dict) for row in routes):
        raise ValueError("invalid approved binding file; expected resolver JSON")
    match = [row for row in routes if row.get("role") == route["role"]]
    if len(match) != 1 or match[0].get("fingerprint") != route["fingerprint"]:
        raise ValueError("approved binding changed; resolve again and obtain model approval")


def inspect_routing(cwd: Path, controller: str, plan: Path | None = None, which=None,
                    *, resolved: list[dict] | None = None) -> list[dict]:
    which = which or shutil.which
    findings, routes = [], {}
    for role in ROLES if resolved is None else [row["role"] for row in resolved]:
        try:
            routes[role] = route = (resolve_role(cwd, role, controller, plan) if resolved is None
                                    else next(row for row in resolved if row["role"] == role))
            if which(route["runtime"]) is None:
                findings.append({"level": "ERROR", "role": role, "message": f"{route['runtime']} CLI not on PATH"})
        except (ValueError, OSError) as exc:
            findings.append({"level": "ERROR", "role": role, "message": str(exc)})
    if "worker" in routes and "reviewer" in routes and routes["worker"]["runtime"] == routes["reviewer"]["runtime"]:
        findings.append({"level": "WARN", "role": "reviewer", "message": "reviewer shares worker runtime; an Independence waiver is required at pre-review"})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--controller-runtime", choices=RUNTIMES, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="read-only; this command never launches agents")
    parser.add_argument("--check-cli", action="store_true")
    parser.add_argument("--binding-file", type=Path, help="Compare fresh bindings with the approved resolver JSON")
    parser.add_argument("--compact", action="store_true", help="JSON summary; omit config and registry bodies")
    args = parser.parse_args()
    args.cwd = args.cwd.resolve()
    try:
        plan = args.cwd / args.plan if args.plan else None
        roles = [args.role] if args.role else ROLES
        routes = [resolve_role(args.cwd, role, args.controller_runtime, plan) for role in roles]
        if args.binding_file:
            for route in routes:
                check_approved_binding(route, args.cwd / args.binding_file)
        findings = inspect_routing(args.cwd, args.controller_runtime, plan, resolved=routes) if args.check_cli else []
        if args.compact:
            keys = ("role", "runtime", "model", "effort", "dispatch", "fingerprint")
            routes = [{key: route[key] for key in keys} for route in routes]
        print(json.dumps({"routes": routes, "findings": findings}, indent=None if args.compact else 2))
        return int(any(row["level"] == "ERROR" for row in findings))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
