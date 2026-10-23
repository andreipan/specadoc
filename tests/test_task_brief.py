from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "skills" / "specadoc" / "scripts" / "task_brief.py"

SPEC = """# Spec

## Requirements

### R1 — Skip reminded

Skip invoices reminded today.

### R2 — Unrelated

Other behaviour.

## Acceptance scenarios

### A1 — Already reminded

- **Given:** an invoice reminded today

### A2 — Unrelated scenario

- **Given:** something else

## Constraints

- Keep the job transport-only.

## Requirement coverage

| Requirement | Acceptance scenarios |
|---|---|
| R1 | A1 |
| R2 | A2 |
"""

PLAN = """# Plan

## Tasks

### T1 — Skip reminded

- [ ] Complete
- **Requirements:** R1
- **Files:** `src/Reminders.php`

### T2 — Other

- [ ] Complete
- **Requirements:** R2
"""


class TaskBriefTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.change = self.repo / "docs" / "specadoc" / "demo"
        self.change.mkdir(parents=True)
        (self.change / "spec.md").write_text(SPEC, encoding="utf-8")
        (self.change / "plan.md").write_text(PLAN, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if key != "SPECADOC_ROOT"}
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True, env=env
        )

    def test_brief_carries_only_the_task_and_its_contract(self) -> None:
        result = self.run_cli("demo", "T1")

        self.assertEqual(result.returncode, 0, result.stderr)
        brief = (self.change / "runs" / "T1-brief.md").read_text(encoding="utf-8")
        self.assertIn("### T1 — Skip reminded", brief)
        self.assertIn("### R1 — Skip reminded", brief)
        self.assertIn("### A1 — Already reminded", brief)
        self.assertIn("Keep the job transport-only.", brief)
        self.assertIn("runs/T1-report.md", brief)
        self.assertIn("worker-result.schema.json", brief)
        for foreign in ("### T2", "### R2", "### A2"):
            self.assertNotIn(foreign, brief)

    def test_unknown_task_fails(self) -> None:
        result = self.run_cli("demo", "T7")

        self.assertEqual(result.returncode, 2)
        self.assertIn("no T7", result.stderr)

    def test_optional_test_context_is_task_local_without_loading_runbooks(self) -> None:
        context = "- **Test context:** `tests/Browser/Example.php`; `docs/testing/browser.md#login`; test-only DB.\n"
        (self.change / "plan.md").write_text(PLAN.replace("### T2", context + "\n### T2"), encoding="utf-8")
        self.assertEqual(self.run_cli("demo", "T1").returncode, 0)
        brief = (self.change / "runs/T1-brief.md").read_text()
        self.assertIn(context.strip(), brief)
        self.assertNotIn("### T2", brief)


if __name__ == "__main__":
    unittest.main()
