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

- `approve <slug> --by user|orchestrator --source '<decision>'` — record plan
  approval and provenance; hashes spec.md/design.md into `runs/approval.json`.
- `preflight <slug> T<n>` — read-only task validation, no Verification execution.
- `dispatch <slug> T<n>` — preflight, task baseline and brief; also supports a
  controller-owned task without launching a worker.
- `manifest <slug> T<n>` — JSON actual changed paths and suggested review bullets.
- `report <slug> T<n> --status … --summary … --red … --green …` — write the task
  report and its schema-valid result JSON from the actual delta.
- `accept <slug> T<n>` — scope check, report validation, exact Verification
  commands, then a second scope check.
  Commands must occupy the entire field, backticked and separated by semicolons.
  Run from the repository root; accept executes shell commands with the
  caller's permissions. Inspect them first and follow host approval rules.
- `external-result <slug> T<n> --outcome PASS|FAIL --evidence '<run>'` — record
  the result of a task's `External verification:`. Its `accept` ends in
  EXTERNAL-PENDING: review may open, `--phase final` requires a PASS.
  `--supersede '<why>'` corrects a recorded result for the same content.
- `refresh <slug> [--controller-path <p> --reason '<finding>']` — re-accept every
  settled task whose evidence went stale, in dependency order, with the same
  report and frozen Verification; controller edits after review are recorded for
  every task first, and all failing tasks are listed at once.
- `design-brief <slug>` / `design-review <slug> --from-agent <id>|--result-file
  <reply>` — the design gate: a fresh independent reviewer checks `## Class
  inventory` before apply; dispatch needs a PASS bound to the current inventory.
- `review-result <slug> --from-agent <id>|--result-file <reply>` — settle the
  pending round; a native reviewer's reply is saved verbatim under `runs/`, and
  a stale snapshot is reported with its cause.
- `status <slug>` — compact task states, latest review and the next allowed step;
  read it instead of plan.md when resuming.
- `handoff <slug> --file <path|->` — overwrite `runs/handoff.md` (at most 4 KiB);
  session notes never accumulate in plan.md.
- `wait <slug> T<n> [--timeout s]` — wait for a new task report of any status
  (a resumed worker answers asynchronously); prints the next step.
- `tidy <slug> [--record --summary '<...>' | --skip '<reason>']` — one worker
  pass of the tidy companion over Review scope before the first initial review;
  required by pre-review when `.specadoc.json` sets `review.tidy: required`.
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

from specadoc_root import ensure_runs, resolve_root  # noqa: E402
from specadoc_config import normalize_runtime  # noqa: E402
from validate_change import SETTLED_STATES, TASK_CHECKBOX, Document, external_verification, task_fields, review_policy_hash, latest_review_round, round_is_stale  # noqa: E402
from review_snapshot import CONTRACT_KEY, diff, tree_manifest  # noqa: E402
from task_state import approval_error, digest, readiness, safe_path, save, task_block, timestamp, update_task  # noqa: E402

COMMAND = re.compile(r"`([^`]+)`")
AUTO_EVIDENCE = re.compile(r"`[^`]+` — PASS")
# A placeholder instead of a decision. Words such as "pending" inside a real
# reason ("integration pending user authorization") are allowed.
PLACEHOLDER = re.compile(r"\s*(?:pending|tbd|n/?a|none|todo|-|\?+)?\s*[.!]?\s*", re.I)


def placeholder(text: str | None) -> bool:
    return text is None or bool(PLACEHOLDER.fullmatch(text))
TAIL_LINES = 30
# Characters of a worker summary copied into plan.md's Accepted result.
ACCEPTED_SUMMARY_LIMIT = 400
# Controller context at which dispatch stops for a session boundary.
CONTEXT_GUARD = 200_000
# Context at a phase boundary from which a fresh session pays back before the next
# phase that dispatches workers (model-routing.md -> Session boundaries).
PHASE_BOUNDARY_CONTEXT = 120_000
# A review round plus MINOR fixes took about 40k in 4.1; above this, hand off before the review.
REVIEW_HANDOFF_CONTEXT = 160_000


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
    return {"PASS": 0, "CHECKED": 0, "ACCEPTED": 0, "EXTERNAL-PENDING": 0, "FAIL": 1}.get(result, 2)


def root_args(root: str | None) -> list[str]:
    return ["--root", root] if root else []


DEFAULTED_CONTROLLER: list[str] = []


def default_controller(controller: str | None) -> str | None:
    """`--controller-runtime`, else the project's `roles.controller.runtime`; never a guess."""
    if controller:
        return controller
    from specadoc_config import load_config
    configured = ((load_config(Path.cwd()).get("roles") or {}).get("controller") or {}).get("runtime")
    if configured:
        DEFAULTED_CONTROLLER.append(f"controller runtime {configured} from .specadoc.json "
                                    "(pass --controller-runtime when this session runs elsewhere)")
    return configured


def binding_check(role: str, controller: str | None) -> list[str]:
    from specadoc_config import load_config
    if not (controller or "roles" in load_config(Path.cwd())):
        return []  # Legacy host/plugin registry fallback, unchanged.
    if not controller:
        raise ValueError("routed dispatch requires --controller-runtime or roles.controller.runtime")
    from role_routing import resolve_role
    route = resolve_role(Path.cwd(), role, controller)
    return [*DEFAULTED_CONTROLLER, f"resolved {role} {route['runtime']}/{route['model']}/{route['effort']}"]


def reopen_attempt(change: Path, task: str, reason: str) -> list[dict]:
    """Archive the current attempt so a later fix starts from today's tree.

    Retries keep the original baseline; a reopen is the explicit exception for
    corrective work after later tasks have changed the tree.
    """
    if placeholder(reason):
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


def preflight_checks(slug: str, task: str, root: str | None, controller: str | None) -> tuple[list[str], list[str]]:
    """Read-only validation. Collect errors before freezing any task state."""
    plan_path = Path(resolve_root(root).path) / slug / "plan.md"
    plan = Document(plan_path, str(plan_path))
    checked = ["apply readiness", "Files/Derived files", "Verification inputs", "Verification", "validate plan"]
    errors = readiness(plan, task)
    _, _, fields = task_block(plan, task)
    from verification_inputs import patterns
    for name in ("Files", "Derived files", "Verification inputs"):
        try:
            resolved = patterns(fields.get(name, ""))
            if name == "Files" and not resolved:
                errors.append("Files: at least one valid path is required")
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
    try:
        verification_commands(slug, task, root)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        if fields.get("Owner", "").lower() == "controller":
            from specadoc_config import load_config
            config = load_config(Path.cwd())
            if "roles" in config and not controller:
                raise ValueError("routed controller execution requires --controller-runtime or roles.controller.runtime")
            expected = config.get("roles", {}).get("controller", {}).get("runtime")
            if expected and expected != controller:
                raise ValueError(f"controller runtime is {controller}, binding expects {expected}")
            checked.append("controller execution; no worker dispatch")
        else:
            checked += binding_check("worker", controller)
    except ValueError as exc:
        errors.append(str(exc))
    gate = run_script("validate_change.py", slug, "--phase", "plan", *root_args(root))
    if gate.returncode:
        # Size warnings do not block; listing them first hid the real violation (4.4).
        output = tail(gate.stderr + gate.stdout)
        errors.append("\n".join(line for line in output.splitlines()
                                 if not line.strip().startswith("warning:")) or output)
    # Build in memory as well, so a missing requirement cannot leave a baseline.
    from task_brief import build_brief
    try:
        build_brief(plan_path.parent, task)
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append(str(exc))
    return checked, list(dict.fromkeys(errors))


def preflight(slug: str, task: str, root: str | None, controller: str | None) -> int:
    checked, errors = preflight_checks(slug, task, root, controller)
    return emit(checked, "FAIL" if errors else "PASS", [], "; ".join(errors),
                "fix all reported task inputs before dispatch" if errors else
                "inputs valid; no commands executed and no state written")


def observed_context(controller: str | None, context_tokens: int | None) -> tuple[int | None, str]:
    """The controller's current context: the reported count, else its own Claude transcript."""
    # A Codex/OpenCode controller started from a Claude shell inherits its session
    # id; that transcript measures the launcher, not this controller.
    if context_tokens is None and controller in (None, "claude"):
        from collect_tokens import claude_context_tokens, current_claude_transcript
        if (transcript := current_claude_transcript()) is not None:
            return claude_context_tokens(transcript), f"read from {transcript.name}"
    return context_tokens, "reported"


def dispatch(slug: str, task: str, root: str | None, controller: str | None = None,
             context_tokens: int | None = None, reopen: str | None = None) -> int:
    context_tokens, context_source = observed_context(controller, context_tokens)
    if context_tokens is not None and context_tokens >= CONTEXT_GUARD:
        return emit([f"context budget ({context_source})"], "BLOCKED", [],
                    f"controller context is {context_tokens} tokens, at least {CONTEXT_GUARD // 1000}k",
                    f"save the current handoff (specadoc_step.py handoff {slug} --file -) and resume apply in a "
                    f"fresh session from specadoc_step.py status {slug}")
    plan_path = Path(resolve_root(root).path) / slug / "plan.md"
    plan = Document(plan_path, str(plan_path))
    checked, errors = preflight_checks(slug, task, root, controller)
    if errors and reopen is not None and all("accepted evidence is stale" in error for error in errors):
        # 4.11: a reopen after a failed task found its dependencies stale (shared files); refresh is what
        # the message asked for, so run it here instead of a second controller turn.
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as output:
            refreshed = refresh(slug, root)
        checked, errors = preflight_checks(slug, task, root, controller)
        checked.append("stale dependency evidence refreshed" if refreshed == 0 and not errors
                       else "refresh before reopen: " + tail(output.getvalue()).replace("\n", " | "))
    if errors:
        return emit(checked, "FAIL" if any("paths" in error for error in errors) else "BLOCKED", [],
                    "; ".join(errors), "resolve all preflight errors before dispatch; no baseline written")
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
    checked += [line.strip() for line in brief.stderr.splitlines() if line.startswith("warning: brief")]
    if uncheckable:
        reason = f"Files items that are not paths: {', '.join(uncheckable)}"
        return emit(checked, "FAIL", [], reason, "make every Files item a path, then rerun dispatch")
    report = brief_path.with_name(f"{task}-report.md")
    _, failure = check_scope(slug, task, root, checked)
    if failure is not None:
        return failure
    owner = task_block(plan, task)[2].get("Owner", "worker").lower()
    finish = f"finish with specadoc_step.py report {slug} {task}, then accept"
    if owner == "controller":
        next_step = f"implement the controller task (brief {brief_path} is optional); {finish}"
    else:
        next_step = f"dispatch the worker with brief {brief_path}; it writes {report} with specadoc_step.py report; then accept"
        route = role_route("worker", controller)
        if route and route["dispatch"] == "external":
            next_step = (f"start the worker: python3 {SCRIPTS / 'run_role.py'} start --role worker --controller-runtime "
                         f"{controller} --prompt-file {brief_path} --name {task}; wait on its run file, then accept")
    return emit(checked, "PASS", [], "", next_step)


