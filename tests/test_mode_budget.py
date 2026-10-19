from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
import warnings
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1] / "skills/specadoc"
MODULE_PATH = SKILL_ROOT / "scripts/mode_budget.py"


def load_module():
    spec = importlib.util.spec_from_file_location("mode_budget", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ModeBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.copy = Path(self.temp.name) / "specadoc"
        shutil.copytree(SKILL_ROOT, self.copy)

    def test_oversized_skill_md_is_error(self) -> None:
        skill = self.copy / "SKILL.md"
        skill.write_bytes(b"x" * 5700)
        errors, _ = self.module.size_findings(self.copy)
        self.assertTrue(
            any("SKILL.md" in e and "5700" in e and "5632" in e for e in errors), errors
        )

    def test_oversized_reference_is_error(self) -> None:
        ref = self.copy / "references/roles/scout.md"
        ref.write_bytes(b"x" * 15361)
        errors, _ = self.module.size_findings(self.copy)
        self.assertTrue(
            any("roles/scout.md" in e and "15361" in e and "15360" in e for e in errors),
            errors,
        )

    def test_low_mode_limit_warns_only(self) -> None:
        manifest = self.module.load_manifest(self.copy)
        manifest["modes"]["explore"]["limit"] = 100
        errors, warns = self.module.size_findings(self.copy, manifest)
        self.assertEqual(errors, [])
        self.assertTrue(any("explore" in w and "> 100" in w for w in warns), warns)
        self.assertFalse(any("propose" in w for w in warns), warns)

    def test_manifest_lists_four_modes(self) -> None:
        manifest = self.module.load_manifest(SKILL_ROOT)
        self.assertEqual(
            set(manifest["modes"]), {"explore", "propose", "apply", "archive"}
        )

    def test_real_skill_has_no_errors(self) -> None:
        errors, warns = self.module.size_findings(SKILL_ROOT)
        for message in warns:
            warnings.warn(message)
        self.assertEqual(errors, [])

    def test_real_skill_has_no_drift(self) -> None:
        self.assertEqual(self.module.drift_findings(SKILL_ROOT), [])

    def test_unlisted_reference_is_drift(self) -> None:
        manifest = self.module.load_manifest(self.copy)
        entry = manifest["modes"]["explore"]
        for key in ("always", "conditional"):
            entry[key] = [n for n in entry.get(key, []) if n != "interoperability.md"]
        drift = self.module.drift_findings(self.copy, manifest)
        self.assertTrue(
            any("explore" in d and "interoperability.md" in d for d in drift), drift
        )

    def test_prefixed_mention_is_drift(self) -> None:
        archive = self.copy / "references/archive.md"
        archive.write_text(
            archive.read_text(encoding="utf-8") + "\nSee `references/runners.md`.\n",
            encoding="utf-8",
        )
        drift = self.module.drift_findings(self.copy)
        self.assertTrue(any("archive" in d and "runners.md" in d for d in drift), drift)

    def test_missing_listed_file_is_drift(self) -> None:
        manifest = self.module.load_manifest(self.copy)
        manifest["modes"]["apply"].setdefault("conditional", []).append("no-such-file.md")
        drift = self.module.drift_findings(self.copy, manifest)
        self.assertTrue(
            any("apply" in d and "no-such-file.md" in d for d in drift), drift
        )

    def test_mode_totals_explore_always(self) -> None:
        refs = SKILL_ROOT / "references"
        expected = sum(
            p.stat().st_size
            for p in (
                SKILL_ROOT / "SKILL.md",
                refs / "explore.md",
                refs / "recon-and-clarify.md",
            )
        )
        totals = self.module.mode_totals(SKILL_ROOT)
        self.assertEqual(totals["explore"]["always"], expected)
        self.assertGreaterEqual(totals["explore"]["worst"], expected)
        self.assertIn("limit", totals["explore"])


if __name__ == "__main__":
    unittest.main()
