#!/usr/bin/env python3
"""Resolve the Specadoc artifact root for the current repository.

Precedence: explicit ``--root`` → ``$SPECADOC_ROOT`` → ``.specadoc.json``
(``{"root": "..."}``) in the working directory → legacy ``docs/agent`` when it
exists and ``docs/specadoc`` does not → ``docs/specadoc``.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from specadoc_config import load_config

DEFAULT_ROOT = "docs/specadoc"
LEGACY_ROOT = "docs/agent"
CONFIG_FILE = ".specadoc.json"
ENV_VAR = "SPECADOC_ROOT"


class RootChoice(NamedTuple):
    path: str
    source: str  # cli | env | config | legacy | default


def _clean(value: str) -> str:
    return value.strip().rstrip("/") or "."


def resolve_root(cli_value: str | os.PathLike[str] | None = None, cwd: Path | None = None) -> RootChoice:
    if cli_value is not None and str(cli_value).strip():
        return RootChoice(_clean(str(cli_value)), "cli")
    env_value = os.environ.get(ENV_VAR, "")
    if env_value.strip():
        return RootChoice(_clean(env_value), "env")
    base = cwd or Path.cwd()
    data = load_config(base)
    if root := data.get("root"):
        return RootChoice(_clean(root), "config")
    if not (base / DEFAULT_ROOT).exists() and (base / LEGACY_ROOT).is_dir():
        return RootChoice(LEGACY_ROOT, "legacy")
    return RootChoice(DEFAULT_ROOT, "default")


def legacy_warning(choice: RootChoice) -> str | None:
    if choice.source != "legacy":
        return None
    return (
        f"warning: using legacy Specadoc root `{LEGACY_ROOT}`; move it with "
        f"`python3 <skill-root>/scripts/migrate_root.py --apply` (target `{DEFAULT_ROOT}`)"
    )
