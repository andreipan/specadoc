"""Regressions from the iam-password-recovery 3.5 run review (November 2026)."""
from __future__ import annotations

import json
import unittest

import test_apply_reliability as reliability
from test_specadoc_step import PLAN

# T2 owns a second file; both tasks overlap on label.py like 3.5's shared providers.
OVERLAP_PLAN = PLAN.replace('- **Files:** `label.py`, `check_label.py`\n- **Test first:** Assert ready label\n'
                            '- **Expected RED:** Old label is not ready\n- **Implementation:** Return ready\n'
                            '- **Verification:** `python3 check_label.py`\n- **Surface:** code\n'
                            '- **Delivery verification:** N/A\n- **Done when:** Assertion passes\n'
                            '- **Evidence:** python3 check_label.py: PASS after observed RED\n### T3',
                            '- **Files:** `label.py`, `extra.py`\n- **Test first:** Assert ready label\n'
                            '- **Expected RED:** Old label is not ready\n- **Implementation:** Return ready\n'
                            '- **Verification:** `python3 check_label.py`\n- **Surface:** code\n'
                            '- **Delivery verification:** N/A\n- **Done when:** Assertion passes\n'
                            '- **Evidence:** python3 check_label.py: PASS after observed RED\n### T3')


class StaleEvidenceAfterLaterTasksTest(unittest.TestCase):
    setUp = reliability.ApplyReliabilityTest.setUp
    tearDown = reliability.ApplyReliabilityTest.tearDown
    run_step = reliability.ApplyReliabilityTest.run_step
    report = reliability.ApplyReliabilityTest.report

    def accept_t1_then_start_t2(self):
        self.assertNotEqual(PLAN, OVERLAP_PLAN)
        self.plan.write_text(OVERLAP_PLAN)
        self.repo.joinpath('extra.py').write_text('x = 1\n')
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        result = self.run_step('dispatch', 'demo', 'T2')
        self.assertEqual(0, result.returncode, result.stdout)
        self.repo.joinpath('extra.py').write_text('x = 2\n')

    def state(self, task):
        return json.loads(self.change.joinpath(f'runs/{task}-baseline.json').read_text())

    def test_later_task_edit_is_attributed_not_a_scope_violation(self):
        self.accept_t1_then_start_t2()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('attributed to later tasks: T2 extra.py', result.stdout)
        self.assertNotIn('extra.py', result.stdout.split('changed files:')[1].splitlines()[0])

    def test_edit_outside_every_later_scope_still_fails(self):
        self.accept_t1_then_start_t2()
        self.repo.joinpath('other.py').write_text('y = 1\n')
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("other.py (outside the task's Files)", result.stdout)
        self.assertNotIn('extra.py (outside', result.stdout)

    def test_earlier_dispatched_task_does_not_absorb_changes(self):
        self.plan.write_text(OVERLAP_PLAN)
        self.repo.joinpath('extra.py').write_text('x = 1\n')
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T2').returncode)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.assertLess(self.state('T2')['sequence'], self.state('T1')['sequence'])
        self.repo.joinpath('extra.py').write_text('x = 2\n')
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("extra.py (outside the task's Files)", result.stdout)

    def test_refresh_reaccepts_stale_evidence_without_reopen(self):
        self.accept_t1_then_start_t2()
        result = self.run_step('pre-review', 'demo', '--dry-run')
        self.assertIn('T1: Evidence predates a later change', result.stdout)
        result = self.run_step('refresh', 'demo')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('T1 accepted (verification inputs changed: extra.py)', result.stdout)
        state = self.state('T1')
        self.assertEqual('accepted', state['state'])
        self.assertNotIn('attempts', state)
        self.assertTrue(self.change.joinpath('runs/T1-report.md').is_file())
        again = self.run_step('refresh', 'demo')
        self.assertEqual(0, again.returncode, again.stdout)
        self.assertIn('no stale task evidence', again.stdout)

    def test_refresh_refuses_changed_verification(self):
        self.plan.write_text(OVERLAP_PLAN)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        self.plan.write_text(self.plan.read_text().replace('`python3 check_label.py`', '`python3 -B check_label.py`', 1))
        result = self.run_step('refresh', 'demo')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('Verification changed since acceptance', result.stdout)
        self.assertIn('--reopen', result.stdout)


if __name__ == '__main__':
    unittest.main()
