#!/usr/bin/env python3
"""Report exact integrity problems across Specadoc capability specs and archives.

This command is read-only. It deliberately reports only structural conflicts and
exact duplicate requirement text; resolving ownership remains a human decision.

`--probe` checks the run environment instead: the shell a controller, orchestrator or
verifier works in. It runs the project's `verification.probe` commands and changes nothing.
`--probe --baseline` also runs `verification.final`, so a gate that already fails is known at the start.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from specadoc_root import legacy_warning, resolve_root  # noqa: E402
from specadoc_config import normalize_runtime  # noqa: E402


CAPABILITY = re.compile(r"^###\s+(?P<id>C\d+)\b\s*(?:—|-)?\s*(?P<title>.*)$")
BACKTICKED = re.compile(r"`([^`]+)`")
BRACE_SET = re.compile(r"\{([^{}]*)\}")
PATH_SUFFIX = re.compile(r"(?:::.*|#.*|:\d+)$")
ARCHIVE_SLUG = re.compile(r"^slug:\s*(?P<slug>\S+)\s*$", re.MULTILINE)


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


def _capability_ref(ref_root: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w./-]){re.escape(ref_root.rstrip('/'))}/specs/(?P<name>[\w./-]+\.md)")


def _archive_capabilities(path: Path, ref_root: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    pattern = _capability_ref(ref_root)
    return [match.group("name") for _, line in _section(text, "Affected capabilities") for match in pattern.finditer(line)]


def _group_lines(rows: list[tuple[int, str]]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for line, value in rows:
        grouped[value].append(line)
    return grouped


def _expand_braces(entry: str) -> list[str]:
    match = BRACE_SET.search(entry)
    if not match:
        return [entry]
    return [item for option in match.group(1).split(",") for item in _expand_braces(entry[:match.start()] + option + entry[match.end():])]


def _key_path_exists(entry: str, repo_root: Path) -> bool:
    for candidate in _expand_braces(entry):
        if "*" in candidate:
            try:
                if any(repo_root.glob(candidate)):
                    return True
            except (ValueError, NotImplementedError):
                # older Path.glob rejects patterns such as `src/**.php`
                continue
        elif (repo_root / candidate).exists():
            return True
    return False


def _key_path_findings(path: Path, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for line, row in _section(path.read_text(encoding="utf-8"), "Key paths"):
        for token in BACKTICKED.findall(row):
            if "/" not in token or re.search(r"[\s<]", token) or token[0] in "~/$":
                continue
            entry = PATH_SUFFIX.sub("", token)
            if entry and not _key_path_exists(entry, repo_root):
                findings.append(Finding("WARN", f"{path}:{line}", f"key path `{token}` does not exist"))
    return findings


def inspect(root: Path, ref_root: str | None = None, repo_root: Path | None = None) -> DoctorReport:
    """`ref_root` is the root as written inside artifacts; defaults to `root`. `repo_root` anchors key paths; defaults to the current directory."""
    repo_root = Path(repo_root) if repo_root else Path.cwd()
    root = Path(root)
    ref_root = (ref_root or root.as_posix()).rstrip("/")
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
        findings.extend(_key_path_findings(path, repo_root))
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
        for name in _archive_capabilities(record, ref_root):
            capability = root / "specs" / name
            if not capability.is_file():
                findings.append(Finding("WARN", str(record), f"references missing capability `{ref_root}/specs/{name}`"))
                continue
            known_changes = {change for _, change in provenance.get(capability, _provenance(capability))}
            if slug not in known_changes:
                findings.append(Finding("WARN", str(record), f"capability `{ref_root}/specs/{name}` has no provenance row for `{slug}`"))
    for slug, paths in slugs.items():
        if len(paths) > 1:
            findings.append(Finding("ERROR", slug, "duplicate archive slug: " + ", ".join(map(str, paths))))

    return DoctorReport(tuple(sorted(findings, key=lambda finding: (finding.level, finding.subject, finding.message))))


ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
PROBE_TIMEOUT = 60.0
BASELINE_TIMEOUT = 1800.0


def _executable_problem(command: str, repo: Path, which) -> str | None:
    """Why the first program of `command` cannot start here, or None. A script's `#!/usr/bin/env <x>`
    interpreter counts: 6.1/6.2 controllers had the suite's launcher script but not its interpreter on PATH."""
    try:
        words = shlex.split(command)
    except ValueError as exc:
        return f"cannot parse ({exc})"
    while words and (ASSIGNMENT.match(words[0]) or words[0] == "env"):
        words.pop(0)
    if not words:
        return "names no program"
    program = words[0]
    if "/" not in program:
        return None if which(program) else f"`{program}` is not on PATH"
    path = Path(program) if Path(program).is_absolute() else repo / program
    if not path.is_file():
        return f"`{program}` does not exist"
    try:
        with path.open("rb") as handle:
            first = handle.readline(200).decode("utf-8", "replace").strip()
    except OSError as exc:
        return f"`{program}` cannot be read ({exc.strerror})"
    if first.startswith("#!"):
        parts = first[2:].split()
        if parts and Path(parts[0]).name == "env":
            parts = [word for word in parts[1:] if not word.startswith("-") and not ASSIGNMENT.match(word)]
        if parts and not which(parts[0]):
            return f"`{program}` needs `{parts[0]}`, which is not on PATH"
    return None


