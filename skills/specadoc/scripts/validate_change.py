#!/usr/bin/env python3
"""Validate Specadoc artifacts against the documented quality gates.

Structure only. The prose gates in references/artifacts.md stay authoritative for
whether a requirement is observable, a task is a real outcome, or evidence is
honest. A passing run is not an accepted specification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402

PHASES = ("spec", "plan", "pre-review", "final")

SPEC_SECTIONS = (
    "Goal",
    "Non-goals",
    "Current context",
    "Affected capabilities",
    "Requirements",
    "Acceptance scenarios",
    "Constraints",
    "Assumptions",
    "Requirement coverage",
)

PLAN_SECTIONS = (
    "Model handoff",
    "Reconnaissance evidence",
    "Confirmed decisions",
    "Technical approach",
    "Global constraints",
    "Files and interfaces",
    "Tasks",
    "Requirement-to-check matrix",
    "Plan approval",
    "Final verification",
    "Review result",
    "Archive summary",
    "Completion evidence",
)

TASK_FIELDS = (
    "Requirements",
    "Risk",
    "Decision risk",
    "Owner",
    "Owner level",
    "Verification owner",
    "Files",
    "Test first",
    "Expected RED",
    "Implementation",
    "Verification",
    "Surface",
    "Delivery verification",
    "Done when",
    "Evidence",
)

OWNERS = ("controller", "worker")
VERIFICATION_OWNERS = ("worker", "controller")
DECISION_RISKS = ("low", "medium", "high")
SURFACES = ("code", "ui", "mixed")

MIN_TASKS = 3
MAX_TASKS = 8

PLACEHOLDER = re.compile(r"<[A-Za-z][^>\n]{2,}>")
INLINE_CODE = re.compile(r"`[^`\n]*`")
DISCLOSURE_TAG = re.compile(
    r"""<(?:details|summary)(?:\s+(?:open|[\w-]+=(?:"[^"]*"|'[^']*')))*\s*>""",
    re.IGNORECASE,
)
FIELD = re.compile(r"^-\s+\*\*(?P<name>[^*]+):\*\*\s*(?P<value>.*)$")
CHECKBOX = re.compile(r"^-\s+\[(?P<mark>[ xX])\]\s+(?P<label>.+)$")
TASK_CHECKBOX = re.compile(r"^-\s+\[(?P<mark>[ xX])\]\s+Complete\s*$")
PENDING = re.compile(r"\b(Pending|TBD)\b")

# The literal placeholder text shipped in assets/plan-template.md's Evidence
# field; a task whose Evidence still contains this was never actually
# recorded, whether or not the field is otherwise non-empty.
PLACEHOLDER_EVIDENCE = "keep final evidence to one or two lines"

# Cap on new-diff review rounds enforced by check_review_round_cap. A
# targeted re-review (Type: re-review) never counts against this.
ROUND_CAP = 3
GATE_JSON_FENCE = "```json"

CAPABILITY_PATH = re.compile(r"^-\s+`(?P<path>[\w./-]+\.md)`(?P<flags>.*)$")
CAPABILITY_OP = re.compile(
    r"^\s+-\s+(?P<op>ADDED|MODIFIED|REMOVED|RENAMED)\s+(?P<id>C\d+)\s*(?P<rest>.*)$"
)
CAPABILITY_HEADING = re.compile(r"^###\s+(?P<id>C\d+)\b")

# RENAMED before REMOVED before MODIFIED before ADDED: a rename must land before
# anything addresses the new heading, and an id freed by REMOVED must not collide
# with one ADDED in the same change.
OPERATION_ORDER = ("RENAMED", "REMOVED", "MODIFIED", "ADDED")


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    message: str

    def render(self) -> str:
        return f"{self.file}:{self.line}: {self.message}"


class Document:
    """A parsed artifact file addressed by section and by `### <id>` block."""

    def __init__(self, path: Path, display: str) -> None:
        self.path = path
        self.display = display
        self.lines = path.read_text(encoding="utf-8").splitlines()
        self.sections: dict[str, tuple[int, int]] = {}
        starts: list[tuple[str, int]] = []
        for index, line in enumerate(self.lines):
            if line.startswith("## "):
                starts.append((line[3:].strip(), index))
        for position, (name, start) in enumerate(starts):
            end = starts[position + 1][1] if position + 1 < len(starts) else len(self.lines)
            self.sections[name] = (start, end)

    def blocks(self, section: str, prefix: str) -> list[tuple[str, int, int]]:
        """Return (identifier, start, end) for each `### <prefix><n>` in a section."""
        if section not in self.sections:
            return []
        start, end = self.sections[section]
        pattern = re.compile(rf"^###\s+({prefix}\d+)\b")
        found = [
            (match.group(1), index)
            for index in range(start, end)
            if (match := pattern.match(self.lines[index]))
        ]
        result = []
        for position, (identifier, block_start) in enumerate(found):
            block_end = found[position + 1][1] if position + 1 < len(found) else end
            result.append((identifier, block_start, block_end))
        return result

    def body(self, section: str) -> list[tuple[int, str]]:
        if section not in self.sections:
            return []
        start, end = self.sections[section]
        return [(index + 1, self.lines[index]) for index in range(start + 1, end)]

    def rows(self, section: str) -> list[tuple[int, list[str]]]:
        """Markdown table rows of a section, excluding header and separator."""
        result = []
        for number, line in self.body(section):
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-", ":", " "} and cell for cell in cells):
                continue
            result.append((number, cells))
        return result[1:] if result else result

    def placeholders(self, section: str) -> list[tuple[int, str]]:
        found = []
        for number, line in self.body(section):
            if "specadoc:ignore-placeholder" in line:
                continue
            bare = DISCLOSURE_TAG.sub("", INLINE_CODE.sub("", line))
            match = PLACEHOLDER.search(bare)
            if match:
                found.append((number, match.group(0)))
        return found


def ids_in(text: str, prefix: str) -> list[str]:
    return re.findall(rf"\b({prefix}\d+)\b", text)


def check_sections(document: Document, required: tuple[str, ...]) -> list[Violation]:
    return [
        Violation(document.display, 1, f"missing required section: ## {name}")
        for name in required
        if name not in document.sections
    ]


def capability_deltas(spec: "Document", root: str) -> list[tuple[int, str, bool, list[tuple[int, str, str, str]]]]:
    """Parse `## Affected capabilities` into (line, path, is_new, operations).

    An operation is (line, op, capability id, rest-of-line text). The
    rest-of-line text is where a requirement citation like `(R7)` lives; see
    `check_capability_deltas`. Lines that are neither a capability path nor an
    operation are returned to the caller as a violation by
    `check_capability_deltas`; this function only reads structure.
    """
    entries: list[tuple[int, str, bool, list[tuple[int, str, str, str]]]] = []
    for number, line in spec.body("Affected capabilities"):
        path_match = CAPABILITY_PATH.match(line)
        if path_match:
            path = path_match.group("path")
            if not path.startswith(f"{root}/specs/"):
                continue
            entries.append((number, path, "(new capability)" in path_match.group("flags"), []))
            continue
        op_match = CAPABILITY_OP.match(line)
        if op_match and entries:
            entries[-1][3].append(
                (number, op_match.group("op"), op_match.group("id"), op_match.group("rest"))
            )
    return entries


def cross_change_findings(
    spec: "Document", root: str, change_slug: str
) -> tuple[list[Violation], list[str]]:
    """Compare this change's capability operations with other active changes.

    Active changes are directories directly under the artifact root, other than
    `archive`, `specs`, and `contracts`, that contain `spec.md`. Returns
    (violations, warnings).
    """
    violations: list[Violation] = []
    warnings: list[str] = []
    mine = capability_deltas(spec, root)
    skipped = {change_slug, "archive", "specs", "contracts"}
    for sibling in sorted(Path(root).iterdir()):
        if sibling.name in skipped or not sibling.is_dir():
            continue
        sibling_spec = sibling / "spec.md"
        if not sibling_spec.is_file():
            continue
        theirs = capability_deltas(Document(sibling_spec, str(sibling_spec)), root)
        added = set()
        edits: dict[tuple[str, str], list[str]] = {}
        for _, path, _, ops in theirs:
            for _, op, identifier, _ in ops:
                if op == "ADDED":
                    added.add((path, identifier))
                else:
                    edits.setdefault((path, identifier), []).append(op)
        for _, path, _, ops in mine:
            for number, op, identifier, _ in ops:
                if op == "ADDED" and (path, identifier) in added:
                    violations.append(
                        Violation(
                            spec.display,
                            number,
                            f"{identifier} on {path} is also ADDED by active change {sibling.name}",
                        )
                    )
                elif op != "ADDED":
                    for their_op in edits.get((path, identifier), []):
                        warnings.append(
                            f"{identifier} on {path}: {op} here, {their_op} by active change {sibling.name}"
                        )
    return violations, warnings


def stray_delta_lines(spec: "Document", root: str) -> list[Violation]:
    """Indented delta-like lines that `capability_deltas` would silently drop.

    A misspelled operation (`MODIFED C3`) or an operation under a path outside
    `{root}/specs/` is not applied at archive, so the requirement change is lost
    without a trace unless it is reported here.
    """
    violations: list[Violation] = []
    owner: str | None = None
    for number, line in spec.body("Affected capabilities"):
        if path_match := CAPABILITY_PATH.match(line):
            owner = path_match.group("path")
            continue
        if not re.match(r"^\s+-\s+\S", line):
            continue
        if owner is None:
            violations.append(Violation(spec.display, number, "operation line before any capability path"))
        elif not owner.startswith(f"{root}/specs/"):
            violations.append(Violation(
                spec.display, number,
                f"{owner}: operations are ignored outside {root}/specs/"))
        elif not CAPABILITY_OP.match(line):
            violations.append(Violation(
                spec.display, number,
                "unrecognized capability operation; use ADDED|MODIFIED|REMOVED|RENAMED C<n>"))
    return violations


def capability_requirements(path: Path) -> set[str]:
    """The `### C<n>` ids a capability file currently defines."""
    if not path.is_file():
        return set()
    return {
        match.group("id")
        for match in (
            CAPABILITY_HEADING.match(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        if match
    }


def check_capability_deltas(
    spec: "Document",
    root: str,
    *,
    expect_applied: bool = False,
    requirement_ids: list[str] | None = None,
) -> list[Violation]:
    """The declared operations must be well formed and must agree with the
    capability files as they stand before this change is archived.

    `expect_applied` flips the ADDED/REMOVED existence checks for callers that
    run after the capability file has already been updated (archive_change.py's
    own gate) rather than before (validate_change.py's `--phase spec/plan/final`
    during propose/apply). MODIFIED/RENAMED targets predate this change either
    way, so their existence check does not depend on `expect_applied`.

    `requirement_ids`, when given, requires every operation to cite at least
    one known `R<n>` in its trailing text (`ADDED C12 (R7) — <effect>`).
    Without this, a capability delta can be pure prose, invisible to
    `check_plan`'s requirement-to-task-to-matrix sweep, and drift undetected
    from the plan and matrix until an expensive reviewer round notices it.
    """
    violations: list[Violation] = []
    entries = capability_deltas(spec, root)

    for number, path, is_new, operations in entries:
        if not operations:
            violations.append(Violation(
                spec.display, number,
                f"{path}: declared with no ADDED/MODIFIED/REMOVED/RENAMED operation"))
            continue

        existing = capability_requirements(Path(path))
        file_present = Path(path).is_file()

        # Before archive a new capability has not been materialized yet. During
        # archive, expect_applied means the file and its declared requirements
        # must exist so archive_change.py can validate their provenance.
        if is_new and file_present and not expect_applied:
            violations.append(Violation(
                spec.display, number,
                f"{path}: marked `(new capability)` but the file already exists"))

        positions = [OPERATION_ORDER.index(op) for _, op, _, _ in operations]
        if positions != sorted(positions):
            violations.append(Violation(
                spec.display, operations[0][0],
                f"{path}: operations out of order; use "
                + ", ".join(OPERATION_ORDER)))

        seen: set[str] = set()
        for op_line, op, identifier, rest in operations:
            if identifier in seen:
                violations.append(Violation(
                    spec.display, op_line, f"{path}: {identifier} appears twice"))
            seen.add(identifier)

            if requirement_ids is not None:
                cited = ids_in(rest, "R")
                if not cited:
                    violations.append(Violation(
                        spec.display, op_line,
                        f"{path}: {op} {identifier} cites no requirement; write "
                        f"e.g. '{op} {identifier} (R7) — <effect>'"))
                for requirement in cited:
                    if requirement not in requirement_ids:
                        violations.append(Violation(
                            spec.display, op_line,
                            f"{path}: {op} {identifier} cites unknown requirement {requirement}"))

            if op == "RENAMED" and not re.search(r"[—–-]\s*\S", re.sub(r"\(R\d+(?:,\s*R\d+)*\)", "", rest)):
                violations.append(Violation(
                    spec.display, op_line,
                    f"{path}: RENAMED {identifier} names no new heading; write "
                    f"'RENAMED {identifier} (R7) — <new heading>'"))

            if is_new and op != "ADDED":
                violations.append(Violation(
                    spec.display, op_line,
                    f"{path}: a new capability admits only ADDED, not {op}"))
                continue
            if not file_present:
                if not is_new:
                    violations.append(Violation(
                        spec.display, op_line,
                        f"{path}: file does not exist; mark it `(new capability)`"))
                continue
            if op == "ADDED" and identifier in existing and not expect_applied:
                violations.append(Violation(
                    spec.display, op_line,
                    f"{path}: ADDED {identifier} already exists in the capability file"))
            if op in ("MODIFIED", "RENAMED") and identifier not in existing:
                violations.append(Violation(
                    spec.display, op_line,
                    f"{path}: {op} {identifier} is not defined in the capability file"))
            if op == "REMOVED" and identifier not in existing and not expect_applied:
                violations.append(Violation(
                    spec.display, op_line,
                    f"{path}: {op} {identifier} is not defined in the capability file"))

    return violations


UNFINISHED = re.compile(r"\b(TBD|TODO)\b")


def check_spec_content(
    spec: "Document",
    requirements: list[tuple[str, int, int]],
    scenarios: list[tuple[str, int, int]],
) -> list[Violation]:
    """Content that has the right shape but no substance."""
    violations: list[Violation] = []

    if "Goal" in spec.sections:
        goal = [(number, line) for number, line in spec.body("Goal") if line.strip()]
        if not goal:
            violations.append(Violation(spec.display, spec.sections["Goal"][0] + 1, "Goal is empty"))
        for number, line in goal:
            if UNFINISHED.search(INLINE_CODE.sub("", line)):
                violations.append(Violation(spec.display, number, "Goal still contains TBD/TODO"))

    for identifier, start, end in requirements:
        for index in range(start, end):
            if UNFINISHED.search(INLINE_CODE.sub("", spec.lines[index])):
                violations.append(Violation(spec.display, index + 1, f"{identifier}: still contains TBD/TODO"))

    for kind, blocks in (("requirement", requirements), ("scenario", scenarios)):
        seen_ids: set[str] = set()
        seen_titles: dict[str, str] = {}
        for identifier, start, _ in blocks:
            if identifier in seen_ids:
                violations.append(Violation(spec.display, start + 1, f"{identifier}: duplicate {kind} id"))
            seen_ids.add(identifier)
            title = re.sub(r"^###\s+\w+\s*[—–:-]?\s*", "", spec.lines[start]).strip()
            key = " ".join(title.casefold().split())
            if key and key in seen_titles:
                violations.append(Violation(
                    spec.display, start + 1,
                    f"{identifier}: {kind} title duplicates {seen_titles[key]} (case/whitespace-insensitive)"))
            seen_titles.setdefault(key, identifier)

    for identifier, start, end in scenarios:
        for label in ("Given", "When", "Then"):
            for index in range(start, end):
                match = re.match(rf"^\s*-\s+\*\*{label}:\*\*(?P<value>.*)$", spec.lines[index])
                if match and not match.group("value").strip():
                    violations.append(Violation(spec.display, index + 1, f"{identifier}: empty {label}"))
    return violations


def check_spec(spec: Document, root: str, *, expect_capabilities_applied: bool = False) -> list[Violation]:
    violations = check_sections(spec, SPEC_SECTIONS)

    requirements = spec.blocks("Requirements", "R")
    scenarios = spec.blocks("Acceptance scenarios", "A")
    requirement_ids = [identifier for identifier, _, _ in requirements]
    scenario_ids = [identifier for identifier, _, _ in scenarios]

    if not requirements:
        violations.append(Violation(spec.display, 1, "no `### R<n>` requirement found"))
    if not scenarios:
        violations.append(Violation(spec.display, 1, "no `### A<n>` acceptance scenario found"))

    for section in SPEC_SECTIONS:
        for number, placeholder in spec.placeholders(section):
            violations.append(
                Violation(spec.display, number, f"unfilled template placeholder: {placeholder}")
            )

    capabilities = " ".join(line for _, line in spec.body("Affected capabilities"))
    if "Affected capabilities" in spec.sections and not re.search(
        rf"{re.escape(root)}/specs/[\w./-]+\.md", capabilities
    ):
        start = spec.sections["Affected capabilities"][0] + 1
        violations.append(
            Violation(
                spec.display,
                start,
                f"no capability file declared under {root}/specs/",
            )
        )

    violations.extend(
        check_capability_deltas(
            spec, root, expect_applied=expect_capabilities_applied, requirement_ids=requirement_ids
        )
    )
    violations.extend(stray_delta_lines(spec, root))
    violations.extend(check_spec_content(spec, requirements, scenarios))

    covered: dict[str, list[str]] = {}
    for identifier, start, end in scenarios:
        block = "\n".join(spec.lines[start:end])
        if not re.search(r"^\s*-\s+\*\*Given:\*\*", block, re.MULTILINE):
            violations.append(Violation(spec.display, start + 1, f"{identifier}: missing Given"))
        if not re.search(r"^\s*-\s+\*\*When:\*\*", block, re.MULTILINE):
            violations.append(Violation(spec.display, start + 1, f"{identifier}: missing When"))
        if not re.search(r"^\s*-\s+\*\*Then:\*\*", block, re.MULTILINE):
            violations.append(Violation(spec.display, start + 1, f"{identifier}: missing Then"))

        covers_match = re.search(r"\*\*Covers:\*\*\s*(?P<value>.+)", block)
        if not covers_match:
            violations.append(
                Violation(spec.display, start + 1, f"{identifier}: missing **Covers:** line")
            )
            continue
        referenced = ids_in(covers_match.group("value"), "R")
        if not referenced:
            violations.append(
                Violation(spec.display, start + 1, f"{identifier}: **Covers:** names no requirement")
            )
        for requirement in referenced:
            if requirement not in requirement_ids:
                violations.append(
                    Violation(
                        spec.display,
                        start + 1,
                        f"{identifier}: covers unknown requirement {requirement}",
                    )
                )
            covered.setdefault(requirement, []).append(identifier)

    table: dict[str, list[str]] = {}
    for number, cells in spec.rows("Requirement coverage"):
        requirement = next(iter(ids_in(cells[0], "R")), None)
        if requirement is None:
            violations.append(
                Violation(spec.display, number, "coverage row without a requirement id")
            )
            continue
        listed = ids_in(cells[1] if len(cells) > 1 else "", "A")
        table[requirement] = listed
        if requirement not in requirement_ids:
            violations.append(
                Violation(spec.display, number, f"coverage row for unknown requirement {requirement}")
            )
        if not listed:
            violations.append(
                Violation(spec.display, number, f"{requirement}: coverage row names no scenario")
            )
        for scenario in listed:
            if scenario not in scenario_ids:
                violations.append(
                    Violation(spec.display, number, f"{requirement}: unknown scenario {scenario}")
                )

    for requirement, start, _ in requirements:
        if requirement not in table:
            violations.append(
                Violation(spec.display, start + 1, f"{requirement}: absent from the coverage table")
            )
        if requirement not in covered:
            violations.append(
                Violation(spec.display, start + 1, f"{requirement}: no acceptance scenario covers it")
            )

    return violations


def task_fields(plan: Document, start: int, end: int) -> dict[str, str]:
    fields: dict[str, str] = {}
    for index in range(start, end):
        if match := FIELD.match(plan.lines[index]):
            fields[match.group("name").strip()] = match.group("value").strip()
    return fields


FILES_PATH = re.compile(r"`(?P<pattern>[^`]+)`")
FILES_SPLIT = re.compile(r"[,;](?![^{]*\})")
FILES_BRACES = re.compile(r"\{([^{}]*)\}")


def _expand_braces(pattern: str) -> list[str]:
    match = FILES_BRACES.search(pattern)
    if match is None:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end() :]
    return [
        expanded
        for option in match.group(1).split(",")
        for expanded in _expand_braces(head + option.strip() + tail)
    ]


def files_patterns(files_field: str) -> tuple[list[str], list[str]]:
    """Split a task's `Files:` into (path patterns, uncheckable items).

    A pattern is every backticked entry that is a path: a literal file, a
    directory (it covers everything below it), or a glob with `*`, `**`, `?`
    and `{a,b}`. Backticked symbols (`Foo::bar`, `run()`) are not paths. A
    comma- or semicolon-separated item without any path is prose that no
    scope check can verify.
    """
    patterns: list[str] = []
    uncheckable: list[str] = []
    for item in FILES_SPLIT.split(files_field):
        item = item.strip()
        if not item:
            continue
        found = [
            match.group("pattern").strip().strip("/")
            for match in FILES_PATH.finditer(item)
        ]
        found = [entry for entry in found if entry and "::" not in entry and "(" not in entry]
        if not found:
            uncheckable.append(item)
            continue
        for entry in found:
            patterns.extend(_expand_braces(entry))
    return patterns, uncheckable


def files_field_hash(files_field: str) -> str | None:
    """Content and presence hash of paths named in a task's `Files:` field.

    Each candidate contributes its literal name plus either its content digest
    or a `missing` sentinel. This detects deletion, rename, and replacement in
    addition to content edits. Returns None only when the field names no
    candidate at all.
    """
    digests: list[str] = []
    for raw in re.split(r"[,\n]", files_field):
        candidate = raw.strip().strip("`")
        if not candidate:
            continue
        path = Path(candidate)
        state = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
        digests.append(f"{candidate}\0{state}")
    if not digests:
        return None
    return hashlib.sha256("\n".join(sorted(digests)).encode("utf-8")).hexdigest()


def check_plan(plan: Document, requirement_ids: list[str]) -> list[Violation]:
    violations = check_sections(plan, PLAN_SECTIONS)

    for section in ("Technical approach", "Files and interfaces", "Tasks", "Requirement-to-check matrix"):
        for number, placeholder in plan.placeholders(section):
            violations.append(
                Violation(plan.display, number, f"unfilled template placeholder: {placeholder}")
            )

    tasks = plan.blocks("Tasks", "T")
    if not MIN_TASKS <= len(tasks) <= MAX_TASKS:
        message = f"{len(tasks)} tasks; a normal change carries {MIN_TASKS} to {MAX_TASKS}"
        if len(tasks) > MAX_TASKS:
            message += "; split the extra work into a separate change"
        violations.append(
            Violation(plan.display, plan.sections.get("Tasks", (0, 0))[0] + 1, message)
        )

    task_requirements: set[str] = set()
    for identifier, start, end in tasks:
        has_checkbox = False
        complete = False
        for index in range(start, end):
            line = plan.lines[index]
            if match := TASK_CHECKBOX.match(line):
                has_checkbox = True
                complete = match.group("mark") in "xX"
        fields = task_fields(plan, start, end)
        if not has_checkbox:
            violations.append(
                Violation(plan.display, start + 1, f"{identifier}: missing `- [ ] Complete` checkbox")
            )
        for field in TASK_FIELDS:
            if field not in fields:
                violations.append(
                    Violation(plan.display, start + 1, f"{identifier}: missing field **{field}:**")
                )
        for field, value in fields.items():
            if field == "Evidence":
                continue
            if PENDING.search(value):
                violations.append(
                    Violation(plan.display, start + 1, f"{identifier}: **{field}:** still Pending")
                )

        owner = fields.get("Owner", "").strip().lower()
        if owner and owner not in OWNERS:
            violations.append(
                Violation(plan.display, start + 1, f"{identifier}: Owner must be {' or '.join(OWNERS)}")
            )
        decision_risk = fields.get("Decision risk", "").strip().lower()
        if decision_risk and decision_risk not in DECISION_RISKS:
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: Decision risk must be one of {', '.join(DECISION_RISKS)}",
                )
            )
        if owner == "controller" and decision_risk == "low":
            justification = fields.get("Controller justification", "").strip()
            if not justification or PENDING.search(justification):
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: Owner is controller with Decision risk low — running "
                        "tools and fixing what they find is worker's job (subagent-routing.md's "
                        "Routing policy). Add a **Controller justification:** line naming the "
                        "specific exception, or change Owner to worker.",
                    )
                )
        if owner == "worker" and not complete and "Files" in fields:
            _, uncheckable = files_patterns(fields["Files"])
            if uncheckable:
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: a worker task's Files must name backticked paths, "
                        "directories, or globs that check-scope can verify; not a path: "
                        + "; ".join(uncheckable),
                    )
                )
        verification_owner = fields.get("Verification owner", "").strip().lower()
        if verification_owner and verification_owner not in VERIFICATION_OWNERS:
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: Verification owner must be one of {', '.join(VERIFICATION_OWNERS)}",
                )
            )

        surface = fields.get("Surface", "").strip().lower()
        if surface and surface not in SURFACES:
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: Surface must be one of {', '.join(SURFACES)}",
                )
            )
        if surface in ("ui", "mixed"):
            delivery = fields.get("Delivery verification", "").lower()
            if any(label not in delivery for label in ("build", "typecheck", "browser")):
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: UI delivery verification must name build, typecheck, and browser checks",
                    )
                )

        referenced = ids_in(fields.get("Requirements", ""), "R")
        if not referenced:
            violations.append(
                Violation(plan.display, start + 1, f"{identifier}: Requirements names no requirement")
            )
        for requirement in referenced:
            if requirement_ids and requirement not in requirement_ids:
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: unknown requirement {requirement}",
                    )
                )
            task_requirements.add(requirement)

    matrix: set[str] = set()
    for number, cells in plan.rows("Requirement-to-check matrix"):
        requirement = next(iter(ids_in(cells[0], "R")), None)
        if requirement is None:
            violations.append(Violation(plan.display, number, "matrix row without a requirement id"))
            continue
        matrix.add(requirement)
        check = cells[2] if len(cells) > 2 else ""
        if not check or PENDING.search(check):
            violations.append(
                Violation(plan.display, number, f"{requirement}: matrix has no exact check")
            )

    for requirement in requirement_ids:
        if requirement not in task_requirements:
            violations.append(Violation(plan.display, 1, f"{requirement}: no task implements it"))
        if requirement not in matrix:
            violations.append(
                Violation(plan.display, 1, f"{requirement}: absent from the requirement-to-check matrix")
            )

    return violations


