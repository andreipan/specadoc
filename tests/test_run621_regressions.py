"""Regressions from orchestrator run 6.16-6.21 (2026-11-24): a reopened task's brief without the reopen
reason (6.16 T5: the worker guessed the fix, the controller corrected it by message), and seven
design-resolve refusals, six of them for real places the pointer check did not know (`spec Constraints`,
`research.md excerpts`, `runs/hub-producer-01a3031b.md §Bounds`); the check stopped at the first bad line,
so 6.20 needed two refusals for two lines."""
from __future__ import annotations

import json
import unittest

import test_run610_regressions as run610
from test_run610_regressions import Base
from test_specadoc_step import PLAN


class ReopenBriefTest(Base):
    def brief(self):
        return self.change.joinpath('runs/T1-brief.md').read_text()

    def test_a_reopened_task_brief_carries_the_reason_and_the_previous_report(self):
        self.plan.write_text(PLAN.replace('- [x] Complete', '- [ ] Complete', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.assertNotIn('## Reopen', self.brief())
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1', '--verify').returncode)
        reason = 'G2-1 IMPORTANT, orchestrator D133: the sentinel must sit on the failing connection'
        result = self.run_step('dispatch', 'demo', 'T1', '--reopen', reason)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn('warning: brief', result.stdout + result.stderr)
        brief = self.brief()
        self.assertIn('## Reopen (attempt 2)', brief)
        self.assertIn(f'- Reason: {reason}', brief)
        self.assertIn('runs/T1-report-a1.md`', brief)
        self.assertLess(brief.index('## Task'), brief.index('## Reopen'))
        self.assertLess(brief.index('## Reopen'), brief.index('## Requirements'))
        record = json.loads(self.change.joinpath('runs/T1-baseline.json').read_text())
        self.assertEqual(reason, record['attempts'][-1]['reopen_reason'])
        retry = self.run_step('dispatch', 'demo', 'T1')  # a plain retry of the reopened attempt
        self.assertEqual(0, retry.returncode, retry.stdout + retry.stderr)
        self.assertIn(f'## Reopen (attempt 2)\n', self.brief())


class ResolvePointerTest(Base):
    review = run610.DesignItemsTest.review
    resolve = run610.DesignItemsTest.resolve
    fail_round = run610.DesignItemsTest.fail_round

    def test_places_the_controllers_named_in_the_run_are_accepted(self):
        self.fail_round()
        done = self.resolve(
            'F1.1: resolved: spec Constraints → Platform preconditions: an over-limit Content-Length answers as today\n'
            'F1.2: resolved: Spec Constraints and research.md excerpts ListAssets Handler (owner always)\n'
            'F2.1: resolved: runs/hub-producer-01a3031b.md §Bounds and spec Constraints: the bounds are write rules\n')
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn('every item answered', done.stdout)

    def test_every_bad_line_is_named_in_one_refusal_and_nothing_is_recorded(self):
        self.fail_round()
        before = self.plan.read_text()
        refused = self.resolve('F1.1: resolved: plan.md T1 Verification\n'
                               'F1.2: resolved: fixed it\n'
                               'F2.1: resolved in part: A2/A4 cover OWNER, ADMIN and MEMBER\n')
        self.assertNotEqual(0, refused.returncode)
        output = refused.stdout + refused.stderr
        self.assertIn('2 line(s) refused, nothing recorded', output)
        self.assertIn('F1.2: name where it is resolved', output)
        self.assertIn('not: F2.1: resolved in part', output)
        self.assertEqual(before, self.plan.read_text())


if __name__ == '__main__':
    unittest.main()
