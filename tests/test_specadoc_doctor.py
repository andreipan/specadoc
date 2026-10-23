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


if __name__ == "__main__":
    unittest.main()