def check_review_round_cap(plan: Document, *, limit: int = ROUND_CAP) -> list[Violation]:
    """Refuse to dispatch a reviewer for the `limit`-th new-diff round.

    Counts only `### G<n>` blocks under `Review result` with `Type: initial`
    — the already-bounded single `re-review` after fixes never counts. A
    plan with no `### G<n>` blocks at all (every change created before this
    mechanism existed) is a silent no-op, not a violation. Checked from
    `check_pre_review`, i.e. before the next reviewer is dispatched, not only
    at `--phase final` after the fact.
    """
    rounds = plan.blocks("Review result", "G")
    if not rounds:
        return []
    new_diff_rounds = sum(
        1
        for _, start, end in rounds
        if task_fields(plan, start, end).get("Type", "").strip().lower() == "initial"
    )
    if new_diff_rounds < limit:
        return []
    _, last_start, last_end = rounds[-1]
    override = task_fields(plan, last_start, last_end).get("Round cap override", "").strip()
    if override and not PENDING.search(override):
        return []
    return [
        Violation(
            plan.display,
            1,
            f"Review result: {new_diff_rounds} new-diff review rounds recorded; add a "
            f"**Round cap override:** reason to the latest round, or stop and ask whether "
            f"to consolidate or split the change",
        )
    ]


