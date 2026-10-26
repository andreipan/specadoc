from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "skills" / "specadoc" / "scripts" / "review_snapshot.py"

PLAN = """# Plan

## Tasks

### T1 — Handler

- **Owner:** worker
- **Files:** `src/Handler.php`, `tests/{Unit,Feature}/HandlerTest.php`, `src/Support/` (helpers); config wiring
- [ ] Complete

### T2 — Prose only

- **Owner:** worker
- **Files:** the billing module
- [ ] Complete
"""


class WorkerScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.change = self.repo / "docs" / "specadoc" / "demo"
        self.change.mkdir(parents=True)
        (self.change / "plan.md").write_text(PLAN, encoding="utf-8")
        (self.repo / "src" / "Support").mkdir(parents=True)
        (self.repo / "src" / "Handler.php").write_text("a\n", encoding="utf-8")
        (self.repo / "src" / "Other.php").write_text("a\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / ".gitignore").write_text("docs/\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if key != "SPECADOC_ROOT"}
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
            env=env,
        )

    def baseline(self, task: str = "T1") -> None:
        result = self.run_cli("baseline", "demo", "--task", task)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changes_inside_declared_files_pass(self) -> None:
        self.baseline()
        (self.repo / "src" / "Handler.php").write_text("b\n", encoding="utf-8")
        (self.repo / "tests" / "Feature").mkdir(parents=True)
        (self.repo / "tests" / "Feature" / "HandlerTest.php").write_text("t\n", encoding="utf-8")
        (self.repo / "src" / "Support" / "Clock.php").write_text("c\n", encoding="utf-8")

        result = self.run_cli("check-scope", "demo", "--task", "T1")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["uncheckable"], ["config wiring"])

    def test_change_outside_files_fails(self) -> None:
        self.baseline()
        (self.repo / "src" / "Other.php").write_text("b\n", encoding="utf-8")

        result = self.run_cli("check-scope", "demo", "--task", "T1")

        self.assertEqual(result.returncode, 1)
        violations = json.loads(result.stdout)["violations"]
        self.assertEqual([item["path"] for item in violations], ["src/Other.php"])

    def test_ignored_artifact_edit_fails_but_runs_directory_and_own_plan_are_free(self) -> None:
        self.baseline()
        (self.change / "plan.md").write_text(PLAN + "\nedited\n", encoding="utf-8")
        (self.change / "spec.md").write_text("edited spec\n", encoding="utf-8")
        (self.change / "runs" / "T1-report.md").write_text("report\n", encoding="utf-8")

        result = self.run_cli("check-scope", "demo", "--task", "T1")

        self.assertEqual(result.returncode, 1)
        violations = json.loads(result.stdout)["violations"]
        self.assertEqual([item["path"] for item in violations], ["docs/specadoc/demo/spec.md"])
        self.assertEqual(violations[0]["reason"], "artifact root is controller-owned")

    def test_deleted_file_outside_scope_fails(self) -> None:
        self.baseline()
        (self.repo / "src" / "Other.php").unlink()

        result = self.run_cli("check-scope", "demo", "--task", "T1")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["violations"][0]["change"], "removed")

    def test_check_scope_without_baseline_is_unresolvable(self) -> None:
        result = self.run_cli("check-scope", "demo", "--task", "T1")

        self.assertEqual(result.returncode, 2)
        self.assertIn("no baseline", result.stderr)

    def test_prose_only_files_are_reported_as_uncheckable(self) -> None:
        result = self.run_cli("baseline", "demo", "--task", "T2")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["uncheckable"], ["the billing module"])

    def test_unknown_task_is_unresolvable(self) -> None:
        result = self.run_cli("baseline", "demo", "--task", "T9")

        self.assertEqual(result.returncode, 2)
        self.assertIn("no task T9", result.stderr)


if __name__ == "__main__":
    unittest.main()
