from __future__ import annotations

import importlib.util
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
        self.root = Path(self.temp.name) / "docs/agent"
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
        self.archive("revoke", "revoke", "- `docs/agent/specs/auth.md`\n")

        report = doctor.inspect(self.root)

        self.assertEqual((), report.findings)
        self.assertEqual(0, report.exit_code(strict=True))

    def test_reports_exact_duplicates_and_broken_archive_links(self) -> None:
        doctor = load_module()
        self.capability("one.md", "### C1 — Shared behavior\n\nSame body.\n\n### C1 — Duplicate\n\nOther body.\n\n## Provenance\n\n| Change |\n|---|\n| one |\n| one |\n")
        self.capability("two.md", "### C2 — Shared behavior\n\nSame body.\n")
        self.archive("wrong-directory", "same", "- `docs/agent/specs/missing.md`\n")
        self.archive("second", "same")

        report = doctor.inspect(self.root)
        messages = "\n".join(finding.render() for finding in report.findings)

        self.assertIn("C1 duplicates", messages)
        self.assertIn("provenance change `one`", messages)
        self.assertIn("exact duplicate capability requirement text", messages)
        self.assertIn("references missing capability", messages)
        self.assertIn("slug `same` does not match directory", messages)
        self.assertIn("duplicate archive slug", messages)
        self.assertEqual(1, report.exit_code(strict=False))

    def test_missing_provenance_is_a_warning_and_strict_only_failure(self) -> None:
        doctor = load_module()
        self.capability("auth.md", "### C1 — Token revocation\n")
        self.archive("revoke", "revoke", "- `docs/agent/specs/auth.md`\n")

        report = doctor.inspect(self.root)

        self.assertEqual((), report.errors)
        self.assertEqual(1, len(report.warnings))
        self.assertEqual(0, report.exit_code(strict=False))
        self.assertEqual(1, report.exit_code(strict=True))


if __name__ == "__main__":
    unittest.main()
