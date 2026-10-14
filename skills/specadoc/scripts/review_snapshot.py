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

`baseline` and `check-scope` guard one delegated task instead: `baseline`
records a content manifest of the whole working tree (git's file list when
available, otherwise a filesystem walk) in the change's `runs/` directory
before dispatch, and `check-scope` fails when anything changed outside the
task's `Files:` or under the artifact root.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402
from validate_change import (  # noqa: E402
    Document,
    PENDING,
    files_patterns,
    latest_review_round,
    review_manifest_hash,
    task_fields,
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

RUNS_DIR = "runs"


def runs_dir(change: Path) -> Path:
    return change / RUNS_DIR


def _hash_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _listed_files(repo_root: Path) -> list[str]:
    """Tracked plus untracked-but-not-ignored files; a filesystem walk outside git."""
    try:
        output = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        ).stdout
        return [item for item in output.decode("utf-8").split("\0") if item]
    except (OSError, subprocess.CalledProcessError):
        found = []
        for directory, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [name for name in dirnames if name != ".git"]
            for name in filenames:
                found.append((Path(directory) / name).relative_to(repo_root).as_posix())
        return found


def tree_manifest(repo_root: Path, artifact_root: str) -> Manifest:
    """Content manifest of the whole working tree for a worker baseline.

    Files under the artifact root are always included, even where the
    repository ignores that directory, so that edits to spec.md, plan.md or
    capability specs are caught. Every change's `runs/` handoff directory is
    excluded: it holds the baseline itself and the worker's report.
    """
    repo_root = repo_root.resolve()
    paths = set(_listed_files(repo_root))
    artifacts = repo_root / artifact_root
    if artifacts.is_dir():
        for directory, dirnames, filenames in os.walk(artifacts):
            dirnames[:] = [name for name in dirnames if name != RUNS_DIR]
            for name in filenames:
                paths.add((Path(directory) / name).relative_to(repo_root).as_posix())
    manifest: Manifest = {}
    for relative in sorted(paths):
        parts = Path(relative).parts
        if _under(relative, artifact_root) and RUNS_DIR in parts:
            continue
        digest = _hash_file(repo_root / relative)
        if digest is not None:
            manifest[relative] = digest
    return manifest


def _under(path: str, prefix: str) -> bool:
    prefix = prefix.strip("/")
    return prefix in ("", ".") or path == prefix or path.startswith(prefix + "/")


def task_scope(plan: Document, task_id: str) -> tuple[list[str], list[str]]:
    """Return (path patterns, uncheckable items) declared by a task's `Files:`."""
    blocks = {identifier: (start, end) for identifier, start, end in plan.blocks("Tasks", "T")}
    if task_id not in blocks:
        raise ScopeError(f"plan.md has no task {task_id}")
    files = task_fields(plan, *blocks[task_id]).get("Files", "")
    if not files.strip():
        raise ScopeError(f"{task_id}: empty Files field")
    return files_patterns(files)


def in_scope(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if path == pattern or path.startswith(pattern + "/"):
            return True
        if any(char in pattern for char in "*?[") and fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def scope_violations(
    baseline: Manifest, current: Manifest, patterns: list[str], artifact_root: str
) -> list[dict[str, str]]:
    delta = diff(baseline, current)
    violations = []
    for kind in ("changed", "added", "removed"):
        for path in delta[kind]:
            if _under(path, artifact_root):
                violations.append({"path": path, "change": kind, "reason": "artifact root is controller-owned"})
            elif not in_scope(path, patterns):
                violations.append({"path": path, "change": kind, "reason": "outside the task's Files"})
    return violations


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
    parser.add_argument("action", choices=("compute", "verify", "diff", "baseline", "check-scope"))
    parser.add_argument("change_slug")
    parser.add_argument("--task", help="Task id such as T3 (for baseline and check-scope)")
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
    if args.action in ("baseline", "check-scope"):
        return _worker_scope(args.action, change, choice.path, args.task)
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


def _worker_scope(action: str, change: Path, artifact_root: str, task: str | None) -> int:
    if not task or not re.fullmatch(r"T\d+", task):
        print("error: --task T<n> is required for baseline and check-scope", file=sys.stderr)
        return 2
    plan_path = change / "plan.md"
    if not plan_path.is_file():
        print(f"unresolvable: missing {plan_path}", file=sys.stderr)
        return 2
    plan = Document(plan_path, str(plan_path))
    try:
        patterns, uncheckable = task_scope(plan, task)
    except ScopeError as exc:
        print(f"unresolvable: {exc}", file=sys.stderr)
        return 2
    baseline_path = runs_dir(change) / f"{task}-baseline.json"
    current = tree_manifest(Path.cwd(), artifact_root)

    if action == "baseline":
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"task": task, "hash": manifest_hash(current), "manifest": current}
        baseline_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"baseline": str(baseline_path), "files": len(current), "uncheckable": uncheckable}))
        return 0

    if not baseline_path.is_file():
        print(f"unresolvable: no baseline at {baseline_path}; run baseline before dispatch", file=sys.stderr)
        return 2
    violations = scope_violations(_load_manifest(str(baseline_path)), current, patterns, artifact_root)
    result = {"task": task, "violations": violations, "uncheckable": uncheckable}
    if violations:
        print(json.dumps(result, indent=2))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
