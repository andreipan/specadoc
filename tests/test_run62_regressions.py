"""Regressions from orchestrator run 6.1 + 6.2 (organization-services, organization-oauth-profile-read):
a planned inventory file that no task created passed accept, a DONE report written with a scope FAIL
released `wait` while the worker still worked, a review round opened without files added during apply,
and macOS's Python 3.9 failed deep inside a step."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from test_run35_regressions import INVENTORY_PLAN
from test_run411_regressions import Run411Base
from test_run51_regressions import Run51Base
from test_specadoc_step import SCRIPTS


class Run62Base(Run411Base):
    def design_pass(self):
        path = self.repo / "design.json"
        path.write_text(json.dumps({"verdict": "PASS", "report": "One port for one boundary.", "findings": []}))
        result = self.run_step("design-review", "demo", "--result-file", "design.json")
        self.assertEqual(0, result.returncode, result.stdout)

    def write_report(self, task="T1", status="DONE"):
        return self.run_step("report", "demo", task, "--status", status, "--summary", "label() returns ready",
                             "--red", "check_label.py failed on the old label", "--green", "python3 check_label.py passed")


class Run62MissingInventoryTest(Run62Base):
    def test_accept_fails_before_verification_when_a_planned_file_is_missing(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.design_pass()
        self.assertEqual(0, self.run_step("dispatch", "demo", "T1").returncode)
        self.report(files=("label.py",))
        result = self.run_step("accept", "demo", "T1")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("src/port.py (Class inventory file not created)", result.stdout)
        self.assertIn("blocking reason: Class inventory files not created", result.stdout)
        self.assertNotIn("python3 check_label.py", result.stdout.split("result:", 1)[0])
        manifest = self.run_step("manifest", "demo", "T1")
        self.assertEqual(1, manifest.returncode, manifest.stdout)
        self.assertIn("src/port.py (Class inventory file not created)", manifest.stdout)
        review = self.run_step("pre-review", "demo", "--dry-run")
        self.assertIn("Class inventory file not created: src/port.py", review.stdout)
        self.repo.joinpath("src").mkdir()
        self.repo.joinpath("src/port.py").write_text("class Port: ...\n")
        self.report(files=("src/port.py",))
        accepted = self.run_step("accept", "demo", "T1")
        self.assertEqual(0, accepted.returncode, accepted.stdout)

    def test_a_file_another_unaccepted_task_covers_is_not_counted(self):
        plan = INVENTORY_PLAN.replace("### T2 — String result\n- [x] Complete\n- **Requirements:** R1\n"
                                      "- **Risk:** low\n- **Decision risk:** low\n- **Owner:** worker\n"
                                      "- **Verification owner:** controller\n- **Files:** `label.py`, `check_label.py`",
                                      "### T2 — String result\n- [x] Complete\n- **Requirements:** R1\n"
                                      "- **Risk:** low\n- **Decision risk:** low\n- **Owner:** worker\n"
                                      "- **Verification owner:** controller\n- **Files:** `label.py`, `check_label.py`, "
                                      "`src/`", 1)
        self.assertNotEqual(INVENTORY_PLAN, plan)
        self.plan.write_text(plan)
        self.design_pass()
        self.assertEqual(0, self.run_step("dispatch", "demo", "T1").returncode)
        self.report(files=("label.py",))
        accepted = self.run_step("accept", "demo", "T1")
        self.assertEqual(0, accepted.returncode, accepted.stdout)
        self.assertNotIn("not created", accepted.stdout)


class Run62ReportTest(Run62Base):
    def test_a_done_report_with_a_scope_violation_is_not_written(self):
        self.assertEqual(0, self.run_step("dispatch", "demo", "T1").returncode)
        self.repo.joinpath("stray.py").write_text("STRAY = 1\n")
        report = self.change / "runs/T1-report.md"
        result = self.write_report()
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("stray.py", result.stdout)
        self.assertIn("report not written", result.stdout)
        self.assertFalse(report.exists())
        waited = self.run_step("wait", "demo", "T1", "--timeout", "1")
        self.assertEqual(2, waited.returncode, waited.stdout)
        # A worker that cannot resolve it says so; that report is written for the controller.
        asked = self.write_report(status="NEEDS_CONTEXT")
        self.assertEqual(1, asked.returncode, asked.stdout)
        self.assertTrue(report.exists())
        self.repo.joinpath("stray.py").unlink()
        done = self.write_report()
        self.assertEqual(0, done.returncode, done.stdout)

    def test_a_done_report_without_a_planned_file_is_not_written(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.design_pass()
        self.assertEqual(0, self.run_step("dispatch", "demo", "T1").returncode)
        result = self.write_report()
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("src/port.py (Class inventory file not created)", result.stdout)
        self.assertFalse((self.change / "runs/T1-report.md").exists())


class Run62PreReviewScopeTest(Run51Base):
    def test_pre_review_blocks_when_a_file_added_during_apply_is_not_in_review_scope(self):
        self.accept_all()
        self.repo.joinpath("late.py").write_text("LATE = 1\n")
        refreshed = self.run_step("refresh", "demo", "--controller-path", "late.py", "--reason", "G1 fix: late file")
        self.assertEqual(0, refreshed.returncode, refreshed.stdout)
        blocked = self.run_step("pre-review", "demo", "--dry-run")
        self.assertEqual(2, blocked.returncode, blocked.stdout)
        self.assertIn("files added during apply are missing from Review scope", blocked.stdout)
        self.assertIn("late.py", blocked.stdout)
        self.repo.joinpath(".DS_Store").write_text("junk")
        self.repo.joinpath("late.py").unlink()
        passed = self.run_step("pre-review", "demo", "--dry-run")
        self.assertNotIn("missing from Review scope", passed.stdout)


class Run62DesignBriefTest(Run62Base):
    def test_design_brief_asks_for_folder_rules_and_verified_component_claims(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
        text = self.change.joinpath("runs/design-brief.md").read_text()
        self.assertIn("folder and naming rules", text)
        self.assertIn("cite file:line", text)


class Run62PythonVersionTest(unittest.TestCase):
    def test_old_python_gets_a_clear_error(self):
        old = shutil.which("python3.9") or ("/usr/bin/python3" if Path("/usr/bin/python3").exists() else None)
        if old is None:
            self.skipTest("no Python older than 3.10 here")
        version = subprocess.run([old, "-c", "import sys; print(sys.version_info >= (3, 10))"],
                                 capture_output=True, text=True).stdout.strip()
        if version != "False":
            self.skipTest(f"{old} is 3.10 or newer")
        result = subprocess.run([old, "-B", str(SCRIPTS / "specadoc_step.py"), "status", "demo"],
                                capture_output=True, text=True)
        self.assertEqual(2, result.returncode)
        self.assertIn("Specadoc scripts need Python 3.10+", result.stderr)


if __name__ == "__main__":
    unittest.main()
