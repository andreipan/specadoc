"""Regressions from orchestrator runs 7.1-8.2 and 6.16-6.17 (2026-11-18..24): the must-not-ship rule.

After `origin` (bad7719) a re-review raised no new topics, yet 6.17 round 2 had more BLOCKERs than round 1
(two missing test cases, a spec promise the code cannot keep), and 7.1, 8.1 and 8.2 took 8, 11 and 7
design rounds. From design round 3 only must-not-ship findings (data, money, access, user path, a silently
wrong result) hold the design; a BLOCKER or IMPORTANT of class `other` becomes an apply obligation that a
task names and the code reviewer checks (8.2 r5 found a real privacy defect late).
"""
from __future__ import annotations

import json
import re
import sys

from test_run35_regressions import INVENTORY_PLAN
from test_run610_regressions import Base
from test_specadoc_step import SCRIPTS


def finding(severity, cls=None, summary="the lock order is not stated", items=("state the lock order",)):
    result = dict(severity=severity, location="plan.md T1", summary=summary, items=list(items))
    if cls:
        result["class"] = cls
    return result


OTHER = [finding("BLOCKER", "other", "two test cases are missing", ("no rejected-name test", "no role test")),
         finding("IMPORTANT", "other", "the spec promises a check the code cannot keep", ())]


