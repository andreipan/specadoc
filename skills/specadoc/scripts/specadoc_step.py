#!/usr/bin/env python3
"""One call per apply step: run the existing gate scripts and print a compact result.

Each step only composes `review_snapshot.py`, `task_brief.py`, and
`validate_change.py`; their logic and exit codes stay authoritative. The output
is five fields so the controller reads one short block instead of several raw
script outputs:

    checked: <what ran>
    result: PASS | FAIL | BLOCKED
    changed files: <paths or ->
    blocking reason: <reason or ->
    next: <the next allowed step>

Steps:

- `dispatch <slug> T<n>` — worker baseline plus brief, before dispatch.
- `accept <slug> T<n> [--verify]` — scope check after the worker returns and,
  with `--verify`, exact Verification commands, then a second scope check.
  Commands must occupy the entire field, backticked and separated by semicolons.
  Run from the repository root; --verify executes shell commands with the
  caller's permissions. Inspect them first and follow host approval rules.
- `pre-review <slug>` — the pre-review gate plus the snapshot manifest to record
  in the new `### G<n>` round.

Exit codes: 0 PASS, 1 FAIL (fixable finding), 2 BLOCKED (cannot evaluate).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from specadoc_root import resolve_root  # noqa: E402
from validate_change import Document, task_fields  # noqa: E402
from review_snapshot import CONTRACT_KEY, diff, tree_manifest  # noqa: E402

COMMAND = re.compile(r"`([^`]+)`")
TAIL_LINES = 30


def run_script(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
    )


def tail(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines[-TAIL_LINES:])[-6000:]


def emit(checked: list[str], result: str, changed: list[str], reason: str, next_step: str, detail: str = "") -> int:
    print(f"checked: {'; '.join(checked)}")
    print(f"result: {result}")
    print(f"changed files: {', '.join(changed) if changed else '-'}")
    print(f"blocking reason: {' '.join(reason.split()) or '-'}")
    print(f"next: {next_step}")
    if detail:
        print(detail)
    return {"PASS": 0, "FAIL": 1}.get(result, 2)


def root_args(root: str | None) -> list[str]:
    return ["--root", root] if root else []


def dispatch(slug: str, task: str, root: str | None) -> int:
    checked = ["baseline", "brief"]
    baseline = run_script("review_snapshot.py", "baseline", slug, "--task", task, *root_args(root))
    if baseline.returncode != 0:
        return emit(checked[:1], "BLOCKED", [], tail(baseline.stderr + baseline.stdout), "fix the plan task, then rerun dispatch")
    uncheckable = json.loads(baseline.stdout).get("uncheckable", [])
    brief = run_script("task_brief.py", slug, task, *root_args(root))
    if brief.returncode != 0:
        return emit(checked, "BLOCKED", [], tail(brief.stderr + brief.stdout), "fix the plan task, then rerun dispatch")
    brief_path = Path(brief.stdout.strip())
    if uncheckable:
        reason = f"Files items that are not paths: {', '.join(uncheckable)}"
        return emit(checked, "FAIL", [], reason, "make every Files item a path, then rerun dispatch")
    report = brief_path.with_name(f"{task}-report.md")
    return emit(checked, "PASS", [], "", f"dispatch the worker with brief {brief_path} and report {report}")


def verification_commands(slug: str, task: str, root: str | None) -> list[str]:
    plan_path = Path(resolve_root(root).path) / slug / "plan.md"
    plan = Document(plan_path, str(plan_path))
    blocks = {identifier: (start, end) for identifier, start, end in plan.blocks("Tasks", "T")}
    if task not in blocks:
        raise ValueError(f"plan.md has no task {task}")
    field = task_fields(plan, *blocks[task]).get("Verification", "")
    if not re.fullmatch(r"\s*`[^`\n]+`(?:\s*;\s*`[^`\n]+`)*\s*", field):
        raise ValueError("Verification must contain only exact backticked commands separated by semicolons; run prose checks manually")
    return COMMAND.findall(field)


def check_scope(slug: str, task: str, root: str | None, checked: list[str]) -> tuple[list[str], int | None]:
    scope = run_script("review_snapshot.py", "check-scope", slug, "--task", task, *root_args(root))
    if scope.returncode == 2:
        return [], emit(checked, "BLOCKED", [], tail(scope.stderr + scope.stdout), "run dispatch before the worker starts")
    try:
        payload = json.loads(scope.stdout)
    except ValueError:
        return [], emit(checked, "BLOCKED", [], "scope check did not return valid JSON", "inspect the baseline and plan, then retry")
    if scope.returncode != 0:
        paths = [f"{item['path']} ({item['reason']})" for item in payload.get("violations", [])]
        return [], emit(checked, "FAIL", paths, "changes outside the task scope", "revert or justify each path; never widen Files")
    if payload.get("uncheckable"):
        return [], emit(checked, "BLOCKED", [], "Files items are not paths", "fix the plan before dispatch")
    artifact_root = resolve_root(root).path
    baseline_path = Path(artifact_root) / slug / "runs" / f"{task}-baseline.json"
    baseline = json.loads(baseline_path.read_text())["manifest"]
    delta = diff(baseline, tree_manifest(Path.cwd(), artifact_root))
    return sorted(path for paths in delta.values() for path in paths), None


def accept(slug: str, task: str, root: str | None, verify: bool) -> int:
    checked = ["check-scope"]
    changed, failure = check_scope(slug, task, root, checked)
    if failure is not None:
        return failure
    if not verify:
        return emit(checked, "PASS", changed, "", "scope only: run the task Verification yourself, then read the worker report")

    try:
        commands = verification_commands(slug, task, root)
    except (OSError, ValueError) as exc:
        return emit(checked, "BLOCKED", changed, str(exc), "run the Verification manually")
    if not commands:
        return emit(checked, "BLOCKED", [], "Verification has no backticked command", "run the Verification yourself")
    for command in commands:
        checked.append(command)
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            detail = tail(result.stdout + result.stderr)
            return emit(checked, "FAIL", changed, f"`{command}` exited {result.returncode}", "fix or re-dispatch with the failure", detail)
    checked.append("check-scope after verification")
    changed, failure = check_scope(slug, task, root, checked)
    if failure is not None:
        return failure
    return emit(checked, "PASS", changed, "", "read the worker report and accept the task")


def pre_review(slug: str, root: str | None) -> int:
    checked = ["validate pre-review"]
    gate = run_script("validate_change.py", slug, "--phase", "pre-review", *root_args(root))
    if gate.returncode != 0:
        result = "BLOCKED" if gate.returncode == 2 else "FAIL"
        return emit(checked, result, [], tail(gate.stderr + gate.stdout), "fix the plan, then rerun pre-review")
    checked.append("snapshot compute")
    snapshot = run_script("review_snapshot.py", "compute", slug, *root_args(root))
    if snapshot.returncode != 0:
        return emit(checked, "BLOCKED", [], tail(snapshot.stderr + snapshot.stdout), "fix Review scope")
    payload = json.loads(snapshot.stdout)
    changed = sorted(path for path in payload["manifest"] if path != CONTRACT_KEY)
    detail = f"snapshot: {payload['hash']}\n```json\n{json.dumps(payload['manifest'])}\n```"
    return emit(checked, "PASS", changed, "", "record this snapshot in a new G<n> round and dispatch the reviewer", detail)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Artifact root (default: resolved, see specadoc_root.py)")
    steps = parser.add_subparsers(dest="step", required=True)
    for name in ("dispatch", "accept"):
        step = steps.add_parser(name)
        step.add_argument("change_slug")
        step.add_argument("task", help="Task id such as T3")
        if name == "accept":
            step.add_argument("--verify", action="store_true", help="Also run the task's Verification commands")
    steps.add_parser("pre-review").add_argument("change_slug")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.step != "pre-review" and not re.fullmatch(r"T\d+", args.task):
        print("error: task must look like T<n>", file=sys.stderr)
        return 2
    try:
        if args.step == "dispatch":
            return dispatch(args.change_slug, args.task, args.root)
        if args.step == "accept":
            return accept(args.change_slug, args.task, args.root, args.verify)
        return pre_review(args.change_slug, args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return emit([args.step], "BLOCKED", [], str(exc), "inspect the plan and handoff files, then retry")


if __name__ == "__main__":
    raise SystemExit(main())
