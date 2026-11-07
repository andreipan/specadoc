"""Regressions from orchestrator run 4.9 + 4.10 + 4.11 (invited registration, profile logo, teams read)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

import test_apply_reliability as fixtures
from test_specadoc_step import PLAN, SCRIPTS

GUIDANCE = ('## Review scope\n'
            '<Populate immediately before each initial review from the actual executable\n'
            'diff. Use one backticked repository-relative literal file path per bullet.>\n\n'
            '- `label.py`\n- `check_label.py`\n')
ROUND_LOG = ('## Review result\n**Result:** Pending\n**Reviewed requirements:** R1\n**Reviewed tasks:** T1, T2, T3\n\n'
             '### Findings\n\n- BLOCKER: None recorded.\n- IMPORTANT: None recorded.\n- MINOR: None recorded.\n\n'
             '### Round log\n\n<One `### G<n>` block per reviewer dispatch, oldest first. Shape below is\n'
             'indented so a copied template does not itself contain a live `G1` block:\n\n'
             '    ### G1\n\n    - **Type:** initial|re-review\n    - **Previous:** none|G<n-1>\n'
             '    - **Reason:** <one line, required on FAIL>\n    - **Round cap override:** Pending\n>\n')
CHECKLIST = ('## Final verification\n- [ ] Every requirement maps to implementation.\n'
             '- [ ] Every acceptance scenario has a test or deterministic verification.\n'
             '- [ ] Focused tests pass.\n- [ ] Relevant regression tests pass.\n'
             '- [ ] Required build, lint, and type-check commands pass.\n'
             '- [ ] Independent final review is complete.\n- [ ] No BLOCKER findings remain.\n'
             '- [ ] No IMPORTANT findings remain.\n')
TEMPLATE_PLAN = (PLAN.replace('## Review scope\n- `label.py`\n- `check_label.py`\n', GUIDANCE)
                 .replace('## Final verification\n- [x] Focused and regression checks pass\n', CHECKLIST)
                 .replace('## Review result\n**Result:** Pending\n**Reviewed requirements:** R1\n'
                          '**Reviewed tasks:** T1, T2, T3\n', ROUND_LOG))


class Run411Base(unittest.TestCase):
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step
    report = fixtures.ApplyReliabilityTest.report

    def validate(self, phase='final'):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'validate_change.py'), 'demo', '--phase', phase],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True)

    def commit_all(self):
        self.git('add', '-A')
        self.git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'base')

    def pass_round(self):
        self.assertEqual(0, self.run_step('pre-review', 'demo').returncode)
        path = self.repo / 'review.json'
        path.write_text(json.dumps(dict(verdict='PASS', findings=[], report='Independent read-only review.')))
        result = self.run_step('review-result', 'demo', '--result-file', str(path))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


class Run49ScopeTest(Run411Base):
    """4.9: tidy refused the template paragraph the controller left in Review scope; every apply
    controller then filled the section with a python heredoc."""

    def test_template_guidance_is_not_a_scope_entry(self):
        self.plan.write_text(TEMPLATE_PLAN)
        result = self.run_step('tidy', 'demo')
        self.assertNotIn('expected a backticked literal path bullet', result.stdout)

    def test_scope_writes_the_executable_diff_without_artifacts(self):
        self.commit_all()
        self.plan.write_text(TEMPLATE_PLAN)
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready!"\n')
        self.repo.joinpath('new_module.py').write_text('NEW = True\n')
        self.repo.joinpath('check_label.py').unlink()
        result = self.run_step('scope', 'demo')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        section = self.plan.read_text().split('## Review scope\n')[1].split('## Final verification')[0]
        self.assertEqual(['- `label.py`', '- `new_module.py`', '- `!check_label.py`'],
                         [line for line in section.splitlines() if line.strip()])
        self.assertIn('artifacts left out: docs/specadoc/demo/plan.md', result.stdout)
        self.assertIn('tidy demo', result.stdout)

    def test_scope_without_a_diff_names_base(self):
        self.commit_all()
        result = self.run_step('scope', 'demo')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('--base', result.stdout)


class Run411FinalizeTest(Run411Base):
    """4.11: validate --phase final flagged the indented G1 example's placeholders and the unticked
    checklist; the controller regex-edited plan.md."""

    def test_indented_round_log_example_is_not_a_placeholder(self):
        self.plan.write_text(TEMPLATE_PLAN.replace('- [ ]', '- [x]'))
        result = self.validate()
        self.assertNotIn('unfilled placeholder: <n-1>', result.stdout + result.stderr)

    def test_finalize_ticks_proven_boxes_and_drops_the_template(self):
        self.plan.write_text(TEMPLATE_PLAN.replace('| R1 | A1 | python3 check_label.py | PASS |',
                                                   '| R1 | A1 | python3 check_label.py | Pending |'))
        self.pass_round()
        result = self.run_step('finalize', 'demo')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        text = self.plan.read_text()
        self.assertNotIn('    ### G1', text)
        self.assertIn('### G1\n', text)
        self.assertIn('- [x] Independent final review is complete.', text)
        self.assertIn('- [x] No BLOCKER findings remain.', text)
        self.assertIn('- [x] Focused tests pass.', text)
        self.assertIn('- [ ] Relevant regression tests pass.', text)
        self.assertIn('- [ ] Every requirement maps to implementation.', text)
        self.assertIn('rows still Pending: R1', result.stdout)
        self.assertIn('--observed', result.stdout)
        result = self.run_step('finalize', 'demo', '--observed', 'python3 -m unittest: 12 passed; lint PASS',
                               '--requirements', 'R1 by accepted T1–T3 Verification')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('result: PASS', result.stdout)
        text = self.plan.read_text()
        self.assertNotIn('- [ ]', text.split('## Final verification')[1].split('## Review result')[0])
        self.assertIn('Observed (', text)
        self.assertIn('| R1 | A1 | python3 check_label.py | PASS |', text)
        validated = self.validate()
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

    def test_finalize_leaves_review_boxes_without_a_pass(self):
        self.plan.write_text(TEMPLATE_PLAN)
        result = self.run_step('finalize', 'demo', '--observed', 'suite PASS')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('- [ ] Independent final review is complete.', self.plan.read_text())
        self.assertIn('no review round', result.stdout)


class Run411ReopenTest(Run411Base):
    """4.11: `dispatch T2 --reopen` was refused because T1's evidence was stale on a shared file, and the
    controller had to run refresh by hand first."""

    def test_reopen_refreshes_stale_dependencies(self):
        open_t2 = PLAN.replace('### T2 — String result\n- [x] Complete', '### T2 — String result\n- [ ] Complete')
        self.plan.write_text(open_t2)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report(task='T1')
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        self.plan.write_text(self.plan.read_text().replace('### T2 — String result\n- [ ] Complete',
                                                           '### T2 — String result\n- [ ] Complete\n- **Depends on:** T1'))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T2').returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # changed by T2\n')
        result = self.run_step('dispatch', 'demo', 'T2', '--reopen', 'fix after a failed check')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('stale dependency evidence refreshed', result.stdout)


class Run411ConfigTest(unittest.TestCase):
    def test_verification_final_is_a_known_key(self):
        sys.path.insert(0, str(SCRIPTS))
        from specadoc_config import validate_config
        validate_config({'version': 1, 'verification': {'final': ['vendor/bin/phpunit', 'vendor/bin/quality']}})
        with self.assertRaises(ValueError):
            validate_config({'version': 1, 'verification': {'final': 'vendor/bin/phpunit'}})


if __name__ == '__main__':
    unittest.main()
