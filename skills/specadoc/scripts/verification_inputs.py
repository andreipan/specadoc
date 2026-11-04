"""Content inputs for verification reuse; no commands or configuration discovery."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sys
from pathlib import Path


def patterns(field: str) -> list[str]:
    from validate_change import files_patterns
    if not field.strip() or re.fullmatch(r"(?:none|n/a|-)(?:;\s*optional\b.*)?", field.strip(), re.I):
        return []
    paths, invalid = files_patterns(field)
    if invalid:
        raise ValueError("expected backticked paths: " + ", ".join(invalid))
    for value in paths:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts or "\\" in value:
            raise ValueError(f"unsafe verification path: {value}")
        if not path.resolve().is_relative_to(Path.cwd().resolve()):
            raise ValueError(f"verification path leaves repository: {value}")
    return paths


def path_field(paths: list[str]) -> str:
    return ", ".join(f"`{path}`" for path in paths)


def owned_digests(fields: dict[str, str]) -> dict[str, str]:
    from validate_change import files_field_digests
    from review_snapshot import LOCKFILES, is_derived, _listed_files
    primary = patterns(fields.get("Files", ""))
    derived = patterns(fields.get("Derived files", ""))
    result = files_field_digests(path_field(primary + derived), repository_only=True)
    candidates = set(_listed_files(Path.cwd()))
    # Include absent implicit lockfiles too, so their later creation invalidates reuse.
    for value in list(result):
        path = Path(value)
        for lock, manifest in LOCKFILES.items():
            if path.name == manifest:
                candidates.add((path.parent / lock).as_posix())
        if path.suffix in (".json", ".toml") or not path.suffix:
            candidates.add(path.with_suffix(".lock").as_posix())
    for candidate in sorted(candidates):
        if is_derived(candidate, primary, derived):
            result.update(files_field_digests(path_field([candidate]), repository_only=True))
    return result


def capture(fields: dict[str, str], artifact_root: str) -> dict:
    from validate_change import files_field_digests
    from review_snapshot import tree_manifest, _under
    declared = patterns(fields.get("Verification inputs", ""))
    if declared:
        checks = files_field_digests(path_field(declared), repository_only=True)
    else:
        # Unknown dependencies: conservative repository fingerprint, not a guess
        # based on shell syntax. Artifact bookkeeping must not invalidate itself.
        checks = {path: value for path, value in tree_manifest(Path.cwd(), artifact_root).items()
                  if not _under(path, artifact_root)}
    owned = owned_digests(fields)
    for path in (*owned, *checks):
        if not Path(path).resolve().is_relative_to(Path.cwd().resolve()):
            raise ValueError(f"verification path leaves repository: {path}")
    environment = environment_digests()
    return {"version": 1, "owned": owned, "checks": checks,
            "declared": declared, "python": [sys.executable, sys.version],
            "environment": environment, "environment_hash": content_hash(environment)}


# Per-session identity, scratch locations and proxy plumbing differ between
# sessions and hosts without changing what a check verifies.
VOLATILE_ENVIRONMENT = ("PWD", "OLDPWD", "SHLVL", "_", "TMPDIR", "*_TMPDIR", "TMPPREFIX", "SSH_AUTH_SOCK",
                        "XPC_SERVICE_NAME", "XPC_FLAGS", "*PROXY*", "*SESSION_ID", "*SESSIONID", "*_THREAD_ID",
                        "*_PID", "*_SOCKET", "*_TOKEN")


def environment_patterns() -> tuple[tuple[str, ...], bool]:
    """Project allowlist from `.specadoc.json` verification.environment, else the volatile denylist."""
    from specadoc_config import load_config
    allow = (load_config(Path.cwd()).get("verification") or {}).get("environment")
    return (tuple(allow), True) if allow else (VOLATILE_ENVIRONMENT, False)


def environment_digests() -> dict[str, str]:
    """Short digest per relevant variable name; values are never stored."""
    selected, allowlist = environment_patterns()
    def matches(name: str) -> bool:
        return any(fnmatch.fnmatchcase(name.upper(), pattern.upper()) for pattern in selected)
    return {name: hashlib.sha256(value.encode()).hexdigest()[:16]
            for name, value in sorted(os.environ.items()) if matches(name) == allowlist}


def environment_drift(previous: dict, current: dict) -> list[str]:
    """Names of variables whose digest differs, for a stale-evidence message."""
    before, after = previous.get("environment"), current.get("environment")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return [] if previous.get("environment_hash") == current.get("environment_hash") else ["(unrecorded)"]
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def content_hash(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