def role_route(role: str, controller: str | None) -> dict | None:
    from specadoc_config import load_config
    if not controller or "roles" not in load_config(Path.cwd()):
        return None
    from role_routing import resolve_role
    return resolve_role(Path.cwd(), role, controller)


def write_report(slug: str, task: str, root: str | None, status: str, summary: str, red: str, green: str,
                 concerns: list[str], body_file: str | None = None) -> int:
    """Write the task report and its schema-valid result JSON; never hand-written JSON."""
    from run_role import schema_errors, schema_path
    from review_snapshot import _under
    checked = ["task delta"]
    changed, violations, _, failure = scope_state(slug, task, root, checked)
    if failure is not None:
        return failure
    artifact_root = resolve_root(root).path
    report = Path(artifact_root) / slug / "runs" / f"{task}-report.md"
    concerns = [" ".join(item.split()) for item in concerns if item.strip()]
    payload = {"status": status, "summary": " ".join(summary.split()),
               "files_changed": [path for path in changed if not _under(path, artifact_root)],
               "tests": {"red": " ".join(red.split()), "green": " ".join(green.split())},
               "concerns": concerns, "report": report.as_posix()}
    if placeholder(payload["summary"]):
        raise ValueError("--summary must describe the delivered result")
    if errors := schema_errors(payload, json.loads(schema_path("worker").read_text())):
        raise ValueError("invalid worker result: " + "; ".join(errors))
    body = safe_path(body_file, allow_missing=False, allow_absolute=True).read_text(encoding="utf-8") if body_file else ""
    sections = [f"# {task} report", "", "## Summary", "", payload["summary"], "", "## RED", "", payload["tests"]["red"],
                "", "## GREEN", "", payload["tests"]["green"], "", "## Concerns", "",
                *([f"- {item}" for item in concerns] or ["None"]), ""]
    if body.strip():
        sections += ["## Notes", "", body.strip(), ""]
    text = "\n".join(sections) + "\n```json\n" + json.dumps(payload, indent=1, ensure_ascii=False) + "\n```\n"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text, encoding="utf-8")
    checked.append(f"wrote {report}")
    detail = json.dumps(payload, ensure_ascii=False)
    if violations:
        return emit(checked, "FAIL", violations, "changes outside the task scope",
                    "revert those paths, or rerun report with --status NEEDS_CONTEXT naming the required path", detail)
    return emit(checked, "CHECKED", payload["files_changed"], "",
                "report written; return the JSON below as the result; the controller runs accept", detail)


def verification_commands(slug: str, task: str, root: str | None) -> list[str]:
    plan_path = Path(resolve_root(root).path) / slug / "plan.md"
    plan = Document(plan_path, str(plan_path))
    blocks = {identifier: (start, end) for identifier, start, end in plan.blocks("Tasks", "T")}
    if task not in blocks:
        raise ValueError(f"plan.md has no task {task}")
    field = task_fields(plan, *blocks[task]).get("Verification", "")
    from validate_change import VERIFICATION_COMMANDS
    if not VERIFICATION_COMMANDS.fullmatch(field):
        raise ValueError("Verification must contain only exact backticked commands separated by semicolons; "
                         "move manual or reserved checks to External verification (amend the plan)")
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
    attributed = payload.get("attributed") or {}
    later = {path for paths in attributed.values() for path in paths}
    if attributed:
        note = "attributed to later tasks: " + "; ".join(f"{owner} {', '.join(paths)}"
                                                        for owner, paths in sorted(attributed.items()))
        if note not in checked:
            checked.append(note)
    changed = sorted(path for paths in delta.values() for path in paths if path not in later)
    from design_gate import outside
    from review_snapshot import _under
    plan_path = Path(artifact_root) / slug / "plan.md"
    added = [path for path in delta["added"] if path not in later and not _under(path, artifact_root)]
    violations += [f"{path} (new file outside Class inventory)"
                   for path in outside(Document(plan_path, str(plan_path)), added)]
    return changed, violations, payload.get("derived", []), None


def check_scope(slug: str, task: str, root: str | None, checked: list[str]) -> tuple[list[str], int | None]:
    changed, violations, _, failure = scope_state(slug, task, root, checked)
    if failure is not None:
        return [], failure
    if violations:
        return [], emit(checked, "FAIL", violations, "changes outside the task scope",
                        "revert each path, list it in Derived files via amend, or amend --allow it with a reason")
    return changed, None


def worker_result(change: Path, task: str, result_file: str | None, resolved: str | None = None) -> tuple[dict, Path]:
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
        hint = ""
        if isinstance(payload, dict) and ({"task", "review_scope"} & payload.keys()):
            hint = "; this is `manifest` output, not a worker result"
        raise ValueError("invalid worker result: " + "; ".join(errors) + hint
                         + f"; write it with specadoc_step.py report {change.name} {task}")
    if safe_path(payload["report"], allow_missing=False, allow_absolute=True).resolve() != report.resolve():
        raise ValueError("worker result points to a different report")
    unfinished = payload["status"] not in ("DONE", "DONE_WITH_CONCERNS")
    if resolved and not unfinished:
        raise ValueError(f"--resolved applies only to a BLOCKED or NEEDS_CONTEXT report, not {payload['status']}")
    if unfinished and not resolved:
        raise ValueError(f"worker status {payload['status']} is not completion; when the parent or controller "
                         "removed the blocker, rerun accept with --resolved '<who removed it and how>' "
                         "(never rewrite the worker report)")
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
           note: str | None = None, verification_timeout: float = 600, resolved: str | None = None) -> int:
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
    scope_next = ("revert each path, list it in Derived files via amend, or amend --allow it with a reason; "
                  "a new file outside Class inventory needs an inventory row and a new design review")
    if scope_only:
        if violations:
            return emit(checked, "FAIL", violations, "changes outside the task scope", scope_next)
        return emit(checked, "CHECKED", changed, "", "scope only; not accepted: run accept without --scope-only")
    if verification_timeout <= 0:
        raise ValueError("verification timeout must be positive")
    if note is not None and placeholder(note):
        raise ValueError("--note must name the actual decision or accepted result")
    if resolved is not None and placeholder(resolved):
        raise ValueError("--resolved must name who removed the blocker and how")

    change = Path(resolve_root(root).path) / slug
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if error := approval_error(plan):
        return emit(checked, "BLOCKED", violations or changed, error, "obtain plan approval before acceptance")
    try:
        payload, report = worker_result(change, task, result_file, resolved)
        commands = verification_commands(slug, task, root)
    except (OSError, ValueError) as exc:
        return emit(checked, "BLOCKED", violations or changed, str(exc),
                    "supply a schema-valid worker report/result and exact Verification commands")
    if not commands:
        return emit(checked, "BLOCKED", violations, "Verification has no backticked command", "run the Verification yourself")
    baseline_path = change / "runs" / f"{task}-baseline.json"
    record = json.loads(baseline_path.read_text())
    _, _, fields = task_block(plan, task)
    from verification_inputs import capture, content_hash
    inputs = capture(fields, resolve_root(root).path)
    prior = record.get("verification", {})
    # A legacy Files hash alone cannot establish verifier input equivalence.
    reuse = (prior.get("inputs") == inputs
              and prior.get("commands") == commands and prior.get("passed") is True)
    logs = []
    for command in ([] if reuse else commands):
        checked.append(command)
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=verification_timeout)
        except subprocess.TimeoutExpired:
            return emit(checked, "BLOCKED", violations, f"verification timed out after {verification_timeout:g}s",
                        "inspect the existing process/log before retrying; keep the same baseline")
        log = change / "runs" / f"{task}-verify.log"
        logs.append(f"$ {command}\n" + result.stdout + result.stderr)
        log.write_text("\n".join(logs), encoding="utf-8")
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
    after_inputs = capture(fields, resolve_root(root).path)
    if after_inputs != inputs:
        record.pop("verification", None)
        save(baseline_path, record)
        return emit(checked, "FAIL" if violations else "BLOCKED", violations or changed,
                    "verification inputs changed while commands ran" + ("; also changes outside scope" if violations else ""),
                    "inspect generated changes, then rerun verification on the stable inputs")
    record["verification"] = {"commands": commands, "files_hash": content_hash(inputs["owned"]),
                               "files": inputs["owned"], "inputs": inputs, "passed": True, "at": timestamp()}
    if violations:
        save(baseline_path, record)
        return emit(checked, "FAIL", violations, "verification passed, but changes are outside the task scope", scope_next)
    record["state"] = "verified"
    save(baseline_path, record)
    concerns = payload["concerns"]
    if (concerns or payload["status"] == "DONE_WITH_CONCERNS") and not (note or resolved):
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
    summary = " ".join(payload["summary"].split())
    if len(summary) > ACCEPTED_SUMMARY_LIMIT:
        # plan.md is re-read at every task; the full summary stays in the report.
        summary = summary[:ACCEPTED_SUMMARY_LIMIT].rsplit(" ", 1)[0] + f" … (full: runs/{task}-report.md)"
    accepted = summary + (f"; controller: {note}" if note else "")
    if resolved:
        accepted = f"worker {payload['status']} → resolved: {resolved}; worker: {accepted}"
        record["blocker_resolution"] = {"worker_status": payload["status"], "resolution": " ".join(resolved.split()),
                                        "at": timestamp()}
    values = {"Evidence": evidence, "Evidence hash": content_hash(inputs["owned"]), "Accepted result": accepted}
    external = external_verification(fields)
    prior = record.get("external") or {}
    # A recorded external PASS holds while the task's own content is unchanged.
    awaiting = bool(external) and not (prior.get("outcome") == "PASS"
                                       and prior.get("files_hash") == values["Evidence hash"])
    plan_path.write_text(update_task(plan, task, values, complete=not awaiting, reopen=awaiting), encoding="utf-8")
    record.update(state="external-pending" if awaiting else "accepted", accepted_at=timestamp(),
                  accepted_result=values["Accepted result"], report_hash=digest(report), concerns=concerns, note=note)
    save(baseline_path, record)
    if awaiting:
        return emit(checked, "EXTERNAL-PENDING", changed, "",
                    f"local evidence saved; review may open. After the external run ({external}), record it: "
                    f"specadoc_step.py external-result {slug} {task} --outcome PASS|FAIL --evidence '<run and result>'")
    return emit(checked, "ACCEPTED", changed, "", "task evidence and accepted result saved; continue with the next ready task")