def check_review_round_structure(plan: Document) -> list[Violation]:
    """Validate round types and the single targeted re-review allowance."""
    violations: list[Violation] = []
    may_re_review = False
    for identifier, start, end in plan.blocks("Review result", "G"):
        round_type = task_fields(plan, start, end).get("Type", "").strip().lower()
        if round_type not in ("initial", "re-review"):
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: Type must be initial or re-review",
                )
            )
            may_re_review = False
            continue
        if round_type == "initial":
            may_re_review = True
            continue
        if not may_re_review:
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: at most one re-review may follow an initial round",
                )
            )
        may_re_review = False

    return violations


def check_review_readiness(plan: Document) -> list[Violation]:
    """Require completed, current task evidence for review and completion."""
    violations: list[Violation] = []
    for identifier, start, end in plan.blocks("Tasks", "T"):
        marks = [
            match.group("mark")
            for index in range(start, end)
            if (match := TASK_CHECKBOX.match(plan.lines[index]))
        ]
        if any(mark == " " for mark in marks):
            violations.append(Violation(plan.display, start + 1, f"{identifier}: not complete"))

        fields = task_fields(plan, start, end)
        evidence_raw = fields.get("Evidence", "").strip()
        if (
            not evidence_raw
            or PENDING.search(evidence_raw)
            or PLACEHOLDER_EVIDENCE in evidence_raw.lower()
        ):
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: Evidence is missing or still the template placeholder; "
                    f"record the command and result",
                )
            )

        evidence_hash = fields.get("Evidence hash", "").strip()
        if evidence_hash and not PENDING.search(evidence_hash):
            current_hash = files_field_hash(fields.get("Files", ""))
            if current_hash is not None and current_hash != evidence_hash:
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: Evidence predates a later change to one of its Files; "
                        f"re-verify and re-record Evidence and Evidence hash",
                    )
                )

        surface = fields.get("Surface", "").strip().lower()
        if surface in ("ui", "mixed"):
            evidence = evidence_raw.lower()
            browser = re.search(r"browser:\s*url:\s*\S+.*state:\s*\S+", evidence)
            build = re.search(r"build:\s*pass(?:\s|$)", evidence)
            typecheck = re.search(r"typecheck:\s*pass(?:\s|$)", evidence)
            if not build or not typecheck or not browser:
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: UI evidence must record final Build: PASS, Typecheck: PASS, and Browser: URL/state results",
                    )
                )
    return violations


