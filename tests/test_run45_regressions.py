"""Regressions from orchestrator run 4.1a + 4.3 + 4.4 + 4.5 (organization members, ownership, invite)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import test_apply_reliability as fixtures


def reviewer_json(verdict='PASS', findings=None):
    return json.dumps(dict(verdict=verdict, findings=findings or [], report='Independent read-only review.'))


MINOR = [dict(severity='MINOR', location='tests/test_label.py:1', summary='Name the case')]
IMPORTANT = [dict(severity='IMPORTANT', location='label.py:1', summary='Wrong label')]


class Run45ReviewOrderTest(unittest.TestCase):
    """4.3: a re-approval while G2 was pending turned its PASS into a stale FAIL and used the re-review."""
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step

    def begin(self, *args):
        return self.run_step('pre-review', 'demo', *args)

    def settle(self, verdict='PASS', findings=None, name='g.json'):
        path = self.change / 'runs' / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(reviewer_json(verdict, findings))
        return self.run_step('review-result', 'demo', '--result-file', str(path.relative_to(self.repo)))

    def approve(self):
        return self.run_step('approve', 'demo', '--by', 'orchestrator', '--source', 'mandate D18, decision D27')

    def test_approve_refuses_while_a_round_is_pending_and_withdraw_reopens_it(self):
        self.assertEqual(0, self.begin().returncode)
        refused = self.approve()
        self.assertEqual(2, refused.returncode, refused.stdout)
        self.assertIn('G1 is recorded but not reviewed', refused.stdout)
        self.assertIn('--withdraw', refused.stdout)
        withdrawn = self.begin('--withdraw')
        self.assertEqual(0, withdrawn.returncode, withdrawn.stdout)
        self.assertNotIn('### G1', self.plan.read_text())
        self.assertFalse((self.change / 'runs' / 'G1-manifest.json').exists())
        self.assertEqual(0, self.approve().returncode)
        self.assertEqual(0, self.begin().returncode)
        self.assertIn('### G1', self.plan.read_text())

    def test_settled_round_cannot_be_withdrawn(self):
        self.assertEqual(0, self.begin().returncode)
        self.assertEqual(0, self.settle().returncode)
        result = self.begin('--withdraw')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('immutable', result.stdout)

    def test_pre_review_refuses_a_spec_changed_since_approval(self):
        self.assertEqual(0, self.approve().returncode)
        spec = self.change / 'spec.md'
        spec.write_text(spec.read_text() + '\nA clarified sentence.\n')
        status = self.run_step('status', 'demo')
        self.assertIn('next: re-approve (spec.md changed)', status.stdout)
        refused = self.begin()
        self.assertEqual(2, refused.returncode, refused.stdout)
        self.assertIn('spec.md changed since approval', refused.stdout)
        self.assertNotIn('### G1', self.plan.read_text())

    def stale_policy_re_review(self):
        self.assertEqual(0, self.begin().returncode)
        self.assertEqual(0, self.settle('FAIL', IMPORTANT, 'g1.json').returncode)
        self.assertEqual(0, self.begin('--review-type', 're-review').returncode)
        # The approval changes while G2 runs (the 4.3 order, before approve refused it).
        self.plan.write_text(self.plan.read_text().replace('**Approved at:** fixture', '**Approved at:** later'))
        return self.settle('PASS', None, 'g2.json')

    def test_a_policy_stale_re_review_uses_no_allowance(self):
        result = self.stale_policy_re_review()
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('approval or review policy changed', result.stdout)
        self.assertIn('uses no review allowance', result.stdout)
        self.assertIn('the diff is unchanged', result.stdout)
        self.assertNotIn('reconcile Review scope', result.stdout)
        status = self.run_step('status', 'demo', '--context-tokens', '170000')
        self.assertIn('(re-review, stale)', status.stdout)
        self.assertIn('next: pre-review --review-type re-review (G2 stale', status.stdout)
        self.assertNotIn('review boundary', status.stdout)
        again = self.begin('--review-type', 're-review')
        self.assertEqual(0, again.returncode, again.stdout)
        self.assertIn('### G3', self.plan.read_text())

    def test_a_stale_initial_round_is_not_counted_by_the_cap(self):
        self.assertEqual(0, self.begin().returncode)
        self.assertEqual(0, self.settle('FAIL', IMPORTANT, 'g1.json').returncode)
        self.assertEqual(0, self.begin('--reason', 'requirements').returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "changed"\n')
        self.assertEqual(0, self.settle('FAIL', IMPORTANT, 'g2.json').returncode)
        self.assertIn('**Snapshot status:** stale', self.plan.read_text())
        self.assertEqual(0, self.begin('--reason', 'requirements').returncode)
        self.assertEqual(0, self.settle('FAIL', IMPORTANT, 'g3.json').returncode)
        fourth = self.begin('--reason', 'requirements')
        self.assertEqual(0, fourth.returncode, fourth.stdout)


class Run45MinorFixTest(unittest.TestCase):
    """4.1a: a test-only MINOR fix after a MINOR-only PASS made status ask for another round."""
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step

    def scope(self, *paths):
        text = self.plan.read_text()
        head, tail = text.split('## Review scope\n', 1)
        rest = tail[tail.index('## Final verification'):]
        self.plan.write_text(head + '## Review scope\n' + ''.join(f'- `{p}`\n' for p in paths) + rest)

    def test_status_needs_no_round_for_test_only_minor_fixes(self):
        test_file = self.repo / 'tests' / 'test_label.py'
        test_file.parent.mkdir()
        test_file.write_text('assert True\n')
        self.scope('label.py', 'check_label.py', 'tests/test_label.py')
        self.assertEqual(0, self.run_step('pre-review', 'demo').returncode)
        result = self.change / 'runs' / 'g1.json'
        result.parent.mkdir(exist_ok=True)
        result.write_text(reviewer_json('PASS', MINOR))
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file',
                                          str(result.relative_to(self.repo))).returncode)
        test_file.write_text('assert True  # names the case\n')
        status = self.run_step('status', 'demo')
        self.assertNotIn('next: pre-review', status.stdout)
        self.repo.joinpath('label.py').write_text('def label():\n    return "changed"\n')
        status = self.run_step('status', 'demo')
        self.assertIn('next: pre-review --review-type re-review (diff changed since G1', status.stdout)



class Run45PlanTextTest(unittest.TestCase):
    """4.4: a worker summary `list<RoleChange>` read as a template placeholder and blocked dispatch."""
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step

    def test_script_written_fields_backtick_generic_types(self):
        import sys
        sys.path.insert(0, str(fixtures.SCRIPTS))
        from task_state import update_task
        from validate_change import Document
        plan = Document(self.plan, 'plan.md')
        text = update_task(plan, 'T1', {'Accepted result': 'transferOwnership(): list<RoleChange> and `Map<K>` kept'})
        self.assertIn('`list<RoleChange>`', text)
        self.assertIn('`Map<K>`', text)
        self.assertNotIn('``', text)
        self.plan.write_text(text)
        self.assertEqual([], Document(self.plan, 'plan.md').placeholders('Tasks'))

    def test_handoff_reads_a_draft_outside_the_repository(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp) / 'handoff.md'
            draft.write_text('# Handoff\n\nNext: T2.\n')
            result = self.run_step('handoff', 'demo', '--file', str(draft))
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('Next: T2.', (self.change / 'runs' / 'handoff.md').read_text())

    def test_change_folder_paths_are_not_controller_paths(self):
        result = self.run_step('refresh', 'demo', '--controller-path', 'docs/specadoc/demo/research.md',
                               '--reason', 'moved evidence')
        self.assertIn('not task scope', result.stdout)



class Run45WaitTest(unittest.TestCase):
    """4.5: a loop waiting for DONE hid a resumed worker's NEEDS_CONTEXT for ten minutes."""
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step
    report = fixtures.ApplyReliabilityTest.report

    def test_wait_returns_on_a_new_report_of_any_status(self):
        import os
        import subprocess
        import sys
        import threading
        self.report('NEEDS_CONTEXT')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        waiting = subprocess.Popen([sys.executable, '-B', str(fixtures.SCRIPTS / 'specadoc_step.py'), 'wait',
                                    'demo', 'T1', '--timeout', '20', '--interval', '0.2'],
                                   cwd=self.repo, env=env, stdout=subprocess.PIPE, text=True)
        timer = threading.Timer(1.0, lambda: self.report('BLOCKED'))
        timer.start()
        out, _ = waiting.communicate(timeout=30)
        timer.join()
        self.assertEqual(0, waiting.returncode, out)
        self.assertIn('report: BLOCKED', out)
        self.assertIn('make the missing decision', out)

    def test_wait_times_out_with_the_current_status(self):
        self.report('NEEDS_CONTEXT')
        result = self.run_step('wait', 'demo', 'T1', '--timeout', '0.5', '--interval', '0.1')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('still NEEDS_CONTEXT', result.stdout)



