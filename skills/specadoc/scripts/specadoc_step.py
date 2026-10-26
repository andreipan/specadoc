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
from validate_change import Document, task_fields, review_policy_hash, files_field_hash, files_field_digests  # noqa: E402
from review_snapshot import CONTRACT_KEY, diff, tree_manifest  # noqa: E402
from task_state import approval_error, digest, readiness, safe_path, save, task_block, timestamp, update_task  # noqa: E402

COMMAND = re.compile(r"`([^`]+)`")
AUTO_EVIDENCE = re.compile(r"`[^`]+` — PASS")
PENDING_REASON = re.compile(r"\b(?:pending|TBD|N/A)\b", re.I)
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
    return {"PASS": 0, "CHECKED": 0, "ACCEPTED": 0, "FAIL": 1}.get(result, 2)


def root_args(root: str | None) -> list[str]:
    return ["--root", root] if root else []


def binding_check(role: str, controller: str | None) -> list[str]:
    from specadoc_config import load_config
    if not (controller or "roles" in load_config(Path.cwd())):
        return []  # Legacy host/plugin registry fallback, unchanged.
    if not controller:
        raise ValueError("routed dispatch requires --controller-runtime")
    from role_routing import resolve_role
    route = resolve_role(Path.cwd(), role, controller)
    return [f"resolved {role} {route['runtime']}/{route['model']}/{route['effort']}"]


def reopen_attempt(change: Path, task: str, reason: str) -> list[dict]:
    """Archive the current attempt so a later fix starts from today's tree.

    Retries keep the original baseline; a reopen is the explicit exception for
    corrective work after later tasks have changed the tree.
    """
    if not reason.strip() or PENDING_REASON.search(reason):
        raise ValueError("reopen needs the controller's concrete reason")
    baseline_path = change / "runs" / f"{task}-baseline.json"
    if not baseline_path.is_file():
        raise ValueError(f"{task} has no previous attempt to reopen; dispatch it normally")
    record = json.loads(baseline_path.read_text(encoding="utf-8"))
    attempts = record.pop("attempts", [])
    report = change / "runs" / f"{task}-report.md"
    archived_report = None
    if report.is_file():
        archived_report = report.with_name(f"{task}-report-a{len(attempts) + 1}.md")
        report.replace(archived_report)
    attempts.append({**{key: value for key, value in record.items() if key != "manifest"},
                     "reopened_at": timestamp(), "reopen_reason": " ".join(reason.split()),
                     "report": archived_report.name if archived_report else None})
    baseline_path.unlink()
    plan_path = change / "plan.md"
    plan_path.write_text(update_task(Document(plan_path, str(plan_path)), task, {}, reopen=True), encoding="utf-8")
    return attempts


def dispatch(slug: str, task: str, root: str | None, controller: str | None = None,
             context_tokens: int | None = None, reopen: str | None = None) -> int:
    context_source = "reported"
    if context_tokens is None:
        from collect_tokens import claude_context_tokens, current_claude_transcript
        if (transcript := current_claude_transcript()) is not None:
            context_tokens, context_source = claude_context_tokens(transcript), f"read from {transcript.name}"
    if context_tokens is not None and context_tokens >= 150000:
        return emit([f"context budget ({context_source})"], "BLOCKED", [],
                    f"controller context is {context_tokens} tokens, at least 150k",
                    "save the current handoff and resume apply in a fresh session before another dispatch")
    plan_path = Path(resolve_root(root).path) / slug / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if errors := readiness(plan, task):
        return emit(["apply readiness"], "BLOCKED", [], "; ".join(errors), "resolve approval, dependencies and decisions before dispatch")
    gate = run_script("validate_change.py", slug, "--phase", "plan", *root_args(root))
    if gate.returncode:
        return emit(["validate plan"], "BLOCKED", [], tail(gate.stderr + gate.stdout), "fix the plan before dispatch")
    checked = binding_check("worker", controller)
    checked.append(f"context {context_tokens} tokens ({context_source})" if context_tokens is not None
                   else "context not reported (pass --context-tokens from the host's observed count)")
    attempts = previous_manifest = None
    if reopen is not None:
        previous_manifest = json.loads((plan_path.parent / "runs" / f"{task}-baseline.json").read_text())["manifest"] \
            if (plan_path.parent / "runs" / f"{task}-baseline.json").is_file() else None
        attempts = reopen_attempt(plan_path.parent, task, reopen)
        checked.append(f"reopened as attempt {len(attempts) + 1}")
    checked += ["baseline", "brief"]
    baseline = run_script("review_snapshot.py", "baseline", slug, "--task", task, *root_args(root))
    if baseline.returncode != 0:
        if attempts:
            # Put the previous attempt back rather than lose its history.
            previous = dict(attempts[-1], attempts=attempts[:-1], manifest=previous_manifest)
            save(plan_path.parent / "runs" / f"{task}-baseline.json", previous)
        return emit(checked[:1], "BLOCKED", [], tail(baseline.stderr + baseline.stdout), "fix the plan task, then rerun dispatch")
    if attempts:
        baseline_path = plan_path.parent / "runs" / f"{task}-baseline.json"
        record = json.loads(baseline_path.read_text(encoding="utf-8"))
        record["attempts"] = attempts
        save(baseline_path, record)
    uncheckable = json.loads(baseline.stdout).get("uncheckable", [])
    brief = run_script("task_brief.py", slug, task, *root_args(root))
    if brief.returncode != 0:
        return emit(checked, "BLOCKED", [], tail(brief.stderr + brief.stdout), "fix the plan task, then rerun dispatch")
    brief_path = Path(brief.stdout.strip())
    if uncheckable:
        reason = f"Files items that are not paths: {', '.join(uncheckable)}"
        return emit(checked, "FAIL", [], reason, "make every Files item a path, then rerun dispatch")
    report = brief_path.with_name(f"{task}-report.md")
    _, failure = check_scope(slug, task, root, checked)
    if failure is not None:
        return failure
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