def external_result(slug: str, task: str, root: str | None, outcome: str, evidence: str, log: str | None = None,
                    supersede: str | None = None) -> int:
    """Record the result of a task's External verification; final requires PASS.

    `supersede` corrects an already recorded result (a wrong log or a garbled
    hash) for the same content; the replaced result stays in `external_history`.
    """
    from validate_change import evidence_staleness
    checked = ["external verification state"]
    if placeholder(evidence):
        raise ValueError("--evidence must name the actual run and its result")
    if supersede is not None and placeholder(supersede):
        raise ValueError("--supersede must name why the recorded result is wrong")
    change = Path(resolve_root(root).path) / slug
    baseline_path = change / "runs" / f"{task}-baseline.json"
    if not baseline_path.is_file():
        raise ValueError(f"{task} has no task state; dispatch and accept it first")
    record = json.loads(baseline_path.read_text(encoding="utf-8"))
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    _, _, fields = task_block(plan, task)
    if not external_verification(fields):
        raise ValueError(f"{task} has no External verification field")
    if supersede is not None:
        if record.get("state") != "accepted" or not record.get("external"):
            return emit(checked, "BLOCKED", [], f"{task} has no recorded external result to supersede "
                        f"(state {record.get('state')})", "record it with external-result without --supersede")
        if record["external"].get("files_hash") != (record.get("verification") or {}).get("files_hash"):
            return emit(checked, "BLOCKED", [], f"{task} recorded external result covers different content",
                        "accept the current content and rerun the external verification")
        checked.append("superseding the recorded external result")
    elif record.get("state") != "external-pending":
        hint = (f"; to correct a recorded result use --supersede '<why it is wrong>'"
                if record.get("state") == "accepted" and record.get("external") else "")
        return emit(checked, "BLOCKED", [], f"{task} state is {record.get('state')}, not external-pending",
                    f"accept {task} first; its local Verification must pass before the external result{hint}")
    fresh, reason = evidence_staleness(change / "runs", task, fields.get("Files", ""))
    if fresh is False:
        return emit(checked, "BLOCKED", [], f"{task} local evidence is stale ({reason})",
                    "run specadoc_step.py refresh, then rerun the external verification on that content")
    if log:
        safe_path(log, allow_missing=False, allow_absolute=True)
    files_hash = (record.get("verification") or {}).get("files_hash")
    text = " ".join(evidence.split())
    if supersede is not None:
        record.setdefault("external_history", []).append(
            {**record["external"], "superseded_at": timestamp(), "reason": " ".join(supersede.split())})
    record["external"] = {"outcome": outcome, "evidence": text, "log": log, "at": timestamp(), "files_hash": files_hash}
    value = f"{outcome}: {text}" + (f" (log `{log}`)" if log else "")
    if outcome == "PASS":
        plan_path.write_text(update_task(plan, task, {"External evidence": value}, complete=True), encoding="utf-8")
        record["state"] = "accepted"
        save(baseline_path, record)
        return emit(checked + ["external PASS recorded"], "ACCEPTED", [], "",
                    "external evidence saved; continue with review or the final gate")
    plan_path.write_text(update_task(plan, task, {"External evidence": value}, reopen=True), encoding="utf-8")
    record["state"] = "dispatched"
    save(baseline_path, record)
    return emit(checked + ["external FAIL recorded"], "FAIL", [], f"external verification failed: {text}",
                f"fix it with dispatch {slug} {task} --reopen '<reason>', accept, then rerun the external verification")


def dependency_order(plan: Document) -> list[str]:
    """Task ids with every dependency before its dependents; plan order otherwise."""
    from validate_change import ids_in
    depends = {identifier: ids_in(task_fields(plan, start, end).get("Depends on", ""), "T")
               for identifier, start, end in plan.blocks("Tasks", "T")}
    order: list[str] = []

    def visit(task: str, trail: frozenset[str]) -> None:
        if task in order or task in trail or task not in depends:
            return
        for dependency in depends[task]:
            visit(dependency, trail | {task})
        order.append(task)

    for task in depends:
        visit(task, frozenset())
    return order


def record_controller_changes(change: Path, artifact_root: str, paths: list[str], reason: str | None) -> list[str]:
    """Record controller edits after review for every task's scope check (`runs/controller-changes.json`)."""
    from review_snapshot import CONTROLLER_CHANGES, _under
    if not reason or placeholder(reason):
        raise ValueError("--controller-path needs --reason naming the review finding or decision")
    literal = [safe_path(path).as_posix() for path in paths]
    if inside := [path for path in literal if _under(path, artifact_root)]:
        raise ValueError(f"controller paths must be outside the artifact root: {', '.join(inside)}; "
                         "files in the change folder are not task scope and need no --controller-path")
    target = change / "runs" / CONTROLLER_CHANGES
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    changes = payload.setdefault("changes", {})
    for path in literal:
        changes[path] = digest(Path(path))
    payload.setdefault("history", []).append({"at": timestamp(), "paths": literal, "reason": " ".join(reason.split())})
    save(target, payload)
    return literal


def refresh(slug: str, root: str | None, verification_timeout: float = 600,
            controller_paths: list[str] | None = None, reason: str | None = None) -> int:
    """Re-verify every settled task whose evidence went stale, in dependency order.

    Stale evidence after later tasks is not corrective work: the same report and
    frozen Verification are re-accepted against today's tree, without --reopen.
    `controller_paths` first records controller edits made after review (MINOR
    fixes), so no task blames them as out of scope. Every stale task is tried;
    the result lists all that could not be re-accepted.
    """
    import contextlib
    import io
    from validate_change import evidence_staleness
    change = Path(resolve_root(root).path) / slug
    plan_path = change / "plan.md"
    checked: list[str] = []
    failures: list[tuple[str, int, str]] = []
    if controller_paths:
        recorded = record_controller_changes(change, resolve_root(root).path, controller_paths, reason)
        checked.append("controller changes recorded: " + ", ".join(recorded))
        from review_snapshot import NON_EXECUTABLE
        executable = [path for path in recorded if not NON_EXECUTABLE.search(path)]
        if executable and not (reason or "").lower().startswith("tidy"):
            # 4.6: a controller MINOR fix in production code introduced an IMPORTANT finding.
            checked.append("WARN executable controller edit: " + ", ".join(executable)
                           + "; prefer a worker (dispatch T<n> --reopen '<finding>') for production code")
    for task in dependency_order(Document(plan_path, str(plan_path))):
        state_path = change / "runs" / f"{task}-baseline.json"
        try:
            record = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("state") not in SETTLED_STATES:
            continue
        _, _, fields = task_block(Document(plan_path, str(plan_path)), task)
        fresh, reason = evidence_staleness(change / "runs", task, fields.get("Files", ""))
        if fresh is not False:
            continue
        if reason.startswith("Verification changed"):
            failures.append((task, 2, f"{reason}; settle it with amend {slug} {task} --reason '<decision>', "
                                      f"or dispatch {task} --reopen for corrective work"))
            continue
        output = io.StringIO()
        resolution = (record.get("blocker_resolution") or {}).get("resolution")
        with contextlib.redirect_stdout(output):
            code = accept(slug, task, root, note=record.get("note"), verification_timeout=verification_timeout,
                          resolved=resolution)
        if code != 0:
            lines = output.getvalue().splitlines()
            why = next((value for line in lines if line.startswith("blocking reason: ")
                        and (value := line.removeprefix("blocking reason: ").strip()) != "-"), "")
            files = next((value for line in lines if line.startswith("changed files: ")
                          and (value := line.removeprefix("changed files: ").strip()) != "-"), "")
            found = [files] if files else []
            hint = (f"edits outside {task}'s scope: rerun refresh --controller-path <path> --reason '<finding>' for "
                    "controller edits" if "outside the task scope" in why else
                    f"fix {task} (dispatch {task} --reopen for code changes)")
            failures.append((task, code, f"{why or 'not re-accepted'} ({reason})"
                             + (f": {found[0]}" if found else "") + f"; {hint}"))
            continue
        result = next((line.removeprefix("result: ") for line in output.getvalue().splitlines()
                       if line.startswith("result: ")), "ACCEPTED")
        checked.append(f"{task} {result.lower()} ({reason})")
    if failures:
        status = "FAIL" if any(code == 1 for _, code, _ in failures) else "BLOCKED"
        return emit(checked + [f"{task}: {detail}" for task, _, detail in failures], status, [],
                    f"{len(failures)} task(s) not re-accepted: {', '.join(task for task, _, _ in failures)}",
                    "resolve each listed task as its line says, then rerun refresh")
    if not checked:
        return emit(["evidence staleness"], "PASS", [], "", "no stale task evidence; continue")
    return emit(checked, "PASS", [], "", "stale evidence re-verified; continue with pre-review or the next task")


