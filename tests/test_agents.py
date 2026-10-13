from __future__ import annotations

import unittest
from pathlib import Path


AGENTS = Path(__file__).parents[1] / "agents"
BEGIN = "<!-- specadoc:tooling:begin -->"
END = "<!-- specadoc:tooling:end -->"
REPORTS = {
    "scout": ["## Relevant files", "## Verification", "## Material unknowns", "## Recommendation"],
    "worker": ["## Status", "## TDD evidence", "## Requirement coverage", "## Remaining risks"],
    "reviewer": ["## Verdict", "## Requirement matrix", "## Findings", "## Verification assessment"],
}


def frontmatter(text: str) -> dict[str, str]:
    _, front, _ = text.split("---\n", 2)
    return {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in front.splitlines())}


class AgentContractTest(unittest.TestCase):
    def test_each_role_has_frontmatter_tooling_block_and_report(self) -> None:
        for name, headings in REPORTS.items():
            with self.subTest(role=name):
                text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
                meta = frontmatter(text)
                self.assertEqual(name, meta["name"])
                for key in ("description", "tools", "model"):
                    self.assertTrue(meta.get(key), key)
                self.assertEqual(1, text.count(BEGIN))
                self.assertLess(text.index(BEGIN), text.index(END))
                for heading in headings:
                    self.assertIn(heading, text)

    def test_only_worker_may_write(self) -> None:
        for name in REPORTS:
            tools = frontmatter((AGENTS / f"{name}.md").read_text(encoding="utf-8"))["tools"]
            writes = "Edit" in tools or "Write" in tools
            self.assertEqual(name == "worker", writes, name)

    def test_scout_reports_capability_drift_and_skips_archives(self) -> None:
        scout = (AGENTS / "scout.md").read_text(encoding="utf-8")
        self.assertIn("report any drift, with code\n  authoritative", scout)
        self.assertIn("search or read `docs/agent/archive/`", scout)


if __name__ == "__main__":
    unittest.main()
