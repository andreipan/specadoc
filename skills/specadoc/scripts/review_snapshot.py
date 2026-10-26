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

from specadoc_root import ensure_runs, legacy_warning, resolve_root  # noqa: E402
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
# Paths whose post-review MINOR fixes cannot change runtime behavior: tests and prose.
NON_EXECUTABLE = re.compile(
    r"(?:^|/)(?:tests?|__tests__)/|_test\.go$|\.(?:test|spec)\.[cm]?[jt]sx?$|\.(?:md|rst|adoc)$")
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


def frozen_contract(plan: Document, task_id: str) -> dict[str, str]:
    """Plan facts a worker must not change: its Verification and the plan approval."""
    from validate_change import review_policy_hash
    blocks = {identifier: (start, end) for identifier, start, end in plan.blocks("Tasks", "T")}
    fields = task_fields(plan, *blocks[task_id]) if task_id in blocks else {}
    return {"verification": " ".join(fields.get("Verification", "").split()),
            "approval": review_policy_hash(plan)}


def task_derived(plan: Document, task_id: str) -> tuple[list[str], list[str]]:
    """Return (path patterns, uncheckable items) of a task's optional `Derived files:`."""
    blocks = {identifier: (start, end) for identifier, start, end in plan.blocks("Tasks", "T")}
    if task_id not in blocks:
        raise ScopeError(f"plan.md has no task {task_id}")
    derived = task_fields(plan, *blocks[task_id]).get("Derived files", "")
    if not derived.strip() or re.match(r"(?:none|n/a|-)\b", derived.strip(), re.I):
        return [], []
    return files_patterns(derived)


# A lockfile follows its manifest: it is derived when a matching manifest in its
# directory, or in a workspace package below it, is in scope.
# A `<stem>.lock` follows a same-stem manifest; anything else goes under `Derived files:`.
LOCKFILES = {"package-lock.json": "package.json", "npm-shrinkwrap.json": "package.json",
             "pnpm-lock.yaml": "package.json", "yarn.lock": "package.json", "bun.lock": "package.json",
             "bun.lockb": "package.json", "go.sum": "go.mod"}


def is_derived(path: str, patterns: list[str], derived: list[str]) -> bool:
    if in_scope(path, derived):
        return True
    directory, _, name = path.rpartition("/")
    prefix = f"{directory}/" if directory else ""
    scoped = [p for p in (*patterns, *derived) if not any(c in p for c in "*?")]
    if (manifest := LOCKFILES.get(name)) is not None:
        # The manifest beside the lockfile, or one in a workspace package below it.
        return any(p.startswith(prefix) and p.rsplit("/", 1)[-1] == manifest for p in scoped)
    if name.endswith(".lock"):
        # `<stem>.lock` follows a manifest with the same stem in its directory
        # (`<stem>.json`, `<stem>.toml`, or an extensionless `<stem>`).
        stem = name.removesuffix(".lock")
        return any(p.startswith(prefix) and "/" not in p[len(prefix):]
                   and p[len(prefix):].split(".", 1)[0] == stem for p in scoped)
    return False