def scope_state(slug: str, task: str, root: str | None, checked: list[str]) -> tuple[list[str], list[str], list[str], int | None]:
    """Return (changed files, violations, derived files, blocking exit)."""
    scope = run_script("review_snapshot.py", "check-scope", slug, "--task", task, *root_args(root))
    if scope.returncode == 2:
        return [], [], [], emit(checked, "BLOCKED", [], tail(scope.stderr + scope.stdout), "run dispatch before the worker starts")
    try:
        payload = json.loads(scope.stdout)
    except ValueError:
        return [], [], [], emit(checked, "BLOCKED", [], "scope check did not return valid JSON", "inspect the baseline and plan, then retry")
    if payload.get("uncheckable"):
        return [], [], [], emit(checked, "BLOCKED", [], "Files items are not paths", "fix the plan before dispatch")
    violations = [f"{item['path']} ({item['reason']})" for item in payload.get("violations", [])]
    artifact_root = resolve_root(root).path
    baseline_path = Path(artifact_root) / slug / "runs" / f"{task}-baseline.json"
    baseline = json.loads(baseline_path.read_text())["manifest"]
    delta = diff(baseline, tree_manifest(Path.cwd(), artifact_root))
    changed = sorted(path for paths in delta.values() for path in paths)
    return changed, violations, payload.get("derived", []), None


def check_scope(slug: str, task: str, root: str | None, checked: list[str]) -> tuple[list[str], int | None]:
    changed, violations, _, failure = scope_state(slug, task, root, checked)
    if failure is not None:
        return [], failure
    if violations:
        return [], emit(checked, "FAIL", violations, "changes outside the task scope",
                        "revert each path, list it in Derived files via amend, or amend --allow it with a reason")
    return changed, None


def worker_result(change: Path, task: str, result_file: str | None) -> tuple[dict, Path]:
    from run_role import _parse_json_text, schema_errors, schema_path
    report = change / "runs" / f"{task}-report.md"
    if not report.is_file():
        raise ValueError(f"worker report is missing: {report}")
    source = safe_path(result_file, allow_missing=False, allow_absolute=True) if result_file else report
    payload = _parse_json_text(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "result" in payload and "exit" in payload:
        if payload["exit"] != 0:
            raise ValueError("external worker exited unsuccessfully")
        payload = payload["result"]
    errors = schema_errors(payload, json.loads(schema_path("worker").read_text()))
    if errors:
        raise ValueError("invalid worker result: " + "; ".join(errors))
    if safe_path(payload["report"], allow_missing=False, allow_absolute=True).resolve() != report.resolve():
        raise ValueError("worker result points to a different report")
    if payload["status"] not in ("DONE", "DONE_WITH_CONCERNS"):
        raise ValueError(f"worker status {payload['status']} is not completion")
    for path in payload["files_changed"]:
        safe_path(path)
    return payload, report


def amendments_since_dispatch(slug: str, task: str, root: str | None) -> list[str]:
    path = Path(resolve_root(root).path) / slug / "runs" / f"{task}-baseline.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f"{item.get('reason', '')} ({', '.join(item.get('allow', []) + item.get('derived', []) + item.get('controller_paths', [])) or 'no paths'})"
            for item in record.get("amendments", []) if isinstance(item, dict)]


