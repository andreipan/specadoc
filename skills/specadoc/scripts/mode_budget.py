#!/usr/bin/env python3
"""Size checks for the skill: per-file limits (errors) and per-mode limits (warnings)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

SKILL_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_RELATIVE = "assets/mode-budget.json"
BACKTICKED_MD = re.compile(r"`([\w./-]+\.md)`")


def load_manifest(skill_root: Path = SKILL_ROOT) -> dict:
    return json.loads((Path(skill_root) / MANIFEST_RELATIVE).read_text(encoding="utf-8"))


def size_findings(
    skill_root: Path = SKILL_ROOT, manifest: dict | None = None
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors: per-file overruns. Warnings: per-mode overruns."""
    skill_root = Path(skill_root)
    if manifest is None:
        manifest = load_manifest(skill_root)
    refs = skill_root / "references"
    errors: list[str] = []
    warnings: list[str] = []

    skill_size = (skill_root / "SKILL.md").stat().st_size
    skill_limit = manifest["limits"]["skill"]
    if skill_size > skill_limit:
        errors.append(f"SKILL.md: {skill_size} > {skill_limit}")

    ref_limit = manifest["limits"]["reference"]
    for path in sorted(refs.rglob("*.md")):
        size = path.stat().st_size
        if size > ref_limit:
            errors.append(f"{path.relative_to(skill_root).as_posix()}: {size} > {ref_limit}")

    for mode, entry in manifest["modes"].items():
        for name in entry.get("always", []):
            if not (refs / name).is_file():
                errors.append(f"{mode}: always file references/{name} does not exist")
    for mode, totals in mode_totals(skill_root, manifest).items():
        if totals["always"] > totals["limit"]:
            warnings.append(f"mode {mode}: {totals['always']} > {totals['limit']}")
    return errors, warnings


def _size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def mode_totals(
    skill_root: Path = SKILL_ROOT,
    manifest: dict | None = None,
    measure: Callable[[Path], int] = _size,
) -> dict[str, dict]:
    """Per mode: always (SKILL.md + always), worst (+ conditional), limit in bytes.

    `measure` sizes each file; the default is bytes, which the limits use.
    """
    skill_root = Path(skill_root)
    if manifest is None:
        manifest = load_manifest(skill_root)
    refs = skill_root / "references"
    skill_size = measure(skill_root / "SKILL.md")
    totals: dict[str, dict] = {}
    for mode, entry in manifest["modes"].items():
        always = skill_size + sum(measure(refs / n) for n in entry.get("always", []))
        worst = always + sum(measure(refs / n) for n in entry.get("conditional", []))
        totals[mode] = {"always": always, "worst": worst, "limit": entry["limit"]}
    return totals


def drift_findings(
    skill_root: Path = SKILL_ROOT, manifest: dict | None = None
) -> list[str]:
    """Errors for mode references naming unlisted files, and listed files that are missing."""
    skill_root = Path(skill_root)
    if manifest is None:
        manifest = load_manifest(skill_root)
    refs = skill_root / "references"
    errors: list[str] = []
    for mode, entry in manifest["modes"].items():
        listed = list(entry.get("always", [])) + list(entry.get("conditional", []))
        for name in listed:
            if not (refs / name).is_file():
                errors.append(f"{mode}: manifest lists references/{name}, which does not exist")
        mode_file = refs / f"{mode}.md"
        if not mode_file.is_file():
            continue
        text = mode_file.read_text(encoding="utf-8")
        mentions = {name.removeprefix("references/") for name in BACKTICKED_MD.findall(text)}
        for name in sorted(mentions):
            if (refs / name).is_file() and name not in listed:
                errors.append(
                    f"{mode}: references/{mode}.md names {name}, not in manifest"
                )
    return errors
