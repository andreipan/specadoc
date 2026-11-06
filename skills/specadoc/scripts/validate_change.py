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
import subprocess
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
    "Handoff",
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

WORKER_ONLY_FIELDS = ("Verification owner",)
PLAN_SIZE_WARNING = 32 * 1024
HANDOFF_SECTION_WARNING = 2 * 1024
# `accept` executes Verification, so it holds only exact commands.
VERIFICATION_COMMANDS = re.compile(r"\s*`[^`\n]+`(?:\s*;\s*`[^`\n]+`)*\s*")

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

    def __init__(self, path: Path, display: str, *, text: str | None = None) -> None:
        self.path = path
        self.display = display
        self.lines = (path.read_text(encoding="utf-8") if text is None else text).splitlines()
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
        if section in LEGACY_SECTION_ALIASES.values():
            return found
        for number, line in self.body(section):
            if "specadoc:ignore-placeholder" in line or LEGACY_FIELD.match(line):
                continue
            bare = DISCLOSURE_TAG.sub("", INLINE_CODE.sub("", line))
            match = PLACEHOLDER.search(bare)
            if match:
                found.append((number, match.group(0)))
        return found


def ids_in(text: str, prefix: str) -> list[str]:
    return re.findall(rf"\b({prefix}\d+)\b", text)


def expand_ids(text: str, prefix: str) -> list[str]:
    """Like ids_in, but `R1–R9` / `R1-R9` / `R1..R9` ranges list every id between."""
    found: list[str] = []
    for match in re.finditer(rf"\b{prefix}(\d+)(?:\s*(?:-|–|—|\.\.)\s*{prefix}?(\d+))?\b", text):
        first, last = int(match[1]), int(match[2] or match[1])
        found.extend(f"{prefix}{n}" for n in range(first, max(first, last) + 1))
    return list(dict.fromkeys(found))


LEGACY_SECTION_ALIASES = {"Handoff": "Model handoff"}
# Fields of the removed model-level fixation; old plans may still carry them unfilled.
LEGACY_FIELD = re.compile(
    r"^\s*(?:-\s*)?\*\*(?:Owner level|Approved profile|Reviewer runtime|Independence waiver):\*\*"
)


