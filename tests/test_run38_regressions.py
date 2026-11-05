"""Regressions from the iam-profile 3.7 and iam-avatar 3.8 run review (November 2026)."""
from __future__ import annotations

import json
import unittest

import test_apply_reliability as reliability
from test_run35_regressions import EXTERNAL_PLAN, ExternalVerificationTest
from test_specadoc_step import PLAN

OPEN_T1 = PLAN.replace('- [x] Complete', '- [ ] Complete', 1)
CAPABILITY = ('# Label\n\n| Change | Requirements |\n|---|---|\n| demo | C1 |\n\n'
              '### C1 — Diagnostic label is ready\nThe label SHALL equal ready.\n')


class Run38Test(unittest.TestCase):
    setUp = reliability.ApplyReliabilityTest.setUp
    tearDown = reliability.ApplyReliabilityTest.tearDown
    run_step = reliability.ApplyReliabilityTest.run_step
    report = reliability.ApplyReliabilityTest.report
    validate = ExternalVerificationTest.validate
    t1_block = ExternalVerificationTest.t1_block

    def state(self, task='T1'):
        return json.loads(self.change.joinpath(f'runs/{task}-baseline.json').read_text())

    # Wrapped Files lines were silently dropped (3.7 T1, 3.8 T2-T4).
    def test_wrapped_files_field_keeps_its_continuation_line(self):
        self.repo.joinpath('extra.py').write_text('x = 1\n')
        self.plan.write_text(OPEN_T1.replace('- **Files:** `label.py`, `check_label.py`\n',
                                             '- **Files:** `label.py`, `check_label.py`,\n  `extra.py`\n', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('extra.py').write_text('x = 2\n')
        self.report(files=('label.py', 'extra.py'))
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('result: ACCEPTED', result.stdout)

    # A sandbox setting frozen into Verification diverged between sessions (3.7, 3.8).
    def test_environment_prefix_in_verification_is_warned(self):
        self.plan.write_text(OPEN_T1.replace('- **Verification:** `python3 check_label.py`',
                                             '- **Verification:** `PHP_INI_SCAN_DIR=:/tmp/ini python3 check_label.py`', 1))
        result = self.validate('plan')
        self.assertIn('T1: Verification sets an environment variable', result.stderr)
        self.plan.write_text(OPEN_T1)
        self.assertNotIn('environment variable', self.validate('plan').stderr)

    # 3.8 T9: the parent fixed composer.lock; the controller rewrote the worker report to DONE.
    def test_blocked_report_is_accepted_only_with_a_named_resolution(self):
        self.plan.write_text(OPEN_T1)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report('BLOCKED', ['composer.lock needs network'])
        report = self.change.joinpath('runs/T1-report.md').read_bytes()
        blocked = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(2, blocked.returncode, blocked.stdout)
        self.assertIn('--resolved', blocked.stdout)
        result = self.run_step('accept', 'demo', 'T1', '--resolved',
                               'parent ran composer update --lock after user approval')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('result: ACCEPTED', result.stdout)
        self.assertEqual(report, self.change.joinpath('runs/T1-report.md').read_bytes())
        self.assertIn('worker BLOCKED → resolved: parent ran composer update', self.t1_block())
        self.assertEqual('BLOCKED', self.state()['blocker_resolution']['worker_status'])

    def test_resolved_is_refused_for_a_completed_report(self):
        self.plan.write_text(OPEN_T1)
        self.run_step('dispatch', 'demo', 'T1')
        self.report()
        result = self.run_step('accept', 'demo', 'T1', '--resolved', 'parent fixed the lock file')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('only to a BLOCKED or NEEDS_CONTEXT report', result.stdout)

    # 3.8 T7: a garbled hash in the external evidence led to a hand edit of the baseline.
    def accept_with_external_pass(self):
        self.plan.write_text(EXTERNAL_PLAN)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        result = self.run_step('external-result', 'demo', 'T1', '--outcome', 'PASS',
                               '--evidence', 'it-3.8-2: 12 tests OK, sha 3605…1f61e?')
        self.assertEqual(0, result.returncode, result.stdout)

    def test_recorded_external_result_is_superseded_not_hand_edited(self):
        self.accept_with_external_pass()
        again = self.run_step('external-result', 'demo', 'T1', '--outcome', 'PASS', '--evidence', 'it-3.8-2: 12 tests OK')
        self.assertEqual(2, again.returncode, again.stdout)
        self.assertIn('--supersede', again.stdout)
        result = self.run_step('external-result', 'demo', 'T1', '--outcome', 'PASS',
                               '--evidence', 'it-3.8-2: 12 tests OK, sha 3605839492dc',
                               '--supersede', 'garbled hash in the recorded evidence')
        self.assertEqual(0, result.returncode, result.stdout)
        state = self.state()
        self.assertEqual('accepted', state['state'])
        self.assertIn('sha 3605839492dc', state['external']['evidence'])
        self.assertEqual('garbled hash in the recorded evidence', state['external_history'][0]['reason'])
        self.assertIn('**External evidence:** PASS: it-3.8-2: 12 tests OK, sha 3605839492dc', self.t1_block())

    def test_supersede_needs_a_recorded_result(self):
        self.plan.write_text(EXTERNAL_PLAN)
        self.run_step('dispatch', 'demo', 'T1')
        self.report()
        self.run_step('accept', 'demo', 'T1')
        result = self.run_step('external-result', 'demo', 'T1', '--outcome', 'PASS', '--evidence', 'run OK',
                               '--supersede', 'wrong log')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('no recorded external result', result.stdout)

    def test_final_gate_needs_external_pass_for_the_accepted_content(self):
        self.plan.write_text(OPEN_T1)
        self.run_step('dispatch', 'demo', 'T1')
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        # External verification added after acceptance: the task is accepted but no run covers it.
        self.plan.write_text(self.plan.read_text().replace(
            '- **Verification:** `python3 check_label.py`\n',
            '- **Verification:** `python3 check_label.py`\n'
            '- **External verification:** Parent runs the integration suite.\n', 1))
        final = self.validate('final')
        self.assertIn('T1: no external PASS recorded for the accepted content', final.stdout + final.stderr)

    # 3.7/3.8: writing docs/specadoc/specs/<cap>.md needed amend --controller-path.
    def test_declared_capability_file_is_not_a_scope_violation(self):
        self.plan.write_text(OPEN_T1)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        capability = self.repo / 'docs/specadoc/specs/label.md'
        capability.parent.mkdir(parents=True)
        capability.write_text(CAPABILITY)
        result = self.run_step('accept', 'demo', 'T1', '--scope-only')
        self.assertEqual(0, result.returncode, result.stdout)
        other = self.repo / 'docs/specadoc/specs/other.md'
        other.write_text('### C1 — Unrelated\n')
        result = self.run_step('accept', 'demo', 'T1', '--scope-only')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn('other.md (artifact root is controller-owned)', result.stdout)

    def test_every_step_accepts_controller_runtime(self):
        self.plan.write_text(OPEN_T1)
        self.run_step('dispatch', 'demo', 'T1')
        self.repo.joinpath('wiring.py').write_text('binding = True\n')
        result = self.run_step('amend', 'demo', 'T1', '--allow', 'wiring.py', '--controller-runtime', 'claude',
                               '--reason', 'Controller approved the composition-root binding')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_status_marks_the_locally_ready_boundary(self):
        self.plan.write_text(OPEN_T1)
        self.run_step('dispatch', 'demo', 'T1')
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        self.repo.joinpath('docs/specadoc/specs').mkdir(parents=True)
        self.repo.joinpath('docs/specadoc/specs/label.md').write_text(CAPABILITY)
        self.assertEqual(0, self.run_step('pre-review', 'demo').returncode)
        self.change.joinpath('runs/review.json').write_text(json.dumps({'verdict': 'PASS', 'findings': [], 'report': 'ok'}))
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file',
                                          'docs/specadoc/demo/runs/review.json').returncode)
        status = self.run_step('status', 'demo', '--context-tokens', '150000').stdout
        self.assertIn('next: validate_change.py demo --phase final', status)
        self.assertIn('locally ready; continue for the final gate', status)
        self.assertNotIn('locally ready', self.run_step('status', 'demo', '--context-tokens', '90000').stdout)

    # 3.8: token collection needed a manual search through other sessions' transcripts.
    def test_writing_steps_record_the_controller_session_status_does_not(self):
        import os
        import subprocess
        import sys
        from test_specadoc_step import SCRIPTS
        home = self.repo / 'home'
        transcript = home / 'projects/p/controller-1.jsonl'
        transcript.parent.mkdir(parents=True)
        transcript.write_text('{}\n')
        self.plan.write_text(OPEN_T1)
        self.change.joinpath('runs').mkdir()

        def step(*args, session='controller-1'):
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CLAUDE_CONFIG_DIR=str(home),
                       CLAUDE_CODE_SESSION_ID=session)
            env.pop('SPECADOC_ROOT', None)
            return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'specadoc_step.py'), *args],
                                  cwd=self.repo, env=env, capture_output=True, text=True, input='notes\n')
        step('status', 'demo')
        ledger = self.change / 'runs/sessions.json'
        self.assertFalse(ledger.exists())
        self.assertEqual(0, step('dispatch', 'demo', 'T1').returncode)
        recorded = json.loads(ledger.read_text())['claude']
        self.assertEqual([(str(transcript), 'apply')], [(item['transcript'], item['mode']) for item in recorded])
        # A Codex controller launched from a Claude shell inherits the launcher's session id.
        other = home / 'projects/p/launcher.jsonl'
        other.write_text('{}\n')
        result = step('handoff', 'demo', '--file', '-', '--controller-runtime', 'codex', session='launcher')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(1, len(json.loads(ledger.read_text())['claude']))

    # 3.8: plan.md reached 55-69 KB; the warning now names what to trim.
    def test_long_summary_is_capped_and_size_warning_names_the_largest_parts(self):
        self.plan.write_text(OPEN_T1)
        self.run_step('dispatch', 'demo', 'T1')
        runs = self.change / 'runs'
        value = dict(status='DONE', summary='word ' * 200, files_changed=['label.py'],
                     tests=dict(red='old label failed', green='passed'), concerns=[],
                     report='docs/specadoc/demo/runs/T1-report.md')
        runs.joinpath('T1-report.md').write_text('```json\n' + json.dumps(value) + '\n```\n')
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        accepted = next(line for line in self.t1_block().splitlines() if line.startswith('- **Accepted result:**'))
        self.assertLess(len(accepted), 480)
        self.assertIn('(full: runs/T1-report.md)', accepted)
        self.plan.write_text(self.plan.read_text().replace('## Reconnaissance evidence\n',
                                                           '## Reconnaissance evidence\n' + 'x' * 40000 + '\n'))
        warning = self.validate('plan').stderr
        self.assertIn('Largest: Reconnaissance evidence', warning)

    # 3.7: the controller transcribed the reviewer's Markdown report into JSON by hand.
    def test_review_result_reads_the_reviewers_markdown_reply(self):
        self.plan.write_text(OPEN_T1)
        self.run_step('dispatch', 'demo', 'T1')
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        self.assertEqual(0, self.run_step('pre-review', 'demo').returncode)
        reply = ('## Verdict\nPASS\n\n## Findings\n- MINOR label.py:2 — naming\n\n## Result JSON\n\n```json\n'
                 + json.dumps({'verdict': 'PASS', 'findings': [{'severity': 'MINOR', 'location': 'label.py:2',
                                                                 'summary': 'rename for clarity'}],
                               'report': 'Label is ready.'}) + '\n```\n')
        self.change.joinpath('runs/G1-reply.md').write_text(reply)
        result = self.run_step('review-result', 'demo', '--result-file', 'docs/specadoc/demo/runs/G1-reply.md')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('MINOR (G1-1): label.py:2 — rename for clarity', self.plan.read_text())

    def test_reviewer_contract_asks_for_result_json(self):
        from test_specadoc_step import SCRIPTS
        role = (SCRIPTS.parent / 'references/roles/reviewer.md').read_text()
        self.assertIn('## Result JSON', role)
        self.assertIn('assets/reviewer-result.schema.json', role)

    # 3.7/3.8: approval and spec/plan/design sha256 sums were written by hand.
    def test_approve_records_provenance_and_detects_later_spec_edits(self):
        self.plan.write_text(OPEN_T1.replace('**Status:** Approved (synthetic test fixture)',
                                             '**Status:** Awaiting user approval'))
        self.assertIn('approval required', self.run_step('status', 'demo').stdout.replace(
            'plan approval is required', 'approval required'))
        result = self.run_step('approve', 'demo', '--by', 'orchestrator',
                               '--source', 'mandate D25, decision D58 (ordinary local plan)')
        self.assertEqual(0, result.returncode, result.stdout)
        section = self.plan.read_text().split('## Plan approval', 1)[1].split('## ', 1)[0]
        self.assertIn('**Status:** Approved', section)
        self.assertIn('**Bindings shown:** worker claude/test/low', section)
        self.assertIn('**Approval provenance:** orchestrator decision under user mandate: mandate D25', section)
        record = json.loads(self.change.joinpath('runs/approval.json').read_text())
        self.assertEqual(['spec.md'], list(record['artifacts']))
        self.assertIn('approval: approved\n', self.run_step('status', 'demo').stdout)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.change.joinpath('spec.md').write_text(self.change.joinpath('spec.md').read_text() + '\nLate edit.\n')
        self.assertIn('changed since approval: spec.md (re-approve)', self.run_step('status', 'demo').stdout)

    def test_approve_needs_a_source_and_bindings(self):
        self.plan.write_text(OPEN_T1.replace('**Bindings shown:** worker claude/test/low', '**Bindings shown:** Pending'))
        result = self.run_step('approve', 'demo', '--by', 'user', '--source', 'Pending')
        self.assertEqual(2, result.returncode, result.stdout)
        result = self.run_step('approve', 'demo', '--by', 'user', '--source', '"ок, одобряю план"')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('--bindings', result.stdout)
        result = self.run_step('approve', 'demo', '--by', 'user', '--source', '"ок, одобряю план"',
                               '--bindings', 'worker claude/sonnet/medium')
        self.assertEqual(0, result.returncode, result.stdout)


if __name__ == '__main__':
    unittest.main()
