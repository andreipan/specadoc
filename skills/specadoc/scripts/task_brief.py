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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import ensure_runs, legacy_warning, resolve_root  # noqa: E402
from validate_change import Document, ids_in, task_fields  # noqa: E402

RUNS_DIR = "runs"
SCHEMA = Path(__file__).resolve().parent.parent / "assets" / "worker-result.schema.json"


class BriefError(RuntimeError):
    pass


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
        "- Work only on the task below. Change only paths named in its **Files:** field.",
        "- Do not edit `spec.md`, `plan.md`, or anything else under the artifact root, except your report.",
        "- Do not commit, push, stash, reset, or switch branches. Do not start other agents.",
        "- Follow the repository agent instructions (for example AGENTS.md or CLAUDE.md) that apply to the files you touch.",
        "- Test first: write the failing test, show it fail (RED), implement, show it pass (GREEN).",
        f"- Write the full report to `{runs / f'{task_id}-report.md'}` using the worker report sections.",
        f"- Return JSON matching `{SCHEMA.name}`: status DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.",
        "",
        "## Task",
        "",
        *task,
        "",
        "## Requirements",
        "",
    ]
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