def accept(slug: str, task: str, root: str | None, *, scope_only: bool = False, result_file: str | None = None,
           note: str | None = None, verification_timeout: float = 600) -> int:
    checked = ["check-scope"]
    changed, violations, derived, failure = scope_state(slug, task, root, checked)
    if failure is not None:
        return failure
    if derived:
        checked.append("derived: " + ", ".join(derived))
    amendments = amendments_since_dispatch(slug, task, root)
    if amendments:
        # A shell-capable worker could call amend itself; make every amendment visible.
        checked.append("amendments: " + " | ".join(amendments))
    scope_next = "revert each path, list it in Derived files via amend, or amend --allow it with a reason"
    if scope_only:
        if violations:
            return emit(checked, "FAIL", violations, "changes outside the task scope", scope_next)
        return emit(checked, "CHECKED", changed, "", "scope only; not accepted: run accept without --scope-only")
    if verification_timeout <= 0:
        raise ValueError("verification timeout must be positive")
    if note is not None and (not note.strip() or PENDING_REASON.search(note)):
        raise ValueError("--note must name the actual decision or accepted result")

    change = Path(resolve_root(root).path) / slug
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if error := approval_error(plan):
        return emit(checked, "BLOCKED", violations or changed, error, "obtain plan approval before acceptance")
    try:
        payload, report = worker_result(change, task, result_file)
        commands = verification_commands(slug, task, root)
    except (OSError, ValueError) as exc:
        return emit(checked, "BLOCKED", violations or changed, str(exc),
                    "supply a schema-valid worker report/result and exact Verification commands")
    if not commands:
        return emit(checked, "BLOCKED", violations, "Verification has no backticked command", "run the Verification yourself")
    baseline_path = change / "runs" / f"{task}-baseline.json"
    record = json.loads(baseline_path.read_text())
    _, _, fields = task_block(plan, task)
    file_hash = files_field_hash(fields.get("Files", ""))
    prior = record.get("verification", {})
    # Verification is reused automatically only for byte-identical Files and commands.
    reuse = (file_hash is not None and prior.get("files_hash") == file_hash
             and prior.get("commands") == commands and prior.get("passed") is True)
    for command in ([] if reuse else commands):
        checked.append(command)
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=verification_timeout)
        except subprocess.TimeoutExpired:
            return emit(checked, "BLOCKED", violations, f"verification timed out after {verification_timeout:g}s",
                        "inspect the existing process/log before retrying; keep the same baseline")
        log = change / "runs" / f"{task}-verify.log"
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            detail = tail(result.stdout + result.stderr)
            reason = f"`{command}` exited {result.returncode}"
            if violations:
                reason += "; also changes outside the task scope"
            return emit(checked, "FAIL", violations, reason, "fix or re-dispatch with the failure", detail)
    if reuse:
        checked.append("reused verification for unchanged files and commands")
    checked.append("check-scope after verification")
    changed, after, derived_after, failure = scope_state(slug, task, root, checked)
    if failure is not None:
        return failure
    violations = list(dict.fromkeys([*violations, *after]))
    record["verification"] = {"commands": commands, "files_hash": files_field_hash(fields.get("Files", "")),
                              "files": files_field_digests(fields.get("Files", "")), "passed": True, "at": timestamp()}
    if violations:
        save(baseline_path, record)
        return emit(checked, "FAIL", violations, "verification passed, but changes are outside the task scope", scope_next)
    record["state"] = "verified"
    save(baseline_path, record)
    concerns = payload["concerns"]
    if (concerns or payload["status"] == "DONE_WITH_CONCERNS") and not note:
        emit(checked, "NEEDS_DECISION", changed, "worker concerns require a controller disposition",
             "read the concerns; rerun accept with --note '<decision>' (verification is reused), or return to implementation")
        return 2
    evidence = "; ".join(f"`{cmd}` — PASS" for cmd in commands)
    if fields.get("Surface", "").lower() in ("ui", "mixed"):
        # Keep the controller's observed Build/Typecheck/Browser records; never fabricate them
        # from a build exit, and never repeat the command list written by an earlier accept.
        previous = [part.strip() for part in fields.get("Evidence", "").split(";")]
        kept = [part for part in previous if part and not AUTO_EVIDENCE.fullmatch(part)
                and re.match(r"(?:build|typecheck|browser):", part, re.I)]
        if kept:
            evidence += "; " + "; ".join(kept)
    values = {"Evidence": evidence, "Evidence hash": files_field_hash(fields.get("Files", "")) or "Not recorded",
              "Accepted result": payload["summary"] + (f"; controller: {note}" if note else "")}
    plan_path.write_text(update_task(plan, task, values, complete=True), encoding="utf-8")
    record.update(state="accepted", accepted_at=timestamp(), accepted_result=values["Accepted result"],
                  report_hash=digest(report), concerns=concerns, note=note)
    save(baseline_path, record)
    return emit(checked, "ACCEPTED", changed, "", "task evidence and accepted result saved; continue with the next ready task")


