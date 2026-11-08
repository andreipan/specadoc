"""Regressions from orchestrator run 5.1 (connector-gate): tidy edits across tasks, refresh after amend,
a whole-suite run before acceptance, Completion evidence by hand, .DS_Store in Review scope."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from test_run411_regressions import Run411Base
from test_specadoc_step import PLAN

OPEN = (PLAN.replace("- [x] Complete", "- [ ] Complete")
        .replace("### T1 — Ready label\n- [ ] Complete\n- **Requirements:** R1\n- **Risk:** low\n"
                 "- **Decision risk:** low\n- **Owner:** worker\n- **Verification owner:** controller\n"
                 "- **Files:** `label.py`, `check_label.py`",
                 "### T1 — Ready label\n- [ ] Complete\n- **Requirements:** R1\n- **Risk:** low\n"
                 "- **Decision risk:** low\n- **Owner:** worker\n- **Verification owner:** controller\n"
                 "- **Files:** `label.py`, `check_label.py`, `helper.py`")
        .replace("### T2 — String result\n- [ ] Complete\n- **Requirements:** R1\n- **Risk:** low\n"
                 "- **Decision risk:** low\n- **Owner:** worker\n- **Verification owner:** controller\n"
                 "- **Files:** `label.py`, `check_label.py`",
                 "### T2 — String result\n- [ ] Complete\n- **Requirements:** R1\n- **Risk:** low\n"
                 "- **Decision risk:** low\n- **Owner:** worker\n- **Verification owner:** controller\n"
                 "- **Files:** `label.py`, `check_label.py`, `t2.py`")
        .replace("## Review scope\n- `label.py`\n- `check_label.py`\n",
                 "## Review scope\n- `check_label.py`\n- `helper.py`\n- `label.py`\n- `t2.py`\n"))
EVIDENCE = ("## Completion evidence\n\n```text\nCommands:\nPending\n\nRequirement mapping:\nR1 -> Pending\n\n"
            "Execution tokens:\n<per-execution totals collected by collect_tokens.py>\n\nReview rounds:\nPending\n```\n")


class Run51Base(Run411Base):
    def accept_all(self):
        """T1 adds helper.py (only T1 owns it), T2 adds t2.py (only T2 owns it), T3 edits check_label.py."""
        self.plan.write_text(OPEN)
        for task in ("T1", "T2", "T3"):
            dispatched = self.run_step("dispatch", "demo", task)
            self.assertEqual(0, dispatched.returncode, dispatched.stdout)
            if task == "T3":
                check = self.repo.joinpath("check_label.py")
                check.write_text(check.read_text() + "# T3\n")
                files = ("check_label.py",)
            else:
                name = "helper.py" if task == "T1" else "t2.py"
                self.repo.joinpath(name).write_text(f"{task} = 1\n")
                files = (name,)
            self.report(task=task, files=files)
            accepted = self.run_step("accept", "demo", task)
            self.assertEqual(0, accepted.returncode, accepted.stdout)

    def tidy_edits(self):
        # As in 5.1: tidy hoists into T1's file and edits T2's own file; T2 goes stale and, re-accepted,
        # sees helper.py changed outside its Files.
        self.repo.joinpath("helper.py").write_text("T1 = 1  # hoisted\n")
        self.repo.joinpath("t2.py").write_text("T2 = 1  # tidied\n")


class Run51TidyTest(Run51Base):
    def test_recorded_tidy_edits_let_refresh_reaccept_without_amend(self):
        self.accept_all()
        self.assertEqual(0, self.run_step("tidy", "demo").returncode)
        self.tidy_edits()
        recorded = self.run_step("tidy", "demo", "--record", "--summary", "fixed 1: hoisted helper; skipped 0")
        self.assertEqual(0, recorded.returncode, recorded.stdout)
        self.assertIn("tidy edits recorded for every task's scope check: helper.py, t2.py", recorded.stdout)
        self.assertEqual(["helper.py", "t2.py"],
                         json.loads((self.change / "runs/tidy.json").read_text())["changed"])
        refreshed = self.run_step("refresh", "demo")
        self.assertEqual(0, refreshed.returncode, refreshed.stdout)
        self.assertIn("result: PASS", refreshed.stdout)
        self.assertNotIn("outside the task scope", refreshed.stdout)

    def test_unrecorded_edits_point_at_refresh_not_amend(self):
        self.accept_all()
        self.tidy_edits()
        refreshed = self.run_step("refresh", "demo")
        self.assertNotEqual(0, refreshed.returncode, refreshed.stdout)
        self.assertIn("never amend --allow", refreshed.stdout)


class Run51AcceptanceTest(Run51Base):
    def test_refresh_names_tasks_reset_by_amend(self):
        self.accept_all()
        amended = self.run_step("amend", "demo", "T2", "--allow", "helper.py", "--reason", "tidy hoist")
        self.assertEqual(0, amended.returncode, amended.stdout)
        refreshed = self.run_step("refresh", "demo")
        self.assertIn("not accepted: T2 (dispatched)", refreshed.stdout)
        self.assertIn("next: accept demo <task>", refreshed.stdout)
        self.assertNotIn("no stale task evidence; continue", refreshed.stdout)

    def test_final_run_waits_for_accepted_tasks(self):
        self.accept_all()
        self.repo.joinpath(".specadoc.json").write_text(json.dumps(
            {"version": 1, "verification": {"final": ["python3 check_label.py"]}}))
        self.run_step("amend", "demo", "T2", "--allow", "helper.py", "--reason", "tidy hoist")
        result = self.run_step("finalize", "demo", "--run")
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("the whole suite runs once over accepted code", result.stdout)
        self.assertIn("T2 dispatched", result.stdout)
        self.assertFalse((self.change / "runs/final-verification.json").exists())


class Run51CompletionEvidenceTest(Run411Base):
    def test_finalize_fills_derivable_evidence_and_names_tokens(self):
        self.repo.joinpath(".specadoc.json").write_text(json.dumps(
            {"version": 1, "verification": {"final": ["python3 check_label.py"]}}))
        self.plan.write_text(re.sub(r"## Completion evidence\n.*\Z", EVIDENCE, PLAN, flags=re.S))
        first = self.run_step("finalize", "demo", "--run")
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertIn("Completion evidence filled: Commands, Requirement mapping", first.stdout)
        self.assertIn("collect_tokens.py demo --mode <mode> --harness <h> --append", first.stdout)
        self.assertIn("Review rounds (no recorded source yet)", first.stdout)
        text = self.plan.read_text()
        self.assertIn("python3 check_label.py: exit 0 (", text)
        self.assertIn("R1 -> A1 / python3 check_label.py: PASS", text)
        self.assertIn("<per-execution totals collected by collect_tokens.py>", text)
        self.pass_round()
        second = self.run_step("finalize", "demo")
        self.assertIn("Completion evidence filled: Review rounds", second.stdout)
        self.assertIn("G1 initial: PASS", self.plan.read_text())
        self.assertEqual(1, self.plan.read_text().count("python3 check_label.py: exit 0 ("))  # written stays


class Run51ScopeTest(Run411Base):
    def test_scope_leaves_out_os_files_and_excluded_paths(self):
        self.commit_all()
        self.repo.joinpath("label.py").write_text('def label():\n    return "ready!"\n')
        self.repo.joinpath(".DS_Store").write_bytes(b"\0")
        self.repo.joinpath("scratch.txt").write_text("notes\n")
        result = self.run_step("scope", "demo", "--exclude", "scratch.*")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("excluded: .DS_Store, scratch.txt", result.stdout)
        section = self.plan.read_text().split("## Review scope\n")[1].split("## ")[0]
        self.assertEqual(["- `label.py`"], [line for line in section.splitlines() if line.strip()])


class Run51ReferencesTest(unittest.TestCase):
    def test_token_samples_append_and_controllers_dispatch_in_the_foreground(self):
        references = Path(__file__).parents[1] / "skills/specadoc/references"
        samples = [line for line in (references / "measurement.md").read_text().splitlines()
                   if line.startswith("python3 <skill-root>/scripts/collect_tokens.py")]
        self.assertTrue(samples)
        self.assertTrue(all("--append" in line for line in samples), samples)
        routing = " ".join((references / "subagent-routing.md").read_text().split())
        self.assertIn("never with `run_in_background: true`", routing)


if __name__ == "__main__":
    unittest.main()
