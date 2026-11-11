"""Regressions from orchestrator run 5.2 (connector-hub): a reopen after an accepted fix of a tidied
file, refused reopens that still counted an attempt, Completion evidence that kept the first fill."""
from __future__ import annotations

import json
import re
import unittest

from test_run411_regressions import Run411Base
from test_run51_regressions import EVIDENCE, Run51Base
from pathlib import Path

from test_specadoc_step import PLAN, SCRIPTS

OLD = "2000-01-01T00:00:00+00:00"
FUTURE = "2999-01-01T00:00:00+00:00"


class Run52ReopenTest(Run51Base):
    def controller_changes(self, payload):
        self.change.joinpath("runs/controller-changes.json").write_text(json.dumps(payload))

    def test_reopen_after_an_accepted_fix_of_a_tidied_file_is_in_scope(self):
        self.accept_all()
        self.repo.joinpath("helper.py").write_text("T1 = 1  # hoisted\n")
        recorded = self.run_step("refresh", "demo", "--controller-path", "helper.py", "--reason", "tidy: hoist")
        self.assertEqual(0, recorded.returncode, recorded.stdout)
        # The tidy pass happened well before the review fixes.
        path = self.change / "runs/controller-changes.json"
        payload = json.loads(path.read_text())
        for entry in payload["history"]:
            entry["at"] = OLD
        path.write_text(json.dumps(payload))
        reopened = self.run_step("dispatch", "demo", "T1", "--reopen", "G1 BLOCKER: helper edge case")
        self.assertEqual(0, reopened.returncode, reopened.stdout)
        self.repo.joinpath("helper.py").write_text("T1 = 2  # G1 fix\n")
        self.report(task="T1", files=("helper.py",))
        self.assertEqual(0, self.run_step("accept", "demo", "T1").returncode)
        second = self.run_step("dispatch", "demo", "T2", "--reopen", "G1 BLOCKER: t2 edge case")
        self.assertEqual(0, second.returncode, second.stdout)
        self.assertNotIn("outside the task scope", second.stdout)
        self.assertIn("reopened as attempt 2", second.stdout)

    def test_refused_reopen_records_no_attempt(self):
        self.accept_all()
        # A controller edit recorded after this dispatch whose file no longer matches: the scope check fails.
        self.controller_changes({"changes": {"helper.py": "0" * 64},
                                 "history": [{"at": FUTURE, "paths": ["helper.py"], "reason": "x"}]})
        refused = self.run_step("dispatch", "demo", "T2", "--reopen", "G1 BLOCKER: t2 edge case")
        self.assertEqual(1, refused.returncode, refused.stdout)
        self.assertIn("changes outside the task scope", refused.stdout)
        self.assertIn("reopen rolled back: attempt 2 not recorded", refused.stdout)
        record = json.loads(self.change.joinpath("runs/T2-baseline.json").read_text())
        self.assertNotIn("attempts", record)
        self.assertTrue(self.change.joinpath("runs/T2-report.md").is_file())
        self.assertFalse(self.change.joinpath("runs/T2-report-a1.md").exists())
        self.controller_changes({"changes": {}, "history": []})
        reopened = self.run_step("dispatch", "demo", "T2", "--reopen", "G1 BLOCKER: t2 edge case")
        self.assertEqual(0, reopened.returncode, reopened.stdout)
        self.assertIn("reopened as attempt 2", reopened.stdout)
        attempts = json.loads(self.change.joinpath("runs/T2-baseline.json").read_text())["attempts"]
        self.assertEqual(1, len(attempts))


class Run52CompletionEvidenceTest(Run411Base):
    def test_finalize_rewrites_state_owned_blocks_and_takes_residual_risks(self):
        self.repo.joinpath(".specadoc.json").write_text(json.dumps(
            {"version": 1, "verification": {"final": ["python3 check_label.py"]}}))
        evidence = EVIDENCE.replace("Review rounds:\nPending\n",
                                    "Review rounds:\nG1 initial: FAIL, 4 finding(s)\n\n"
                                    "Residual risks or waivers:\nPending\n")
        self.plan.write_text(re.sub(r"## Completion evidence\n.*\Z", evidence, PLAN, flags=re.S))
        self.pass_round()
        first = self.run_step("finalize", "demo", "--run")
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertIn("Review rounds (refreshed)", first.stdout)
        self.assertIn("finalize demo --residual '<risks and waivers, or none>'", first.stdout)
        text = self.plan.read_text()
        self.assertIn("G1 initial: PASS", text)
        self.assertNotIn("4 finding(s)", text)
        second = self.run_step("finalize", "demo", "--residual", "none")
        self.assertIn("Completion evidence filled: Residual risks or waivers", second.stdout)
        text = self.plan.read_text()
        self.assertIn("Residual risks or waivers:\nnone\n", text)
        self.assertEqual(1, text.count("python3 check_label.py: exit 0 ("))



class Run52DesignBriefTest(Run411Base):
    def test_design_brief_asks_for_tests_of_value_shape_rules_and_shows_the_matrix(self):
        from test_run35_regressions import INVENTORY_PLAN
        self.plan.write_text(INVENTORY_PLAN)
        brief = self.run_step("design-brief", "demo")
        self.assertEqual(0, brief.returncode, brief.stdout)
        text = self.change.joinpath("runs/design-brief.md").read_text()
        self.assertIn("explicit null versus absent", text)
        self.assertIn("empty object versus empty list", text)
        self.assertIn("one accepted and one rejected value", text)
        self.assertIn("## Requirement-to-check matrix", text)
        matrix = text.split("## Requirement-to-check matrix", 1)[1].split("\n## ", 1)[0]
        self.assertIn("R1", matrix)


class Run52ScoutChoiceTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)

    def init(self, *args):
        import os
        import subprocess
        import sys
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("SPECADOC_ROOT", None)
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "init_change.py"), "demo", *args],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def test_init_change_needs_a_scout_choice_and_records_it(self):
        missing = self.init("--risk", "low")
        self.assertEqual(2, missing.returncode)
        self.assertIn("--scout", missing.stderr)
        self.assertFalse(self.repo.joinpath("docs/specadoc/demo").exists())
        created = self.init("--risk", "low", "--scout", "scout agent a1b2: Hub client and connector map")
        self.assertEqual(0, created.returncode, created.stderr)
        plan = self.repo.joinpath("docs/specadoc/demo/plan.md").read_text()
        self.assertIn("**Scout:** scout agent a1b2: Hub client and connector map  \n", plan)
        reused = self.init("--risk", "low", "--no-scout", "explore evidence in runs/explore.md", "--force")
        self.assertEqual(0, reused.returncode, reused.stderr)
        plan = self.repo.joinpath("docs/specadoc/demo/plan.md").read_text()
        self.assertIn("**Scout:** none: explore evidence in runs/explore.md", plan)


if __name__ == "__main__":
    unittest.main()
