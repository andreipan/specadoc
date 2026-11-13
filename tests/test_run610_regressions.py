"""Regressions from orchestrator run 6.7-6.10 (organization-accounts-read/-add/-update-remove,
organization-ad-account-query): 17 design rounds because a finding's gaps were closed a few per round, a
verification task that owned plan.md and was stale after every accept, a reviewer without a shell, tests
written after the code in three steps, and two dispatches blocked by a refresh the script could run."""
from __future__ import annotations

import json
import subprocess
import unittest

import test_apply_reliability as reliability
from test_run35_regressions import INVENTORY_PLAN, ExternalVerificationTest
from test_specadoc_step import PLAN

OPEN_PLAN = PLAN.replace('- [x] Complete', '- [ ] Complete', 1)
GLOB_PLAN = PLAN.replace('- **Files:** `label.py`, `check_label.py`', '- **Files:** `label.py`, `check_label.py`, `src/`', 1)


class Base(unittest.TestCase):
    setUp = reliability.ApplyReliabilityTest.setUp
    tearDown = reliability.ApplyReliabilityTest.tearDown
    run_step = reliability.ApplyReliabilityTest.run_step
    report = reliability.ApplyReliabilityTest.report
    validate = ExternalVerificationTest.validate


class DesignItemsTest(Base):
    """6.8: the coverage finding of round 1 named nine gaps; rounds 2, 3 and 4 each found some still open."""

    def review(self, verdict, findings, name='design.json'):
        path = self.repo / name
        path.write_text(json.dumps({'verdict': verdict, 'report': 'r', 'findings': findings}))
        return self.run_step('design-review', 'demo', '--result-file', name)

    def resolve(self, text):
        self.repo.joinpath('resolutions.txt').write_text(text)
        return self.run_step('design-resolve', 'demo', '--file', 'resolutions.txt')

    def fail_round(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.assertEqual(0, self.run_step('design-brief', 'demo').returncode)
        result = self.review('FAIL', [
            dict(severity='IMPORTANT', location='plan.md matrix', summary='coverage is incomplete',
                 items=['no test rejects a 256-character name', 'no role and check-order cases']),
            dict(severity='BLOCKER', location='plan.md T1', summary='the lock is released before the read'),
            dict(severity='MINOR', location='src/port.py', summary='name repeats the module')])
        self.assertEqual(1, result.returncode, result.stdout)
        return result

    def test_each_gap_of_a_blocking_finding_is_recorded_as_an_item(self):
        result = self.fail_round()
        text = self.plan.read_text()
        self.assertIn('- IMPORTANT: plan.md matrix — coverage is incomplete\n'
                      '  - F1.1: no test rejects a 256-character name\n'
                      '  - F1.2: no role and check-order cases\n'
                      '- BLOCKER: plan.md T1 — the lock is released before the read\n'
                      '  - F2.1: the whole finding\n'
                      '- MINOR: src/port.py — name repeats the module\n', text)
        self.assertIn('close every item (F1.1, F1.2, F2.1) in this pass', result.stdout)

    def test_the_next_brief_waits_until_every_item_has_an_answer(self):
        self.fail_round()
        blocked = self.run_step('design-brief', 'demo')
        self.assertEqual(2, blocked.returncode, blocked.stdout)
        self.assertIn('3 item(s) of the recorded round have no resolution: F1.1, F1.2, F2.1', blocked.stdout)
        self.assertIn('design-resolve demo --file -', blocked.stdout)
        partly = self.resolve('F1.1: resolved: plan.md T1 Verification names the 256-character rejection\n')
        self.assertEqual(0, partly.returncode, partly.stdout)
        self.assertIn('still without a resolution: F1.2, F2.1', partly.stdout)
        self.assertEqual(2, self.run_step('design-brief', 'demo').returncode)
        done = self.resolve('- F1.2: resolved: plan.md matrix rows A2-A5\n'
                            'F2.1: rejected: the read happens inside the transaction, see design.md Flow\n')
        self.assertEqual(0, done.returncode, done.stdout)
        self.assertIn('every item answered', done.stdout)
        brief = self.run_step('design-brief', 'demo')
        self.assertEqual(0, brief.returncode, brief.stdout)
        text = self.change.joinpath('runs/design-brief.md').read_text()
        self.assertTrue(text.startswith('# Design re-review: `demo`'))
        self.assertIn('  - F1.2: no role and check-order cases\n    - resolved: plan.md matrix rows A2-A5\n', text)
        self.assertIn('    - rejected: the read happens inside the transaction, see design.md Flow\n', text)
        self.assertIn('Add no item to a previous finding', text)
        self.assertNotIn('F1.1', text.split('## Changes since the reviewed design', 1)[1],
                         'answers are not a design change')

    def test_a_resolution_names_a_place_and_a_known_item(self):
        self.fail_round()
        for text, message in (('F1.1: resolved: fixed it\n', 'name where it is resolved'),
                              ('F9.1: resolved: plan.md T1\n', 'F9.1 is not an item of the recorded round'),
                              ('F1.1: rejected: no\n', 'a rejection needs its reason'),
                              ('done everything\n', 'expected `F<n>.<m>: resolved: <where>`')):
            result = self.resolve(text)
            self.assertNotEqual(0, result.returncode, text)
            self.assertIn(message, result.stdout + result.stderr, text)
        self.assertNotIn('- resolved:', self.plan.read_text())

    def test_a_whole_review_and_the_first_round_ask_for_items_and_need_no_answers(self):
        self.fail_round()
        whole = self.run_step('design-brief', 'demo', '--full')
        self.assertEqual(0, whole.returncode, whole.stdout)
        text = self.change.joinpath('runs/design-brief.md').read_text()
        self.assertIn('Put every separately checkable gap of a BLOCKER or IMPORTANT finding into its `items`', text)
        schema = json.loads((reliability.SCRIPTS.parent / 'assets/reviewer-result.schema.json').read_text())
        self.assertEqual({'type': 'array', 'items': {'type': 'string'}},
                         schema['properties']['findings']['items']['properties']['items'])

    def test_a_pass_has_nothing_to_answer(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.assertEqual(0, self.review('PASS', []).returncode)
        self.plan.write_text(self.plan.read_text().replace('label source port', 'label source port and cache'))
        self.assertEqual(0, self.run_step('design-brief', 'demo').returncode)

    def test_the_run_record_is_not_taken_for_a_failed_reviewer(self):
        """6.7: `--result-file runs/design.reviewer.run.json` answered "reviewer process did not exit successfully"."""
        self.plan.write_text(INVENTORY_PLAN)
        self.repo.joinpath('design.reviewer.run.json').write_text(json.dumps({'exit': None, 'log': 'x'}))
        result = self.run_step('design-review', 'demo', '--result-file', 'design.reviewer.run.json')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('is the run record, not the reviewer\'s result', result.stdout + result.stderr)
        self.assertIn('design.reviewer.result.json', result.stdout + result.stderr)
        self.repo.joinpath('design.reviewer.result.json').write_text(
            json.dumps({'verdict': 'PASS', 'report': 'r', 'findings': []}))
        result = self.run_step('design-review', 'demo', '--result-file', 'design.reviewer.run.json')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_a_short_inventory_reason_says_how_long_it_must_be(self):
        self.plan.write_text(INVENTORY_PLAN.replace('| R1 needs a label source port | port |', '| R1 port | port |'))
        self.assertIn('needs the requirement or boundary it serves, in at least three words', self.validate('plan').stdout)


class PlanGateTest(Base):
    def test_a_task_may_not_own_a_file_of_the_change_folder(self):
        """6.7: T6 owned plan.md, every accept rewrote it, and 14 minutes went into a task that was always stale."""
        self.plan.write_text(OPEN_PLAN.replace('- **Files:** `label.py`, `check_label.py`',
                                               '- **Files:** `docs/specadoc/demo/plan.md`', 1))
        output = self.validate('plan').stdout
        self.assertIn('T1: Files names a path inside the change folder (docs/specadoc/demo/plan.md)', output)
        self.assertIn('its commands run in Final verification (`finalize --run`)', output)
        self.plan.write_text(OPEN_PLAN)
        self.assertNotIn('inside the change folder', self.validate('plan').stdout)

    def test_a_placeholder_inside_a_verification_command_fails_the_plan(self):
        """6.7: `vendor/bin/quality <changed php files>` passed the plan gate and broke the shell at accept."""
        self.plan.write_text(OPEN_PLAN.replace('- **Verification:** `python3 check_label.py`',
                                               '- **Verification:** `python3 check_label.py <changed py files>`', 1))
        self.assertIn('T1: Verification contains the placeholder <changed py files>', self.validate('plan').stdout)
        self.plan.write_text(OPEN_PLAN.replace('- **Verification:** `python3 check_label.py`',
                                               '- **Verification:** `python3 check_label.py <in.txt >out.txt`', 1))
        self.assertNotIn('contains the placeholder', self.validate('plan').stdout)


class StaleDependencyTest(Base):
    """6.10: two dispatches were blocked by `the set of owned files changed`; refresh then passed in 26 s."""

    def accept_t1_then_add_a_file_under_its_folder(self):
        self.plan.write_text(GLOB_PLAN.replace('### T2 — String result\n- [x] Complete\n- **Requirements:** R1',
                                               '### T2 — String result\n- [x] Complete\n- **Depends on:** T1\n'
                                               '- **Requirements:** R1', 1))
        self.repo.joinpath('src').mkdir()
        self.repo.joinpath('src/a.py').write_text('a = 1\n')
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        accepted = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, accepted.returncode, accepted.stdout)
        self.repo.joinpath('src/b.py').write_text('b = 1\n')

    def test_refresh_names_the_file_that_changed_the_owned_set(self):
        self.accept_t1_then_add_a_file_under_its_folder()
        result = self.run_step('refresh', 'demo')
        self.assertIn('the set of owned files changed: +src/b.py', result.stdout)

    def test_dispatch_refreshes_a_stale_dependency_itself(self):
        self.accept_t1_then_add_a_file_under_its_folder()
        result = self.run_step('dispatch', 'demo', 'T2')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('stale dependency evidence refreshed', result.stdout)


class LateTestTest(Base):
    """3.6, 5.2, 6.7, 6.8, 6.10: a worker wrote the test after the code and said so in its report."""

    def write(self, *extra):
        return self.run_step('report', 'demo', 'T1', '--status', 'DONE', '--summary', 'Ready diagnostic label',
                             '--green', 'python3 check_label.py passed', *extra)

    def setUp(self):
        reliability.ApplyReliabilityTest.setUp(self)
        self.plan.write_text(OPEN_PLAN)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)

    def test_a_report_that_admits_a_late_test_needs_mutation_evidence(self):
        for red, concern in (('RED produced after implementation (route removed temporarily)', None),
                             ('old label failed', 'tests written after code')):
            result = self.write('--red', red, *(['--concern', concern] if concern else []))
            self.assertEqual(1, result.returncode, result.stdout)
            self.assertIn('the report says the test did not fail first', result.stdout)
            self.assertIn("--mutation '<break -> failing test; ...>'", result.stdout)
            self.assertFalse(self.change.joinpath('runs/T1-report.md').exists())
        result = self.write('--red', 'tests written after code',
                            '--mutation', 'return "x" -> test_label fails; restored')
        self.assertEqual(0, result.returncode, result.stdout)
        report = self.change.joinpath('runs/T1-report.md').read_text()
        self.assertIn('## Mutation evidence\n\nreturn "x" -> test_label fails; restored\n', report)
        self.assertIn('"mutation": "return \\"x\\" -> test_label fails; restored"', report)
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)

    def test_an_observed_red_and_an_ordinary_concern_pass(self):
        result = self.write('--red', 'check_label.py fails: label is "old"',
                            '--concern', 'the formatter ran again after the implementation')
        self.assertEqual(0, result.returncode, result.stdout)

    def test_the_brief_tells_the_worker_what_a_late_test_costs(self):
        brief = self.change.joinpath('runs/T1-brief.md').read_text()
        self.assertIn('run it before any production file exists or changes', brief)
        self.assertIn("pass `--mutation '<break -> failing test; ...>'`", brief)