def amend(slug: str, task: str, root: str | None, allowed: list[str], controller_paths: list[str], reason: str,
          derived: list[str] | None = None) -> int:
    if not reason.strip() or re.search(r"\b(?:pending|TBD|N/A)\b", reason, re.I):
        raise ValueError("scope amendment needs the controller's concrete reason")
    change = Path(resolve_root(root).path) / slug
    baseline_path = change / "runs" / f"{task}-baseline.json"
    record = json.loads(baseline_path.read_text())
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if error := approval_error(plan):
        raise ValueError(error)
    _, _, fields = task_block(plan, task)
    paths = [safe_path(path).as_posix() for path in allowed]
    derived_paths = [safe_path(path).as_posix() for path in derived or []]
    if any(path == resolve_root(root).path or path.startswith(resolve_root(root).path + "/") for path in paths + derived_paths):
        raise ValueError("worker scope cannot include the controller-owned artifact root")
    for path in controller_paths:
        safe_path(path)
    scope = record.get("scope", [])
    from validate_change import files_patterns
    if not scope:
        scope = files_patterns(fields["Files"])[0]
    new_scope = list(dict.fromkeys([*scope, *paths]))
    from review_snapshot import task_derived
    old_derived = record.get("derived", task_derived(plan, task)[0])
    new_derived = list(dict.fromkeys([*old_derived, *derived_paths]))
    values = {"Files": ", ".join(f"`{path}`" for path in new_scope), "Scope amendment": reason}
    if new_derived:
        values["Derived files"] = ", ".join(f"`{path}`" for path in new_derived)
    plan_path.write_text(update_task(plan, task, values, reopen=True), encoding="utf-8")
    changes = record.setdefault("controller_changes", {})
    for path in controller_paths:
        changes[path] = digest(Path(path))
    record["scope"] = new_scope
    record["derived"] = new_derived
    from review_snapshot import frozen_contract
    record["frozen"] = frozen_contract(Document(plan_path, str(plan_path)), task)
    record.setdefault("amendments", []).append({"at": timestamp(), "allow": paths, "derived": derived_paths,
                                                "controller_paths": controller_paths, "reason": reason})
    record["state"] = "dispatched"
    record.pop("verification", None)
    save(baseline_path, record)
    return emit(["explicit controller amendment"], "CHECKED", paths, "", "retry the same task; original baseline is retained")


