"""Project-owned Specadoc configuration; no installer or model configuration."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = ".specadoc.json"
RUNTIMES = ("claude", "codex", "opencode")
# Host provider ids that name a Specadoc runtime (4.1: `--controller-runtime claude-code` was refused).
RUNTIME_ALIASES = {"claude-code": "claude"}


def normalize_runtime(value: str) -> str:
    """argparse `type=` for runtime options: map a host alias, keep `choices` validation."""
    return RUNTIME_ALIASES.get(value.strip().lower(), value.strip().lower())
ROLES = ("scout", "worker", "reviewer")


def validate_config(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("expected Specadoc config object")
    unknown = set(data) - {"$schema", "root", "version", "roles", "verification", "review"}
    if unknown:
        raise ValueError(f"expected known Specadoc keys; unknown: {', '.join(sorted(unknown))}")
    if "verification" in data:
        verification = data["verification"]
        if not isinstance(verification, dict) or set(verification) - {"environment", "external_only"}:
            raise ValueError("verification: expected an object with environment and external_only only")
        environment = verification.get("environment", [])
        if not isinstance(environment, list) or not all(isinstance(item, str) and item.strip() for item in environment):
            raise ValueError("verification.environment: expected a list of variable names or globs")
        external = verification.get("external_only", [])
        if not isinstance(external, list) or not all(isinstance(item, str) and item.strip() for item in external):
            raise ValueError("verification.external_only: expected a list of command fragments")
    if "review" in data:
        review = data["review"]
        if not isinstance(review, dict) or set(review) - {"tidy"}:
            raise ValueError("review: expected an object with tidy only")
        if review.get("tidy", "optional") not in ("required", "optional"):
            raise ValueError("review.tidy: expected required or optional")
    if "root" in data and (not isinstance(data["root"], str) or not data["root"].strip()):
        raise ValueError("expected nonempty root path")
    if "version" in data and (type(data["version"]) is not int or data["version"] != 1):
        raise ValueError("expected Specadoc version 1")
    if "roles" in data:
        if data.get("version") != 1:
            raise ValueError("expected version 1 for role routing")
        if not isinstance(data["roles"], dict):
            raise ValueError("expected roles object")
        for role, binding in data["roles"].items():
            if role not in (*ROLES, "controller"):
                raise ValueError(f"unknown role {role!r}")
            if not isinstance(binding, dict) or set(binding) != {"runtime"}:
                raise ValueError(f"roles.{role}: expected runtime only (models belong to the registry)")
            if binding["runtime"] not in RUNTIMES:
                raise ValueError(f"roles.{role}: expected runtime from {RUNTIMES}")
    return data


def load_config(cwd: Path) -> dict:
    path = Path(cwd) / CONFIG_FILE
    if not path.exists() and not path.is_symlink():
        return {}
    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: cannot read Specadoc config: {exc}") from exc
