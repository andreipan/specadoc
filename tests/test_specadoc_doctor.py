from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "skills/specadoc/scripts/doctor.py"


def load_module():
    spec = importlib.util.spec_from_file_location("specadoc_doctor", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Specadoc doctor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SpecadocDoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "docs/specadoc"
        self.root.joinpath("specs").mkdir(parents=True)
        self.root.joinpath("archive").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def capability(self, name: str, content: str) -> Path:
        path = self.root / "specs" / name
        path.write_text(content, encoding="utf-8")
        return path

    def archive(self, directory: str, slug: str, capabilities: str = "") -> Path:
        path = self.root / "archive" / directory
        path.mkdir()
        record = path / "record.md"
        record.write_text(f"---\nschema: specadoc.archive/v1\nslug: {slug}\n---\n\n## Affected capabilities\n\n{capabilities}\n", encoding="utf-8")
        return record

    def test_clean_corpus_has_no_findings(self) -> None:
        doctor = load_module()
        self.capability("auth.md", "### C1 — Token revocation\n\nBehavior.\n\n## Provenance\n\n| Change |\n|---|\n| revoke |\n")
        self.archive("revoke", "revoke", "- `docs/specadoc/specs/auth.md`\n")

        report = doctor.inspect(self.root, "docs/specadoc")

        self.assertEqual((), report.findings)
        self.assertEqual(0, report.exit_code(strict=True))

    def test_reports_exact_duplicates_and_broken_archive_links(self) -> None:
        doctor = load_module()
        self.capability("one.md", "### C1 — Shared behavior\n\nSame body.\n\n### C1 — Duplicate\n\nOther body.\n\n## Provenance\n\n| Change |\n|---|\n| one |\n| one |\n")
        self.capability("two.md", "### C2 — Shared behavior\n\nSame body.\n")
        self.archive("wrong-directory", "same", "- `docs/specadoc/specs/missing.md`\n")
        self.archive("second", "same")

        report = doctor.inspect(self.root, "docs/specadoc")
        messages = "\n".join(finding.render() for finding in report.findings)

        self.assertIn("C1 duplicates", messages)
        self.assertIn("provenance change `one`", messages)
        self.assertIn("exact duplicate capability requirement text", messages)
        self.assertIn("references missing capability", messages)
        self.assertIn("slug `same` does not match directory", messages)
        self.assertIn("duplicate archive slug", messages)
        self.assertEqual(1, report.exit_code(strict=False))

    def key_path_capability(self, entries: str) -> Path:
        return self.capability("kp.md", f"### C1 — Thing\n\nBehavior.\n\n## Key paths\n\n{entries}\n\n## Provenance\n")

    def key_path_findings(self, report) -> list:
        return [finding for finding in report.findings if "key path" in finding.message]

    def test_missing_key_path_warns_with_file_line_and_entry(self) -> None:
        doctor = load_module()
        path = self.key_path_capability("- `src/Gone.php`")

        report = doctor.inspect(self.root, "docs/specadoc", repo_root=Path(self.temp.name))

        found = self.key_path_findings(report)
        self.assertEqual(1, len(found))
        self.assertEqual("WARN", found[0].level)
        self.assertEqual(f"{path}:7", found[0].subject)
        self.assertEqual("key path `src/Gone.php` does not exist", found[0].message)
        self.assertEqual(0, report.exit_code(strict=False))

    def test_strict_fails_on_missing_key_path(self) -> None:
        doctor = load_module()
        self.key_path_capability("- `src/Gone.php`")

        report = doctor.inspect(self.root, "docs/specadoc", repo_root=Path(self.temp.name))

        self.assertEqual(1, report.exit_code(strict=True))

    def test_non_path_tokens_are_ignored(self) -> None:
        doctor = load_module()
        self.key_path_capability("- `GET /companies`\n- `~/.cache/x.json`\n- `/categories`\n- `companies()`\n- `README.md`")

        report = doctor.inspect(self.root, "docs/specadoc", repo_root=Path(self.temp.name))

        self.assertEqual([], self.key_path_findings(report))

    def test_suffixes_and_patterns_resolve_before_checking(self) -> None:
        doctor = load_module()
        base = Path(self.temp.name)
        (base / "src").mkdir()
        (base / "src/A.php").write_text("", encoding="utf-8")
        (base / "ui").mkdir()
        (base / "ui/b.tsx").write_text("", encoding="utf-8")
        self.key_path_capability("- `src/A.php::handle`\n- `src/A.php:12`\n- `src/A.php#top`\n- `ui/*.tsx`\n- `ui/{b,c}.tsx`\n- `ui/*.vue`")

        report = doctor.inspect(self.root, "docs/specadoc", repo_root=base)

        found = self.key_path_findings(report)
        self.assertEqual(["key path `ui/*.vue` does not exist"], [finding.message for finding in found])

    def test_invalid_glob_pattern_is_a_warning_not_a_crash(self) -> None:
        doctor = load_module()
        self.key_path_capability("- `src/**.php`")

        report = doctor.inspect(self.root, "docs/specadoc", repo_root=Path(self.temp.name))

        self.assertEqual(["key path `src/**.php` does not exist"], [finding.message for finding in self.key_path_findings(report)])

    def test_existing_key_paths_are_silent_and_file_is_untouched(self) -> None:
        doctor = load_module()
        base = Path(self.temp.name)
        (base / "src").mkdir()
        (base / "src/A.php").write_text("", encoding="utf-8")
        path = self.key_path_capability("- `src/A.php`")
        before = path.read_bytes()

        report = doctor.inspect(self.root, "docs/specadoc", repo_root=base)

        self.assertEqual([], self.key_path_findings(report))
        self.assertEqual(before, path.read_bytes())

    def test_capability_references_follow_the_configured_root(self) -> None:
        doctor = load_module()
        self.archive("revoke", "revoke", "- `custom/sd/specs/missing.md`\n- `docs/specadoc/specs/ignored.md`\n")

        report = doctor.inspect(self.root, "custom/sd")
        messages = "\n".join(finding.render() for finding in report.findings)

        self.assertIn("references missing capability `custom/sd/specs/missing.md`", messages)
        self.assertNotIn("ignored.md", messages)

    def test_missing_provenance_is_a_warning_and_strict_only_failure(self) -> None:
        doctor = load_module()
        self.capability("auth.md", "### C1 — Token revocation\n")
        self.archive("revoke", "revoke", "- `docs/specadoc/specs/auth.md`\n")

        report = doctor.inspect(self.root, "docs/specadoc")

        self.assertEqual((), report.errors)
        self.assertEqual(1, len(report.warnings))
        self.assertEqual(0, report.exit_code(strict=False))
        self.assertEqual(1, report.exit_code(strict=True))


    def test_plan_option_is_a_usage_error_and_same_runtime_pair_warns_once(self) -> None:
        project = self.root.parents[1]
        bin_dir = project / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "codex"
        fake.write_text("#!/bin/sh\n", encoding="utf-8")
        fake.chmod(0o755)
        project.joinpath(".specadoc.json").write_text(json.dumps(
            {"version": 1, "roles": {role: {"runtime": "codex"} for role in ("scout", "worker", "reviewer")}}))
        for role in ("scout", "worker", "reviewer"):
            path = project / f".codex/agents/{role}.toml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('model = "m"\nmodel_reasoning_effort = "low"\n', encoding="utf-8")

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, str(MODULE_PATH), *args], cwd=project, capture_output=True,
                                  text=True, env={**os.environ, "PATH": str(bin_dir)})

        refused = run("--controller-runtime", "claude", "--plan", "plan.md")
        self.assertEqual(2, refused.returncode)
        self.assertIn("--plan", refused.stderr)
        checked = run("--controller-runtime", "claude")
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
        warnings = [line for line in checked.stdout.splitlines() if line.startswith("WARN: routing/")]
        self.assertEqual(1, len(warnings), checked.stdout)
        self.assertIn("reviewer shares worker runtime codex", warnings[0])