RUNTIMES = ("claude", "codex", "opencode")
HANDOFF_FIELD = re.compile(r"^\*\*(?P<name>[^*]+):\*\*\s*(?P<value>.*?)\s*$")


def _runtime(value: str) -> str | None:
    runtime = value.split("/", 1)[0].strip().strip("`").lower()
    return runtime if runtime in RUNTIMES else None


def handoff_fields(plan: Document) -> dict[str, str]:
    fields: dict[str, str] = {}
    for _, line in plan.body("Model handoff"):
        if match := HANDOFF_FIELD.match(line):
            fields[match.group("name").strip()] = match.group("value")
    return fields


def check_reviewer_independence(plan: Document) -> list[Violation]:
    """A reviewer on the worker's runtime needs a recorded Independence waiver.

    Applies only when the plan delegates at least one task to a worker and both
    runtimes are recorded (`runners.md`). A round's own `Reviewer runtime`
    overrides the one in `## Model handoff`.
    """
    has_worker = any(
        task_fields(plan, start, end).get("Owner", "").strip().lower() == "worker"
        for _, start, end in plan.blocks("Tasks", "T")
    )
    handoff = handoff_fields(plan)
    worker = _runtime(handoff.get("Worker runtime", ""))
    if not has_worker or worker is None:
        return []
    violations: list[Violation] = []
    for identifier, start, end in plan.blocks("Review result", "G"):
        fields = task_fields(plan, start, end)
        reviewer = _runtime(fields.get("Reviewer runtime", "")) or _runtime(handoff.get("Reviewer runtime", ""))
        if reviewer != worker:
            continue
        waiver = fields.get("Independence waiver", "").strip()
        if not waiver or PENDING.search(waiver):
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: reviewer runs on the worker's runtime ({worker}); record "
                    "**Independence waiver:** <reason> or review on another runtime (runners.md)",
                )
            )
    return violations


