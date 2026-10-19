from __future__ import annotations

import unittest
from pathlib import Path


REFERENCES = Path(__file__).parents[1] / "skills/specadoc/references"
EXPLORE = REFERENCES / "explore.md"
RECON = REFERENCES / "recon-and-clarify.md"


class SpecadocExploreTest(unittest.TestCase):
    def test_capability_context_precedes_scout_and_excludes_archives(self) -> None:
        text = EXPLORE.read_text(encoding="utf-8")

        capability_search = text.index("search `docs/specadoc/specs/`")
        scout_dispatch = text.index("Attempt exactly one bounded read-only `scout`")

        self.assertLess(capability_search, scout_dispatch)
        self.assertIn("Read at most three files", text)
        self.assertIn("Relevant capability-specs: none found.", text)
        self.assertIn("Do not\n   search or read `docs/specadoc/archive/`", text)
        self.assertIn("code is authoritative", text)

    def test_explore_runs_doctor_for_missing_key_paths(self) -> None:
        text = EXPLORE.read_text(encoding="utf-8")
        step2 = text[text.index("2. Before dispatching") : text.index("3. Attempt")]
        step2 = " ".join(step2.split())

        self.assertIn("<skill-root>/scripts/doctor.py", step2)
        self.assertIn("once", step2)
        self.assertIn("missing key-path", step2)
        self.assertIn("do not edit the capability file", step2)

    def test_recon_requires_capability_drift_reporting(self) -> None:
        recon = RECON.read_text(encoding="utf-8")

        self.assertIn("include their paths in\nthe scout's `Read` list", recon)
        self.assertIn("conflict as capability\ndrift", recon)
        self.assertIn("code authoritative", recon)


if __name__ == "__main__":
    unittest.main()
