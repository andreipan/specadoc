"""Regressions from orchestrator run 4.6 + 4.7 + 4.8 (invitation resend/revoke, preview, accept/decline)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

import test_apply_reliability as fixtures
from test_specadoc_step import SCRIPTS


OPEN_T1 = fixtures.PLAN.replace('### T1 — Ready label\n- [x] Complete', '### T1 — Ready label\n- [ ] Complete')


class Run48Base(unittest.TestCase):
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step

    def validate(self, phase='plan'):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'validate_change.py'), 'demo', '--phase', phase],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def require_tidy(self, value='required'):
        self.repo.joinpath('.specadoc.json').write_text(json.dumps({'version': 1, 'review': {'tidy': value}}))


class Run48DecisionRiskTest(Run48Base):
    """4.8: four worker tasks with Decision risk medium passed validate and approve, then dispatch refused T2."""

    def test_plan_validation_refuses_a_worker_task_without_low_decision_risk(self):
        self.plan.write_text(OPEN_T1.replace('- **Decision risk:** low', '- **Decision risk:** medium', 1))
        result = self.validate()
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('T1: Owner: worker needs Decision risk: low', result.stdout + result.stderr)
        approve = self.run_step('approve', 'demo', '--by', 'orchestrator', '--source', 'mandate D18, decision D64')
        self.assertNotEqual(0, approve.returncode, approve.stdout)

    def test_a_completed_task_keeps_its_recorded_decision_risk(self):
        self.plan.write_text(fixtures.PLAN.replace('- **Decision risk:** low', '- **Decision risk:** medium', 1))
        self.assertEqual(0, self.validate().returncode, self.validate().stdout)

    def test_dispatch_names_the_same_rule(self):
        self.plan.write_text(OPEN_T1.replace('- **Decision risk:** low', '- **Decision risk:** medium', 1))
        result = self.run_step('preflight', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('Owner: worker needs Decision risk: low', result.stdout)

    # 4.7: "PENDING" as a domain status tripped the placeholder check.
    def test_pending_inside_domain_prose_is_not_a_placeholder(self):
        self.plan.write_text(OPEN_T1.replace('- **Implementation:** Return ready',
                                             '- **Implementation:** Return ready for a PENDING invitation', 1))
        result = self.validate()
        self.assertNotIn('still Pending', result.stdout + result.stderr)
        self.plan.write_text(OPEN_T1.replace('- **Implementation:** Return ready', '- **Implementation:** Pending', 1))
        self.assertIn('still Pending', self.validate().stdout + self.validate().stderr)


class Run48SessionLedgerTest(Run48Base):
    """4.8: a re-approval in the apply session ended its token window; totals saw 1 of 9 sub-agents."""

    def test_approve_after_dispatch_records_the_apply_session(self):
        home = self.repo / 'home'
        transcript = home / 'projects/p/controller-1.jsonl'
        transcript.parent.mkdir(parents=True)
        transcript.write_text('{}\n')
        runs = self.change / 'runs'
        runs.mkdir()
        runs.joinpath('T1-baseline.json').write_text('{}\n')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CLAUDE_CONFIG_DIR=str(home),
                   CLAUDE_CODE_SESSION_ID='controller-1')
        env.pop('SPECADOC_ROOT', None)
        subprocess.run([sys.executable, '-B', str(SCRIPTS / 'specadoc_step.py'), 'approve', 'demo', '--by',
                        'orchestrator', '--source', 'mandate D18, decision D66'],
                       cwd=self.repo, env=env, capture_output=True, text=True)
        modes = [item['mode'] for item in json.loads(runs.joinpath('sessions.json').read_text())['claude']]
        self.assertEqual(['apply'], modes)


class Run48TidyGateTest(Run48Base):
    """User decision after 4.8: one tidy pass over Review scope before the first initial review."""

    def test_pre_review_refuses_the_initial_round_without_a_tidy_pass(self):
        self.require_tidy()
        status = self.run_step('status', 'demo')
        self.assertIn('tidy: required, not recorded', status.stdout)
        self.assertIn('next: scope demo', status.stdout)
        self.assertIn('then tidy demo', status.stdout)
        refused = self.run_step('pre-review', 'demo')
        self.assertEqual(2, refused.returncode, refused.stdout)
        self.assertIn('no tidy pass recorded', refused.stdout)
        self.assertNotIn('### G1', self.plan.read_text())

    def test_brief_then_record_opens_the_review(self):
        self.require_tidy()
        brief = self.run_step('tidy', 'demo')
        self.assertEqual(0, brief.returncode, brief.stdout)
        text = (self.change / 'runs/tidy-brief.md').read_text()
        self.assertIn('tidy/SKILL.md', text)
        self.assertIn('- `label.py`', text)
        self.assertIn('`python3 check_label.py`', text)
        self.assertIn('tidy demo --record', text)
        recorded = self.run_step('tidy', 'demo', '--record', '--summary', 'fixed 0; skipped 0; for the controller: none')
        self.assertEqual(0, recorded.returncode, recorded.stdout)
        self.assertIn('refresh demo', recorded.stdout)
        self.assertIn('tidy: recorded: fixed 0', self.run_step('status', 'demo').stdout)
        self.assertEqual(0, self.run_step('pre-review', 'demo').returncode)

    def test_skip_needs_a_reason_and_re_review_needs_no_pass(self):
        self.require_tidy()
        self.assertNotEqual(0, self.run_step('tidy', 'demo', '--skip', '').returncode)
        self.assertEqual(0, self.run_step('tidy', 'demo', '--skip', 'one-line constant change').returncode)
        self.assertEqual(0, self.run_step('pre-review', 'demo').returncode)
        (self.change / 'runs/tidy.json').unlink()
        result = self.run_step('pre-review', 'demo', '--review-type', 're-review', '--dry-run')
        self.assertNotIn('no tidy pass recorded', result.stdout)

    def test_optional_by_default(self):
        self.assertEqual(0, self.run_step('pre-review', 'demo').returncode)
        self.require_tidy('sometimes')
        self.assertNotEqual(0, self.run_step('status', 'demo').returncode)


class Run48BriefAndRefreshTest(Run48Base):
    def test_external_brief_compares_by_value_and_carries_lessons(self):
        self.plan.write_text(OPEN_T1.replace('- **Delivery verification:** N/A',
                                             '- **Delivery verification:** N/A\n- **External verification:** '
                                             '`python3 run_integration.py` by the parent', 1))
        runs = self.change / 'runs'
        runs.mkdir()
        runs.joinpath('lessons.md').write_text('- Compare database rows with assertEquals (T3).\n')
        sys.path.insert(0, str(SCRIPTS))
        from task_brief import build_brief
        brief = build_brief(self.change, 'T1')
        self.assertIn('not object identity', brief)
        self.assertIn('trace ids', brief)
        self.assertIn('## Lessons from earlier tasks of this change', brief)
        self.assertIn('assertEquals (T3)', brief)

    # 4.6: the controller's own MINOR fix in production code introduced an IMPORTANT finding.
    def test_refresh_warns_on_an_executable_controller_edit(self):
        (self.change / 'runs').mkdir()
        result = self.run_step('refresh', 'demo', '--controller-path', 'label.py', '--reason', 'G1 MINOR-1')
        self.assertIn('WARN executable controller edit: label.py', result.stdout)
        quiet = self.run_step('refresh', 'demo', '--controller-path', 'label.py', '--reason', 'tidy pass')
        self.assertNotIn('WARN executable', quiet.stdout)


if __name__ == '__main__':
    unittest.main()