def check_sections(document: Document, required: tuple[str, ...]) -> list[Violation]:
    return [
        Violation(document.display, 1, f"missing required section: ## {name}")
        for name in required
        if name not in document.sections
        and LEGACY_SECTION_ALIASES.get(name) not in document.sections
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
    baseline: dict | None = None,
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

        state = (baseline or {}).get(path)
        existing = set(state["requirements"]) if state is not None and not expect_applied else capability_requirements(Path(path))
        file_present = state["present"] if state is not None and not expect_applied else Path(path).is_file()

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


def check_spec(spec: Document, root: str, *, expect_capabilities_applied: bool = False,
               capability_baseline: dict | None = None) -> list[Violation]:
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
            spec, root, expect_applied=expect_capabilities_applied, requirement_ids=requirement_ids,
            baseline=capability_baseline
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


# Path and command fields whose indented continuation lines are part of the
# value: a wrapped `Files:` must not silently lose its second line (3.7, 3.8).
CONTINUED_FIELDS = frozenset({"Files", "Derived files", "Verification", "Verification inputs",
                              "Depends on", "Scope amendment"})


def task_fields(plan: Document, start: int, end: int) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    for index in range(start, end):
        line = plan.lines[index]
        if match := FIELD.match(line):
            current = match.group("name").strip()
            fields[current] = match.group("value").strip()
        elif current in CONTINUED_FIELDS and line.startswith((" ", "\t")) and line.strip():
            fields[current] = f"{fields[current]} {line.strip()}".strip()
        else:
            current = None
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
            match.group("pattern").strip().rstrip("/")
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
    digests = [f"{path}\0{state}" for path, state in files_field_digests(files_field).items()]
    if not digests:
        return None
    return hashlib.sha256("\n".join(sorted(digests)).encode("utf-8")).hexdigest()


def files_field_digests(files_field: str, *, repository_only: bool = False) -> dict[str, str]:
    """Content/presence digests; directories and globs include their actual children.

    Keep literal absolute paths for the legacy --files-hash utility. Apply tasks
    validate repository-relative patterns separately before using this helper.
    """
    import glob
    def check(path: Path) -> None:
        if repository_only and not path.resolve().is_relative_to(Path.cwd().resolve()):
            raise ValueError(f"verification path leaves repository: {path}")
    digests: dict[str, str] = {}
    candidates, invalid = files_patterns(files_field)
    if "`" not in files_field:
        # Legacy --files-hash accepts bare paths, including absolute ones.
        candidates = [path for raw in FILES_SPLIT.split(files_field) if raw.strip()
                      for path in _expand_braces(raw.strip())]
        invalid = []
    if invalid:
        raise ValueError("Files items are not paths: " + ", ".join(invalid))
    for candidate in candidates:
        # Brackets are literal route segments, not character classes. Escape them
        # even in patterns such as app/[slug]/*.tsx; only * and ? are wildcards.
        glob_pattern = "".join(glob.escape(char) if char in "[]" else char for char in candidate)
        matches = sorted(glob.glob(glob_pattern, recursive=True)) if any(c in candidate for c in "*?") else [candidate]
        if not matches:
            digests[candidate] = "missing"
        for match in matches:
            path = Path(match)
            check(path)
            if path.is_dir():
                digests[path.as_posix()] = "directory"
                for child in sorted(path.rglob("*")):
                    check(child)
                    if ".git" not in child.parts and child.is_file():
                        digests[child.as_posix()] = hashlib.sha256(child.read_bytes()).hexdigest()
            else:
                digests[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
    return digests


# Task states whose local evidence is settled. `external-pending` passed its local
# Verification and awaits a run the controller may not execute (integration on
# a shared database, a manual check); review may open, `final` may not.
SETTLED_STATES = ("accepted", "external-pending")
NO_VALUE = re.compile(r"(?:none|n/a|-)(?:\b|;|$)", re.I)


def external_verification(fields: dict[str, str]) -> str | None:
    """The task's `External verification:` description, or None."""
    value = " ".join(fields.get("External verification", "").split())
    return None if not value or NO_VALUE.match(value) else value


def evidence_is_current(runs: Path, task: str, files_field: str) -> bool | None:
    """Whether a task's accepted evidence still covers its Files.

    A file may have changed since, when a later accepted task recorded exactly
    its current content (overlapping tasks). None when the task has no
    per-file acceptance record (older plans fall back to Evidence hash).
    """
    return evidence_staleness(runs, task, files_field)[0]


def evidence_staleness(runs: Path, task: str, files_field: str) -> tuple[bool | None, str]:
    """`evidence_is_current` plus the reason when the evidence is stale."""
    try:
        record = json.loads((runs / f"{task}-baseline.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, ""
    recorded = (record.get("verification") or {}).get("files") if isinstance(record, dict) else None
    if not isinstance(recorded, dict) or record.get("state") not in SETTLED_STATES:
        return None, ""
    inputs = (record.get("verification") or {}).get("inputs")
    if not isinstance(inputs, dict) or inputs.get("version") != 1:
        # Older acceptance records must be reverified, never upgraded by assumption.
        return False, "the acceptance record predates input manifests"
    from verification_inputs import capture, environment_drift
    plan = Document(runs.parent / "plan.md", "plan.md")
    fields = next((task_fields(plan, start, end) for identifier, start, end in plan.blocks("Tasks", "T")
                   if identifier == task), {})
    if " ".join(fields.get("Verification", "").split()) != record.get("frozen", {}).get("verification"):
        return False, "Verification changed since acceptance"
    root = runs.parent.parent.resolve().relative_to(Path.cwd().resolve()).as_posix()
    current_inputs = capture(fields, root)
    current = current_inputs["owned"]
    if current_inputs.get("declared") != inputs.get("declared"):
        return False, "declared Verification inputs changed"
    if current_inputs.get("python") != inputs.get("python"):
        return False, "the Python interpreter changed"
    if current_inputs.get("environment_hash") != inputs.get("environment_hash"):
        names = ", ".join(environment_drift(inputs, current_inputs))
        return False, (f"environment changed: {names}; list only verifier-relevant variables in "
                       ".specadoc.json verification.environment")
    if set(current) != set(recorded):
        return False, "the set of owned files changed"
    owned: dict[str, set[str]] = {}
    for other in runs.glob("T*-baseline.json"):
        if other.name == f"{task}-baseline.json":
            continue
        try:
            state = json.loads(other.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(state, dict) and state.get("state") in SETTLED_STATES:
            for path, value in ((state.get("verification") or {}).get("files") or {}).items():
                owned.setdefault(path, set()).add(value)
    drifted = sorted(path for path in current
                     if current[path] != recorded[path] and current[path] not in owned.get(path, ()))
    if drifted:
        return False, "owned files changed: " + _first(drifted)
    previous_checks = inputs.get("checks", {})
    current_checks = current_inputs["checks"]
    # Later accepted work may independently verify overlapping inputs. Other
    # config/source/context drift must invalidate dependency evidence as well.
    changed = sorted(path for path in previous_checks.keys() | current_checks.keys()
                     if current_checks.get(path, "missing") != previous_checks.get(path, "missing")
                     and current_checks.get(path, "missing") not in owned.get(path, ()))
    if changed:
        return False, "verification inputs changed: " + _first(changed)
    return True, ""


def _first(paths: list[str], limit: int = 5) -> str:
    return ", ".join(paths[:limit]) + (f" and {len(paths) - limit} more" if len(paths) > limit else "")


def repeated_verification_warnings(plan: Document) -> list[str]:
    """The same Verification in three or more worker tasks is usually the full suite."""
    by_command: dict[str, list[str]] = {}
    for identifier, start, end in plan.blocks("Tasks", "T"):
        fields = task_fields(plan, start, end)
        if fields.get("Owner", "").strip().lower() != "worker":
            continue
        command = " ".join(fields.get("Verification", "").split())
        if command and not PENDING.search(command):
            by_command.setdefault(command, []).append(identifier)
    return [f"{', '.join(tasks)} share Verification {command}: narrow worker checks to the task's "
            "focused tests; the controller runs the full suite once in Final verification"
            for command, tasks in by_command.items() if len(tasks) >= 3]


def controller_routing_warnings(plan: Document) -> list[str]:
    """Open controller tasks a worker could take; the controller's context is the scarce budget."""
    eligible = []
    for identifier, start, end in plan.blocks("Tasks", "T"):
        fields = task_fields(plan, start, end)
        marks = [m["mark"] for line in plan.lines[start:end] if (m := TASK_CHECKBOX.match(line))]
        justification = " ".join(fields.get("Controller justification", "").split())
        if (fields.get("Owner", "").strip().lower() != "controller" or (marks and " " not in marks)
                or (justification and not NO_VALUE.match(justification))
                or fields.get("Decision risk", "").strip().lower() != "low"
                or not NO_VALUE.match(fields.get("Open decisions", "None").strip() or "None")):
            continue
        if not VERIFICATION_COMMANDS.fullmatch(fields.get("Verification", "")):
            continue
        paths, uncheckable = files_patterns(fields.get("Files", ""))
        if paths and not uncheckable:
            eligible.append(identifier)
    if not eligible:
        return []
    return [f"{', '.join(eligible)}: low decision risk with exact Files and Verification; set Owner: worker, "
            "or record a Controller justification (open material decision, edit smaller than its brief)"]


def plan_size_warnings(plan: Document) -> list[str]:
    """plan.md is re-read at every task and review; size multiplies its cost."""
    warnings = []
    handoff = len("\n".join(line for _, line in plan.body("Handoff")).encode("utf-8"))
    if handoff > HANDOFF_SECTION_WARNING:
        warnings.append(f"plan.md Handoff is {handoff} bytes (> {HANDOFF_SECTION_WARNING}): keep the checkpoint "
                        "and one Continue line; session notes go to runs/handoff.md via specadoc_step.py handoff")
    size = len("\n".join(plan.lines).encode("utf-8"))
    if size > PLAN_SIZE_WARNING:
        def weight(start: int, end: int) -> int:
            return len("\n".join(plan.lines[start:end]).encode("utf-8"))
        # Name what to trim: in 3.8 the plan was 55 KB at approval, before any evidence.
        parts = [(weight(start, end), name) for name, (start, end) in plan.sections.items() if name != "Tasks"]
        parts += [(weight(start, end), identifier) for identifier, start, end in plan.blocks("Tasks", "T")]
        largest = ", ".join(f"{name} {bytes_} B" for bytes_, name in sorted(parts, reverse=True)[:4])
        warnings.append(f"plan.md is {size} bytes (> {PLAN_SIZE_WARNING}): keep only decisions, tasks, "
                        "one-line evidence and current state; move bulky evidence to research.md or drop it. "
                        f"Largest: {largest}")
    return warnings


ENV_PREFIX = re.compile(r"`\s*(?:env\b|[A-Za-z_][A-Za-z0-9_]*=)")


def verification_env_warnings(plan: Document) -> list[str]:
    """A runtime setting frozen into Verification diverges between sessions and sandboxes."""
    return [f"{identifier}: Verification sets an environment variable; a host or sandbox setting belongs "
            "in the runtime (php.ini, harness), not in the frozen command"
            for identifier, start, end in plan.blocks("Tasks", "T")
            if ENV_PREFIX.search(task_fields(plan, start, end).get("Verification", ""))]


def check_plan(plan: Document, requirement_ids: list[str]) -> list[Violation]:
    violations = check_sections(plan, PLAN_SECTIONS)

    for section in ("Technical approach", "Files and interfaces", "Tasks", "Requirement-to-check matrix"):
        for number, placeholder in plan.placeholders(section):
            violations.append(
                Violation(plan.display, number, f"unfilled template placeholder: {placeholder}")
            )

    tasks = plan.blocks("Tasks", "T")
    if not tasks:
        violations.append(Violation(plan.display, 1, "Tasks: at least one independently verifiable outcome is required"))

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
            if field in WORKER_ONLY_FIELDS and fields.get("Owner", "").strip().lower() != "worker":
                continue
            if field not in fields:
                violations.append(
                    Violation(plan.display, start + 1, f"{identifier}: missing field **{field}:**")
                )
        for field, value in fields.items():
            if field in ("Evidence", "Evidence hash"):
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
        verification = fields.get("Verification", "")
        if (not complete and verification.strip() and not PENDING.search(verification)
                and not re.search(r"<[^>]+>", verification) and not VERIFICATION_COMMANDS.fullmatch(verification)):
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: Verification must be exact backticked commands separated by semicolons, "
                    "because accept executes them; move manual or reserved checks to External verification "
                    "and conditions to Done when",
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

    from design_gate import check_inventory
    violations += check_inventory(plan)
    return violations


def check_review_round_cap(plan: Document, *, limit: int = ROUND_CAP, next_type: str = "initial",
                           decision: str | None = None) -> list[Violation]:
    """Refuse to dispatch a reviewer for the `limit`-th new-diff round.

    Counts only `### G<n>` blocks under `Review result` with `Type: initial`
    — the already-bounded single `re-review` after fixes never counts. A
    plan with no `### G<n>` blocks at all (every change created before this
    mechanism existed) is a silent no-op, not a violation. Checked from
    `check_pre_review`, i.e. before the next reviewer is dispatched, not only
    at `--phase final` after the fact.
    """
    rounds = plan.blocks("Review result", "G")
    if next_type == "re-review":
        return []
    if decision and not PENDING.search(decision) and decision.strip().lower() not in ("n/a", "none", "-"):
        return []
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
    fields = task_fields(plan, last_start, last_end)
    override = fields.get("Round cap override", "").strip()
    if override and not PENDING.search(override) and not fields.get("Decision used"):
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


def review_policy_hash(plan: Document) -> str:
    """Plan approval only, not mutable handoff or progress prose."""
    payload = {"approval": [line for _, line in plan.body("Plan approval")]}
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def documentation_followup(plan: Document, current: dict, previous: dict, previous_id: str) -> bool:
    digest = current.get("Snapshot", "").strip()
    policy = current.get("Policy snapshot", "").strip()
    return (current.get("Scope", "").strip().lower() == "documentation-only"
            and previous.get("Scope", "").strip().lower() != "documentation-only"
            and previous.get("Type", "").strip().lower() == "re-review"
            and previous.get("Outcome", "").strip().upper() == "FAIL"
            and previous.get("Remaining findings", "").strip().lower() == "documentation-only"
            and current.get("Previous", "").strip() == previous_id
            and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", digest))
            and digest == previous.get("Snapshot", "").strip()
            and policy == previous.get("Policy snapshot", "").strip() == review_policy_hash(plan))


def check_review_round_structure(plan: Document) -> list[Violation]:
    """One targeted re-review, then at most one guarded documentation follow-up."""
    violations: list[Violation] = []
    may_re_review = False
    previous, previous_id = {}, ""
    for identifier, start, end in plan.blocks("Review result", "G"):
        fields = task_fields(plan, start, end)
        round_type = fields.get("Type", "").strip().lower()
        if round_type not in ("initial", "re-review"):
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: Type must be initial or re-review",
                )
            )
            may_re_review = False
            previous, previous_id = {}, ""
            continue
        if round_type == "initial":
            if previous and fields.get("Reason", "").strip().lower() == "corrections":
                violations.append(Violation(plan.display, start + 1,
                    f"{identifier}: corrections remain a re-review; do not relabel to bypass the round limit"))
            may_re_review = True
            previous, previous_id = fields, identifier
            continue
        decision = fields.get("Review decision", "").strip()
        explicit = (bool(decision) and not PENDING.search(decision) and decision.lower() not in ("n/a", "none", "-")
                    and fields.get("Previous", "").strip() == previous_id)
        # One uncapped review of executable MINOR fixes after a MINOR-only PASS; never chained.
        minor_fixes = (fields.get("Reason", "").strip().lower() == "minor-fixes"
                       and previous.get("Reason", "").strip().lower() != "minor-fixes"
                       and fields.get("Previous", "").strip() == previous_id
                       and minor_only_pass(plan, previous_id))
        if minor_fixes:
            may_re_review = False
            previous, previous_id = fields, identifier
            continue
        if not may_re_review and not explicit and not documentation_followup(plan, fields, previous, previous_id):
            violations.append(
                Violation(
                    plan.display,
                    start + 1,
                    f"{identifier}: at most one re-review may follow an initial round; a documentation-only follow-up needs unchanged Snapshot/Policy snapshot and prior documentation-only FAIL",
                )
            )
        may_re_review = False
        previous, previous_id = fields, identifier

    return violations


def check_review_readiness(plan: Document, *, allow_external_pending: bool = False) -> list[Violation]:
    """Require completed, current task evidence for review and completion.

    Review may open while a task awaits only its external verification; the
    final gate requires that result.
    """
    violations: list[Violation] = []
    for identifier, start, end in plan.blocks("Tasks", "T"):
        state_path = plan.path.parent / "runs" / f"{identifier}-baseline.json"
        awaiting_external = False
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                current = state.get("state")
                awaiting_external = current == "external-pending"
                if state.get("schema") == "specadoc.task/v2" and awaiting_external and not allow_external_pending:
                    violations.append(Violation(plan.display, start + 1,
                        f"{identifier}: external verification result missing; record it with "
                        f"specadoc_step.py external-result"))
                elif state.get("schema") == "specadoc.task/v2" and current not in SETTLED_STATES:
                    violations.append(Violation(plan.display, start + 1,
                        f"{identifier}: task has not reached report-aware ACCEPTED; settle its result before review"))
                elif (state.get("schema") == "specadoc.task/v2" and current == "accepted"
                      and external_verification(task_fields(plan, start, end)) and not allow_external_pending):
                    # An external PASS covers only the content it ran on (amend can keep an old PASS).
                    external = state.get("external") or {}
                    verified = (state.get("verification") or {}).get("files_hash")
                    if external.get("outcome") != "PASS" or external.get("files_hash") != verified:
                        violations.append(Violation(plan.display, start + 1,
                            f"{identifier}: no external PASS recorded for the accepted content; rerun "
                            "specadoc_step.py accept (it becomes external-pending), run the external "
                            "verification, then record it with external-result"))
            except (OSError, ValueError, TypeError, AttributeError):
                violations.append(Violation(plan.display, start + 1, f"{identifier}: task state is unreadable"))
        marks = [
            match.group("mark")
            for index in range(start, end)
            if (match := TASK_CHECKBOX.match(plan.lines[index]))
        ]
        if any(mark == " " for mark in marks) and not awaiting_external:
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
        current_evidence, stale_reason = evidence_staleness(plan.path.parent / "runs", identifier,
                                                            fields.get("Files", ""))
        if current_evidence is False or (evidence_hash and not PENDING.search(evidence_hash) and current_evidence is not True):
            current_hash = files_field_hash(fields.get("Files", ""))
            if current_evidence is False or (current_hash is not None and current_hash != evidence_hash):
                change = f" ({stale_reason})" if stale_reason else " to one of its Files"
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: Evidence predates a later change{change}; "
                        f"re-verify with specadoc_step.py refresh",
                    )
                )

        surface = fields.get("Surface", "").strip().lower()
        if surface in ("ui", "mixed"):
            evidence = evidence_raw.lower()
            browser = re.search(r"browser:\s*url:\s*\S+.*state:\s*\S+", evidence)
            build = re.search(r"build:\s*pass(?=\s|[.;,)]|$)", evidence)
            typecheck = re.search(r"typecheck:\s*pass(?=\s|[.;,)]|$)", evidence)
            if not build or not typecheck or not browser:
                violations.append(
                    Violation(
                        plan.display,
                        start + 1,
                        f"{identifier}: UI evidence must record final Build: PASS, Typecheck: PASS, and Browser: URL/state results",
                    )
                )
    return violations


def check_pre_review(plan: Document, *, next_type: str = "initial", decision: str | None = None) -> list[Violation]:
    """Validate readiness and refuse only a new reviewer dispatch past the cap."""
    from design_gate import gate_violations
    return (
        check_review_readiness(plan, allow_external_pending=True)
        + gate_violations(plan)
        + check_review_round_structure(plan)
        + check_review_round_cap(plan, next_type=next_type, decision=decision)
    )


def review_manifest_hash(manifest: dict[str, str]) -> str:
    ordered = "\n".join(f"{path}:{digest}" for path, digest in sorted(manifest.items()))
    return "sha256:" + hashlib.sha256(ordered.encode("utf-8")).hexdigest()


RECORDED_FINDING = re.compile(r"^- (?P<severity>BLOCKER|IMPORTANT|MINOR) \((?P<round>G\d+)-\d+\):")


def minor_only_pass(plan: Document, identifier: str) -> bool:
    """A settled PASS whose recorded findings are all MINOR (at least one)."""
    for found, start, end in plan.blocks("Review result", "G"):
        if found != identifier:
            continue
        if task_fields(plan, start, end).get("Outcome", "").strip().upper() != "PASS":
            return False
        severities = [m["severity"] for line in plan.lines[start:end] if (m := RECORDED_FINDING.match(line))]
        return bool(severities) and all(severity == "MINOR" for severity in severities)
    return False


ROUND_MANIFEST_FILE = re.compile(r"`?(runs/G\d+-manifest\.json)`?")


def round_block_manifest(plan: Document, start: int, end: int) -> dict[str, str] | None:
    """A review round's manifest: `runs/G<n>-manifest.json`, or an inline fence (older plans)."""
    fields = task_fields(plan, start, end)
    payload: object = None
    if match := ROUND_MANIFEST_FILE.fullmatch(fields.get("Manifest", "").strip()):
        try:
            payload = json.loads((plan.path.parent / match[1]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    else:
        block_text = "\n".join(plan.lines[start:end])
        if GATE_JSON_FENCE not in block_text:
            return None
        try:
            payload = json.loads(block_text.split(GATE_JSON_FENCE, 1)[1].split("```", 1)[0])
        except json.JSONDecodeError:
            return None
    if isinstance(payload, dict) and all(isinstance(path, str) and isinstance(digest, str)
                                         for path, digest in payload.items()):
        return payload
    return None


def latest_review_round(
    plan: Document,
) -> tuple[str, dict[str, str], dict[str, str] | None] | None:
    rounds = plan.blocks("Review result", "G")
    if not rounds:
        return None
    identifier, start, end = rounds[-1]
    return identifier, task_fields(plan, start, end), round_block_manifest(plan, start, end)


def check_final(spec: Document, plan: Document) -> list[Violation]:
    violations: list[Violation] = []
    violations += check_review_readiness(plan)
    from design_gate import gate_violations
    violations += gate_violations(plan)
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
        actual = set(expand_ids(match.group("value"), prefix))
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

    for section in ("Handoff", "Plan approval"):
        for number, line in plan.body(section):
            if PENDING.search(line) and not LEGACY_FIELD.match(line):
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
    parser.add_argument("--next-review-type", choices=("initial", "re-review"), default="initial",
                        help="The proposed dispatch, not a relabelled historical round")
    parser.add_argument("--review-decision", help="Explicit user decision for the proposed extra review")
    parser.add_argument(
        "--files-hash",
        metavar="FIELD",
        help=(
            "Print the content hash for a task's Files: field value (for recording "
            "Evidence hash) and exit. Ignores change_slug/--phase."
        ),
    )
    return parser


def legacy_capability_baseline(spec: Document, root: str, manifest: dict) -> dict | None:
    """Recover V1 state only from content matching its immutable original hash.

    HEAD is an optional content source, never assumed to be the task baseline.
    A dirty baseline with no recoverable content remains an explicit missing fact.
    """
    recovered = {}
    for _, path, _, _ in capability_deltas(spec, root):
        original_hash = manifest.get(path)
        if original_hash is None:
            recovered[path] = {"present": False, "requirements": []}
            continue
        result = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True)
        if result.returncode or hashlib.sha256(result.stdout).hexdigest() != original_hash:
            return None
        identifiers = [match["id"] for line in result.stdout.decode("utf-8").splitlines()
                       if (match := CAPABILITY_HEADING.match(line))]
        recovered[path] = {"present": True, "requirements": identifiers}
    return recovered


HEADER_RISK = re.compile(r"^\*\*Risk:\*\*\s*(\w+)", re.I)


def risk_mismatch(change: Path) -> list[Violation]:
    """spec, design and plan headers must name one risk; it drives routing and review (4.2: medium vs High)."""
    found: dict[str, tuple[str, int]] = {}
    for name in ("spec.md", "design.md", "plan.md"):
        path = change / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines()[:15], 1):
            if match := HEADER_RISK.match(line.strip()):
                found[name] = (match[1].capitalize(), number)
                break
    if len({value for value, _ in found.values()}) <= 1:
        return []
    shown = ", ".join(f"{name} {value}" for name, (value, _) in found.items())
    reference = found.get("spec.md", next(iter(found.values())))[0]
    return [Violation(str(change / name), line, f"Risk headers differ ({shown}); make them match spec.md")
            for name, (value, line) in found.items() if value != reference]


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

    capability_baseline = None
    saved_baselines = []
    for baseline_path in sorted((change / "runs").glob("T*-baseline.json")):
        try:
            saved = json.loads(baseline_path.read_text(encoding="utf-8"))
            if saved.get("capabilities"):
                saved_baselines.append((saved.get("started", ""), saved["capabilities"]))
            elif isinstance(saved.get("manifest"), dict):
                if recovered := legacy_capability_baseline(spec, root, saved["manifest"]):
                    saved_baselines.append((saved.get("started", ""), recovered))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    if saved_baselines:
        capability_baseline = min(saved_baselines, key=lambda item: item[0])[1]
    violations = check_spec(spec, root, expect_capabilities_applied=args.phase == "final",
                            capability_baseline=capability_baseline)
    if args.phase in ("plan", "pre-review", "final"):
        violations += check_plan(plan, requirement_ids) + risk_mismatch(change)
    if args.phase == "pre-review":
        violations += check_pre_review(plan, next_type=args.next_review_type, decision=args.review_decision)
        from review_snapshot import ScopeError, SnapshotError, compute as compute_snapshot

        try:
            current = compute_snapshot(change, Path.cwd())
            latest = latest_review_round(plan)
            if (latest and latest[1].get("Scope", "").strip().lower() == "documentation-only"
                    and latest[1].get("Snapshot", "").strip() != review_manifest_hash(current)):
                violations.append(Violation(plan.display, 1,
                    "documentation-only follow-up cannot review a changed executable/requirements snapshot"))
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
    if args.phase == "plan":
        from design_gate import missing_inventory_warning
        cross_warnings += (repeated_verification_warnings(plan) + controller_routing_warnings(plan)
                           + missing_inventory_warning(plan) + verification_env_warnings(plan))
    if args.phase != "spec":
        cross_warnings += plan_size_warnings(plan)
    task_count = len(plan.blocks("Tasks", "T"))
    if args.phase != "spec" and task_count > MAX_TASKS:
        cross_warnings.append(f"{task_count} tasks: inspect change size and dependency boundaries; retain corrective tasks rather than folding them into completed work")

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
