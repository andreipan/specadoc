"""Regressions from orchestrator run 6.3 + 6.4 (organization-authorization-link, organization-oauth-profile-write):
`collect_tokens --append` kept the `Pending` line under Execution tokens and the final gate refused the plan,
plan validation passed an `Open decisions: None (…)` line that dispatch then refused, and a `wait` timeout
called a running worker BLOCKED."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from test_collect_tokens import load_module as load_collect_tokens
from test_run411_regressions import Run411Base
from test_specadoc_step import PLAN, SCRIPTS

OPEN_TASK = PLAN.replace("- [x] Complete", "- [ ] Complete", 1)


def with_open_decisions(value: str) -> str:
    return OPEN_TASK.replace("- **Owner:** worker", f"- **Owner:** worker\n- **Open decisions:** {value}", 1)


def load_validate():
    spec = importlib.util.spec_from_file_location("validate_change", SCRIPTS / "validate_change.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("validate_change", module)
    spec.loader.exec_module(module)
    return module


class Run64TokensTest(unittest.TestCase):
    def test_append_replaces_the_pending_line_under_execution_tokens_only(self):
        collect = load_collect_tokens()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.md"
            plan.write_text("## Completion evidence\n\nExecution tokens:\nPending\n\nReview rounds:\nPending\n")
            collect.append_to_plan(plan, ["mode=apply claude run", "total mode=apply claude 1 run(s)"], "apply")
            text = plan.read_text()
        self.assertIn("Execution tokens:\ntotal mode=apply claude 1 run(s)\n", text)
        self.assertIn("Review rounds:\nPending\n", text)

    def test_the_template_marks_execution_tokens_pending_like_the_other_blocks(self):
        template = (SCRIPTS.parent / "assets/plan-template.md").read_text()
        self.assertIn("Execution tokens:\nPending\n", template)


class Run64OpenDecisionsTest(Run411Base):
    def test_one_rule_decides_whether_open_decisions_are_closed(self):
        error = load_validate().open_decisions_error
        for closed in ("None", "none", "None (Q1 settled by D25)", "None; see D25", "n/a", "нет", "-", "", None):
            self.assertIsNone(error("T2", closed), closed)
        for still_open in ("choose the error code", "None yet, choose the error code", "Q1"):
            self.assertIn("T2: unresolved decisions", error("T2", still_open) or "", still_open)

    def test_a_note_after_none_passes_plan_validation_and_dispatch(self):
        self.plan.write_text(with_open_decisions("None (Q1 settled by D25)"))
        self.assertNotIn("unresolved decisions", self.validate("plan").stdout)
        result = self.run_step("dispatch", "demo", "T1")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_an_open_decision_of_a_worker_task_fails_plan_validation_before_dispatch_does(self):
        self.plan.write_text(with_open_decisions("choose the error code"))
        validated = self.validate("plan")
        self.assertNotEqual(0, validated.returncode, validated.stdout)
        self.assertIn("T1: unresolved decisions: choose the error code", validated.stdout)
        dispatched = self.run_step("dispatch", "demo", "T1")
        self.assertNotEqual(0, dispatched.returncode, dispatched.stdout)
        self.assertIn("T1: unresolved decisions: choose the error code", dispatched.stdout)


class Run64WaitTest(Run411Base):
    def test_a_wait_timeout_says_waiting_not_blocked(self):
        result = self.run_step("wait", "demo", "T1", "--timeout", "0.2", "--interval", "0.1")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("result: WAITING", result.stdout)
        self.assertNotIn("result: BLOCKED", result.stdout)


if __name__ == "__main__":
    unittest.main()