def in_scope(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if path == pattern or path.startswith(pattern + "/"):
            return True
        if any(char in pattern for char in "*?[") and fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def scope_violations(
    baseline: Manifest, current: Manifest, patterns: list[str], artifact_root: str,
    derived: list[str] | None = None, exempt: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    """Changes outside Files. Derived files and the controller's own plan are not violations."""
    delta = diff(baseline, current)
    violations = []
    for kind in ("changed", "added", "removed"):
        for path in delta[kind]:
            if path in exempt:
                continue
            if _under(path, artifact_root):
                violations.append({"path": path, "change": kind, "reason": "artifact root is controller-owned"})
            elif not in_scope(path, patterns) and not is_derived(path, patterns, derived or []):
                violations.append({"path": path, "change": kind, "reason": "outside the task's Files"})
    return violations


def derived_changes(baseline: Manifest, current: Manifest, patterns: list[str], derived: list[str]) -> list[str]:
    delta = diff(baseline, current)
    return sorted(path for paths in delta.values() for path in paths
                  if not in_scope(path, patterns) and is_derived(path, patterns, derived))


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
    from validate_change import minor_only_pass
    paths = sorted({path for values in delta.values() for path in values})
    minor = minor_only_pass(plan, round_id)
    if minor and CONTRACT_KEY not in paths and all(NON_EXECUTABLE.search(path) for path in paths):
        print(f"warning: {round_id} PASS covers post-review MINOR fixes in non-executable files: "
              f"{', '.join(paths)}; name them in Archive summary", file=sys.stderr)
        return []
    if minor and fields.get("Reason", "").strip().lower() == "minor-fixes":
        hint = ("revert it and record the remaining MINOR findings as residual risks, "
                "or ask the user for a --review-decision on one more round")
    elif minor:
        hint = "run pre-review --review-type re-review --reason minor-fixes for the executable MINOR fixes"
    else:
        hint = "return to apply for a new review"
    return [
        f"Review result: diff changed since {round_id}'s snapshot "
        f"(changed={delta['changed']}, added={delta['added']}, removed={delta['removed']}); {hint}"
    ]


def round_manifest(plan: Document, identifier: str) -> Manifest:
    """The manifest recorded in plan.md's `### G<n>` review round."""
    for found, start, end in plan.blocks("Review result", "G"):
        if found == identifier:
            text = "\n".join(plan.lines[start:end])
            if "```json" in text:
                payload = json.loads(text.split("```json", 1)[1].split("```", 1)[0])
                if isinstance(payload, dict):
                    return payload
            raise ValueError(f"{identifier} has no recorded manifest")
    raise ValueError(f"plan.md has no review round {identifier}")


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
    parser.add_argument("--previous", help="Previous round id (G<n>), or its manifest as a JSON file path or inline JSON (for diff)")
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
    try:
        previous = (round_manifest(Document(change / "plan.md", "plan.md"), args.previous)
                    if re.fullmatch(r"G\d+", args.previous) else _load_manifest(args.previous))
    except (OSError, ValueError) as exc:
        print(f"unresolvable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(diff(previous, current), indent=2))
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
        derived, derived_uncheckable = task_derived(plan, task)
        uncheckable += derived_uncheckable
    except ScopeError as exc:
        print(f"unresolvable: {exc}", file=sys.stderr)
        return 2
    baseline_path = runs_dir(change) / f"{task}-baseline.json"
    current = tree_manifest(Path.cwd(), artifact_root)

    if action == "baseline":
        ensure_runs(baseline_path.parent)
        if baseline_path.exists():
            # Retries must compare against the first attempt, never adopt its writes.
            try:
                original = json.loads(baseline_path.read_text(encoding="utf-8"))
                manifest = original["manifest"]
                if not isinstance(manifest, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in manifest.items()):
                    raise ValueError("invalid baseline manifest")
                if original.get("hash") != manifest_hash(manifest):
                    raise ValueError("baseline hash mismatch; inspect original evidence, do not reset")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                print(f"unresolvable: invalid existing baseline ({exc})", file=sys.stderr)
                return 2
            print(json.dumps({"baseline": str(baseline_path), "files": len(original["manifest"]),
                              "uncheckable": uncheckable, "reused": True}))
            return 0
        from task_state import SCHEMA, save, timestamp
        from validate_change import capability_deltas, capability_requirements
        spec_path = change / "spec.md"
        capabilities = {}
        if spec_path.is_file():
            spec = Document(spec_path, str(spec_path))
            for _, path, _, _ in capability_deltas(spec, artifact_root):
                capabilities[path] = {"present": Path(path).is_file(),
                                      "requirements": sorted(capability_requirements(Path(path)))}
        payload = {"schema": SCHEMA, "task": task, "hash": manifest_hash(current),
                   "manifest": current, "scope": patterns, "derived": derived, "state": "dispatched",
                   "frozen": frozen_contract(plan, task),
                   "started": timestamp(), "capabilities": capabilities}
        save(baseline_path, payload)
        print(json.dumps({"baseline": str(baseline_path), "files": len(current), "uncheckable": uncheckable}))
        return 0

    if not baseline_path.is_file():
        print(f"unresolvable: no baseline at {baseline_path}; run baseline before dispatch", file=sys.stderr)
        return 2
    record = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline = _load_manifest(str(baseline_path))
    if record.get("hash") != manifest_hash(baseline):
        print("unresolvable: baseline hash mismatch; do not reset the attempt", file=sys.stderr)
        return 2
    for path, digest in record.get("controller_changes", {}).items():
        if digest == DELETED_DIGEST:
            baseline.pop(path, None)
        else:
            baseline[path] = digest
    frozen = record.get("scope", patterns)
    frozen_derived = record.get("derived", derived)
    # The controller owns this change's plan.md; the worker brief forbids editing it.
    own_plan = Path(os.path.relpath(plan_path.resolve(), Path.cwd().resolve())).as_posix()
    violations = scope_violations(baseline, current, frozen, artifact_root, frozen_derived, (own_plan,))
    if set(patterns) != set(frozen) or set(derived) != set(frozen_derived):
        violations.append({"path": own_plan, "change": "changed",
                           "reason": "task scope differs from its baseline; use specadoc_step.py amend"})
    contract = record.get("frozen")
    if isinstance(contract, dict):
        current_contract = frozen_contract(plan, task)
        for key in sorted(k for k in contract if contract[k] != current_contract.get(k)):
            violations.append({"path": own_plan, "change": "changed",
                               "reason": f"task {key} changed since dispatch; the controller uses specadoc_step.py amend"})
    result = {"task": task, "violations": violations, "uncheckable": uncheckable,
              "derived": derived_changes(baseline, current, frozen, frozen_derived)}
    if violations:
        print(json.dumps(result, indent=2))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
