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
# 6.12 took six design rounds, 6.14 seven: after ROUND_CAP recorded rounds the next one needs a decision,
# `continue: <source>` (one more round) or `accept: <source>` (open IMPORTANT items become apply obligations).
ROUND_CAP = 4
# After SHIP_ROUNDS recorded rounds only "must not ship" defects hold the design; a BLOCKER or IMPORTANT of
# class `other` becomes an apply obligation. 7.1, 8.1, 8.2 took 8, 11 and 7 rounds, and from round 3 on most
# of their BLOCKERs were test design or spec wording; 6.17 r2 (after `origin`) still had more BLOCKERs than r1.
SHIP_ROUNDS = 2
SHIP_CLASSES = ("data", "money", "access", "user-path", "wrong-result")
OTHER = "other"
SHIP_RULE = f"must-not-ship rule after design round {SHIP_ROUNDS}"
ROUND_FILE = "design-round.json"
ACCEPTED = "ACCEPTED"
DECISION = re.compile(r"\s*(?P<kind>continue|accept)\s*:\s*(?P<source>\S.*?)\s*$", re.I)
RESOLVE_EXAMPLE = "e.g. `F1.1: resolved: plan.md T2` or `F1.2: rejected: <why, three words or more>`"
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
                                        f"Class inventory: {file} needs the requirement or boundary it serves, "
                                        "in at least three words"))
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
    if result not in ("PASS", "FAIL", ACCEPTED):
        return "design review missing: run specadoc_step.py design-brief, an independent reviewer, then design-review"
    if fields.get("Inventory hash") != current:
        return "design review predates the current Class inventory; review the changed inventory again"
    if result == "FAIL":
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


def missing(plan: Document) -> list[str]:
    """Exact non-test inventory paths absent from the tree (6.2: a task left out two planned Mappers
    and accept, tidy and the whole suite passed; only the final review saw it)."""
    return sorted(path for path in patterns(plan) or []
                  if not any(c in path for c in "*?[") and not exempt(path) and not Path(path).exists())


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
    for path in missing(plan):
        violations.append(Violation(plan.display, 1, f"Class inventory file not created: {path}"))
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


BLOCKING = ("BLOCKER", "IMPORTANT")
FINDING = re.compile(r"- (?P<severity>BLOCKER|IMPORTANT|MINOR)(?: \[(?P<cls>[a-z-]+)\])?: ")
OBLIGATION = re.compile(r"\s*- Design obligation (?P<id>[A-Z]\d+(?:\.\d+)+) \(")
ITEM = re.compile(r"  - (?P<id>F\d+\.\d+): (?P<text>.*)")
RESOLUTION = re.compile(r"    - (?P<kind>resolved|rejected): (?P<text>.*)")
ENTRY = re.compile(r"\s*(?:[-*]\s*)?(?P<id>F\d+\.\d+)\s*[:=]\s*(?P<kind>resolved|rejected)\s*:\s*(?P<text>.+?)\s*$", re.I)
# A resolution points at the place a reviewer can check, not at an intention.
POINTER = re.compile(r"(?:spec|plan|design)\.md|\b[TRA]\d+\b|\S+:\d+")


def finding_lines(findings: list[dict]) -> list[str]:
    """`### Findings` lines: one per finding and, for a BLOCKER or IMPORTANT, one per separately checkable
    item. 6.8: the round-1 coverage finding named nine gaps and the fixes closed part of them each round,
    so four more rounds answered "partially resolved"."""
    flat = lambda value: " ".join(str(value).split())  # noqa: E731
    lines, number = [], 0
    for finding in findings:
        tag = f" [{finding['class']}]" if finding.get("class") else ""
        lines.append(f"- {finding['severity']}{tag}: {flat(finding['location'])} — {flat(finding['summary'])}")
        if finding["severity"] in BLOCKING:
            number += 1
            items = [flat(item) for item in finding.get("items") or [] if flat(item)] or ["the whole finding"]
            lines += [f"  - F{number}.{index}: {item}" for index, item in enumerate(items, 1)]
    return lines


