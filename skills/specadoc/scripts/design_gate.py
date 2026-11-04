"""Design gate: a plan's Class inventory and its independent design review.

Run 3.5 mirrored an existing feature with about seven ports and no one counted
classes before code. A plan lists every new non-test file in `## Class
inventory` (file, layer, why it exists, kind). An independent reviewer checks
that inventory before apply; `## Design review` records its verdict bound to the
inventory hash. Dispatch requires a current PASS, and accept, pre-review and
final reject a new non-test file outside the inventory.

Plans without a `## Class inventory` section keep the earlier behavior.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from validate_change import PENDING, Document, Violation, files_patterns

INVENTORY = "Class inventory"
DESIGN_REVIEW = "Design review"
KINDS = ("port", "concrete", "file")
APPLY_START = "apply-start.json"
# Tests and prose need no design decision; everything else new does.
EXEMPT = re.compile(r"(?:^|/)(?:tests?|__tests__|spec)/|_test\.\w+$|Test\.\w+$|\.(?:test|spec)\.[cm]?[jt]sx?$"
                    r"|\.(?:md|rst|adoc|txt)$")
FIELD = re.compile(r"\*\*(?P<key>[^*]+):\*\*\s*(?P<value>.*)")


def rows(plan: Document) -> list[tuple[int, list[str]]] | None:
    """Inventory table rows, or None when the plan has no inventory section."""
    if INVENTORY not in plan.sections:
        return None
    return plan.rows(INVENTORY)


def patterns(plan: Document) -> list[str] | None:
    found = rows(plan)
    if found is None:
        return None
    result = []
    for _, cells in found:
        paths, _ = files_patterns(cells[0] if cells else "")
        result += paths
    return result


def inventory_hash(plan: Document) -> str | None:
    found = rows(plan)
    if found is None:
        return None
    text = "\n".join("\x1f".join(" ".join(cell.split()) for cell in cells) for _, cells in found)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_inventory(plan: Document) -> list[Violation]:
    found = rows(plan)
    if found is None:
        return []
    violations = []
    for number, cells in found:
        if len(cells) != 4:
            violations.append(Violation(plan.display, number, "Class inventory row needs File | Layer | Why it exists | Kind"))
            continue
        file, layer, why, kind = cells
        paths, invalid = files_patterns(file)
        if len(paths) != 1 or invalid:
            violations.append(Violation(plan.display, number, f"Class inventory: one backticked path or glob per row, not {file}"))
        if not layer or PENDING.search(layer) or "<" in layer:
            violations.append(Violation(plan.display, number, f"Class inventory: {file} has no layer"))
        if len(why.split()) < 3 or PENDING.search(why) or "<" in why:
            violations.append(Violation(plan.display, number,
                                        f"Class inventory: {file} needs the requirement or boundary it serves"))
        if kind.strip().lower() not in KINDS:
            violations.append(Violation(plan.display, number, f"Class inventory: {file} kind must be one of {', '.join(KINDS)}"))
    return violations


def review_fields(plan: Document) -> dict[str, str]:
    return {m["key"].strip(): m["value"].strip() for _, line in plan.body(DESIGN_REVIEW)
            if (m := FIELD.match(line.strip()))}


def review_error(plan: Document) -> str | None:
    """Why apply may not start yet, or None. Only plans with an inventory have the gate."""
    current = inventory_hash(plan)
    if current is None or not rows(plan):
        return None
    fields = review_fields(plan)
    result = fields.get("Result", "").upper()
    if result not in ("PASS", "FAIL"):
        return "design review missing: run specadoc_step.py design-brief, an independent reviewer, then design-review"
    if fields.get("Inventory hash") != current:
        return "design review predates the current Class inventory; review the changed inventory again"
    if result != "PASS":
        return "design review FAIL: revise the approach or inventory, then review again"
    return None


def exempt(path: str) -> bool:
    return bool(EXEMPT.search(path))


def outside(plan: Document, paths: list[str]) -> list[str]:
    """New non-test paths no inventory row covers; empty when the plan has no inventory."""
    from review_snapshot import in_scope
    allowed = patterns(plan)
    if allowed is None:
        return []
    return [path for path in paths if not exempt(path) and not in_scope(path, allowed)]


def record_apply_start(runs: Path, manifest: dict[str, str]) -> None:
    """The tree before the first task: later additions are this change's new files."""
    path = runs / APPLY_START
    if not path.exists():
        path.write_text(json.dumps({"paths": sorted(manifest)}, indent=0) + "\n", encoding="utf-8")


