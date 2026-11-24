"""A worker records each departure from its brief as it happens (`runs/T<n>-deviations.md`).

AI Dev Live 2026 (coordinator-mode in pragmatic-orchestration): deviations kept only for the final report
section are lost when the worker's own context is compacted, and the controller learns about them late.
"""
from __future__ import annotations

import test_apply_reliability as reliability
from test_run610_regressions import OPEN_PLAN, Base


class WorkerDeviationsTest(Base):
    def setUp(self):
        reliability.ApplyReliabilityTest.setUp(self)
        self.plan.write_text(OPEN_PLAN)
        self.assertEqual(0, self.run_step("dispatch", "demo", "T1").returncode)
        self.log = self.change / "runs/T1-deviations.md"

    def deviate(self, text):
        return self.run_step("deviation", "demo", "T1", "--text", text)

    def write(self, *extra):
        return self.run_step("report", "demo", "T1", "--status", "DONE", "--summary", "Ready diagnostic label",
                             "--red", "check_label.py fails: label is old", "--green", "python3 check_label.py passed",
                             *extra)

    def test_each_deviation_gets_an_id_in_the_live_file(self):
        first = self.deviate("used label() directly; the brief's helper does not exist")
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertIn("recorded T1.d1", first.stdout)
        self.assertIn("--deviation 'T1.d1: kept|reverted: <why>'", first.stdout)
        self.assertEqual(0, self.deviate("kept the old constant name for the callers").returncode)
        lines = self.log.read_text().splitlines()
        self.assertEqual(2, len(lines))
        self.assertRegex(lines[1], r"^- T1\.d2 \([^)]+\): kept the old constant name for the callers$")

    def test_a_vague_long_or_undispatched_deviation_is_refused(self):
        for text in ("changed it", "x " * 250):
            with self.subTest(text=text[:10]):
                self.assertNotEqual(0, self.deviate(text).returncode)
        undispatched = self.run_step("deviation", "demo", "T2", "--text", "renamed the helper for clarity")
        self.assertNotEqual(0, undispatched.returncode)
        self.assertIn("T2 is not dispatched", undispatched.stdout)
        self.assertFalse(self.log.exists())

    def test_a_done_report_needs_a_decision_for_every_deviation(self):
        self.deviate("used label() directly; the brief's helper does not exist")
        self.deviate("kept the old constant name for the callers")
        refused = self.write("--deviation", "T1.d1: reverted: went back to the helper the brief names")
        self.assertEqual(1, refused.returncode, refused.stdout)
        self.assertIn("deviation(s) T1.d2 have no decision", refused.stdout)
        self.assertFalse(self.change.joinpath("runs/T1-report.md").exists())
        unknown = self.write("--deviation", "T1.d9: kept: no such entry here")
        self.assertNotEqual(0, unknown.returncode)
        self.assertIn("T1.d9 is not a recorded deviation of T1", unknown.stdout)
        written = self.write("--deviation", "T1.d1: reverted: went back to the helper the brief names",
                             "--deviation", "T1.d2: kept: callers outside Files still use it")
        self.assertEqual(0, written.returncode, written.stdout)
        report = self.change.joinpath("runs/T1-report.md").read_text()
        self.assertIn("## Deviations\n\n- T1.d1: reverted: used label() directly", report)
        self.assertIn("- T1.d2: kept: kept the old constant name for the callers — callers outside Files", report)
        self.assertIn('"deviation T1.d2 kept: kept the old constant name for the callers', report)

    def test_a_kept_deviation_needs_the_controllers_decision_at_accept(self):
        self.deviate("kept the old constant name for the callers")
        self.assertEqual(0, self.write("--deviation", "T1.d1: kept: callers outside Files still use it").returncode)
        pending = self.run_step("accept", "demo", "T1")
        self.assertEqual(2, pending.returncode, pending.stdout)
        self.assertIn("NEEDS_DECISION", pending.stdout)
        accepted = self.run_step("accept", "demo", "T1", "--note", "keep the constant; rename it in a later change")
        self.assertEqual(0, accepted.returncode, accepted.stdout)

    def test_a_deviation_recorded_after_the_report_blocks_accept(self):
        self.assertEqual(0, self.write().returncode)
        self.deviate("swapped the assertion order after reporting")
        blocked = self.run_step("accept", "demo", "T1")
        self.assertEqual(2, blocked.returncode, blocked.stdout)
        self.assertIn("T1.d1 of runs/T1-deviations.md were recorded after the report", blocked.stdout)

    def test_a_reopen_archives_the_deviations_with_the_report(self):
        self.deviate("kept the old constant name for the callers")
        self.assertEqual(0, self.write("--deviation", "T1.d1: reverted: renamed as the brief says").returncode)
        self.assertEqual(0, self.run_step("accept", "demo", "T1").returncode)
        import sys
        from test_specadoc_step import SCRIPTS
        sys.path.insert(0, str(SCRIPTS))
        import specadoc_step
        attempts = specadoc_step.reopen_attempt(self.change, "T1", "the label must also cover the empty case")
        self.assertFalse(self.log.exists())
        archived = self.change / "runs/T1-deviations-a1.md"
        self.assertTrue(archived.is_file())
        self.assertEqual("T1-deviations-a1.md", attempts[-1]["deviations"])
        specadoc_step.restore_attempt(self.change, "T1", attempts, None)
        self.assertTrue(self.log.is_file())
        self.assertFalse(archived.exists())

    def test_the_code_reviewer_gets_the_decided_deviations(self):
        import os
        import subprocess
        import sys
        from test_specadoc_step import SCRIPTS
        self.deviate("kept the old constant name for the callers")
        self.assertEqual(0, self.write("--deviation", "T1.d1: kept: callers outside Files still use it").returncode)
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "add", "-A"], cwd=self.repo, check=True)
        subprocess.run([*git, "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.repo.joinpath("label.py").write_text('def label():\n    return "set"\n')
        sys.path.insert(0, str(SCRIPTS))
        import specadoc_step
        previous = os.getcwd()
        os.chdir(self.repo)
        try:
            files = specadoc_step.review_files(self.change, "G1", ["label.py"])
        finally:
            os.chdir(previous)
        self.assertTrue(any(path.endswith("G1-deviations.md") for path in files), files)
        text = (self.change / "runs/G1-deviations.md").read_text()
        self.assertIn("- T1.d1: kept: kept the old constant name for the callers — callers outside Files", text)

    def test_the_brief_tells_the_worker_to_record_deviations_as_they_happen(self):
        brief = self.change.joinpath("runs/T1-brief.md").read_text()
        self.assertIn("deviation demo T1 --text '<what and why>'", brief)
        self.assertIn("--deviation '<id>: kept|reverted: <why>'", brief)