def check_pre_review(plan: Document) -> list[Violation]:
    """Validate readiness and refuse only a new reviewer dispatch past the cap."""
    return (
        check_review_readiness(plan)
        + check_review_round_structure(plan)
        + check_review_round_cap(plan)
        + check_reviewer_independence(plan)
    )


def review_manifest_hash(manifest: dict[str, str]) -> str:
    ordered = "\n".join(f"{path}:{digest}" for path, digest in sorted(manifest.items()))
    return "sha256:" + hashlib.sha256(ordered.encode("utf-8")).hexdigest()


def latest_review_round(
    plan: Document,
) -> tuple[str, dict[str, str], dict[str, str] | None] | None:
    rounds = plan.blocks("Review result", "G")
    if not rounds:
        return None
    identifier, start, end = rounds[-1]
    fields = task_fields(plan, start, end)
    block_text = "\n".join(plan.lines[start:end])
    manifest: dict[str, str] | None = None
    if GATE_JSON_FENCE in block_text:
        fenced = block_text.split(GATE_JSON_FENCE, 1)[1]
        payload_text = fenced.split("```", 1)[0]
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and all(
            isinstance(path, str) and isinstance(digest, str)
            for path, digest in payload.items()
        ):
            manifest = payload
    return identifier, fields, manifest