def probe(repo: Path, *, expect_head: str | None = None, controller: str | None = None, which=None,
          timeout: float = PROBE_TIMEOUT, baseline: bool = False,
          baseline_timeout: float = BASELINE_TIMEOUT) -> tuple[list[str], list[Finding]]:
    """Check the environment this shell gives a run, before roadmap work starts on it. Every run so far
    lost its largest block of time to first contact with a changed environment: another checkout (4.9),
    a runtime that cannot start in the sandbox (5.2), no interpreter on PATH (6.1), no test database (6.4).

    `baseline` also runs every `verification.final` command on the checkout as it is: in 6.5 a lint error
    in a file no task touched stopped the first `accept`, 55 minutes into the run, and cost two user
    decisions that the same run before the mandate question would have cost none."""
    from specadoc_config import load_config
    which = which or shutil.which
    passed: list[str] = [f"python {sys.version.split()[0]} ({sys.executable})"]
    findings: list[Finding] = []
    try:
        config = load_config(repo)
    except ValueError as exc:
        return passed, [Finding("ERROR", "probe/config", str(exc))]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    current = head.stdout.strip()
    if head.returncode != 0:
        findings.append(Finding("WARN" if not expect_head else "ERROR", "probe/checkout",
                                f"{repo} is not a git checkout"))
    elif expect_head and not (current.startswith(expect_head) or expect_head.startswith(current)):
        findings.append(Finding("ERROR", "probe/checkout", f"HEAD is {current[:12]}, expected {expect_head[:12]}: "
                                "this session runs in another checkout or revision"))
    else:
        passed.append(f"checkout {repo} at {current[:12]}")
    verification = config.get("verification") or {}
    for command in verification.get("final", []):
        if problem := _executable_problem(command, repo, which):
            findings.append(Finding("ERROR", "probe/final", f"`{command}`: {problem}"))
        else:
            passed.append(f"final command can start: {command}")
            if baseline:
                _baseline(command, repo, current, baseline_timeout, passed, findings)
    for command in verification.get("probe", []):
        try:
            done = subprocess.run(command, shell=True, cwd=repo, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            findings.append(Finding("ERROR", "probe/command", f"`{command}`: no result within {timeout:g} s"))
            continue
        if done.returncode != 0:
            tail = " | ".join((done.stderr + done.stdout).strip().splitlines()[-3:])
            findings.append(Finding("ERROR", "probe/command", f"`{command}`: exit {done.returncode}: {tail}"))
        else:
            passed.append(f"probe command: {command}")
    import run_role
    checks = {"codex": run_role._check_codex_home, "opencode": run_role._check_opencode_log}
    for role, binding in sorted((config.get("roles") or {}).items()):
        runtime = binding["runtime"]
        if runtime == controller:
            continue
        if not which(runtime):
            findings.append(Finding("ERROR", f"probe/{role}", f"{runtime} CLI is not on PATH"))
            continue
        try:
            if runtime in checks and role != "controller":
                checks[runtime](role, True)
        except run_role.SandboxedRun as exc:
            findings.append(Finding("ERROR", f"probe/{role}", str(exc)))
        else:
            passed.append(f"{role} runtime {runtime} can start")
    return passed, findings


def _baseline(command: str, repo: Path, head: str, timeout: float, passed: list[str],
              findings: list[Finding]) -> None:
    """Run one final command before any change and report a failure as the checkout's own."""
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo,
                           capture_output=True, text=True).stdout.strip()
    where = f"{head[:12] or 'this checkout'}{' with uncommitted changes' if dirty else ''}"
    try:
        done = subprocess.run(command, shell=True, cwd=repo, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        findings.append(Finding("ERROR", "probe/baseline", f"`{command}`: no result within {timeout:g} s"))
        return
    if done.returncode != 0:
        tail = " | ".join((done.stdout + done.stderr).strip().splitlines()[-6:])
        findings.append(Finding("ERROR", "probe/baseline", f"`{command}` fails on {where} before any change: "
                                f"exit {done.returncode}: {tail}"))
    else:
        passed.append(f"final command passes on {where}: {command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="artifact root (default: resolved, see specadoc_root.py)")
    parser.add_argument("--strict", action="store_true", help="return non-zero for warnings too")
    parser.add_argument("--controller-runtime", choices=("claude", "codex", "opencode"), type=normalize_runtime, help="also inspect role routing, CLI presence and independence")
    parser.add_argument("--probe", action="store_true",
                        help="check this shell's run environment (final commands, verification.probe, runtimes, "
                             "checkout) instead of the specs; exit 1 on any error")
    parser.add_argument("--expect-head", metavar="SHA",
                        help="with --probe: the revision the parent session works on")
    parser.add_argument("--baseline", action="store_true",
                        help="with --probe: also run every verification.final command on the checkout as it is")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if (args.expect_head or args.baseline) and not args.probe:
        print("error: --expect-head and --baseline need --probe", file=sys.stderr)
        return 2
    if args.probe:
        passed, findings = probe(Path.cwd(), expect_head=args.expect_head, controller=args.controller_runtime,
                                 baseline=args.baseline)
        for line in passed:
            print(f"ok: {line}")
        for finding in findings:
            print(finding.render())
        errors = sum(1 for finding in findings if finding.level == "ERROR")
        print(f"probe: {'FAIL' if errors else 'PASS'} ({len(passed)} ok, {errors} error(s), "
              f"{len(findings) - errors} warning(s)); PATH={os.environ.get('PATH', '')}" if errors
              else f"probe: PASS ({len(passed)} ok, {len(findings)} warning(s))")
        return int(bool(errors))
    try:
        choice = resolve_root(args.root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if warning := legacy_warning(choice):
        print(warning, file=sys.stderr)
    root = Path(choice.path)
    report = inspect(root, choice.path, Path.cwd())
    if args.controller_runtime:
        from role_routing import inspect_routing

        routing = inspect_routing(Path.cwd(), args.controller_runtime)
        report = DoctorReport(report.findings + tuple(Finding(row["level"], f"routing/{row['role']}", row["message"]) for row in routing))
    print(f"root: {choice.path} ({choice.source})")
    print(f"capability specs: {len(list((root / 'specs').glob('**/*.md')))}")
    print(f"archive records: {len(list((root / 'archive').glob('*/record.md')))}")
    if not report.findings:
        print("Specadoc doctor: no findings.")
        return 0
    for finding in report.findings:
        print(finding.render())
    print(f"findings: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return report.exit_code(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