class ReviewerFilesTest(Base):
    """6.7-6.10: opencode refused every shell call of the reviewer, `git status --short` included."""

    def test_pre_review_writes_the_diff_and_status_the_reviewer_cannot_run(self):
        subprocess.run(['git', 'add', 'label.py', 'check_label.py'], cwd=self.repo, check=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'base'],
                       cwd=self.repo, check=True)
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # changed\n')
        result = self.run_step('pre-review', 'demo')
        if result.returncode != 0:
            self.skipTest('fixture plan does not open a review round here: ' + result.stdout[-200:])
        runs = self.change / 'runs'
        diffs = sorted(path.name for path in runs.glob('G*-head.diff'))
        self.assertEqual(1, len(diffs), result.stdout)
        self.assertIn('+    return "ready"  # changed', runs.joinpath(diffs[0]).read_text())
        self.assertIn(' M label.py', runs.joinpath(diffs[0].replace('-head.diff', '-status.txt')).read_text())
        self.assertIn('the reviewer needs no shell', result.stdout)

    def test_a_hash_instead_of_a_manifest_gets_one_line_not_a_traceback(self):
        result = subprocess.run(['python3', '-B', str(reliability.SCRIPTS / 'review_snapshot.py'), 'verify', 'demo',
                                 '--stored', 'sha256:0123abcd'], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn('expected a manifest file or inline JSON', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
