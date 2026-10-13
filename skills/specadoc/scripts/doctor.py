#!/usr/bin/env python3
"""Report exact integrity problems across Specadoc capability specs and archives.

This command is read-only. It deliberately reports only structural conflicts and
exact duplicate requirement text; resolving ownership remains a human decision.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


CAPABILITY = re.compile(r"^###\s+(?P<id>C\d+)\b\s*(?:—|-)?\s*(?P<title>.*)$")
ARCHIVE_SLUG = re.compile(r"^slug:\s*(?P<slug>\S+)\s*$", re.MULTILINE)
CAPABILITY_REF = re.compile(r"\bdocs/agent/specs/(?P<name>[\w./-]+\.md)")


@dataclass(frozen=True)
class Finding:
    level: str
    subject: str
    message: str

    def render(self) -> str:
        return f"{self.level}: {self.subject}: {self.message}"


@dataclass(frozen=True)
class DoctorReport:
    findings: tuple[Finding, ...]

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.level == "ERROR")

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.level == "WARN")

    def exit_code(self, *, strict: bool) -> int:
        return int(bool(self.errors) or (strict and bool(self.warnings)))


@dataclass(frozen=True)
class Requirement:
    path: Path
    identifier: str
    line: int
    text: str


def _section(text: str, name: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    marker = f"## {name}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return []
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return [(index + 1, lines[index]) for index in range(start, end)]


def _requirements(path: Path) -> list[Requirement]:
    lines = path.read_text(encoding="utf-8").splitlines()
    headings = [(index, match) for index, line in enumerate(lines) if (match := CAPABILITY.match(line))]
    result: list[Requirement] = []
    for position, (start, match) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        end = next((index for index in range(start + 1, end) if lines[index].startswith("## ")), end)
        body = "\n".join([match.group("title"), *lines[start + 1:end]])
        result.append(Requirement(path, match.group("id"), start + 1, " ".join(body.split())))
    return result


def _provenance(path: Path) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for line, row in _section(path.read_text(encoding="utf-8"), "Provenance"):
        stripped = row.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0].lower() == "change" or set(cells[0]) <= {"-", ":", " "}:
            continue
        change = cells[0].strip("`")
        if change:
            result.append((line, change))
    return result


def _archive_capabilities(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [match.group("name") for _, line in _section(text, "Affected capabilities") for match in CAPABILITY_REF.finditer(line)]


def _group_lines(rows: list[tuple[int, str]]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for line, value in rows:
        grouped[value].append(line)
    return grouped


def inspect(root: Path) -> DoctorReport:
    root = Path(root)
    specs = sorted((root / "specs").glob("**/*.md")) if (root / "specs").is_dir() else []
    records = sorted((root / "archive").glob("*/record.md")) if (root / "archive").is_dir() else []
    findings: list[Finding] = []
    requirements: list[Requirement] = []
    provenance: dict[Path, list[tuple[int, str]]] = {}

    for path in specs:
        seen: dict[str, Requirement] = {}
        for requirement in _requirements(path):
            if requirement.identifier in seen:
                first = seen[requirement.identifier]
                findings.append(Finding("ERROR", f"{path}:{requirement.line}", f"{requirement.identifier} duplicates {path}:{first.line}"))
                continue
            seen[requirement.identifier] = requirement
            requirements.append(requirement)
        provenance[path] = _provenance(path)
        for change, lines in _group_lines(provenance[path]).items():
            if len(lines) > 1:
                findings.append(Finding("WARN", f"{path}:{lines[1]}", f"provenance change `{change}` is already recorded at line {lines[0]}"))

    by_text: dict[str, list[Requirement]] = defaultdict(list)
    for requirement in requirements:
        if requirement.text:
            by_text[requirement.text].append(requirement)
    for matches in by_text.values():
        if len({match.path for match in matches}) > 1:
            locations = ", ".join(f"{match.path}:{match.line} ({match.identifier})" for match in matches)
            findings.append(Finding("WARN", locations, "exact duplicate capability requirement text"))

    slugs: dict[str, list[Path]] = defaultdict(list)
    for record in records:
        text = record.read_text(encoding="utf-8")
        match = ARCHIVE_SLUG.search(text)
        if not match:
            findings.append(Finding("ERROR", str(record), "missing `slug` front matter"))
            continue
        slug = match.group("slug")
        slugs[slug].append(record)
        if slug != record.parent.name:
            findings.append(Finding("ERROR", str(record), f"slug `{slug}` does not match directory `{record.parent.name}`"))
        for name in _archive_capabilities(record):
            capability = root / "specs" / name
            if not capability.is_file():
                findings.append(Finding("WARN", str(record), f"references missing capability `docs/agent/specs/{name}`"))
                continue
            known_changes = {change for _, change in provenance.get(capability, _provenance(capability))}
            if slug not in known_changes:
                findings.append(Finding("WARN", str(record), f"capability `docs/agent/specs/{name}` has no provenance row for `{slug}`"))
    for slug, paths in slugs.items():
        if len(paths) > 1:
            findings.append(Finding("ERROR", slug, "duplicate archive slug: " + ", ".join(map(str, paths))))

    return DoctorReport(tuple(sorted(findings, key=lambda finding: (finding.level, finding.subject, finding.message))))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("docs/agent"))
    parser.add_argument("--strict", action="store_true", help="return non-zero for warnings too")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = inspect(args.root)
    print(f"capability specs: {len(list((args.root / 'specs').glob('**/*.md')))}")
    print(f"archive records: {len(list((args.root / 'archive').glob('*/record.md')))}")
    if not report.findings:
        print("Specadoc doctor: no findings.")
        return 0
    for finding in report.findings:
        print(finding.render())
    print(f"findings: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return report.exit_code(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
