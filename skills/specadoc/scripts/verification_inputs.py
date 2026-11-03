"""Content inputs for verification reuse; no commands or configuration discovery."""
from __future__ import annotations

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
    return {"version": 1, "owned": owned, "checks": checks,
            "declared": declared, "python": [sys.executable, sys.version],
            # macOS launchd changes this process identity from an application
            # name to "0" for Python children; it is not verifier configuration.
            "environment_hash": content_hash({key: value for key, value in os.environ.items()
                                               if key != "XPC_SERVICE_NAME"})}


def content_hash(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