def pre_review(slug: str, root: str | None, controller: str | None = None, *,
               review_type: str = "initial", reason: str | None = None,
               decision: str | None = None, record_round: bool = False) -> int:
    checked = binding_check("reviewer", controller) + ["validate pre-review"]
    extras = ["--review-decision", decision] if decision else []
    gate = run_script("validate_change.py", slug, "--phase", "pre-review", "--next-review-type", review_type,
                      *extras, *root_args(root))
    if gate.returncode != 0:
        result = "BLOCKED" if gate.returncode == 2 else "FAIL"
        return emit(checked, result, [], tail(gate.stderr + gate.stdout), "fix the plan, then rerun pre-review")
    checked.append("snapshot compute")
    snapshot = run_script("review_snapshot.py", "compute", slug, *root_args(root))
    if snapshot.returncode != 0:
        return emit(checked, "BLOCKED", [], tail(snapshot.stderr + snapshot.stdout), "fix Review scope")
    payload = json.loads(snapshot.stdout)
    changed = sorted(path for path in payload["manifest"] if path != CONTRACT_KEY)
    plan = Document(Path(resolve_root(root).path) / slug / "plan.md", "plan.md")
    if record_round:
        from review_state import insert_round
        identifier = insert_round(Path(resolve_root(root).path) / slug, payload, review_type,
                                  reason or ("corrections" if review_type == "re-review" else "implementation"), decision)
        return emit(checked, "PASS", changed, "", f"dispatch independent reviewer for recorded {identifier}",
                    f"snapshot: {payload['hash']}\npolicy snapshot: {review_policy_hash(plan)}\nmanifest: recorded in plan.md")
    detail = f"snapshot: {payload['hash']}\npolicy snapshot: {review_policy_hash(plan)}\n```json\n{json.dumps(payload['manifest'])}\n```"
    return emit(checked, "PASS", changed, "", "record this snapshot in a new G<n> round and dispatch the reviewer", detail)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Artifact root (default: resolved, see specadoc_root.py)")
    steps = parser.add_subparsers(dest="step", required=True)
    for name in ("dispatch", "accept", "amend"):
        step = steps.add_parser(name)
        step.add_argument("change_slug")
        step.add_argument("task", help="Task id such as T3")
        if name == "accept":
            step.add_argument("--scope-only", action="store_true", help="Check scope only; never accepts")
            step.add_argument("--verify", action="store_true", help=argparse.SUPPRESS)  # default since 2026-10
            step.add_argument("--result-file", help="Schema-valid worker JSON; default: fenced JSON in its report")
            step.add_argument("--note", help="Controller decision on concerns or corrections to the accepted result")
            step.add_argument("--verification-timeout", type=float, default=600)
        if name == "dispatch":
            step.add_argument("--context-tokens", type=int, help="Observed current controller input context")
            step.add_argument("--reopen", metavar="REASON",
                              help="Start a new attempt of an earlier task from the current tree (corrective work)")
        if name == "amend":
            step.add_argument("--allow", action="append", default=[], help="Additional literal worker path")
            step.add_argument("--derived", action="append", default=[], help="Generated/wiring path the task may touch")
            step.add_argument("--controller-path", action="append", default=[], help="Current content explicitly changed by controller")
            step.add_argument("--reason", required=True)
    review = steps.add_parser("pre-review")
    review.add_argument("change_slug")
    review.add_argument("--review-type", choices=("initial", "re-review"), default="initial")
    review.add_argument("--reason", choices=("implementation", "corrections", "minor-fixes", "requirements", "polish"))
    review.add_argument("--review-decision", help="Actual user decision authorizing a bounded extra round")
    review.add_argument("--dry-run", action="store_true", help="Run the gate and print the snapshot without recording a round")
    review.add_argument("--record-round", action="store_true", help=argparse.SUPPRESS)  # default since 2026-10
    settled = steps.add_parser("review-result")
    settled.add_argument("change_slug")
    settled.add_argument("--result-file", required=True)
    for step in (steps.choices["dispatch"], review):
        step.add_argument("--controller-runtime", choices=("codex", "claude", "opencode"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.step in ("dispatch", "accept", "amend") and not re.fullmatch(r"T\d+", args.task):
        print("error: task must look like T<n>", file=sys.stderr)
        return 2
    try:
        if args.step == "dispatch":
            return dispatch(args.change_slug, args.task, args.root, args.controller_runtime, args.context_tokens,
                            args.reopen)
        if args.step == "accept":
            return accept(args.change_slug, args.task, args.root, scope_only=args.scope_only,
                          result_file=args.result_file, note=args.note,
                          verification_timeout=args.verification_timeout)
        if args.step == "amend":
            return amend(args.change_slug, args.task, args.root, args.allow, args.controller_path, args.reason, args.derived)
        if args.step == "review-result":
            from review_state import record_result
            identifier = record_result(Path(resolve_root(args.root).path) / args.change_slug, args.result_file)
            return emit(["review schema", "snapshot", "persist result"], "CHECKED", [], "",
                        f"{identifier} saved; read findings before a user question or further edits")
        return pre_review(args.change_slug, args.root, args.controller_runtime,
                          review_type=args.review_type, reason=args.reason, decision=args.review_decision,
                          record_round=not args.dry_run)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return emit([args.step], "BLOCKED", [], str(exc), "inspect the plan and handoff files, then retry")


if __name__ == "__main__":
    raise SystemExit(main())