def recorded_findings(plan: Document) -> list[str]:
    """The recorded round's finding, item and resolution lines."""
    if DESIGN_REVIEW not in plan.sections:
        return []
    lines = [line.rstrip() for _, line in plan.body(DESIGN_REVIEW)]
    start = next((i for i, line in enumerate(lines) if line.strip() == "### Findings"), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("### ")), len(lines))
    return [line for line in lines[start + 1:end]
            if FINDING.match(line) or ITEM.fullmatch(line) or RESOLUTION.fullmatch(line) or line.startswith("- ")]


def unresolved(plan: Document) -> list[str]:
    """Item ids of the recorded FAIL round that have no resolution yet."""
    if review_fields(plan).get("Result", "").upper() != "FAIL":
        return []
    lines = recorded_findings(plan)
    return [match["id"] for index, line in enumerate(lines) if (match := ITEM.fullmatch(line))
            and not (index + 1 < len(lines) and RESOLUTION.fullmatch(lines[index + 1]))]


def short(ids: list[str], limit: int = 5) -> str:
    """At most `limit` ids and the count (6.14: a refusal listed 37 ids)."""
    if not ids:
        return "none"
    return ", ".join(ids[:limit]) + (f" and {len(ids) - limit} more ({len(ids)} in all)" if len(ids) > limit else "")


