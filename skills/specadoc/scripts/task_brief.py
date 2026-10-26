#!/usr/bin/env python3
"""Write a self-contained brief for one delegated plan task.

The brief carries exactly what a worker on any runtime needs: the task block
from plan.md verbatim, the spec requirements it names, the acceptance
scenarios that cover them (from spec.md's Requirement coverage table), the
spec's Constraints, and the handoff contract (report path, result schema,
scope rules). It is written to `<root>/<slug>/runs/T<n>-brief.md`, so the
dispatch prompt only needs that path and the run survives a context reset.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import ensure_runs, legacy_warning, resolve_root  # noqa: E402
from validate_change import Document, ids_in, task_fields  # noqa: E402

RUNS_DIR = "runs"
SCHEMA = Path(__file__).resolve().parent.parent / "assets" / "worker-result.schema.json"


class BriefError(RuntimeError):
    pass



def optional(value: str | None) -> str | None:
    """An optional field left at its template default (`None; ...`) is absent."""
    if not value or re.match(r"(?:none|n/a|-)\b", value.strip(), re.I):
        return None
    return value

def _block(document: Document, section: str, prefix: str, identifier: str) -> list[str]:
    for found, start, end in document.blocks(section, prefix):
        if found == identifier:
            return document.lines[start:end]
    raise BriefError(f"{document.display}: no {identifier} under ## {section}")


def _coverage(spec: Document) -> dict[str, list[str]]:
    table: dict[str, list[str]] = {}
    for _, cells in spec.rows("Requirement coverage"):
        requirement = next(iter(ids_in(cells[0], "R")), None)
        if requirement and len(cells) > 1:
            table[requirement] = ids_in(cells[1], "A")
    return table


def build_brief(change: Path, task_id: str) -> str:
    plan_path, spec_path = change / "plan.md", change / "spec.md"
    if not plan_path.is_file() or not spec_path.is_file():
        raise BriefError(f"missing spec.md/plan.md under {change}")
    plan = Document(plan_path, "plan.md")
    spec = Document(spec_path, "spec.md")

    task = _block(plan, "Tasks", "T", task_id)
    start = next(start for found, start, _ in plan.blocks("Tasks", "T") if found == task_id)
    fields = task_fields(plan, start, start + len(task))
    requirements = ids_in(fields.get("Requirements", ""), "R")
    if not requirements:
        raise BriefError(f"{task_id}: Requirements names no requirement")
    # Include explicit transitive references, not the entire specification.
    for requirement in requirements:
        for related in ids_in("\n".join(_block(spec, "Requirements", "R", requirement)), "R"):
            if related not in requirements:
                requirements.append(related)
    coverage = _coverage(spec)
    scenarios: list[str] = []
    for requirement in requirements:
        for scenario in coverage.get(requirement, []):
            if scenario not in scenarios:
                scenarios.append(scenario)

    runs = change / RUNS_DIR
    lines = [
        f"# Brief: {task_id} of `{change.name}`",
        "",
        "## Contract",
        "",
        "- Work only on the task below. Change only paths named in its **Files:** field, plus its **Derived files:** and the lockfile of a manifest in Files.",
        f"- Do not edit `spec.md`, `plan.md`, baseline or other briefs/reports. Only your report and `{runs}/{task_id}-*.log` diagnostics may change under the artifact root.",
        "- Do not commit, push, stash, reset, or switch branches. Do not start other agents.",
        "- Follow the repository agent instructions (for example AGENTS.md or CLAUDE.md) that apply to the files you touch.",
        (f"- Approved TDD exception: {fields['TDD exception']}" if optional(fields.get("TDD exception"))
         else "- Test first: write the failing test, show it fail (RED), implement, show it pass (GREEN)."),
        f"- Write the full report to `{runs / f'{task_id}-report.md'}` using the worker report sections.",
        f"- Return JSON matching `{SCHEMA.resolve()}`: status DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED. Embed the same JSON as the last fenced block of your report so native and external results can both be validated.",
        "- Run focused task checks; the controller owns the final integration suite. Save a failure once, then inspect that log instead of rerunning it for a different output view.",
        "- Stop at NEEDS_CONTEXT before required wiring, exports or dependent tests outside Files and Derived files; stop at BLOCKED for a new architecture, compatibility or catalog decision, or when requirements conflict. Never weaken a test, threshold or requirement to make it pass. Disclosing a deviation is not approval to make it.",
        "",
        "## Task",
        "",
        *task,
        "",
        "## Requirements",
        "",
    ]
    context = []
    for dependency in ids_in(fields.get("Depends on", ""), "T"):
        block = _block(plan, "Tasks", "T", dependency)
        position = next(start for found, start, _ in plan.blocks("Tasks", "T") if found == dependency)
        result = optional(task_fields(plan, position, position + len(block)).get("Accepted result"))
        context.append(f"- {dependency}: {result or 'accepted result not recorded; ask the controller for its current interfaces.'}")
    if not fields.get("Decisions"):
        context.extend(line for _, line in plan.body("Confirmed decisions") if task_id in ids_in(line, "T"))
    if context:
        lines[-2:-2] = ["## Accepted dependency context", "", *context, ""]
    for requirement in requirements:
        lines += _block(spec, "Requirements", "R", requirement) + [""]
    if scenarios:
        lines += ["## Acceptance scenarios", ""]
        for scenario in scenarios:
            lines += _block(spec, "Acceptance scenarios", "A", scenario) + [""]
    constraints = [line for _, line in spec.body("Constraints")]
    if any(line.strip() for line in constraints):
        lines += ["## Constraints", "", *constraints, ""]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_slug")
    parser.add_argument("task", help="Task id such as T3")
    parser.add_argument("--root", help="Artifact root (default: resolved, see specadoc_root.py)")
    args = parser.parse_args()
    try:
        choice = resolve_root(args.root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if warning := legacy_warning(choice):
        print(warning, file=sys.stderr)
    change = Path(choice.path) / args.change_slug
    try:
        brief = build_brief(change, args.task)
    except BriefError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    target = change / RUNS_DIR / f"{args.task}-brief.md"
    ensure_runs(target.parent)
    target.write_text(brief, encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