def check_final(spec: Document, plan: Document) -> list[Violation]:
    violations: list[Violation] = []
    violations += check_review_readiness(plan)
    violations += check_review_round_structure(plan)

    archive_summary = "\n".join(line for _, line in plan.body("Archive summary")).strip()
    if not archive_summary or PENDING.search(archive_summary):
        violations.append(
            Violation(plan.display, 1, "Archive summary: missing final durable outcome")
        )

    for number, line in plan.body("Final verification"):
        match = CHECKBOX.match(line.strip())
        if match and match.group("mark") == " ":
            violations.append(
                Violation(plan.display, number, f"final verification unchecked: {match.group('label')}")
            )

    review = "\n".join(line for _, line in plan.body("Review result"))
    result_match = re.search(r"\*\*Result:\*\*\s*(?P<value>.+)", review)
    result = None
    if not result_match:
        violations.append(Violation(plan.display, 1, "Review result: missing **Result:**"))
    else:
        result = result_match.group("value").strip().upper()
    if result is not None and result != "PASS":
        violations.append(
            Violation(plan.display, 1, f"Review result is {result_match.group('value').strip()}, not PASS")
        )

    latest = latest_review_round(plan)
    if latest is not None:
        round_id, fields, manifest = latest
        outcome = fields.get("Outcome", "").strip().upper()
        if outcome != "PASS":
            violations.append(
                Violation(plan.display, 1, f"Review result: latest round {round_id} outcome is {outcome or 'missing'}, not PASS")
            )
        if result is not None and outcome and result != outcome:
            violations.append(
                Violation(plan.display, 1, f"Review result: header Result {result} disagrees with latest round {round_id} Outcome {outcome}")
            )
        if manifest is None:
            violations.append(
                Violation(plan.display, 1, f"Review result: latest round {round_id} has no valid manifest")
            )
        else:
            recorded = fields.get("Snapshot", "").strip()
            expected = review_manifest_hash(manifest)
            if recorded != expected:
                violations.append(
                    Violation(plan.display, 1, f"Review result: latest round {round_id} Snapshot does not match its manifest hash")
                )

    requirement_ids = {identifier for identifier, _, _ in spec.blocks("Requirements", "R")}
    task_ids = {identifier for identifier, _, _ in plan.blocks("Tasks", "T")}
    for label, expected, prefix in (
        ("Reviewed requirements", requirement_ids, "R"),
        ("Reviewed tasks", task_ids, "T"),
    ):
        match = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(?P<value>.+)", review)
        if not match:
            violations.append(Violation(plan.display, 1, f"Review result: missing **{label}:**"))
            continue
        actual = set(ids_in(match.group("value"), prefix))
        if actual != expected:
            missing = ", ".join(sorted(expected - actual)) or "None"
            extra = ", ".join(sorted(actual - expected)) or "None"
            violations.append(
                Violation(
                    plan.display,
                    1,
                    f"Review result: {label} mismatch (missing: {missing}; extra: {extra})",
                )
            )

    evidence = plan.body("Completion evidence")
    evidence_text = "\n".join(line for _, line in evidence)
    for label in ("Commands:", "Requirement mapping:", "Execution tokens:", "Review rounds:"):
        if label not in evidence_text:
            violations.append(
                Violation(plan.display, 1, f"Completion evidence: missing `{label}` block")
            )
    for number, line in evidence:
        if PENDING.search(line):
            violations.append(
                Violation(plan.display, number, f"Completion evidence still Pending: {line.strip()}")
            )

    for section in ("Model handoff", "Plan approval"):
        for number, line in plan.body(section):
            if PENDING.search(line):
                violations.append(
                    Violation(plan.display, number, f"{section} still Pending: {line.strip()}")
                )

    for number, cells in plan.rows("Requirement-to-check matrix"):
        status = cells[3] if len(cells) > 3 else ""
        if PENDING.search(status) or not status:
            violations.append(Violation(plan.display, number, "matrix row has no final status"))

    for document in (spec, plan):
        for section in document.sections:
            for number, placeholder in document.placeholders(section):
                violations.append(
                    Violation(document.display, number, f"unfilled placeholder: {placeholder}")
                )

    return violations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate spec.md and plan.md for a Specadoc change."
    )
    parser.add_argument("change_slug", nargs="?")
    parser.add_argument("--phase", choices=PHASES)
    parser.add_argument(
        "--root",
        help="Artifact root relative to the current repository (default: resolved, see specadoc_root.py)",
    )
    parser.add_argument("--json", action="store_true", help="Emit violations as JSON")
    parser.add_argument(
        "--files-hash",
        metavar="FIELD",
        help=(
            "Print the content hash for a task's Files: field value (for recording "
            "Evidence hash) and exit. Ignores change_slug/--phase."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.files_hash is not None:
        print(files_field_hash(args.files_hash) or "unresolved")
        return 0

    if not args.change_slug or not args.phase:
        print("error: change_slug and --phase are required unless --files-hash is used", file=sys.stderr)
        return 2

    try:
        choice = resolve_root(args.root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if warning := legacy_warning(choice):
        print(warning, file=sys.stderr)
    root = choice.path
    change = Path(root) / args.change_slug

    if not change.is_dir():
        print(f"error: no change directory: {change}", file=sys.stderr)
        return 2

    documents: dict[str, Document] = {}
    for name in ("spec.md", "plan.md"):
        path = change / name
        if not path.is_file():
            print(f"error: missing artifact: {path}", file=sys.stderr)
            return 2
        documents[name] = Document(path, str(path))

    spec = documents["spec.md"]
    plan = documents["plan.md"]
    requirement_ids = [identifier for identifier, _, _ in spec.blocks("Requirements", "R")]

    violations = check_spec(spec, root, expect_capabilities_applied=args.phase == "final")
    if args.phase in ("plan", "pre-review", "final"):
        violations += check_plan(plan, requirement_ids)
    if args.phase == "pre-review":
        violations += check_pre_review(plan)
        from review_snapshot import ScopeError, SnapshotError, compute as compute_snapshot

        try:
            compute_snapshot(change, Path.cwd())
        except (ScopeError, SnapshotError) as exc:
            violations.append(
                Violation(plan.display, 1, f"Review scope cannot produce a snapshot: {exc}")
            )
    if args.phase == "final":
        violations += check_final(spec, plan)
        from review_snapshot import verify_latest

        violations += [
            Violation(plan.display, 1, message)
            for message in verify_latest(plan, change, Path.cwd())
        ]

    cross_violations, cross_warnings = cross_change_findings(spec, root, args.change_slug)
    violations += cross_violations

    violations.sort(key=lambda violation: (violation.file, violation.line))

    for warning_text in cross_warnings:
        print(f"warning: {warning_text}", file=sys.stderr)

    if args.json:
        print(
            json.dumps(
                {
                    "phase": args.phase,
                    "change": args.change_slug,
                    "violations": [
                        {"file": v.file, "line": v.line, "message": v.message} for v in violations
                    ],
                    "warnings": cross_warnings,
                },
                indent=2,
            )
        )
    else:
        for violation in violations:
            print(violation.render())
        if violations:
            print(f"{len(violations)} violation(s) in phase {args.phase}", file=sys.stderr)
        else:
            print(f"{args.change_slug}: phase {args.phase} passes structural validation")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
