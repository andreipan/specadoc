from __future__ import annotations

import unittest
from pathlib import Path


SKILLS = Path(__file__).parents[1] / "skills"
REFERENCES = SKILLS / "specadoc/references"
COMPANIONS = ("tidy", "codebase-design", "domain-modeling")


class EngineeringCompanionsTest(unittest.TestCase):
    def test_bundled_companions_are_standalone_skills(self) -> None:
        for name in COMPANIONS:
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text()
                self.assertTrue(text.startswith(f"---\nname: {name}\n"))
                self.assertNotIn("specadoc", text.lower())

    def test_optional_cleanup_precedes_final_verification(self) -> None:
        apply = (REFERENCES / "apply.md").read_text()
        cleanup = apply.index("optional behavior-preserving cleanup")
        verification = apply.index("The controller runs the final affected-only verification")
        review = apply.index("run one independent read-only `reviewer`")
        self.assertLess(cleanup, verification)
        self.assertLess(verification, review)

    def test_companions_preserve_role_and_artifact_boundaries(self) -> None:
        companions = (REFERENCES / "interoperability.md").read_text()
        self.assertIn("Architecture design", companions)
        self.assertIn("Domain modeling", companions)
        self.assertIn("Behavior-preserving cleanup", companions)
        self.assertIn("no-file explore", companions)
        self.assertIn("do not write glossary or ADR files", companions)
        self.assertIn("not a second questionnaire", companions)
        self.assertIn("never a substitute for independent review", companions)


if __name__ == "__main__":
    unittest.main()