def added_since_start(change: Path, artifact_root: str) -> list[str] | None:
    from review_snapshot import _under, tree_manifest
    try:
        start = set(json.loads((change / "runs" / APPLY_START).read_text(encoding="utf-8"))["paths"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return sorted(path for path in tree_manifest(Path.cwd(), artifact_root)
                  if path not in start and not _under(path, artifact_root))


def gate_violations(plan: Document) -> list[Violation]:
    """Pre-review and final: a current design PASS, and every new file inventoried."""
    if rows(plan) is None:
        return []
    violations = []
    if error := review_error(plan):
        violations.append(Violation(plan.display, 1, error))
    change = plan.path.parent
    root = change.parent.resolve().relative_to(Path.cwd().resolve()).as_posix()
    for path in outside(plan, added_since_start(change, root) or []):
        violations.append(Violation(plan.display, 1, f"new file outside Class inventory: {path}"))
    return violations


def missing_inventory_warning(plan: Document) -> list[str]:
    """A plan that will add non-test files but lists no inventory skips the gate."""
    if rows(plan) is not None:
        return []
    from validate_change import task_fields
    new = sorted({path for _, start, end in plan.blocks("Tasks", "T")
                  for path in files_patterns(task_fields(plan, start, end).get("Files", ""))[0]
                  if not any(c in path for c in "*?[") and not exempt(path) and not Path(path).exists()})
    if not new:
        return []
    shown = ", ".join(new[:5]) + (f" and {len(new) - 5} more" if len(new) > 5 else "")
    return [f"tasks add new files ({shown}) but plan.md has no Class inventory; list them and run the design review"]


def write_brief(change: Path) -> Path:
    """Reviewer prompt from the plan sections that decide the design; no code yet."""
    spec = Document(change / "spec.md", "spec.md")
    plan = Document(change / "plan.md", "plan.md")

    def section(document: Document, name: str) -> list[str]:
        return [line for _, line in document.body(name)] if name in document.sections else ["(absent)"]

    lines = [f"# Design review: `{change.name}`", "", "## Contract", "",
             "- Read-only. Review the design before any code exists; do not edit files or run builds.",
             "- Inspect the existing code the plan names as exemplars only to judge the design.",
             "- For each Class inventory row ask: is the file needed for a requirement? Does a port cross a real "
             "boundary or have a second implementation? Is the layer right? Does it mirror an existing feature "
             "without a reason? Is there a simpler shape with fewer files and the same behavior?",
             "- BLOCKER: the design cannot meet a requirement or breaks a layer rule. IMPORTANT: a file or port "
             "without a reason, or a clearly simpler design. MINOR: naming or placement.",
             f"- Return JSON matching `{(Path(__file__).resolve().parent.parent / 'assets/reviewer-result.schema.json')}`; "
             "`report` is a short prose summary; location is the inventory path or plan section.", ""]
    for title, document, name in (("Requirements", spec, "Requirements"), ("Constraints", spec, "Constraints"),
                                  ("Confirmed decisions", plan, "Confirmed decisions"),
                                  ("Technical approach", plan, "Technical approach"),
                                  ("Files and interfaces", plan, "Files and interfaces"),
                                  ("Class inventory", plan, INVENTORY)):
        lines += [f"## {title}", "", *section(document, name), ""]
    path = change / "runs" / "design-brief.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def record(change: Path, source: str, reviewer: str) -> str:
    """Write `## Design review` from a reviewer-schema result, bound to the inventory hash."""
    from run_role import _parse_json_text, schema_errors, schema_path
    from task_state import digest, safe_path
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    current = inventory_hash(plan)
    if not rows(plan):
        raise ValueError("plan.md has no Class inventory rows to review")
    result_path = safe_path(source, allow_missing=False, allow_absolute=True)
    payload = _parse_json_text(result_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "result" in payload and "exit" in payload:
        if payload["exit"] != 0:
            raise ValueError("reviewer process did not exit successfully")
        payload = payload["result"]
    if errors := schema_errors(payload, json.loads(schema_path("reviewer").read_text())):
        raise ValueError("invalid design review result: " + "; ".join(errors))
    if payload["verdict"] == "PASS" and any(f["severity"] in ("BLOCKER", "IMPORTANT") for f in payload["findings"]):
        raise ValueError("design review PASS contradicts open BLOCKER/IMPORTANT findings")
    flat = lambda value: " ".join(value.split())  # noqa: E731
    body = ["", f"**Result:** {payload['verdict']}", f"**Inventory hash:** {current}",
            f"**Reviewer:** {flat(reviewer)}", f"**Result source:** `{source}`",
            f"**Result digest:** {digest(result_path)}", "", "### Findings", "",
            *([f"- {f['severity']}: {flat(f['location'])} — {flat(f['summary'])}" for f in payload["findings"]]
              or ["- None."]), ""]
    lines = list(plan.lines)
    if DESIGN_REVIEW in plan.sections:
        start, end = plan.sections[DESIGN_REVIEW]
        lines[start + 1:end] = body
    else:
        anchor = plan.sections[INVENTORY][1]
        lines[anchor:anchor] = [f"## {DESIGN_REVIEW}", *body]
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return payload["verdict"]