class SpecadocProbeTest(unittest.TestCase):
    """`doctor.py --probe`: the run environment, checked before roadmap work starts on it."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base"],
                       cwd=self.project, check=True)
        self.head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project, capture_output=True,
                                   text=True).stdout.strip()
        self.doctor = load_module()

    def config(self, **verification) -> None:
        self.project.joinpath(".specadoc.json").write_text(json.dumps({"version": 1, "verification": verification}))

    def script(self, name: str, first_line: str) -> None:
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(first_line + "\n", encoding="utf-8")

    def probe(self, **options):
        passed, findings = self.doctor.probe(self.project, **options)
        return passed, [finding.render() for finding in findings]

    def test_a_clean_environment_passes_and_names_what_it_checked(self) -> None:
        self.script("bin/suite", "#!/bin/sh")
        self.config(final=["bin/suite --all"], probe=["true"])
        passed, findings = self.probe(expect_head=self.head[:12])
        self.assertEqual([], findings)
        self.assertIn("final command can start: bin/suite --all", passed)
        self.assertIn("probe command: true", passed)

    def test_a_final_command_without_its_file_or_interpreter_is_an_error(self) -> None:
        self.script("bin/suite", "#!/usr/bin/env no-such-interpreter-xyz")
        self.config(final=["bin/suite", "bin/missing", "NAME=1 no-such-program-xyz --flag"])
        _, findings = self.probe()
        self.assertEqual(3, len(findings), findings)
        self.assertIn("`bin/suite` needs `no-such-interpreter-xyz`, which is not on PATH", findings[0])
        self.assertIn("`bin/missing` does not exist", findings[1])
        self.assertIn("`no-such-program-xyz` is not on PATH", findings[2])

    def test_a_failing_probe_command_reports_its_exit_code_and_output_tail(self) -> None:
        self.config(probe=["echo cannot reach the test database >&2; exit 3"])
        _, findings = self.probe()
        self.assertEqual(1, len(findings), findings)
        self.assertIn("exit 3: cannot reach the test database", findings[0])

    def test_baseline_runs_the_final_commands_and_reports_a_gate_that_already_fails(self) -> None:
        self.script("bin/lint", "#!/bin/sh\necho 'GateTransport.php:56 already narrowed'\nexit 1")
        self.script("bin/suite", "#!/bin/sh\nexit 0")
        for name in ("bin/lint", "bin/suite"):
            (self.project / name).chmod(0o755)
        self.config(final=["bin/suite", "bin/lint"])
        passed, findings = self.probe()
        self.assertEqual([], findings, "without --baseline the final commands are not run")
        passed, findings = self.probe(baseline=True)
        self.assertIn(f"final command passes on {self.head[:12]}: bin/suite", passed)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("ERROR: probe/baseline: `bin/lint` fails on", findings[0])
        self.assertIn("before any change: exit 1: GateTransport.php:56 already narrowed", findings[0])

    def test_baseline_says_when_the_checkout_has_uncommitted_changes(self) -> None:
        self.script("bin/suite", "#!/bin/sh\nexit 0")
        (self.project / "bin/suite").chmod(0o755)
        subprocess.run(["git", "add", "bin/suite"], cwd=self.project, check=True)
        self.config(final=["bin/suite"])
        passed, _ = self.probe(baseline=True)
        self.assertIn(f"final command passes on {self.head[:12]} with uncommitted changes: bin/suite", passed)

    def test_another_revision_than_the_parent_expects_is_an_error(self) -> None:
        self.config(final=[])
        _, findings = self.probe(expect_head="0" * 40)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("ERROR: probe/checkout: HEAD is", findings[0])

    def test_a_routed_runtime_without_its_cli_is_an_error_unless_it_is_the_controller(self) -> None:
        self.project.joinpath(".specadoc.json").write_text(json.dumps(
            {"version": 1, "roles": {"worker": {"runtime": "claude"}, "reviewer": {"runtime": "codex"}}}))
        _, findings = self.probe(controller="claude", which=lambda name: None)
        self.assertEqual(["ERROR: probe/reviewer: codex CLI is not on PATH"], findings)

    def test_the_command_exits_1_on_an_error_and_0_when_clean(self) -> None:
        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, str(MODULE_PATH), "--probe", *args], cwd=self.project,
                                  capture_output=True, text=True)

        self.config(probe=["true"])
        clean = run("--expect-head", self.head)
        self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)
        self.assertIn("probe: PASS", clean.stdout)
        self.config(probe=["false"])
        failed = run()
        self.assertEqual(1, failed.returncode, failed.stdout + failed.stderr)
        self.assertIn("probe: FAIL", failed.stdout)
        self.assertIn("PATH=", failed.stdout)


if __name__ == "__main__":
    unittest.main()
