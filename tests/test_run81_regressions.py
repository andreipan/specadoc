"""Regressions from orchestrator runs 7.1, 8.1 and 8.2 (2026-11-18..20).

Design reviews took 8, 11 and 7 rounds: every re-review cited five to seven files no earlier round had
cited, and controllers entered design rounds at 233-373k context because only dispatch measured it.
"""
from __future__ import annotations

import json
import re

from test_run35_regressions import INVENTORY_PLAN
from test_run610_regressions import Base


def finding(severity, origin=None, summary="the lock order is not stated"):
    result = dict(severity=severity, location="plan.md T1", summary=summary, items=["state the lock order"])
    if origin:
        result["origin"] = origin
    return result


class DesignRereviewScopeTest(Base):
    def review(self, verdict, findings):
        path = self.repo / "design.json"
        path.write_text(json.dumps({"verdict": verdict, "report": "r", "findings": findings}))
        return self.run_step("design-review", "demo", "--result-file", "design.json")

    def resolve_all(self):
        ids = sorted(set(re.findall(r"  - (F\d+\.\d+): ", self.plan.read_text())))
        self.repo.joinpath("resolutions.txt").write_text("".join(f"{item}: resolved: plan.md T1\n" for item in ids))
        result = self.run_step("design-resolve", "demo", "--file", "resolutions.txt")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def first_round_failed(self, findings=None):
        self.plan.write_text(INVENTORY_PLAN)
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
        self.assertEqual(1, self.review("FAIL", findings or [finding("IMPORTANT")]).returncode)
        self.resolve_all()
        brief = self.run_step("design-brief", "demo")
        self.assertEqual(0, brief.returncode, brief.stdout)

    def test_a_new_important_outside_the_changes_is_a_note_not_a_fail(self):
        self.first_round_failed()
        result = self.review("FAIL", [finding("IMPORTANT", "new", "HubTransport.php:47 has no byte cap")])
        self.assertEqual(0, result.returncode, result.stdout)
        plan = self.plan.read_text()
        self.assertIn("**Result:** PASS", plan)
        self.assertIn("**Reviewer verdict:** FAIL", plan)
        self.assertIn("### Notes outside the re-review scope", plan)
        self.assertIn("- note (IMPORTANT, outside the changes): plan.md T1 — HubTransport.php:47", plan)
        self.assertNotIn("  - F1.1: state the lock order\n    - resolved", plan.split("**Result:** PASS")[1])

    def test_a_defect_in_the_changes_or_a_kept_item_still_fails(self):
        for origin in ("change", "previous"):
            with self.subTest(origin=origin):
                self.first_round_failed()
                self.assertEqual(1, self.review("FAIL", [finding("IMPORTANT", origin)]).returncode)
                self.assertIn("**Result:** FAIL", self.plan.read_text())

    def test_a_new_blocker_outside_the_changes_still_fails(self):
        self.first_round_failed()
        self.assertEqual(1, self.review("FAIL", [finding("BLOCKER", "new")]).returncode)

    def test_a_whole_review_counts_every_finding(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
        self.assertEqual(1, self.review("FAIL", [finding("IMPORTANT", "new")]).returncode)
        self.assertNotIn("Notes outside", self.plan.read_text())

    def test_a_recorded_brief_cannot_start_another_round(self):
        self.first_round_failed()
        brief = self.change / "runs" / "design-brief.md"
        self.assertTrue(brief.is_file())
        self.review("FAIL", [finding("IMPORTANT", "previous")])
        self.assertFalse(brief.exists())

    def test_continue_past_the_cap_carries_important_items_and_reviews_blockers(self):
        self.plan.write_text(INVENTORY_PLAN)
        mixed = [finding("BLOCKER", summary="the lock is released early"), finding("IMPORTANT")]
        for number in range(4):
            if number:
                self.resolve_all()
            self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
            self.assertEqual(1, self.review("FAIL", mixed).returncode)
        self.resolve_all()
        for _ in range(2):
            result = self.run_step("design-brief", "demo", "--attempt-decision", "continue: orchestrator D15")
            self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("carried 1 IMPORTANT item(s)", result.stdout)
        plan = self.plan.read_text()
        self.assertEqual(1, plan.count("- Design obligation F2.1 (carried after round 4; orchestrator D15)"))
        brief = (self.change / "runs" / "design-brief.md").read_text()
        previous = brief.split("## Previous findings", 1)[1].split("## Changes since", 1)[0]
        self.assertIn("BLOCKER: plan.md T1 — the lock is released early", previous)
        self.assertNotIn("IMPORTANT:", previous)
        self.assertIn("Past the design round cap", brief)

    def test_continue_past_the_cap_without_a_blocker_says_what_happened_to_the_items(self):
        self.plan.write_text(INVENTORY_PLAN)
        for number in range(4):
            if number:
                self.resolve_all()
            self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
            self.assertEqual(1, self.review("FAIL", [finding("IMPORTANT")]).returncode)
        self.resolve_all()
        result = self.run_step("design-brief", "demo", "--attempt-decision", "continue: orchestrator D16")
        self.assertEqual(0, result.returncode, result.stdout)
        brief = (self.change / "runs" / "design-brief.md").read_text()
        self.assertIn("- None: the IMPORTANT items are apply obligations now.", brief)
        self.assertNotIn("changed after a PASS", brief)


class DesignContextBudgetTest(Base):
    def test_design_brief_refuses_at_the_dispatch_guard(self):
        """A fresh controller needs 60-100k before its first step: refusing at the review boundary would have
        handed every high-risk propose of 7.1-8.2 (176-254k) to a new session before round 1."""
        self.plan.write_text(INVENTORY_PLAN)
        refused = self.run_step("design-brief", "demo", "--context-tokens", "233000")
        self.assertEqual(2, refused.returncode, refused.stdout)
        self.assertIn("at least 200k", refused.stdout)
        self.assertIn("handoff demo --file -", refused.stdout)
        self.assertFalse((self.change / "runs" / "design-brief.md").exists())
        allowed = self.run_step("design-brief", "demo", "--context-tokens", "176000")
        self.assertEqual(0, allowed.returncode, allowed.stdout)

    def test_status_advises_at_the_review_boundary_before_a_design_round(self):
        self.plan.write_text(INVENTORY_PLAN)
        status = self.run_step("status", "demo", "--context-tokens", "170000")
        self.assertIn("review boundary", status.stdout)
        self.assertIn("at least 160k; design-brief refuses at 200k", status.stdout)

    def test_project_config_sets_the_context_boundaries(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.repo.joinpath(".specadoc.json").write_text(json.dumps(
            {"version": 1, "context": {"review_boundary": 300000, "dispatch_guard": 350000}}))
        self.assertNotIn("review boundary", self.run_step("status", "demo", "--context-tokens", "250000").stdout)
        self.assertEqual(0, self.run_step("design-brief", "demo", "--context-tokens", "300000").returncode)
        refused = self.run_step("design-brief", "demo", "--context-tokens", "360000")
        self.assertEqual(2, refused.returncode, refused.stdout)
        self.assertIn("at least 350k", refused.stdout)

    def test_project_config_refuses_a_bad_context_value(self):
        self.plan.write_text(INVENTORY_PLAN)
        for context in ({"dispatch_guard": "200k"}, {"dispatch_guard": 500}, {"window": 400000}):
            with self.subTest(context=context):
                self.repo.joinpath(".specadoc.json").write_text(json.dumps({"version": 1, "context": context}))
                result = self.run_step("design-brief", "demo", "--context-tokens", "1000")
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertIn("context", result.stdout + result.stderr)

    def test_design_brief_runs_the_plan_validation_first(self):
        """8.1 r9: a reviewer started on a plan with placeholders was stopped and run again."""
        plan = INVENTORY_PLAN.replace("without changing the interface", "behind <the cache we pick>", 1)
        self.assertNotEqual(plan, INVENTORY_PLAN)
        self.plan.write_text(plan)
        refused = self.run_step("design-brief", "demo")
        self.assertNotEqual(0, refused.returncode, refused.stdout)
        self.assertIn("plan validation", refused.stdout)
        self.assertFalse((self.change / "runs" / "design-brief.md").exists())
