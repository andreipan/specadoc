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


EXTERNAL_PLAN = PLAN.replace(
    '- **Verification:** `python3 check_label.py`\n',
    '- **Verification:** `python3 check_label.py`\n'
    '- **External verification:** Parent runs the MySQL integration suite after the user allows it.\n', 1)


class ExternalVerificationTest(unittest.TestCase):
    """3.5 deadlock: review needed T6 accepted, T6 needed an integration run allowed only after review."""
    setUp = reliability.ApplyReliabilityTest.setUp
    tearDown = reliability.ApplyReliabilityTest.tearDown
    run_step = reliability.ApplyReliabilityTest.run_step
    report = reliability.ApplyReliabilityTest.report
    state = StaleEvidenceAfterLaterTasksTest.state

    def validate(self, phase):
        import os
        import subprocess
        import sys
        from test_specadoc_step import SCRIPTS
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'validate_change.py'), 'demo', '--phase', phase],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def accept_local(self):
        self.plan.write_text(EXTERNAL_PLAN)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        return result

    def t1_block(self):
        text = self.plan.read_text()
        return text.split('### T1', 1)[1].split('### T2', 1)[0]

    def test_accept_waits_for_external_result_but_review_may_open(self):
        result = self.accept_local()
        self.assertIn('result: EXTERNAL-PENDING', result.stdout)
        self.assertIn('external-result demo T1', result.stdout)
        self.assertEqual('external-pending', self.state('T1')['state'])
        self.assertIn('- [ ] Complete', self.t1_block())
        self.assertIn('**Evidence:** `python3 check_label.py` — PASS', self.t1_block())
        review = self.run_step('pre-review', 'demo', '--dry-run')
        self.assertEqual(0, review.returncode, review.stdout)
        final = self.validate('final')
        self.assertIn('T1: external verification result missing', final.stdout + final.stderr)

    def test_external_pass_completes_the_task(self):
        self.accept_local()
        result = self.run_step('external-result', 'demo', 'T1', '--outcome', 'PASS',
                               '--evidence', 'it-3.5-2: 12 tests OK on adraptor_it_testing')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('accepted', self.state('T1')['state'])
        self.assertIn('- [x] Complete', self.t1_block())
        self.assertIn('**External evidence:** PASS: it-3.5-2', self.t1_block())
        final = self.validate('final')
        self.assertNotIn('T1: external verification', final.stdout + final.stderr)
        # Unchanged content keeps the external PASS on a later re-accept ...
        again = self.run_step('accept', 'demo', 'T1')
        self.assertIn('result: ACCEPTED', again.stdout)
        # ... changed content needs a new external run.
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # changed\n')
        changed = self.run_step('accept', 'demo', 'T1')
        self.assertIn('result: EXTERNAL-PENDING', changed.stdout)

    def test_external_fail_returns_task_to_work(self):
        self.accept_local()
        result = self.run_step('external-result', 'demo', 'T1', '--outcome', 'FAIL',
                               '--evidence', 'it-3.5-1: replay assertion failed')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertEqual('dispatched', self.state('T1')['state'])
        self.assertIn('--reopen', result.stdout)
        self.assertIn('- [ ] Complete', self.t1_block())

    def test_external_result_needs_real_evidence_and_pending_state(self):
        self.accept_local()
        result = self.run_step('external-result', 'demo', 'T1', '--outcome', 'PASS', '--evidence', 'pending')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertEqual('external-pending', self.state('T1')['state'])
        result = self.run_step('external-result', 'demo', 'T2', '--outcome', 'PASS', '--evidence', 'run 1 OK')
        self.assertEqual(2, result.returncode, result.stdout)

    def test_dependent_task_may_start_while_external_run_waits(self):
        self.accept_local()
        self.plan.write_text(self.plan.read_text().replace(
            '### T2 — String result\n- [x] Complete\n- **Requirements:** R1',
            '### T2 — String result\n- [ ] Complete\n- **Depends on:** T1\n- **Requirements:** R1'))
        result = self.run_step('dispatch', 'demo', 'T2')
        self.assertEqual(0, result.returncode, result.stdout)


if __name__ == '__main__':
    unittest.main()