class Run45ExternalOnlyTest(unittest.TestCase):
    """4.4: the integration run reserved for the parent sat in a task's Verification."""
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown

    def validate(self):
        import subprocess
        import sys
        return subprocess.run([sys.executable, '-B', str(fixtures.SCRIPTS / 'validate_change.py'), 'demo',
                               '--phase', 'plan'], cwd=self.repo, capture_output=True, text=True)

    def test_external_only_command_in_verification_is_refused(self):
        text = self.plan.read_text()
        start = text.index('### T1')
        self.plan.write_text(text[:start] + text[start:].replace('- [x] Complete', '- [ ] Complete', 1))
        self.assertNotIn('external-only', self.validate().stdout)
        self.repo.joinpath('.specadoc.json').write_text(json.dumps(
            {'version': 1, 'verification': {'external_only': ['check_label.py']}}))
        result = self.validate()
        self.assertIn('T1: Verification runs an external-only command (check_label.py', result.stdout)

    def test_config_rejects_a_malformed_external_only_list(self):
        import sys
        sys.path.insert(0, str(fixtures.SCRIPTS))
        from specadoc_config import validate_config
        self.assertTrue(validate_config({'verification': {'external_only': ['suite.xml']}}))
        with self.assertRaises(ValueError):
            validate_config({'verification': {'external_only': 'suite.xml'}})


if __name__ == '__main__':
    unittest.main()
