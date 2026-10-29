"""Static contracts, not a substitute for live management-skill evaluations."""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILLS = ROOT / "skills"
MANAGEMENT = ("foreman", "orchestrator")
CASES = {
    "foreman": {"continue-executor", "continuation-unavailable", "review-and-recovery"},
    "orchestrator": {"dependent-projects", "checkpoint-authority", "lost-event-and-recovery"},
}


class ManagementSkillsTest(unittest.TestCase):
    def test_management_skills_are_in_portable_bundle(self) -> None:
        spec = importlib.util.spec_from_file_location("package_plugin", ROOT / "scripts/package_plugin.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(set(MANAGEMENT).issubset(module.SKILLS))

    def test_explicit_discovery_and_bounded_entrypoints(self) -> None:
        for name in MANAGEMENT:
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text()
                self.assertTrue(text.startswith(f"---\nname: {name}\n"))
                description = text.split("\n---\n", 1)[0]
                self.assertIn("explicit", description.lower())
                self.assertLessEqual(len(text.splitlines()), 150)
                policy = (SKILLS / name / "agents/openai.yaml").read_text()
                self.assertRegex(policy, r"allow_implicit_invocation:\s*false\b")

    def test_references_are_local_and_exist(self) -> None:
        for name in MANAGEMENT:
            root = SKILLS / name
            text = (root / "SKILL.md").read_text()
            refs = re.findall(r"`(references/[^`\s]+\.md)`", text)
            self.assertTrue(refs)
            for ref in refs:
                self.assertTrue((root / ref).is_file(), f"{name}: {ref}")
            for path in root.rglob("*.md"):
                self.assertNotIn("../", path.read_text(), str(path))

    def test_foreman_is_standalone_and_preserves_review(self) -> None:
        text = (SKILLS / "foreman/SKILL.md").read_text()
        self.assertIn("one persistent executor", text)
        self.assertIn("independent review", text)
        self.assertIn("Do not insert this mode inside", text)
        self.assertNotIn("specadoc", text.lower())

    def test_orchestrator_owns_integration_not_local_lifecycle(self) -> None:
        text = (SKILLS / "orchestrator/SKILL.md").read_text()
        self.assertIn("Specadoc", text)
        self.assertIn("one writer", text)
        self.assertIn("end-to-end", text)
        self.assertIn("Do not direct their workers", text)
        checkpoints = (SKILLS / "orchestrator/references/checkpoints.md").read_text()
        self.assertIn("explicit user mandate", checkpoints)
        self.assertIn("does not create permission", checkpoints)

    def test_orchestrator_guards_found_in_pilot_runs(self) -> None:
        root = SKILLS / "orchestrator"
        text = (root / "SKILL.md").read_text()
        self.assertIn("Never edit routing or role files yourself", text)
        self.assertIn("test asserts the exact field set", text)
        controllers = (root / "references/controllers.md").read_text()
        self.assertIn("bb thread wait <id>", controllers)
        self.assertIn("CLAUDE_CODE_SESSION_ID", controllers)
        checkpoints = (root / "references/checkpoints.md").read_text()
        self.assertIn("**Approval provenance:**", checkpoints)
        self.assertIn("`.specadoc.json`", checkpoints)

    def test_capabilities_and_recovery_are_not_assumed(self) -> None:
        for name in MANAGEMENT:
            paths = [SKILLS / name / "SKILL.md", *sorted((SKILLS / name / "references").glob("*.md"))]
            text = "\n".join(path.read_text() for path in paths)
            for requirement in ("continuation", "foreground", "timer", "allow_once", "read back", "model"):
                self.assertIn(requirement, text, f"{name}: {requirement}")
            self.assertIn("Do not retry a launch blindly", text)
            self.assertIn("No model names or levels are fixed", text)

    def test_simulation_fixtures_have_prompts_and_trace_graders(self) -> None:
        for name, expected in CASES.items():
            root = SKILLS / name / "evals"
            self.assertEqual(expected, {p.name for p in root.iterdir() if p.is_dir()})
            for case in expected:
                directory = root / case
                metadata = (directory / "case.yaml").read_text()
                self.assertIn('schema_version: "1.1"', metadata)
                self.assertIn(f"name: {case}\n", metadata)
                self.assertIn("expected_outcome: |", metadata)
                prompt = (directory / "prompt.md").read_text()
                self.assertTrue(prompt.startswith("---\n"))
                self.assertIn("timeout_seconds:", prompt)
                graders = list((directory / "graders").glob("*.md"))
                self.assertTrue(graders)
                for grader in graders:
                    self.assertTrue(grader.read_text().startswith("---\ntype: llm\nfocus: trace\nweight: 1\n---\n"))

    def test_package_enforces_explicit_policy_for_all_management_modes(self) -> None:
        spec = importlib.util.spec_from_file_location("package_plugin", ROOT / "scripts/package_plugin.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(set(MANAGEMENT).issubset(module.EXPLICIT_SKILLS))


if __name__ == "__main__":
    unittest.main()