def design_brief(slug: str, root: str | None, controller: str | None) -> int:
    import design_gate
    change = Path(resolve_root(root).path) / slug
    plan = Document(change / "plan.md", "plan.md")
    if not design_gate.rows(plan):
        return emit(["Class inventory"], "BLOCKED", [], "plan.md has no Class inventory rows",
                    "list every new non-test file (File | Layer | Why it exists | Kind) first")
    if violations := design_gate.check_inventory(plan):
        return emit(["Class inventory"], "FAIL", [], "; ".join(v.message for v in violations), "fix the inventory rows")
    checked = ["Class inventory", *binding_check("reviewer", controller)]
    path = design_gate.write_brief(change)
    route = role_route("reviewer", controller)
    start = (f"python3 {SCRIPTS / 'run_role.py'} start --role reviewer --controller-runtime {controller} "
             f"--prompt-file {path} --name design" if route and route["dispatch"] == "external"
             else f"the native reviewer with {path}")
    return emit(checked + [f"wrote {path}"], "PASS", [], "",
                f"run {start} (strongest reviewer binding, a fresh agent each round); then design-review {slug} "
                "--from-agent <id> (native) or --result-file <reply> (external)")


def reviewer_source(change: Path, source: str | None, agent: str | None, name: str) -> str:
    """The result file to parse: --result-file as given, or the agent's own reply saved to runs/<name>."""
    if source:
        return source
    from reviewer_reply import save_reply
    return str(save_reply(agent, change / "runs" / name))


def design_review(slug: str, root: str | None, source: str | None, controller: str | None,
                  agent: str | None = None, same_reviewer_reason: str | None = None) -> int:
    import design_gate
    change = Path(resolve_root(root).path) / slug
    checked = binding_check("reviewer", controller)
    reviewer = next((item.removeprefix("resolved reviewer ") for item in checked if item.startswith("resolved ")),
                    "host reviewer")
    number = len(list((change / "runs").glob("design-review-*-reply.md"))) + 1
    source = reviewer_source(change, source, agent, f"design-review-{number}-reply.md")
    verdict = design_gate.record(change, source, reviewer, agent, same_reviewer_reason)
    checked += ["reviewer schema", "inventory hash", "recorded Design review"] + ([f"reply saved to {source}"] if agent else [])
    if verdict == "PASS":
        return emit(checked, "PASS", [], "", "design gate passed; present the plan for approval (or apply the "
                    "orchestrator mandate), then dispatch")
    return emit(checked, "FAIL", [], "design review FAIL; read its findings in plan.md",
                "revise the approach or Class inventory, then design-brief and review again")


HANDOFF_LIMIT = 4096


def write_handoff(slug: str, root: str | None, source: str) -> int:
    """Overwrite the change's session handoff; plan.md keeps only its pointer."""
    if source != "-" and not Path(source).is_file():
        raise ValueError(f"file does not exist: {source}")
    # Input only: a draft in the session temp directory is fine (4.5 was refused for $TMPDIR).
    text = (sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")).strip()
    if not text:
        raise ValueError("handoff is empty")
    size = len((text + "\n").encode("utf-8"))
    if size > HANDOFF_LIMIT:
        return emit(["handoff size"], "FAIL", [], f"handoff is {size} bytes (> {HANDOFF_LIMIT})",
                    "keep current state, next step and open risks; move settled decisions to plan.md "
                    "Confirmed decisions and task results to Accepted result")
    path = Path(resolve_root(root).path) / slug / "runs" / "handoff.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return emit(["handoff size", f"wrote {path} ({size} bytes)"], "CHECKED", [], "",
                "a new session runs status, then reads this file instead of re-reading plan.md")


def status(slug: str, root: str | None, controller: str | None = None,
           context_tokens: int | None = None) -> int:
    """Compact read-only state for a controller or orchestrator; replaces re-reading plan.md."""
    from validate_change import TASK_CHECKBOX, evidence_staleness, latest_review_round
    change = Path(resolve_root(root).path) / slug
    plan_path = change / "plan.md"
    record = Path(resolve_root(root).path) / "archive" / slug / "record.md"
    if not plan_path.is_file() and record.is_file():
        print(f"change: {slug}; result: ARCHIVED ({record})\nnext: none for this change")
        return 0
    if not plan_path.is_file():
        print(f"change: {slug}; result: NOT STARTED ({plan_path} does not exist)\n"
              f"next: explore, then init_change.py {slug} --risk <low|medium|high> and write spec.md and plan.md")
        return 0
    plan = Document(plan_path, str(plan_path))
    approval = approval_error(plan)
    import design_gate
    design = ("n/a (no Class inventory)" if not design_gate.rows(plan)
              else design_gate.review_error(plan) or "PASS (current inventory)")
    handoff = change / "runs" / "handoff.md"
    drift = approval_drift(change) if not approval else []
    approved = "approved" + (f"; changed since approval: {', '.join(drift)} (re-approve)" if drift else "")
    lines = [f"change: {slug}; plan.md {plan_path.stat().st_size} bytes; approval: {approval or approved}",
             f"design: {design}",
             f"handoff: {handoff} ({handoff.stat().st_size} bytes)" if handoff.is_file() else "handoff: none"]
    from validate_change import plan_size_warnings
    lines += [f"size: {warning}" for warning in plan_size_warnings(plan)]
    working, stale, waiting, unstarted = [], [], [], []
    for task, start, end in plan.blocks("Tasks", "T"):
        fields = task_fields(plan, start, end)
        owner = fields.get("Owner", "-").strip().lower() or "-"
        state_path = change / "runs" / f"{task}-baseline.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")).get("state", "unknown")
        except (OSError, ValueError, AttributeError):
            state = None
        if state is None:
            marks = [m["mark"] for line in plan.lines[start:end] if (m := TASK_CHECKBOX.match(line))]
            state = "complete (no task state)" if marks and " " not in marks else "not started"
            if state == "not started":
                unstarted.append(task)
        elif state in SETTLED_STATES:
            fresh, reason = evidence_staleness(change / "runs", task, fields.get("Files", ""))
            if fresh is False:
                stale.append(task)
                state += f", stale: {reason}"
            if state.startswith("external-pending"):
                waiting.append(task)
        else:
            working.append(task)
        lines.append(f"  {task} {owner} {state}")
    if tidy_state := tidy_status(change):
        lines.append(f"tidy: {tidy_state}")
    latest = latest_review_round(plan)
    outcome = latest[1].get("Outcome", "").strip() if latest else ""
    lines.append(f"review: {latest[0]} {outcome or 'missing'} ({latest[1].get('Type', '-').strip()}"
                 f"{', stale' if round_is_stale(latest[1]) else ''})" if latest else "review: none")
    pending = bool(latest) and outcome.upper() not in ("PASS", "FAIL")
    stale_round = bool(latest) and round_is_stale(latest[1])
    if design_gate.rows(plan) and design_gate.review_error(plan):
        next_step = f"design review: specadoc_step.py design-brief {slug}, reviewer, design-review"
    elif approval:
        next_step = "obtain plan approval"
    elif drift and pending:
        next_step = (f"{', '.join(drift)} changed while {latest[0]} is pending: pre-review {slug} --withdraw, "
                     "then approve, then pre-review again")
    elif drift:
        next_step = f"re-approve ({', '.join(drift)} changed): approve {slug} --by <user|orchestrator> --source '<decision>'"
    elif working:
        next_step = f"finish {working[0]}: report, then accept"
    elif stale:
        next_step = f"specadoc_step.py refresh {slug} ({', '.join(stale)})"
    elif unstarted:
        errors = readiness(plan, unstarted[0])
        next_step = (f"dispatch {unstarted[0]}" if not errors
                     else f"{unstarted[0]} not ready: {'; '.join(errors)}")
    elif stale_round:
        cause = latest[1].get("Stale reason", "").split(";")[0].strip()
        kind = ("re-review" if "content changed" in cause
                else latest[1].get("Type", "re-review").strip() or "re-review")
        next_step = f"pre-review --review-type {kind} ({latest[0]} stale: {cause}; it uses no review allowance)"
    elif not latest and tidy_missing(change):
        next_step = (f"scope {slug} (Review scope from the diff), then tidy {slug}: one worker pass over it "
                     f"(runs/{TIDY_BRIEF}), then refresh {slug}, then pre-review")
    elif not latest or outcome.upper() == "FAIL":
        next_step = "pre-review" + (" --review-type re-review after fixing the findings" if latest else "")
    elif outcome.upper() not in ("PASS", "FAIL"):
        next_step = f"run the reviewer for {latest[0]}, then review-result"
    elif drift := review_drift(plan, change, latest):
        next_step = f"pre-review --review-type re-review ({drift})"
    elif capability := capability_gap(change, resolve_root(root).path, slug):
        next_step = f"apply step 9: update capability specs before the final gate ({capability})"
    elif waiting:
        next_step = f"external-result {waiting[0]} after its external run"
    else:
        next_step = f"validate_change.py {slug} --phase final"
    lines.append(f"next: {next_step}")
    context_tokens, context_source = observed_context(controller, context_tokens)
    if context_tokens is None:
        lines.append("context: not reported (pass --context-tokens from the host's observed count)")
    else:
        # Apply has not started yet: the plan-approval phase boundary.
        apply_start = next_step.startswith("dispatch ") and len(unstarted) == len(plan.blocks("Tasks", "T"))
        # Locally ready: review passed and only the final gate or an external run remains.
        locally_ready = bool(latest) and outcome.upper() == "PASS" and not (working or stale or unstarted)
        advice = ""
        # A stale round re-run on an unchanged diff needs no fixes (~5–6k), not a fresh session.
        rerun = stale_round and "content changed" not in latest[1].get("Stale reason", "")
        if context_tokens >= PHASE_BOUNDARY_CONTEXT and apply_start:
            advice = ("; phase boundary: fresh session recommended before worker dispatch "
                      f"(at least {PHASE_BOUNDARY_CONTEXT // 1000}k)")
        elif context_tokens >= REVIEW_HANDOFF_CONTEXT and next_step.startswith("pre-review") and not rerun:
            advice = ("; review boundary: write the handoff and review in a fresh session; a round and its "
                      f"fixes need about 40k (at least {REVIEW_HANDOFF_CONTEXT // 1000}k)")
        elif context_tokens >= PHASE_BOUNDARY_CONTEXT and locally_ready:
            advice = ("; phase boundary: locally ready; continue for the final gate, but start a later fix "
                      f"in a fresh session (at least {PHASE_BOUNDARY_CONTEXT // 1000}k)")
        lines.append(f"context: {context_tokens} tokens ({context_source}){advice}")
    print("\n".join(lines))
    return 0


