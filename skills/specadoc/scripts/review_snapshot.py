#!/usr/bin/env python3
"""Content-hash review snapshot for a Specadoc change.

No git dependency: a snapshot is correct on a clean or dirty worktree alike,
and needs no commit/ref bookkeeping. This replaces an earlier design that used
a git-commit baseline, which misfired on ordinary dirty worktrees and could
not express "the same files, uncommitted" at all.

A snapshot is the sorted `{path: sha256}` manifest of every literal repository-
relative path in `plan.md`'s `Review scope`, plus one synthetic
`spec.md#contract` entry covering spec.md's `Requirements`, `Acceptance
scenarios`, `Constraints`, and `Affected capabilities` sections (so an approved
requirement edit changes the snapshot too, per `references/apply.md`).
`plan.md` itself and capability-document provenance-table-only edits are
excluded, matching `SKILL.md`'s existing PASS-durability rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402
from validate_change import (  # noqa: E402
    Document,
    PENDING,
    latest_review_round,
    review_manifest_hash,
)

CONTRACT_SECTIONS = ("Requirements", "Acceptance scenarios", "Constraints", "Affected capabilities")
CONTRACT_KEY = "spec.md#contract"
DELETED_DIGEST = "deleted"
SCOPE_ENTRY = re.compile(r"^\s*-\s+`(?P<path>[^`]+)`\s*$")
NON_LITERAL = re.compile(r"[*?\[\]{}]")

Manifest = dict[str, str]


class SnapshotError(RuntimeError):
    """The current manifest cannot be computed because content is unavailable."""


class ScopeError(SnapshotError):
    """The Review scope declaration is absent, unsafe, or contradictory."""


def review_scope(plan: Document, repo_root: Path) -> dict[str, str]:
    if "Review scope" not in plan.sections:
        raise ScopeError("missing ## Review scope")

    repo_root = repo_root.resolve()
    entries: dict[str, str] = {}
    for number, line in plan.body("Review scope"):
        if not line.strip():
            continue
        match = SCOPE_ENTRY.match(line)
        if match is None:
            raise ScopeError(f"line {number}: expected a backticked literal path bullet")
        raw = match.group("path").strip()
        state = "deleted" if raw.startswith("!") else "present"
        candidate = raw[1:] if state == "deleted" else raw
        path = Path(candidate)
        if (
            not candidate
            or path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or "::" in candidate
            or NON_LITERAL.search(candidate)
            or "\\" in candidate
        ):
            raise ScopeError(f"line {number}: Review scope path is not a safe literal: {raw}")
        normalized = path.as_posix()
        if normalized in entries:
            raise ScopeError(f"line {number}: duplicate Review scope path: {normalized}")
        resolved = (repo_root / path).resolve(strict=False)
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            raise ScopeError(f"line {number}: Review scope path leaves repository: {raw}") from exc
        if state == "present" and not resolved.is_file():
            raise ScopeError(f"line {number}: Review scope file does not exist: {normalized}")
        if state == "deleted" and (resolved.exists() or resolved.is_symlink()):
            raise ScopeError(f"line {number}: path marked deleted still exists: {normalized}")
        entries[normalized] = state

    if not entries:
        raise ScopeError("Review scope is empty")
    return entries


def _contract_hash(spec: Document) -> str:
    payload = [
        [section, [line for _, line in spec.body(section)]]
        for section in CONTRACT_SECTIONS
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute(change: Path, repo_root: Path | None = None) -> Manifest:
    plan_path = change / "plan.md"
    spec_path = change / "spec.md"
    if not plan_path.is_file() or not spec_path.is_file():
        raise SnapshotError(f"missing spec.md/plan.md under {change}")
    plan = Document(plan_path, str(plan_path))
    spec = Document(spec_path, str(spec_path))

    base = (repo_root or Path.cwd()).resolve()
    manifest: Manifest = {}
    for candidate, state in review_scope(plan, base).items():
        if state == "deleted":
            manifest[candidate] = DELETED_DIGEST
            continue
        path = base / candidate
        try:
            manifest[candidate] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise SnapshotError(f"cannot read Review scope path {candidate}: {exc}") from exc

    manifest[CONTRACT_KEY] = _contract_hash(spec)
    return manifest


def manifest_hash(manifest: Manifest) -> str:
    return review_manifest_hash(manifest)


def diff(previous: Manifest, current: Manifest) -> dict[str, list[str]]:
    changed = sorted(path for path in previous.keys() & current.keys() if previous[path] != current[path])
    added = sorted(current.keys() - previous.keys())
    removed = sorted(previous.keys() - current.keys())
    return {"changed": changed, "added": added, "removed": removed}


GATE_JSON_FENCE = "```json"


def latest_round(plan: Document) -> tuple[str, dict[str, str], Manifest | None] | None:
    """The most recent `### G<n>` block under `Review result`: its id, its
    `- **Field:** value` fields, and its embedded manifest (None if the block
    has no fenced ```json manifest yet, e.g. still being written)."""
    return latest_review_round(plan)


def verify_latest(plan: Document, change: Path, repo_root: Path) -> list[str]:
    """Verify that the latest recorded round still covers the current snapshot.

    A waiver covers only an otherwise valid scope whose content cannot be read.
    Invalid scope declarations and real manifest differences always fail.
    """
    entry = latest_round(plan)
    if entry is None:
        return []
    round_id, fields, stored_manifest = entry
    if stored_manifest is None:
        return []

    waiver = fields.get("Snapshot waiver", "").strip()
    has_waiver = bool(waiver) and not PENDING.search(waiver)
    try:
        current = compute(change, repo_root)
    except ScopeError as exc:
        return [f"Review result: invalid Review scope ({exc}); return to apply"]
    except SnapshotError as exc:
        if has_waiver:
            return []
        return [
            f"Review result: snapshot unresolvable ({exc}); record a Snapshot waiver "
            f"on {round_id} or return to apply"
        ]

    delta = diff(stored_manifest, current)
    if not any(delta.values()):
        return []
    return [
        f"Review result: diff changed since {round_id}'s snapshot "
        f"(changed={delta['changed']}, added={delta['added']}, removed={delta['removed']}); "
        f"return to apply for a new review"
    ]


def _load_manifest(value: str) -> Manifest:
    path = Path(value)
    payload: Any = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else json.loads(value)
    return payload.get("manifest", payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("compute", "verify", "diff"))
    parser.add_argument("change_slug")
    parser.add_argument("--root", help="Artifact root relative to the current repository (default: resolved, see specadoc_root.py)")
    parser.add_argument("--stored", help="Stored manifest: a JSON file path or inline JSON (for verify)")
    parser.add_argument("--previous", help="Previous-round manifest: a JSON file path or inline JSON (for diff)")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        choice = resolve_root(args.root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if warning := legacy_warning(choice):
        print(warning, file=sys.stderr)
    change = Path(choice.path) / args.change_slug
    try:
        current = compute(change, Path.cwd())
    except (ScopeError, SnapshotError) as exc:
        print(f"unresolvable: {exc}", file=sys.stderr)
        return 2

    if args.action == "compute":
        print(json.dumps({"hash": manifest_hash(current), "manifest": current}, indent=2))
        return 0

    if args.action == "verify":
        if not args.stored:
            print("error: --stored is required for verify", file=sys.stderr)
            return 2
        result = diff(_load_manifest(args.stored), current)
        if any(result.values()):
            print(json.dumps(result, indent=2))
            return 1
        print("match")
        return 0

    if not args.previous:
        print("error: --previous is required for diff", file=sys.stderr)
        return 2
    print(json.dumps(diff(_load_manifest(args.previous), current), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
