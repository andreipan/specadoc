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


class WorkerResultTest(unittest.TestCase):
    """3.5: the only worker result was manifest-shaped JSON; the controller then implemented everything."""
    setUp = reliability.ApplyReliabilityTest.setUp
    tearDown = reliability.ApplyReliabilityTest.tearDown
    run_step = reliability.ApplyReliabilityTest.run_step
    validate = ExternalVerificationTest.validate

    def dispatch_and_edit(self):
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('specadoc_step.py report', result.stdout)
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # final\n')

    def write_report(self, *extra):
        return self.run_step('report', 'demo', 'T1', '--status', 'DONE', '--summary', 'label() returns ready',
                             '--red', 'check_label.py failed on the old label', '--green', 'python3 check_label.py passed',
                             *extra)

    def test_report_step_writes_a_result_accept_takes(self):
        self.dispatch_and_edit()
        result = self.write_report()
        self.assertEqual(0, result.returncode, result.stdout)
        report = self.change.joinpath('runs/T1-report.md').read_text()
        payload = json.loads(report.rsplit('```json\n', 1)[1].split('```', 1)[0])
        self.assertEqual(['label.py'], payload['files_changed'])
        self.assertEqual('docs/specadoc/demo/runs/T1-report.md', payload['report'])
        self.assertIn(json.dumps(payload, ensure_ascii=False), result.stdout)
        accepted = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, accepted.returncode, accepted.stdout)
        self.assertIn('label() returns ready', self.plan.read_text())

    def test_report_step_flags_changes_outside_scope(self):
        self.dispatch_and_edit()
        self.repo.joinpath('stray.py').write_text('z = 1\n')
        result = self.write_report()
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("stray.py (outside the task's Files)", result.stdout)

    def test_manifest_shaped_result_names_the_mistake(self):
        self.dispatch_and_edit()
        runs = self.change / 'runs'
        manifest = {'task': 'T1', 'files_changed': ['label.py'], 'review_scope': ['- `label.py`']}
        runs.joinpath('T1-report.md').write_text('# report\n\n```json\n' + json.dumps(manifest) + '\n```\n')
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('$.summary: missing', result.stdout)
        self.assertIn('this is `manifest` output, not a worker result', result.stdout)
        self.assertIn('specadoc_step.py report demo T1', result.stdout)

    def test_brief_ends_with_report_not_manifest(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        brief = self.change.joinpath('runs/T1-brief.md').read_text()
        self.assertIn('specadoc_step.py report demo T1 --status DONE', brief)
        self.assertNotIn(' manifest demo T1', brief)

    def test_external_worker_route_prints_the_start_command(self):
        self.repo.joinpath('.codex/agents').mkdir(parents=True)
        self.repo.joinpath('.codex/agents/worker.toml').write_text('model = "executor"\nmodel_reasoning_effort = "low"\n')
        self.repo.joinpath('.specadoc.json').write_text(json.dumps(
            {'version': 1, 'roles': {'worker': {'runtime': 'codex'}, 'controller': {'runtime': 'claude'}}}))
        result = self.run_step('dispatch', 'demo', 'T1', '--controller-runtime', 'claude')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('run_role.py start --role worker --controller-runtime claude', result.stdout)
        self.assertIn('--prompt-file docs/specadoc/demo/runs/T1-brief.md --name T1', result.stdout)

    def test_plan_warns_on_worker_ready_controller_task(self):
        open_controller = PLAN.replace('- [x] Complete', '- [ ] Complete', 1).replace(
            '- **Owner:** worker\n- **Verification owner:** controller', '- **Owner:** controller', 1)
        self.plan.write_text(open_controller)
        result = self.validate('plan')
        self.assertIn('T1: low decision risk with exact Files and Verification; set Owner: worker', result.stderr)
        self.plan.write_text(open_controller.replace(
            '- **Owner:** controller', '- **Owner:** controller\n'
            '- **Controller justification:** One-line edit; the brief would be longer than the change.', 1))
        self.assertNotIn('set Owner: worker', self.validate('plan').stderr)


class PlanGrowthTest(unittest.TestCase):
    """3.5: plan.md reached 68 KB; two inline round manifests were 16 KB, session notes 7.5 KB."""
    setUp = reliability.ApplyReliabilityTest.setUp
    tearDown = reliability.ApplyReliabilityTest.tearDown
    run_step = reliability.ApplyReliabilityTest.run_step
    report = reliability.ApplyReliabilityTest.report
    validate = ExternalVerificationTest.validate

    def accepted(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)

    def latest(self):
        import sys
        from test_specadoc_step import SCRIPTS
        sys.path.insert(0, str(SCRIPTS))
        from validate_change import Document, latest_review_round, review_manifest_hash
        return latest_review_round(Document(self.plan, 'plan.md')), review_manifest_hash

    def test_round_manifest_lives_in_runs_and_stays_hash_bound(self):
        self.accepted()
        result = self.run_step('pre-review', 'demo')
        self.assertEqual(0, result.returncode, result.stdout)
        text = self.plan.read_text()
        self.assertNotIn('```json', text)
        self.assertIn('- **Manifest:** `runs/G1-manifest.json`', text)
        (identifier, fields, manifest), manifest_hash = self.latest()
        self.assertEqual('G1', identifier)
        self.assertIn('label.py', manifest)
        self.assertEqual(fields['Snapshot'], manifest_hash(manifest))
        path = self.change / 'runs/G1-manifest.json'
        path.write_text(json.dumps({**manifest, 'label.py': '0' * 64}))
        (_, fields, tampered), manifest_hash = self.latest()
        self.assertNotEqual(fields['Snapshot'], manifest_hash(tampered))
        path.unlink()
        self.assertIsNone(self.latest()[0][2])

    def test_inline_manifest_of_older_plans_is_still_read(self):
        manifest = {'label.py': 'a' * 64}
        self.plan.write_text(self.plan.read_text().replace(
            '**Result:** Pending', '**Result:** Pending\n\n### G1\n\n- **Type:** initial\n- **Outcome:** Pending\n\n'
            '<details><summary>Manifest</summary>\n\n```json\n' + json.dumps(manifest) + '\n```\n\n</details>\n'))
        self.assertEqual(manifest, self.latest()[0][2])

    def test_handoff_is_overwritten_and_bounded(self):
        notes = self.repo / 'notes.md'
        notes.write_text('T2 next; quality needs the unsandboxed shell.\n')
        result = self.run_step('handoff', 'demo', '--file', 'notes.md')
        self.assertEqual(0, result.returncode, result.stdout)
        notes.write_text('T3 next.\n')
        self.assertEqual(0, self.run_step('handoff', 'demo', '--file', 'notes.md').returncode)
        handoff = self.change / 'runs/handoff.md'
        self.assertEqual('T3 next.\n', handoff.read_text())
        notes.write_text('x' * 5000)
        result = self.run_step('handoff', 'demo', '--file', 'notes.md')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertEqual('T3 next.\n', handoff.read_text())

    def test_handoff_during_a_task_is_not_a_scope_violation(self):
        import os
        import subprocess
        import sys
        from test_specadoc_step import SCRIPTS
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        piped = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'specadoc_step.py'), 'handoff', 'demo', '--file', '-'],
                               cwd=self.repo, env=env, input='mid-task notes\n', capture_output=True, text=True)
        self.assertEqual(0, piped.returncode, piped.stdout)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)

    def test_large_handoff_section_warns(self):
        self.plan.write_text(self.plan.read_text().replace(
            'Read spec.md and plan.md, then continue with the next task.',
            'Read spec.md and plan.md, then continue with the next task.\n\n### Apply session notes\n\n'
            + '- note about a finished task and its interfaces\n' * 60))
        self.assertIn('plan.md Handoff is', self.validate('plan').stderr)

    def test_status_names_task_states_and_next_step(self):
        self.plan.write_text(PLAN.replace('Approved (synthetic test fixture)', 'Awaiting user approval'))
        self.assertIn('next: obtain plan approval', self.run_step('status', 'demo').stdout)
        self.plan.write_text(PLAN)
        self.accepted()
        result = self.run_step('status', 'demo')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('  T1 worker accepted', result.stdout)
        self.assertIn('  T2 worker complete (no task state)', result.stdout)
        self.assertIn('review: none', result.stdout)
        self.assertIn('next: pre-review', result.stdout)
        self.repo.joinpath('extra.py').write_text('drift\n')
        result = self.run_step('status', 'demo')
        self.assertIn('T1 worker accepted, stale: verification inputs changed: extra.py', result.stdout)
        self.assertIn('next: specadoc_step.py refresh demo (T1)', result.stdout)
        self.assertLess(len(result.stdout.splitlines()), 12)


if __name__ == '__main__':
    unittest.main()