APPROVAL_ARTIFACTS = ("spec.md", "design.md")


def plan_bindings(plan_path: Path, controller: str | None) -> str:
    """`role runtime/model/effort` for the roles this plan dispatches, or "" when unresolvable."""
    try:
        from role_routing import plan_roles, resolve_role
        runtime = default_controller(controller)
        if not runtime:
            return ""
        routes = [resolve_role(Path.cwd(), role, runtime) for role in sorted(plan_roles(plan_path))]
    except (OSError, ValueError):
        return ""
    return ", ".join(f"{r['role']} {r['runtime']}/{r['model']}/{r['effort']}" for r in routes)


def approve(slug: str, root: str | None, by: str, source: str, bindings: str | None = None,
            controller: str | None = None) -> int:
    """Record plan approval and its provenance; hash the approved spec and design.

    Replaces hand-written Status/Approved at lines and hand-computed sha256 sums
    (3.7, 3.8). `by` is `user` for a direct decision, `orchestrator` for a
    decision under a recorded user mandate, which `source` must name.
    """
    checked = ["approval source", "validate plan"]
    if placeholder(source):
        raise ValueError("--source must quote the user's decision or name the mandate and decision")
    change = Path(resolve_root(root).path) / slug
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if "Plan approval" not in plan.sections:
        raise ValueError("plan.md has no Plan approval section")
    import design_gate
    if design_gate.rows(plan) and (error := design_gate.review_error(plan)):
        return emit(checked + ["design review"], "BLOCKED", [], error, "finish the design review before approval")
    latest = latest_review_round(plan)
    if latest and latest[1].get("Outcome", "").strip().upper() not in ("PASS", "FAIL"):
        return emit(checked + ["review round"], "BLOCKED", [],
                    f"{latest[0]} is recorded but not reviewed; an approval change now would make it stale",
                    f"pre-review {slug} --withdraw, then approve, then pre-review again")
    gate = run_script("validate_change.py", slug, "--phase", "plan", *root_args(root))
    if gate.returncode:
        return emit(checked, "BLOCKED", [], tail(gate.stderr + gate.stdout), "fix the plan, then approve")
    start, end = plan.sections["Plan approval"]
    body = plan.lines[start:end]
    current = next((m[1].strip() for line in body if (m := re.match(r"\*\*Bindings shown:\*\*\s*(.*)", line))), "")
    shown = " ".join((bindings or current).split())
    from validate_change import PENDING
    if placeholder(shown) or PENDING.search(shown):
        suggested = plan_bindings(plan_path, controller)
        command = (f"approve {slug} --by {by} --source '<as before>' --bindings '{suggested}' (show these to the "
                   "approver)" if suggested else "role_routing.py --controller-runtime <rt> --change "
                   f"{slug} --dry-run --compact, then approve with --bindings '<role runtime/model/effort, ...>'")
        return emit(checked, "BLOCKED", [], "plan.md has no Bindings shown; pass --bindings", command)
    at = timestamp()
    provenance = (f"user decision: {' '.join(source.split())}" if by == "user"
                  else f"orchestrator decision under user mandate: {' '.join(source.split())}")
    values = {"Status": "Approved", "Bindings shown": shown, "Approved at": at, "Approval provenance": provenance}
    for key, value in values.items():
        pattern = re.compile(rf"\*\*{re.escape(key)}:\*\*")
        index = next((i for i, line in enumerate(body) if pattern.match(line)), None)
        line = f"**{key}:** {value}" + ("  " if key != "Approval provenance" else "")
        if index is None:
            last = max((i for i, text in enumerate(body) if text.startswith("**")), default=0)
            body.insert(last + 1, line)
        else:
            body[index] = line
    text = "\n".join(plan.lines[:start] + body + plan.lines[end:]).rstrip("\n") + "\n"
    plan_path.write_text(text, encoding="utf-8")
    record = {"by": by, "source": " ".join(source.split()), "at": at,
              "artifacts": {name: digest(change / name) for name in APPROVAL_ARTIFACTS if (change / name).is_file()}}
    (change / "runs").mkdir(exist_ok=True)
    save(change / "runs" / "approval.json", record)
    return emit(checked + ["recorded approval"], "PASS", ["plan.md", "runs/approval.json"], "",
                "approval recorded; start apply (status, then dispatch)")


def review_type_of(change: Path, identifier: str) -> str:
    """The Type of a recorded round (initial or re-review)."""
    plan = Document(change / "plan.md", "plan.md")
    for found, start, end in plan.blocks("Review result", "G"):
        if found == identifier:
            return task_fields(plan, start, end).get("Type", "re-review").strip() or "re-review"
    return "re-review"