def round_state(change: Path) -> dict:
    """Recorded design rounds of this change and the decisions that allowed rounds past the cap."""
    try:
        state = json.loads((change / "runs" / ROUND_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    return {"recorded": int(state.get("recorded", 0)), "decisions": list(state.get("decisions", [])),
            "rounds": list(state.get("rounds", []))}


def save_round_state(change: Path, state: dict) -> None:
    path = change / "runs" / ROUND_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")


def parse_decision(text: str) -> tuple[str, str]:
    match = DECISION.fullmatch(text or "")
    if not match:
        raise ValueError("--attempt-decision takes `continue: <source>` (one more round) or `accept: <source>` "
                         "(open IMPORTANT items become apply obligations); <source> names the decision, e.g. "
                         "`orchestrator D12 under mandate D80`")
    return match["kind"].lower(), " ".join(match["source"].split())


def needs_decision(change: Path, plan: Document) -> int | None:
    """The number of the next round when it is past the cap after a FAIL, else None."""
    recorded = round_state(change)["recorded"]
    if recorded >= ROUND_CAP and review_fields(plan).get("Result", "").upper() == "FAIL":
        return recorded + 1
    return None


def record_continue(change: Path, authorization: str) -> None:
    """Keep a `continue` decision in plan.md, where the archive keeps it, once per round."""
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    line = f"- Design round authorization: {authorization}"
    if line in plan.lines:
        return
    lines = list(plan.lines)
    if "Confirmed decisions" in plan.sections:
        anchor = plan.sections["Confirmed decisions"][1]
        while anchor > 0 and not lines[anchor - 1].strip():
            anchor -= 1
        lines[anchor:anchor] = [line]
    else:
        lines += ["", "## Confirmed decisions", "", line]
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    state = round_state(change)
    state["decisions"].append({"round": state["recorded"] + 1, "kind": "continue", "source": authorization})
    save_round_state(change, state)


def must_not_ship(finding: dict) -> bool:
    """A finding without a class counts as must-not-ship: the rule never defers what it cannot classify."""
    return finding.get("class", "") != OTHER


def open_ship_items(plan: Document) -> int:
    """BLOCKER/IMPORTANT findings of the recorded FAIL round with an explicit must-not-ship class. An
    unclassified finding is never deferred, but it does not demand a new method either (a reviewer that
    sets no class keeps the earlier behavior)."""
    if review_fields(plan).get("Result", "").upper() != "FAIL":
        return 0
    return sum(1 for line in recorded_findings(plan)
               if (m := FINDING.match(line)) and m["severity"] in BLOCKING and m["cls"] in SHIP_CLASSES)


def needs_method(change: Path, plan: Document) -> int | None:
    """The next round's number when it is past SHIP_ROUNDS with must-not-ship findings still open: that
    round must change how it verifies them (another method or owner), not only the reviewer model."""
    recorded = round_state(change)["recorded"]
    if recorded >= SHIP_ROUNDS and open_ship_items(plan):
        return recorded + 1
    return None


def methods(plan: Document) -> list[str]:
    """Verification methods recorded for earlier design rounds, in order."""
    found = []
    for _, line in (plan.body("Confirmed decisions") if "Confirmed decisions" in plan.sections else []):
        if m := re.match(r"\s*- Design round method: round \d+ — (?P<text>.+?)\s*$", line):
            found.append(" ".join(m["text"].split()).lower())
    return found


def record_method(change: Path, number: int, method: str) -> None:
    """Keep the round's verification method in `## Confirmed decisions`; the same method twice is refused."""
    method = " ".join(method.split())
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if len(method.split()) < 3:
        raise ValueError("--verify-by needs the method or owner of this round in three words or more, e.g. "
                         "`spike test of the lock order` or `user decides the retry contract`")
    if method.lower() in methods(plan):
        raise ValueError(f"design round {number} repeats an earlier method ({method}); a round past "
                         f"{SHIP_ROUNDS} changes how the open items are verified or who owns them")
    line = f"- Design round method: round {number} — {method}"
    lines = list(plan.lines)
    if "Confirmed decisions" in plan.sections:
        anchor = plan.sections["Confirmed decisions"][1]
        while anchor > 0 and not lines[anchor - 1].strip():
            anchor -= 1
        lines[anchor:anchor] = [line]
    else:
        lines += ["", "## Confirmed decisions", "", line]
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def deferred_obligations(findings: list[dict], number: int) -> list[str]:
    """`## Global constraints` lines for the BLOCKER/IMPORTANT findings of class `other` a round past
    SHIP_ROUNDS defers: one per item, ids `R<round>.<n>`."""
    flat = lambda value: " ".join(str(value).split())  # noqa: E731
    lines, index = [], 0
    for finding in findings:
        items = [flat(item) for item in finding.get("items") or [] if flat(item)] or [flat(finding["summary"])]
        for item in items:
            index += 1
            lines.append(f"- Design obligation R{number}.{index} (deferred in design round {number}, not "
                         f"must-not-ship; {finding['severity']}): {flat(finding['location'])} — {item}")
    return lines


def obligation_lines(plan: Document) -> dict[str, str]:
    """Design obligations of `## Global constraints` by id."""
    if "Global constraints" not in plan.sections:
        return {}
    return {m["id"]: line.strip() for _, line in plan.body("Global constraints") if (m := OBLIGATION.match(line))}


def uncited_obligations(plan: Document) -> list[str]:
    """Design obligation ids no task names in its `**Obligations:**` field."""
    from validate_change import task_fields
    known = obligation_lines(plan)
    if not known:
        return []
    cited: set[str] = set()
    for _, start, end in plan.blocks("Tasks", "T"):
        cited |= set(re.findall(r"[A-Z]\d+(?:\.\d+)+", task_fields(plan, start, end).get("Obligations", "")))
    return [identifier for identifier in known if identifier not in cited]


def rounds_line(change: Path, limit: int = 400) -> str | None:
    """One archive line with every recorded round's verdict and counts, or None before the first round."""
    rounds = round_state(change)["rounds"]
    if not rounds:
        return None
    parts = [f"r{r['round']} {r['verdict']} B{r.get('BLOCKER', 0)}/I{r.get('IMPORTANT', 0)}/M{r.get('MINOR', 0)}"
             + (f" +{r['deferred']} deferred" if r.get("deferred") else "") for r in rounds]
    line = "Design rounds: " + ", ".join(parts)
    while len(line) > limit and len(parts) > 3:
        parts = [parts[0], "…", *parts[-(len(parts) - 3):]] if parts[1] != "…" else [parts[0], "…", *parts[3:]]
        line = "Design rounds: " + ", ".join(parts)
    return line


def passed_label(plan: Document) -> str:
    fields = review_fields(plan)
    if fields.get("Result", "").upper() == ACCEPTED:
        return f"ACCEPTED ({fields.get('Accepted by', 'no source')}; open items are apply obligations)"
    return "PASS (current inventory)"


def accept(change: Path, source: str) -> list[str]:
    """Close the gate after the cap: every item of the recorded FAIL round becomes an apply obligation in
    `## Global constraints`. A BLOCKER is never accepted. Returns the obligation lines."""
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if review_fields(plan).get("Result", "").upper() != "FAIL":
        raise ValueError("accept closes a recorded FAIL round; the design review is not FAIL")
    if review_fields(plan).get("Inventory hash") != inventory_hash(plan):
        raise ValueError("the Class inventory changed after the recorded round, so that round no longer judges it; "
                         "decide `continue: <source>` and review the changed design")
    findings = recorded_findings(plan)
    if any(FINDING.match(line) and FINDING.match(line)["severity"] == "BLOCKER" for line in findings):
        raise ValueError("a BLOCKER of the recorded round stays open: accept takes IMPORTANT findings only; "
                         "fix it and review again (`continue: <source>`) or ask the user")
    state = round_state(change)
    obligations = important_obligations(findings, f"accepted after round {state['recorded']}; {source}")
    lines = list(plan.lines)
    start, end = plan.sections[DESIGN_REVIEW]
    for index in range(start + 1, end):
        if lines[index].startswith("**Result:**"):
            lines[index] = f"**Result:** {ACCEPTED}"
            lines.insert(index + 1, f"**Accepted by:** {source}")
            break
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    add_constraints(plan_path, obligations)
    state["decisions"].append({"round": state["recorded"] + 1, "kind": "accept", "source": source})
    save_round_state(change, state)
    return obligations


def important_obligations(findings: list[str], why: str) -> list[str]:
    """One `## Global constraints` line per IMPORTANT item of the recorded round, with the author's answer."""
    obligations, severity = [], None
    for index, line in enumerate(findings):
        if match := FINDING.match(line):
            severity = match["severity"]
        elif (item := ITEM.fullmatch(line)) and severity == "IMPORTANT":
            note = RESOLUTION.fullmatch(findings[index + 1]) if index + 1 < len(findings) else None
            answer = f" (author: {note['kind']}: {note['text']})" if note else ""
            obligations.append(f"- Design obligation {item['id']} ({why}): {item['text']}{answer}")
    return obligations


def add_constraints(plan_path: Path, obligations: list[str]) -> None:
    """Append lines to `## Global constraints`, creating the section when the plan has none; a line already
    there is not added again (a repeated `continue` for the same round)."""
    plan = Document(plan_path, str(plan_path))
    lines = list(plan.lines)
    obligations = [line for line in obligations if line not in lines]
    if not obligations:
        return
    if "Global constraints" in plan.sections:
        anchor = plan.sections["Global constraints"][1]
        while anchor > 0 and not lines[anchor - 1].strip():
            anchor -= 1
        lines[anchor:anchor] = obligations
    else:
        lines += ["", "## Global constraints", "", *obligations]
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def carry_important(change: Path, source: str) -> list[str]:
    """Past the cap a `continue` round checks the BLOCKER items only: the IMPORTANT items of the recorded
    round become apply obligations now, as an accept would make them. 7.1, 8.1, 8.2: rounds 5-11 of three
    changes each re-checked every IMPORTANT item and the accept condition (no BLOCKER) stayed out of reach."""
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    obligations = important_obligations(recorded_findings(plan),
                                        f"carried after round {round_state(change)['recorded']}; {source}")
    add_constraints(plan_path, obligations)
    return obligations


def blocker_findings(findings: list[str]) -> list[str]:
    """The BLOCKER findings of a recorded round with their items and answers."""
    kept, keep = [], False
    for line in findings:
        if match := FINDING.match(line):
            keep = match["severity"] == "BLOCKER"
        if keep:
            kept.append(line)
    return kept


def resolve(change: Path, text: str) -> tuple[list[str], list[str]]:
    """Write `F<n>.<m>: resolved: <where>` / `rejected: <why>` entries under their items.
    Returns (recorded ids, ids still without a resolution)."""
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    if DESIGN_REVIEW not in plan.sections:
        raise ValueError("plan.md has no recorded design review")
    start, end = plan.sections[DESIGN_REVIEW]
    lines = list(plan.lines)
    known = {match["id"]: index for index in range(start, end) if (match := ITEM.fullmatch(lines[index].rstrip()))}
    entries: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip():
            continue
        match = ENTRY.fullmatch(raw)
        if not match:
            raise ValueError(f"expected `F<n>.<m>: resolved: <where>` or `F<n>.<m>: rejected: <why>`, one line per "
                             f"item, {RESOLVE_EXAMPLE}; not: {raw.strip()}")
        kind, value = match["kind"].lower(), " ".join(match["text"].split())
        if match["id"] not in known:
            raise ValueError(f"{match['id']} is not an item of the recorded round; items: {short(list(known))}")
        if kind == "resolved" and not POINTER.search(value):
            raise ValueError(f"{match['id']}: name where it is resolved (spec.md, plan.md or design.md section, "
                             f"a task or requirement id, or file:line), {RESOLVE_EXAMPLE}")
        if kind == "rejected" and len(value.split()) < 3:
            raise ValueError(f"{match['id']}: a rejection needs its reason, {RESOLVE_EXAMPLE}")
        entries[match["id"]] = f"    - {kind}: {value}"
    if not entries:
        raise ValueError("no resolution entries given")
    for identifier in sorted(entries, key=lambda item: known[item], reverse=True):
        index = known[identifier]
        if index + 1 < len(lines) and RESOLUTION.fullmatch(lines[index + 1].rstrip()):
            lines[index + 1] = entries[identifier]
        else:
            lines.insert(index + 1, entries[identifier])
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return list(entries), unresolved(Document(plan_path, str(plan_path)))


BRIEF = "design-brief.md"
# The reviewer reads the change's own files, not only the brief: the round's diff base is a copy of them.
DESIGN_FILES = ("spec.md", "plan.md", "design.md")
BRIEFED = "design-briefed"    # the files as the latest design-brief saw them
REVIEWED = "design-reviewed"  # the files the recorded round reviewed


def _design_lines(path: Path) -> list[str]:
    """A design file's lines without `## Design review`, which every recorded round rewrites."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    kept, skipping = [], False
    for line in lines:
        if line.startswith("## "):
            skipping = line.strip() == f"## {DESIGN_REVIEW}"
        if not skipping:
            kept.append(line)
    return kept


def _copy_design(source: Path, target: Path) -> None:
    import shutil
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for name in DESIGN_FILES:
        if (source / name).is_file():
            shutil.copyfile(source / name, target / name)


def previous_round(change: Path, plan: Document) -> tuple[list[str], list[str]] | None:
    """(findings, diff of the design files since) of the recorded design round, or None before the first."""
    import difflib
    reviewed = change / "runs" / REVIEWED
    if DESIGN_REVIEW not in plan.sections or not reviewed.is_dir():
        return None
    if review_fields(plan).get("Result", "").upper() not in ("PASS", "FAIL"):
        return None
    findings = recorded_findings(plan)
    changes: list[str] = []
    for name in DESIGN_FILES:
        changes += difflib.unified_diff(_design_lines(reviewed / name), _design_lines(change / name),
                                        f"reviewed {name}", f"current {name}", n=2, lineterm="")
    return [line for line in findings if line.strip() != "- None."], changes


def write_brief(change: Path, full: bool = False, authorization: str | None = None,
                method: str | None = None) -> tuple[Path, bool]:
    """Reviewer prompt from the plan sections that decide the design; no code yet. After a recorded
    round it is a re-review of that round's findings and of what changed in spec.md, plan.md and
    design.md since, unless `full`. Returns the path and whether the brief is a re-review.

    6.5 took six whole design reviews (31 min) and 6.6 four: each round read the whole design again and
    the last rounds returned one narrow finding each."""
    spec = Document(change / "spec.md", "spec.md")
    plan = Document(change / "plan.md", "plan.md")

    def section(document: Document, name: str) -> list[str]:
        return [line for _, line in document.body(name)] if name in document.sections else ["(absent)"]

    body: list[str] = []
    for title, document, name in (("Requirements", spec, "Requirements"), ("Constraints", spec, "Constraints"),
                                  ("Confirmed decisions", plan, "Confirmed decisions"),
                                  ("Technical approach", plan, "Technical approach"),
                                  ("Files and interfaces", plan, "Files and interfaces"),
                                  ("Requirement-to-check matrix", plan, "Requirement-to-check matrix"),
                                  ("Class inventory", plan, INVENTORY)):
        body += [f"## {title}", "", *section(document, name), ""]
    previous = None if full else previous_round(change, plan)
    scope: list[str] = []
    prior: list[str] = []
    if previous:
        findings, changes = previous
        carried = []
        if authorization:
            findings = blocker_findings(findings)
            carried = ["- Past the design round cap: the IMPORTANT items of the previous round are apply "
                       "obligations in `## Global constraints` now; check the BLOCKER items below and the changes."]
        scope = ["- This is a re-review. Each finding under `Previous findings` lists its items (`F1.2`) and, "
                 "under each, where the author says it is resolved or why it is rejected. Check that place for "
                 "every item and name the items still open by id; a finding stays open, with its severity, "
                 "while one item is open. Add no item to a previous finding: a gap none of its items names is a "
                 "new finding.", *carried,
                 # 7.1: rounds 2-5 of one change each cited five to seven files no round had cited before;
                 # the old rule (a new IMPORTANT outside the changes if it cites file:line) filtered nothing,
                 # so every round was a whole review again (8, 11 and 7 rounds).
                 "- Then ask the questions below of the lines under `Changes since the reviewed design` and the "
                 "inventory rows they touch, not of the whole design again.",
                 "- Set `origin` on every finding: `previous` when it keeps an item above open, `change` for a "
                 "defect in the changed lines, `new` for anything else. Outside the changes report only a BLOCKER "
                 "(origin `new`, its summary citing the file:line that proves it); an IMPORTANT or MINOR there "
                 "belongs in `report` as a note and does not fail the round."]
        none = ("- None: the IMPORTANT items are apply obligations now." if authorization
                else "- None: the design changed after a PASS.")
        prior = ["## Previous findings", "", *(findings or [none]), "",
                "## Changes since the reviewed design", "", "````diff", *(changes or ["(no change)"]), "````", ""]
    number = round_state(change)["recorded"] + 1
    ship = ([f"- This is design round {number}: only must-not-ship findings (class other than `other`) hold the "
             "design now. A BLOCKER or IMPORTANT of class `other` becomes an apply obligation and does not fail "
             "the round, so classify honestly."] if number > SHIP_ROUNDS else [])
    lines = [f"# Design {'re-review' if previous else 'review'}: `{change.name}`", "",
             *([f"Round authorization: {authorization}", ""] if authorization else []),
             *([f"Round method: {' '.join(method.split())} (check the open must-not-ship items this way)", ""]
               if method else []), "## Contract", "",
             "- Read-only. Review the design before any code exists; do not edit files or run builds.",
             "- Inspect the existing code the plan names as exemplars only to judge the design.",
             *scope,
             "- For each Class inventory row ask: is the file needed for a requirement? Does a port cross a real "
             "boundary or have a second implementation? Is the layer right? Does it mirror an existing feature "
             "without a reason? Is there a simpler shape with fewer files and the same behavior?",
             # 3.8: review found these only after apply (legacy rows, trailing data, an undeclared extension,
             # an ambiguous error code).
             "- For the design as a whole ask: which existing data states (legacy or partial rows) must it "
             "handle? Which platform requirements (runtime extensions, binaries) does it add, and are they "
             "declared? Which input-format edge cases (truncated, oversized, trailing or malformed data) does it "
             "accept or reject? Which error code or outcome does each failure map to? A missing answer that "
             "affects a requirement is IMPORTANT.",
             # 4.3-4.5: design rounds and the integration run found these after the plan was written.
             "- Also ask: in what order does each operation check authorization, input, existence and state, and "
             "what does each actor role get for valid, malformed and unknown input? Which rows and parent rows "
             "(including those locked by foreign-key checks) does each transaction lock, in what order relative "
             "to the other writers, and what does a deadlock or retry return? Which existing tests or fixtures "
             "write a table whose constraints change, and are they in a task's Files? Does any planned exception "
             "contradict a repository architecture rule (module boundaries, allowed bridges or consumers)?",
             # 5.2: four value-shape rules of the spec had no test and came back from the final review as BLOCKERs.
             "- For each spec rule on the shape of a value (format, anchors, ranges, explicit null versus absent, "
             "empty object versus empty list, length or precision limits), name the matrix row or task "
             "Verification that tests one accepted and one rejected value. A rule without such a test is IMPORTANT.",
             # 6.1: a planned path broke the closed use-case folder rule and stopped apply; 6.1/6.2: the spec
             # promised one Gate request (GETs retry) and a timestamp format the connector rejects.
             # 6.5: half of the findings of rounds 2-5 were folder and naming rules, one rule a round.
             f"- Check {'each inventory path the changes add or move' if previous else 'every inventory path'} "
             "against the repository's folder and naming rules (code standards, "
             "lint structure rules), row by row and in this round: for each row find the rule that fixes its "
             "folder and the rule that fixes its name and kind, and end `report` with one line per row, "
             "`<path>: <rule file:line>` or `<path>: no rule`. A path such a rule forbids is IMPORTANT. Check "
             "each spec or plan statement "
             "about an existing component's behavior (retries, accepted formats, error mapping) against that "
             "component's code and cite file:line; an unverified statement a requirement depends on is IMPORTANT.",
             "- Put every separately checkable gap of a BLOCKER or IMPORTANT finding into its `items`, one "
             "entry each (a missing accepted/rejected test pair, an unlocked row, an unanswered case), and list "
             "them all in this round: the author answers item by item and a re-review adds none.",
             "- BLOCKER: the design cannot meet a requirement or breaks a layer rule. IMPORTANT: a file or port "
             "without a reason, or a clearly simpler design. MINOR: naming or placement.",
             "- Set `class` on every BLOCKER and IMPORTANT: `data` (data lost or corrupted), `money`, `access` "
             "(secrets, authentication, another user's data, personal data left in clear), `user-path` (a user "
             "cannot finish a required path), `wrong-result` (a silently wrong result), else `other` (test "
             "design, spec wording, internal rules, structure). A finding of the first five classes names the "
             "actor, the input and the wrong outcome in `summary`, and shows that the state can occur: the code "
             "path (file:line), existing rows, or an input the spec admits. A state nobody showed can occur (a "
             "hypothetical legacy row, deadline or timing arithmetic, an unverified claim about another "
             "component) is `other` until shown.", *ship,
             f"- Return JSON matching `{(Path(__file__).resolve().parent.parent / 'assets/reviewer-result.schema.json')}`; "
             "`report` is a short prose summary, then the row lines; location is the inventory path or plan "
             "section.", ""]
    lines += prior + body
    path = change / "runs" / BRIEF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    _copy_design(change, change / "runs" / BRIEFED)
    return path, bool(previous)


def record(change: Path, source: str, reviewer: str, agent: str | None = None,
           same_reviewer_reason: str | None = None) -> str:
    """Write `## Design review` from a reviewer-schema result, bound to the inventory hash."""
    from reviewer_reply import previous_agent
    from run_role import _parse_json_text, result_source, schema_errors, schema_path
    from task_state import digest, safe_path
    plan_path = change / "plan.md"
    plan = Document(plan_path, str(plan_path))
    current = inventory_hash(plan)
    if not rows(plan):
        raise ValueError("plan.md has no Class inventory rows to review")
    if agent and not same_reviewer_reason and DESIGN_REVIEW in plan.sections:
        start, end = plan.sections[DESIGN_REVIEW]
        if previous_agent("\n".join(plan.lines[start:end])) == agent:
            raise ValueError(f"agent {agent} reviewed the previous design round; dispatch a fresh reviewer "
                             "or pass --same-reviewer-reason")
    stale_brief(source)
    # 6.7: the run record was passed and the answer was "reviewer process did not exit successfully".
    source = result_source(source)
    result_path = safe_path(source, allow_missing=False, allow_absolute=True,
                            hint=f"save it under {change}/runs/")
    payload = _parse_json_text(result_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "result" in payload and "exit" in payload:
        if payload["exit"] != 0:
            raise ValueError("reviewer process did not exit successfully")
        payload = payload["result"]
    if errors := schema_errors(payload, json.loads(schema_path("reviewer").read_text())):
        raise ValueError("invalid design review result: " + "; ".join(errors))
    counted, notes = split_findings(payload["findings"], rereview_brief(change))
    number = round_state(change)["recorded"] + 1
    deferred = ([f for f in counted if f["severity"] in BLOCKING and not must_not_ship(f)]
                if number > SHIP_ROUNDS else [])
    counted = [f for f in counted if f not in deferred]
    verdict = payload["verdict"]
    if not any(f["severity"] in BLOCKING for f in counted):
        if deferred:
            verdict = ACCEPTED
        elif verdict == "FAIL" and notes:
            verdict = "PASS"
    if verdict == "PASS" and any(f["severity"] in BLOCKING for f in counted):
        raise ValueError("design review PASS contradicts open BLOCKER/IMPORTANT findings")
    obligations = deferred_obligations(deferred, number)
    flat = lambda value: " ".join(value.split())  # noqa: E731
    note_lines = [f"- note ({f['severity']}, outside the changes): {flat(f['location'])} — {flat(f['summary'])}"
                  for f in notes]
    why = ("only findings outside the re-review scope; see Notes" if not deferred
           else f"findings of class `other` are apply obligations after round {SHIP_ROUNDS}; see Deferred")
    body = ["", f"**Result:** {verdict}",
            *([f"**Accepted by:** {SHIP_RULE}"] if verdict == ACCEPTED else []),
            *([f"**Reviewer verdict:** {payload['verdict']} ({why})"] if verdict != payload["verdict"] else []),
            f"**Inventory hash:** {current}",
            f"**Reviewer:** {flat(reviewer)}",
            *([f"**Reviewer agent:** `{agent}`"] if agent else []),
            *([f"**Same reviewer reason:** {flat(same_reviewer_reason)}"] if agent and same_reviewer_reason else []),
            f"**Result source:** `{source}`",
            f"**Result digest:** {digest(result_path)}", "", "### Findings", "",
            *(finding_lines(counted) or ["- None."]), "",
            *(["### Deferred to apply (not must-not-ship)", "",
               *(line.replace("- Design obligation ", "- ", 1) for line in obligations), ""] if obligations else []),
            *(["### Notes outside the re-review scope", "", *note_lines, ""] if note_lines else [])]
    lines = list(plan.lines)
    if DESIGN_REVIEW in plan.sections:
        start, end = plan.sections[DESIGN_REVIEW]
        lines[start + 1:end] = body
    else:
        anchor = plan.sections[INVENTORY][1]
        lines[anchor:anchor] = [f"## {DESIGN_REVIEW}", *body]
    plan_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    add_constraints(plan_path, obligations)
    briefed = change / "runs" / BRIEFED
    if briefed.is_dir():
        # The next design-brief diffs against what this round saw: the files as its brief was written,
        # not as they are now (6.6: the controller edited spec and plan while the reviewer ran).
        _copy_design(briefed, change / "runs" / REVIEWED)
    state = round_state(change)
    state["recorded"] += 1
    # Per-round counts survive in the archive record (runs/ is removed at archive; 8.1 and 8.2 lost theirs).
    every = counted + deferred
    state["rounds"].append({
        "round": state["recorded"], "verdict": verdict, "reviewer_verdict": payload["verdict"],
        **{severity: sum(1 for f in counted if f["severity"] == severity) for severity in ("BLOCKER", "IMPORTANT", "MINOR")},
        "deferred": len(deferred), "notes": len(notes),
        "classes": {cls: n for cls in (*SHIP_CLASSES, OTHER, "unset")
                    if (n := sum(1 for f in every if f["severity"] in BLOCKING and f.get("class", "unset") == cls))}})
    save_round_state(change, state)
    # A recorded brief starts no other round (8.2: a chain ran the reviewer on the previous brief after
    # design-brief had refused round 5).
    (change / "runs" / BRIEF).unlink(missing_ok=True)
    return verdict


def rereview_brief(change: Path) -> bool:
    """Whether the brief this round answered was a re-review (its first line says so)."""
    try:
        with (change / "runs" / BRIEF).open(encoding="utf-8") as handle:
            return handle.readline().startswith("# Design re-review")
    except OSError:
        return False


def split_findings(findings: list[dict], rereview: bool) -> tuple[list[dict], list[dict]]:
    """(findings that judge the round, notes). In a re-review an IMPORTANT or MINOR with origin `new` lies
    outside the changes and the open items, so it is a note, not a reason to fail the round."""
    if not rereview:
        return list(findings), []
    notes = [f for f in findings if f.get("origin") == "new" and f["severity"] != "BLOCKER"]
    return [f for f in findings if f not in notes], notes


def stale_brief(source: str) -> None:
    """Refuse a reviewer run whose prompt file changed after `run_role.py start` (6.12, 6.13: a reviewer
    started on the previous round's brief)."""
    for suffix in (".run.json", ".result.json"):
        if source.endswith(suffix):
            run_file = Path(source.removesuffix(suffix) + ".run.json")
            break
    else:
        return
    try:
        record = json.loads(run_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    seen, prompt = record.get("prompt_sha256"), record.get("prompt_file")
    if not seen or not prompt or not Path(prompt).is_file():
        return
    if hashlib.sha256(Path(prompt).read_bytes()).hexdigest() != seen:
        raise ValueError(f"the reviewer ran on a stale brief: {prompt} changed after this run started; start a "
                         "new round with a new --name on the current brief")
