"""Regressions from orchestrator run 4.1a + 4.3 + 4.4 + 4.5 (organization members, ownership, invite)."""
from __future__ import annotations

import json
import unittest

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


if __name__ == '__main__':
    unittest.main()
