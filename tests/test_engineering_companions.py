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

    def test_tidy_pass_precedes_the_independent_review(self) -> None:
        # After run 4.8 the cleanup is one pass over Review scope, once the scope is filled.
        apply = (REFERENCES / "apply.md").read_text()
        verification = apply.index("Controller runs the whole suite and the repository gates once")
        cleanup = apply.index("`tidy <slug>`")
        review = apply.index("independent read-only `reviewer`")
        self.assertLess(verification, cleanup)
        self.assertLess(cleanup, review)

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