def approval_drift(change: Path) -> list[str]:
    """Approved artifacts that changed after `approve`."""
    try:
        record = json.loads((change / "runs" / "approval.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [name for name, value in (record.get("artifacts") or {}).items() if digest(change / name) != value]


def capability_gap(change: Path, artifact_root: str, slug: str) -> str:
    """First capability promotion still missing after review (apply step 9), or ''."""
    spec_path = change / "spec.md"
    if not spec_path.is_file():
        return ""
    from archive_change import capability_findings
    _, messages = capability_findings(Document(spec_path, str(spec_path)), artifact_root.rstrip("/"), slug)
    return messages[0] if messages else ""


def review_drift(plan: Document, change: Path, latest: tuple) -> str:
    """Why the latest PASS no longer covers the change: a changed diff or an unreviewed task.

    Test- or prose-only MINOR fixes after a MINOR-only PASS need no round (`tdd-and-review.md`),
    the same rule the final gate applies (`review_snapshot.verify_latest`).
    """
    from review_snapshot import NON_EXECUTABLE, SnapshotError, compute, manifest_hash
    from validate_change import expand_ids, minor_only_pass
    reasons = []
    try:
        current = compute(change, Path.cwd())
        if manifest_hash(current) != latest[1].get("Snapshot", "").strip():
            paths = sorted({path for values in diff(latest[2] or {}, current).values() for path in values})
            exempt = (latest[2] is not None and minor_only_pass(plan, latest[0]) and CONTRACT_KEY not in paths
                      and paths and all(NON_EXECUTABLE.search(path) for path in paths))
            if not exempt:
                reasons.append(f"diff changed since {latest[0]}")
    except SnapshotError as exc:
        reasons.append(f"Review scope cannot be hashed: {exc}")
    header = "\n".join(line for _, line in plan.body("Review result"))
    if match := re.search(r"\*\*Reviewed tasks:\*\*\s*(.+)", header):
        unreviewed = [task for task, _, _ in plan.blocks("Tasks", "T") if task not in expand_ids(match[1], "T")]
        if unreviewed:
            reasons.append(f"{', '.join(unreviewed)} not reviewed")
    return "; ".join(reasons)


def amend(slug: str, task: str, root: str | None, allowed: list[str], controller_paths: list[str], reason: str,
          derived: list[str] | None = None) -> int:
    if placeholder(reason):
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
    if controller_paths and not paths and not derived_paths and record.get("state") in SETTLED_STATES:
        # A controller edit on accepted work changes no scope: keep the acceptance, let refresh re-verify.
        changes = record.setdefault("controller_changes", {})
        for path in controller_paths:
            changes[path] = digest(Path(path))
        record.setdefault("amendments", []).append({"at": timestamp(), "allow": [], "derived": [],
                                                    "controller_paths": controller_paths, "reason": reason})
        save(baseline_path, record)
        return emit(["explicit controller amendment", f"{task} stays {record['state']}"], "CHECKED",
                    controller_paths, "", f"run refresh {slug} to re-verify stale evidence "
                    "(refresh --controller-path records edits for all tasks at once)")
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


def task_manifest(slug: str, task: str, root: str | None) -> int:
    """Suggest literal deltas, never edit reports, scope or acceptance decisions."""
    changed, violations, _, failure = scope_state(slug, task, root, ["task manifest"])
    if failure is not None:
        return failure
    if violations:
        return emit(["task manifest"], "FAIL", violations, "changes outside the task scope",
                    "resolve the scope violation; no paths adopted automatically")
    artifact_root = resolve_root(root).path
    from review_snapshot import _under
    paths = [path for path in changed if not _under(path, artifact_root)]
    print(json.dumps({"task": task, "files_changed": paths,
                      "review_scope": [f"- `{path if Path(path).is_file() else '!' + path}`" for path in paths]}, indent=2))
    return 0


TIDY_FILE = "tidy.json"
TIDY_BRIEF = "tidy-brief.md"
TIDY_SKILL = Path(__file__).resolve().parents[2] / "tidy" / "SKILL.md"


def tidy_required() -> bool:
    from specadoc_config import load_config
    return ((load_config(Path.cwd()).get("review") or {}).get("tidy")) == "required"


def tidy_missing(change: Path) -> bool:
    """The project requires a tidy pass before the first initial review and none is recorded."""
    return tidy_required() and not (change / "runs" / TIDY_FILE).is_file()


def tidy_status(change: Path) -> str:
    try:
        record = json.loads((change / "runs" / TIDY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "required, not recorded" if tidy_required() else ""
    return f"{record.get('outcome', 'recorded')}: {record.get('summary', '-')}"


def tidy(slug: str, root: str | None, *, record: bool = False, summary: str | None = None,
         agent: str | None = None, skip: str | None = None) -> int:
    """One behavior-preserving pass over the whole Review scope before the first initial review.

    Without flags: write runs/tidy-brief.md for one worker. `--record` (the worker's last step)
    or `--skip '<reason>'` (a trivial diff) writes runs/tidy.json, which pre-review requires when
    `.specadoc.json` sets review.tidy: required. Re-reviews never need another pass.
    """
    from review_snapshot import SnapshotError, review_scope
    artifact_root = resolve_root(root).path
    change = Path(artifact_root) / slug
    plan = Document(change / "plan.md", "plan.md")
    try:
        scope = review_scope(plan, Path.cwd(), change)
    except SnapshotError as exc:
        return emit(["review scope"], "BLOCKED", [], str(exc),
                    "fill ## Review scope from the executable diff (apply step 6), then tidy again")
    present = sorted(path for path, state in scope.items() if state == "present")
    target = change / "runs" / TIDY_FILE
    if record or skip is not None:
        if record and skip is not None:
            raise ValueError("use --record or --skip, not both")
        text = " ".join((skip or summary or "").split())
        if placeholder(text):
            raise ValueError("--record needs --summary 'fixed N: ...; skipped M: ... and why'"
                             if record else "--skip needs the reason the diff needs no tidy pass")
        ensure_runs(target.parent)
        save(target, {"at": timestamp(), "outcome": "skipped" if skip is not None else "recorded", "summary": text,
                      "agent": agent, "scope": present})
        return emit(["tidy " + ("skip" if skip is not None else "record")], "PASS", [f"runs/{TIDY_FILE}"], "",
                    f"refresh {slug} (tidy edits make task evidence stale), then pre-review {slug}")
    if not TIDY_SKILL.is_file():
        return emit(["tidy skill"], "BLOCKED", [], f"tidy skill not installed at {TIDY_SKILL}",
                    f"install the Specadoc tidy companion, or tidy {slug} --skip '<reason>'")
    if not present:
        return emit(["review scope"], "BLOCKED", [], "Review scope lists no present file",
                    f"tidy {slug} --skip 'deletions only'")
    commands: list[str] = []
    for task, _, _ in plan.blocks("Tasks", "T"):
        for command in verification_commands(slug, task, root):
            if command not in commands:
                commands.append(command)
    step = Path(__file__).resolve()
    root_flag = f"--root {root} " if root else ""
    brief = "\n".join([
        f"# Tidy brief: `{slug}`",
        "",
        f"Read and follow `{TIDY_SKILL}` for exactly the files below: the change's executable diff",
        "(Review scope), after every task was accepted and before the independent review.",
        "",
        *[f"- `{path}`" for path in present],
        "",
        "## Rules",
        "",
        "- Behavior-preserving only. Edit only the files above; never edit spec.md, plan.md or anything under "
        f"`{artifact_root}`. Do not commit, stash, reset or start other agents.",
        "- Look across files too: duplicated helpers or test doubles between tasks are in scope.",
        "- Do not fix a correctness or security defect or make an architecture choice; list it in your summary "
        "for the controller.",
        "- After your edits run the formatter once over the files you changed, then these checks:",
        *[f"  - `{command}`" for command in commands],
        f"- Finish with `python3 {step} {root_flag}tidy {slug} --record --summary 'fixed N: <what>; skipped M: "
        "<what and why>; for the controller: <defects or none>'` and return its output. Finding nothing is a "
        "valid result: say so in the summary.",
        "",
    ])
    path = change / "runs" / TIDY_BRIEF
    ensure_runs(path.parent)
    path.write_text(brief, encoding="utf-8")
    return emit(["review scope", "tidy skill", "brief"], "PASS", [f"runs/{TIDY_BRIEF}"], "",
                f"dispatch one worker with {path}; it ends with tidy {slug} --record; then refresh {slug}")


def pre_review(slug: str, root: str | None, controller: str | None = None, *,
               review_type: str = "initial", reason: str | None = None,
               decision: str | None = None, record_round: bool = False, withdraw: bool = False) -> int:
    change = Path(resolve_root(root).path) / slug
    if withdraw:
        from review_state import withdraw_round
        identifier = withdraw_round(change)
        return emit(["withdraw pending round"], "PASS", ["plan.md"], "",
                    f"{identifier} withdrawn; settle the approval, then pre-review again")
    if drift := approval_drift(change):
        return emit(["approval current"], "BLOCKED", [],
                    f"{', '.join(drift)} changed since approval; a round recorded now would settle stale",
                    f"approve {slug} --by <user|orchestrator> --source '<decision that covers the change>', then pre-review")
    if record_round and review_type == "initial" and tidy_missing(change):
        return emit(["tidy pass"], "BLOCKED", [],
                    f"no tidy pass recorded (.specadoc.json review.tidy: required)",
                    f"tidy {slug}, dispatch one worker with runs/{TIDY_BRIEF}, refresh {slug}, then pre-review")
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


REPORT_STATUS = re.compile(r'"status":\s*"(?P<status>DONE_WITH_CONCERNS|DONE|NEEDS_CONTEXT|BLOCKED)"')
WAIT_NEXT = {"DONE": "accept {slug} {task}",
             "DONE_WITH_CONCERNS": "resolve or record each concern, then accept {slug} {task}",
             "NEEDS_CONTEXT": "add exactly the named context and dispatch again (foreground)",
             "BLOCKED": "make the missing decision (or ask), update the plan, then dispatch again"}


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=Path.cwd())
    if result.returncode != 0:
        raise ValueError(f"git {' '.join(args)}: {(result.stderr or result.stdout).strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def scope(slug: str, root: str | None, *, base: str = "HEAD", dry_run: bool = False) -> int:
    """Fill `## Review scope` from the executable diff: tracked changes since `base` plus untracked
    files, relative to the current directory, without Specadoc artifacts (4.9–4.11: every apply
    controller wrote the section by hand, and tidy refused the template paragraph left in it)."""
    artifact_root = Path(resolve_root(root).path).resolve()
    change = artifact_root / slug
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if "Review scope" not in plan.sections:
        return emit(["review scope"], "BLOCKED", [], "plan.md has no ## Review scope section",
                    "add the section from assets/plan-template.md, then rerun scope")
    try:
        changed = git_lines("diff", "--name-status", "--relative", "--no-renames", base)
        untracked = git_lines("ls-files", "--others", "--exclude-standard")
    except ValueError as exc:
        return emit(["git"], "BLOCKED", [], str(exc), "run scope from the repository the plan describes")
    present: set[str] = set()
    deleted: set[str] = set()
    for line in changed:
        status, _, path = line.partition("\t")
        (deleted if status.startswith("D") else present).add(path.strip())
    present.update(path.strip() for path in untracked)
    cwd = Path.cwd().resolve()

    def artifact(path: str) -> bool:
        return (cwd / path).resolve().is_relative_to(artifact_root)
    skipped = sorted(path for path in present | deleted if artifact(path))
    present = {path for path in present if not artifact(path) and (cwd / path).is_file()}
    deleted = {path for path in deleted if not artifact(path) and not (cwd / path).exists()}
    checked = [f"git diff vs {base} + untracked", f"{len(present)} present, {len(deleted)} deleted"]
    if skipped:
        checked.append(f"artifacts left out: {', '.join(skipped)}")
    if not present and not deleted:
        return emit(checked, "BLOCKED", [], f"no executable diff against {base}",
                    "pass --base <rev> when the step's changes are already committed")
    bullets = [f"- `{path}`" for path in sorted(present)] + [f"- `!{path}`" for path in sorted(deleted)]
    if dry_run:
        return emit(checked + ["dry run"], "CHECKED", [], "", "rerun without --dry-run to write plan.md",
                    "\n".join(bullets))
    start, end = plan.sections["Review scope"]
    text = "\n".join(plan.lines[:start + 1] + [""] + bullets + [""] + plan.lines[end:]).rstrip("\n") + "\n"
    plan_path.write_text(text, encoding="utf-8")
    return emit(checked, "PASS", ["plan.md"], "", f"tidy {slug} when it is not recorded yet, else pre-review {slug}",
                "\n".join(bullets))


FINAL_PROOFS = (
    ("requirement maps", "matrix"), ("acceptance scenario", "matrix"), ("focused", "tasks"),
    ("regression", "observed"), ("lint", "observed"), ("build", "observed"),
    ("independent", "review"), ("blocker", "blocker"), ("important", "important"),
)


def finalize(slug: str, root: str | None, *, observed: str | None = None, requirements: str | None = None) -> int:
    """Tick the `## Final verification` boxes the recorded state proves, drop the Round log template
    example, and name what the controller still owns (4.9–4.11: three apply controllers edited the
    checklist, the matrix and the template placeholders with python heredocs)."""
    from validate_change import CHECKBOX, RECORDED_FINDING, evidence_staleness
    change = Path(resolve_root(root).path) / slug
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    checked: list[str] = []
    lines = list(plan.lines)
    # 1. The Round log guidance and its indented example are template text once a real round exists.
    if "Review result" in plan.sections:
        start, end = plan.sections["Review result"]
        log = next((i for i in range(start, end) if lines[i].strip() == "### Round log"), None)
        if log is not None:
            first = next((i for i in range(log + 1, end) if re.match(r"^###\s+G\d+\b", lines[i])), end)
            keep, guidance, dropped = [], False, 0
            for line in lines[log + 1:first]:
                stripped = line.strip()
                if guidance or stripped.startswith("<") or line.startswith("    ") or stripped == ">":
                    guidance = (guidance or stripped.startswith("<")) and not stripped.endswith(">")
                    dropped += 1
                    continue
                keep.append(line)
            if dropped:
                lines[log + 1:first] = [""] + [line for line in keep if line.strip()] + [""]
                checked.append(f"round log template dropped ({dropped} lines)")
    plan = Document(plan_path, str(plan_path), text="\n".join(lines))
    # 2. Proofs from the recorded state.
    why: dict[str, str] = {}
    tasks = plan.blocks("Tasks", "T")
    unproven = []
    for task, t_start, t_end in tasks:
        fields = task_fields(plan, t_start, t_end)
        try:
            state = json.loads((change / "runs" / f"{task}-baseline.json").read_text(encoding="utf-8")).get("state")
        except (OSError, ValueError, AttributeError):
            state = None
        if state is None:
            marks = [m["mark"] for line in plan.lines[t_start:t_end] if (m := TASK_CHECKBOX.match(line))]
            if not marks or " " in marks:
                unproven.append(f"{task} not complete")
            continue
        if state != "accepted":
            unproven.append(f"{task} {state}")
            continue
        fresh, reason = evidence_staleness(change / "runs", task, fields.get("Files", ""))
        if fresh is False:
            unproven.append(f"{task} stale ({reason})")
    proofs = {"tasks": not unproven}
    if unproven:
        why["tasks"] = "; ".join(unproven)
    latest = latest_review_round(plan)
    outcome = latest[1].get("Outcome", "").strip().upper() if latest else ""
    proofs["review"] = bool(latest) and outcome == "PASS" and not round_is_stale(latest[1])
    if not proofs["review"]:
        why["review"] = (f"{latest[0]} {outcome or 'pending'}" + (", stale" if latest and round_is_stale(latest[1]) else "")
                         if latest else "no review round")
    remaining = {"BLOCKER": False, "IMPORTANT": False}
    if "Review result" in plan.sections:
        for _, line in plan.body("Review result"):
            if line.strip() == "### Round log":
                break
            match = re.match(r"^- (BLOCKER|IMPORTANT)\b(.*)$", line.strip())
            if match and "none recorded" not in match[2].lower():
                remaining[match[1]] = True
    if latest and outcome == "PASS":
        _, r_start, r_end = plan.blocks("Review result", "G")[-1]
        for line in plan.lines[r_start:r_end]:
            if (m := RECORDED_FINDING.match(line)) and m["severity"] in remaining:
                remaining[m["severity"]] = True
    for severity in ("BLOCKER", "IMPORTANT"):
        key = severity.lower()
        proofs[key] = proofs["review"] and not remaining[severity]
        if not proofs[key]:
            why[key] = f"{severity} findings recorded" if remaining[severity] else why.get("review", "")
    rows = plan.rows("Requirement-to-check matrix")
    if requirements:
        m_start, m_end = plan.sections["Requirement-to-check matrix"]
        filled = 0
        for i in range(m_start + 1, m_end):
            cells = [cell.strip() for cell in lines[i].strip().strip("|").split("|")] if lines[i].strip().startswith("|") else []
            if len(cells) >= 4 and cells[0] not in ("Requirement", "") and not cells[0].startswith("-") \
                    and PENDING_MATRIX.match(cells[-1]):
                cells[-1] = "PASS"
                lines[i] = "| " + " | ".join(cells) + " |"
                filled += 1
        checked.append(f"matrix: {filled} Pending status(es) set to PASS ({' '.join(requirements.split())})")
        plan = Document(plan_path, str(plan_path), text="\n".join(lines))
        rows = plan.rows("Requirement-to-check matrix")
    pending_rows = [cells[0] for _, cells in rows if cells and PENDING_MATRIX.match(cells[-1])]
    proofs["matrix"] = bool(rows) and not pending_rows
    if not proofs["matrix"]:
        why["matrix"] = ("rows still Pending: " + ", ".join(pending_rows)) if pending_rows else "no matrix rows"
    proofs["observed"] = bool(observed)
    if not observed:
        why["observed"] = "pass --observed '<full suite and gates: command, result>'"
    # 3. Tick what is proven; record the observed run.
    if "Final verification" not in plan.sections:
        return emit(checked + ["final verification"], "BLOCKED", [], "plan.md has no ## Final verification section",
                    "add the section from assets/plan-template.md")
    f_start, f_end = plan.sections["Final verification"]
    ticked, left = [], []
    for i in range(f_start + 1, f_end):
        match = CHECKBOX.match(lines[i].strip())
        if not match:
            continue
        label = match["label"].strip()
        if match["mark"] != " ":
            continue
        proof = next((key for needle, key in FINAL_PROOFS if needle in label.lower()), None)
        if proof and proofs.get(proof):
            lines[i] = lines[i].replace("[ ]", "[x]", 1)
            ticked.append(label.rstrip("."))
        else:
            left.append(f"{label.rstrip('.')} ({why.get(proof, 'no recorded proof; tick it by evidence')})")
    if observed:
        text = " ".join(observed.split())
        insert = f_end
        while insert > f_start + 1 and not lines[insert - 1].strip():
            insert -= 1
        lines[insert:insert] = ["", f"Observed ({timestamp()}): {text}"]
        checked.append("observed run recorded")
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    if ticked:
        checked.append("ticked: " + ", ".join(ticked))
    if left:
        checked.append("left to the controller: " + "; ".join(left))
    if left:
        return emit(checked, "CHECKED", ["plan.md"], "",
                    f"tick the remaining boxes by evidence (or rerun finalize with --observed/--requirements), "
                    f"then validate_change.py {slug} --phase final")
    return emit(checked, "PASS", ["plan.md"], "", f"validate_change.py {slug} --phase final")


PENDING_MATRIX = re.compile(r"^\s*(Pending|TBD)\b", re.I)


def wait_report(slug: str, task: str, root: str | None, timeout: float, interval: float = 5.0) -> int:
    """Wait until a worker writes a new task report, whatever its status.

    For a worker answering asynchronously (a resumed agent). A sub-agent's reply reaches the
    controller only after the running command returns, so a long blocking loop that waits for
    DONE alone hid a NEEDS_CONTEXT for ten minutes in 4.5.
    """
    import time
    report = Path(resolve_root(root).path) / slug / "runs" / f"{task}-report.md"

    def snapshot() -> tuple[float, str]:
        try:
            text = report.read_text(encoding="utf-8")
        except OSError:
            return 0.0, ""
        found = REPORT_STATUS.findall(text)
        return report.stat().st_mtime, (found[-1] if found else "")

    start_mtime, start_status = snapshot()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
        mtime, status = snapshot()
        if status and mtime != start_mtime:
            return emit(["task report"], "CHECKED", [], "", WAIT_NEXT[status].format(slug=slug, task=task),
                        f"report: {status} ({report})")
    before = f"still {start_status or 'no report'}"
    return emit(["task report"], "BLOCKED", [], f"no new {task} report within {int(timeout)}s ({before})",
                f"read any sub-agent reply that arrived, then wait again or inspect the worker")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Artifact root (default: resolved, see specadoc_root.py)")
    steps = parser.add_subparsers(dest="step", required=True)
    for name in ("preflight", "dispatch", "accept", "amend", "manifest"):
        step = steps.add_parser(name)
        step.add_argument("change_slug")
        step.add_argument("task", help="Task id such as T3")
        if name == "accept":
            step.add_argument("--scope-only", action="store_true", help="Check scope only; never accepts")
            step.add_argument("--verify", action="store_true", help=argparse.SUPPRESS)  # default since 2026-10
            step.add_argument("--result-file", help="Schema-valid worker JSON; default: fenced JSON in its report")
            step.add_argument("--note", help="Controller decision on concerns or corrections to the accepted result")
            step.add_argument("--resolved", metavar="HOW",
                              help="Accept a BLOCKED/NEEDS_CONTEXT report whose blocker the parent or controller "
                                   "removed: who did it and how; the worker report stays unchanged")
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
    scoped = steps.add_parser("scope", help="Fill ## Review scope from the executable diff (tracked changes "
                                            "since --base plus untracked files, Specadoc artifacts left out)")
    scoped.add_argument("change_slug")
    scoped.add_argument("--base", default="HEAD", help="Revision the step's diff is measured against (default HEAD)")
    scoped.add_argument("--dry-run", action="store_true", help="Print the bullets without writing plan.md")
    final = steps.add_parser("finalize", help="Tick the Final verification boxes the recorded state proves, drop the "
                                              "Round log template, and list what the controller still owns")
    final.add_argument("change_slug")
    final.add_argument("--observed", metavar="RUN",
                       help="The full suite and gates the controller ran once: command and result (ticks regression, "
                            "build/lint boxes)")
    final.add_argument("--requirements", metavar="WHY",
                       help="Set every Pending matrix Status to PASS, with the evidence in one line")
    waited = steps.add_parser("wait", help="Wait for a new task report of any status (a resumed worker)")
    waited.add_argument("change_slug")
    waited.add_argument("task")
    waited.add_argument("--timeout", type=float, default=300.0, help="Seconds (default 300)")
    waited.add_argument("--interval", type=float, default=5.0, help=argparse.SUPPRESS)
    waited.add_argument("--controller-runtime", choices=("codex", "claude", "opencode"), type=normalize_runtime)
    review = steps.add_parser("pre-review")
    review.add_argument("change_slug")
    review.add_argument("--review-type", choices=("initial", "re-review"), default="initial")
    review.add_argument("--reason", choices=("implementation", "corrections", "minor-fixes", "requirements", "polish"))
    review.add_argument("--review-decision", help="Decision authorizing a bounded extra round, with its author: the user's words, "
                             "or 'orchestrator D<n> under mandate D<m>: <scope>'")
    review.add_argument("--dry-run", action="store_true", help="Run the gate and print the snapshot without recording a round")
    review.add_argument("--withdraw", action="store_true",
                        help="Remove the latest round while it is Pending (before an approval change)")
    review.add_argument("--record-round", action="store_true", help=argparse.SUPPRESS)  # default since 2026-10
    tidied = steps.add_parser("tidy", help="Tidy pass over Review scope before the first initial review: "
                                           "write the worker brief, or record its result")
    tidied.add_argument("change_slug")
    tidied.add_argument("--record", action="store_true", help="Record the tidy worker's result (its last step)")
    tidied.add_argument("--summary", help="With --record: fixed N: ...; skipped M: ... and why")
    tidied.add_argument("--from-agent", help="With --record: the tidy worker's agent id, if known")
    tidied.add_argument("--skip", metavar="REASON", help="Record that this diff needs no tidy pass, and why")
    brief = steps.add_parser("design-brief", help="Write the design reviewer prompt from the Class inventory")
    brief.add_argument("change_slug")
    reviewed = steps.add_parser("design-review", help="Record the design reviewer's result against the inventory")
    reviewed.add_argument("change_slug")
    for step in (brief, reviewed):
        step.add_argument("--controller-runtime", choices=("codex", "claude", "opencode"), type=normalize_runtime)
    approved = steps.add_parser("approve", help="Record plan approval, its provenance and the approved spec/design hashes")
    approved.add_argument("change_slug")
    approved.add_argument("--by", choices=("user", "orchestrator"), required=True,
                          help="user: a direct decision; orchestrator: a decision under a recorded user mandate")
    approved.add_argument("--source", required=True, help="The user's words, or the mandate and decision id")
    approved.add_argument("--bindings", help="Role bindings shown at approval (default: keep the recorded line)")
    handoff = steps.add_parser("handoff", help="Overwrite runs/handoff.md (session notes) from a file or stdin")
    handoff.add_argument("change_slug")
    handoff.add_argument("--file", required=True, help="Notes file, or - for stdin")
    state = steps.add_parser("status", help="Compact read-only state and the next allowed step")
    state.add_argument("change_slug")
    state.add_argument("--context-tokens", type=int, help="Observed current controller input context")
    state.add_argument("--controller-runtime", choices=("codex", "claude", "opencode"), type=normalize_runtime)
    reported = steps.add_parser("report", help="Write the task report with its schema-valid result JSON")
    reported.add_argument("change_slug")
    reported.add_argument("task", help="Task id such as T3")
    reported.add_argument("--status", choices=("DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"), required=True)
    reported.add_argument("--summary", required=True, help="Delivered result: behavior and interfaces, one or two sentences")
    reported.add_argument("--red", required=True, help="Observed failing test, or the approved TDD exception")
    reported.add_argument("--green", required=True, help="Observed passing checks")
    reported.add_argument("--concern", action="append", default=[], help="One concern; repeat as needed")
    reported.add_argument("--body-file", help="Optional longer notes appended to the report")
    external = steps.add_parser("external-result", help="Record a task's External verification result")
    external.add_argument("change_slug")
    external.add_argument("task", help="Task id such as T6")
    external.add_argument("--outcome", choices=("PASS", "FAIL"), required=True)
    external.add_argument("--evidence", required=True, help="The actual run (command, run id) and its result")
    external.add_argument("--log", help="Repository path of the run log")
    external.add_argument("--supersede", metavar="REASON",
                          help="Replace the recorded result of an accepted task for the same content; "
                               "the old one is kept in external_history")
    refreshed = steps.add_parser("refresh", help="Re-verify stale accepted task evidence without --reopen")
    refreshed.add_argument("change_slug")
    refreshed.add_argument("--verification-timeout", type=float, default=600)
    refreshed.add_argument("--controller-path", action="append", default=[],
                           help="A file the controller changed after review (e.g. a MINOR fix); repeatable")
    refreshed.add_argument("--reason", help="The finding or decision behind --controller-path")
    settled = steps.add_parser("review-result")
    settled.add_argument("change_slug")
    for step in (reviewed, settled):
        source = step.add_mutually_exclusive_group(required=True)
        source.add_argument("--result-file", help="Reviewer reply file (external runs); it ends in the result JSON")
        source.add_argument("--from-agent", metavar="ID",
                            help="Native reviewer agent id: its final reply is saved verbatim under runs/")
        step.add_argument("--same-reviewer-reason",
                          help="Why the previous round's reviewer agent reviews again (default: refused)")
    for step in (steps.choices["preflight"], steps.choices["dispatch"], review):
        step.add_argument("--controller-runtime", choices=("codex", "claude", "opencode"), type=normalize_runtime)
    # Accept the flag on every step, so a controller can pass it uniformly (3.7: amend rejected it).
    for step in steps.choices.values():
        if "--controller-runtime" not in step._option_string_actions:
            step.add_argument("--controller-runtime", choices=("codex", "claude", "opencode"), type=normalize_runtime,
                              help="Not used by this step; accepted so every call can pass it")
    return parser


PROPOSE_STEPS = ("approve", "design-brief", "design-review")
# Read-only steps also run by an orchestrator; they must not record its session.
UNRECORDED_STEPS = ("status", "preflight", "manifest")


def record_session(args: argparse.Namespace) -> None:
    """Remember the controller's Claude transcript for token collection (`runs/sessions.json`)."""
    if args.step in UNRECORDED_STEPS:
        return
    runtime = args.controller_runtime
    if runtime is None:
        from specadoc_config import load_config
        try:
            runtime = ((load_config(Path.cwd()).get("roles") or {}).get("controller") or {}).get("runtime")
        except ValueError:
            return
    if runtime not in (None, "claude"):
        return  # a Codex/OpenCode controller started from a Claude shell inherits the launcher's id
    try:
        change = Path(resolve_root(args.root).path) / args.change_slug
        from collect_tokens import remember_session
        # A handoff before the first dispatch closes propose (4.2 counted it, and the
        # whole propose session, as apply).
        dispatched = any((change / "runs").glob("T*-baseline.json"))
        before_apply = args.step == "handoff" and not dispatched
        # A re-approval during apply (4.8: Decision risk changed after T1) stays apply; recording it
        # as propose ended the apply token window there and dropped every later worker and round.
        propose = args.step in PROPOSE_STEPS and not (args.step == "approve" and dispatched)
        remember_session(change, "propose" if propose or before_apply else "apply")
    except (OSError, ValueError):
        pass  # bookkeeping never blocks a step


def main() -> int:
    args = build_parser().parse_args()
    if args.step in ("preflight", "dispatch", "accept", "amend", "manifest", "external-result", "report") and not re.fullmatch(r"T\d+", args.task):
        print("error: task must look like T<n>", file=sys.stderr)
        return 2
    try:
        if args.step in ("preflight", "dispatch", "pre-review", "design-brief", "design-review", "status"):
            args.controller_runtime = default_controller(args.controller_runtime)
        record_session(args)
        if args.step == "preflight":
            return preflight(args.change_slug, args.task, args.root, args.controller_runtime)
        if args.step == "manifest":
            return task_manifest(args.change_slug, args.task, args.root)
        if args.step == "dispatch":
            return dispatch(args.change_slug, args.task, args.root, args.controller_runtime, args.context_tokens,
                            args.reopen)
        if args.step == "accept":
            return accept(args.change_slug, args.task, args.root, scope_only=args.scope_only,
                          result_file=args.result_file, note=args.note,
                          verification_timeout=args.verification_timeout, resolved=args.resolved)
        if args.step == "amend":
            return amend(args.change_slug, args.task, args.root, args.allow, args.controller_path, args.reason, args.derived)
        if args.step == "design-brief":
            return design_brief(args.change_slug, args.root, args.controller_runtime)
        if args.step == "design-review":
            return design_review(args.change_slug, args.root, args.result_file, args.controller_runtime,
                                 args.from_agent, args.same_reviewer_reason)
        if args.step == "approve":
            return approve(args.change_slug, args.root, args.by, args.source, args.bindings, args.controller_runtime)
        if args.step == "handoff":
            return write_handoff(args.change_slug, args.root, args.file)
        if args.step == "tidy":
            return tidy(args.change_slug, args.root, record=args.record, summary=args.summary,
                        agent=args.from_agent, skip=args.skip)
        if args.step == "wait":
            return wait_report(args.change_slug, args.task, args.root, args.timeout, args.interval)
        if args.step == "scope":
            return scope(args.change_slug, args.root, base=args.base, dry_run=args.dry_run)
        if args.step == "finalize":
            return finalize(args.change_slug, args.root, observed=args.observed, requirements=args.requirements)
        if args.step == "status":
            return status(args.change_slug, args.root, args.controller_runtime, args.context_tokens)
        if args.step == "report":
            return write_report(args.change_slug, args.task, args.root, args.status, args.summary, args.red,
                                args.green, args.concern, args.body_file)
        if args.step == "external-result":
            return external_result(args.change_slug, args.task, args.root, args.outcome, args.evidence, args.log,
                                   args.supersede)
        if args.step == "refresh":
            return refresh(args.change_slug, args.root, args.verification_timeout, args.controller_path, args.reason)
        if args.step == "review-result":
            from review_state import record_result
            change = Path(resolve_root(args.root).path) / args.change_slug
            pending = latest_review_round(Document(change / "plan.md", "plan.md"))
            source = reviewer_source(change, args.result_file, args.from_agent,
                                     f"{pending[0] if pending else 'G0'}-reply.md")
            identifier, stale = record_result(change, source, args.from_agent, args.same_reviewer_reason)
            checked = ["review schema", "snapshot", "persist result"] + ([f"reply saved to {source}"] if args.from_agent else [])
            if stale:
                kind = review_type_of(change, identifier)
                if "content changed" in stale or "unresolvable" in stale:
                    advice = ("reconcile Review scope (only the executable diff), then pre-review "
                              "--review-type re-review")
                else:
                    advice = (f"the diff is unchanged: pre-review --review-type {kind} and dispatch a fresh "
                              "reviewer on the same diff")
                return emit(checked + [f"stale: {stale}"], "CHECKED", [], "",
                            f"{identifier} recorded FAIL against a stale snapshot ({stale}); a stale round "
                            f"uses no review allowance; {advice}")
            return emit(checked, "CHECKED", [], "",
                        f"{identifier} saved; read findings before a user question or further edits")
        return pre_review(args.change_slug, args.root, args.controller_runtime,
                          review_type=args.review_type, reason=args.reason, decision=args.review_decision,
                          record_round=not args.dry_run, withdraw=args.withdraw)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return emit([args.step], "BLOCKED", [], str(exc), "inspect the plan and handoff files, then retry")


if __name__ == "__main__":
    raise SystemExit(main())