class MustNotShipTest(Base):
    def review(self, verdict, findings):
        path = self.repo / "design.json"
        path.write_text(json.dumps({"verdict": verdict, "report": "r", "findings": findings}))
        return self.run_step("design-review", "demo", "--result-file", "design.json")

    def resolve_all(self):
        ids = sorted(set(re.findall(r"  - (F\d+\.\d+): ", self.plan.read_text())))
        self.repo.joinpath("resolutions.txt").write_text("".join(f"{item}: resolved: plan.md T1\n" for item in ids))
        result = self.run_step("design-resolve", "demo", "--file", "resolutions.txt")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def failed_rounds(self, count, findings):
        """`count` recorded FAIL rounds with `findings`; every item answered after the last one."""
        self.plan.write_text(INVENTORY_PLAN)
        for number in range(count):
            if number:
                self.resolve_all()
            brief = self.run_step("design-brief", "demo")
            self.assertEqual(0, brief.returncode, brief.stdout)
            self.assertEqual(1, self.review("FAIL", findings).returncode)
        self.resolve_all()

    def accepted_round_three(self):
        self.failed_rounds(2, OTHER)
        brief = self.run_step("design-brief", "demo")
        self.assertEqual(0, brief.returncode, brief.stdout)
        self.assertIn("This is design round 3", (self.change / "runs/design-brief.md").read_text())
        result = self.review("FAIL", OTHER)
        self.assertEqual(0, result.returncode, result.stdout)
        return result

    def test_round_three_defers_findings_of_class_other_and_accepts_the_design(self):
        result = self.accepted_round_three()
        plan = self.plan.read_text()
        self.assertIn("**Result:** ACCEPTED\n**Accepted by:** must-not-ship rule after design round 2", plan)
        self.assertIn("**Reviewer verdict:** FAIL (findings of class `other` are apply obligations", plan)
        self.assertIn("- Design obligation R3.1 (deferred in design round 3, not must-not-ship; BLOCKER): "
                      "plan.md T1 — no rejected-name test", plan)
        self.assertIn("- Design obligation R3.3 (deferred in design round 3, not must-not-ship; IMPORTANT): "
                      "plan.md T1 — the spec promises a check the code cannot keep", plan)
        self.assertIn("### Deferred to apply (not must-not-ship)\n\n- R3.1 (deferred", plan)
        self.assertIn("accepted by the must-not-ship rule", result.stdout)
        self.assertIn("R3.1, R3.2, R3.3", result.stdout)
        self.assertIn("**Obligations:**", result.stdout)
        rounds = json.loads((self.change / "runs/design-round.json").read_text())["rounds"]
        self.assertEqual({"round": 3, "verdict": "ACCEPTED", "reviewer_verdict": "FAIL", "BLOCKER": 0,
                          "IMPORTANT": 0, "MINOR": 0, "deferred": 2, "notes": 0, "classes": {"other": 2}}, rounds[-1])
        self.assertEqual(["FAIL", "FAIL", "ACCEPTED"], [entry["verdict"] for entry in rounds])
        sys.path.insert(0, str(SCRIPTS))
        import design_gate
        self.assertEqual("Design rounds: r1 FAIL B1/I1/M0, r2 FAIL B1/I1/M0, r3 ACCEPTED B0/I0/M0 +2 deferred",
                         design_gate.rounds_line(self.change))

    def test_rounds_one_and_two_count_every_class(self):
        self.failed_rounds(1, OTHER)
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
        self.assertEqual(1, self.review("FAIL", OTHER).returncode)
        plan = self.plan.read_text()
        self.assertIn("**Result:** FAIL", plan)
        self.assertIn("- BLOCKER [other]: plan.md T1 — two test cases are missing", plan)
        self.assertNotIn("Design obligation", plan)

    def test_a_must_not_ship_finding_still_fails_round_three_and_the_rest_is_deferred(self):
        self.failed_rounds(2, OTHER)
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
        leak = finding("BLOCKER", "access", "a member reads another organization's audit events",
                       ("the query has no organization filter",))
        result = self.review("FAIL", [leak, OTHER[1]])
        self.assertEqual(1, result.returncode, result.stdout)
        plan = self.plan.read_text()
        self.assertIn("**Result:** FAIL", plan)
        self.assertIn("- BLOCKER [access]: plan.md T1 — a member reads another organization's audit events\n"
                      "  - F1.1: the query has no organization filter", plan)
        self.assertIn("- Design obligation R3.1 (deferred in design round 3, not must-not-ship; IMPORTANT)", plan)
        self.assertIn("close every item (F1.1) in this pass", result.stdout)

    def test_unclassified_findings_are_never_deferred_and_need_no_method(self):
        """A reviewer that sets no class keeps the earlier behavior."""
        self.failed_rounds(2, [finding("BLOCKER")])
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
        self.assertEqual(1, self.review("FAIL", [finding("BLOCKER")]).returncode)
        plan = self.plan.read_text()
        self.assertIn("**Result:** FAIL", plan)
        self.assertNotIn("Design obligation", plan)

    def test_a_round_past_two_with_must_not_ship_items_open_needs_a_new_method(self):
        sweep = [finding("BLOCKER", "data", "the sweep deletes a logo still in use", ("canonical path rule",))]
        self.failed_rounds(2, sweep)
        blocked = self.run_step("design-brief", "demo")
        self.assertEqual(2, blocked.returncode, blocked.stdout)
        self.assertIn("1 must-not-ship finding(s) open", blocked.stdout)
        self.assertIn("--verify-by", blocked.stdout)
        self.assertFalse((self.change / "runs/design-brief.md").exists())
        vague = self.run_step("design-brief", "demo", "--verify-by", "spike")
        self.assertEqual(2, vague.returncode, vague.stdout)
        self.assertIn("three words or more", vague.stdout)
        allowed = self.run_step("design-brief", "demo", "--verify-by", "spike test of the sweep path")
        self.assertEqual(0, allowed.returncode, allowed.stdout)
        self.assertIn("- Design round method: round 3 — spike test of the sweep path", self.plan.read_text())
        self.assertIn("Round method: spike test of the sweep path", (self.change / "runs/design-brief.md").read_text())
        self.assertEqual(1, self.review("FAIL", sweep).returncode)
        self.resolve_all()
        repeated = self.run_step("design-brief", "demo", "--verify-by", "Spike test of the  sweep path")
        self.assertEqual(2, repeated.returncode, repeated.stdout)
        self.assertIn("repeats an earlier method", repeated.stdout)
        other = self.run_step("design-brief", "demo", "--verify-by", "user decides the cleanup contract")
        self.assertEqual(0, other.returncode, other.stdout)

    def test_a_full_review_after_a_redesign_needs_no_method(self):
        self.failed_rounds(2, [finding("BLOCKER", "data", "the sweep deletes a logo still in use")])
        full = self.run_step("design-brief", "demo", "--full")
        self.assertEqual(0, full.returncode, full.stdout)

    def test_every_obligation_is_named_by_a_task_before_approval(self):
        self.accepted_round_three()
        validated = self.validate("plan")
        self.assertIn("R3.1, R3.2, R3.3", validated.stderr)
        self.assertIn("named by no task", validated.stderr)
        refused = self.run_step("approve", "demo", "--by", "user", "--source", "User said approve")
        self.assertEqual(2, refused.returncode, refused.stdout)
        self.assertIn("are named by no task", refused.stdout)
        plan = self.plan.read_text()
        self.plan.write_text(plan.replace("- **Implementation:** Return ready",
                                          "- **Implementation:** Return ready\n- **Obligations:** R3.1, R3.4", 1))
        unknown = self.validate("plan")
        self.assertNotEqual(0, unknown.returncode)
        self.assertIn("T1: **Obligations:** names ids", unknown.stdout + unknown.stderr)
        self.assertIn("unknown: R3.4", unknown.stdout + unknown.stderr)
        self.plan.write_text(plan.replace("- **Implementation:** Return ready",
                                          "- **Implementation:** Return ready\n- **Obligations:** R3.1, R3.2,\n"
                                          "  R3.3", 1))
        named = self.validate("plan")
        self.assertNotIn("named by no task", named.stderr)
        self.assertNotIn("Obligations:", named.stdout + named.stderr)

    def test_the_worker_brief_and_the_code_review_files_carry_the_obligations(self):
        self.accepted_round_three()
        plan = self.plan.read_text()
        self.plan.write_text(plan.replace("- **Implementation:** Return ready",
                                          "- **Implementation:** Return ready\n- **Obligations:** R3.3", 1))
        sys.path.insert(0, str(SCRIPTS))
        import task_brief
        brief = task_brief.build_brief(self.change, "T1")
        self.assertIn("## Design obligations", brief)
        self.assertIn("- Design obligation R3.3 (deferred in design round 3", brief)
        self.assertNotIn("R3.1 (", brief)
        self.assertNotIn("## Design obligations", task_brief.build_brief(self.change, "T2"))
        import os
        import subprocess
        import specadoc_step
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "add", "-A"], cwd=self.repo, check=True)
        subprocess.run([*git, "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.repo.joinpath("label.py").write_text('def label():\n    return "set"\n')
        previous = os.getcwd()
        os.chdir(self.repo)
        try:
            files = specadoc_step.review_files(self.change, "G1", ["label.py"])
        finally:
            os.chdir(previous)
        obligations = [path for path in files if path.endswith("G1-obligations.md")]
        self.assertEqual(1, len(obligations), files)
        text = (self.change / "runs/G1-obligations.md").read_text()
        self.assertIn("an unmet one is an IMPORTANT finding", text)
        self.assertIn("- Design obligation R3.1", text)
