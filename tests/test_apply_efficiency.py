"""Safety and workflow regressions from the November waitlist audit."""
from __future__ import annotations

import json
import unittest

import test_apply_reliability as reliability
from test_specadoc_step import PLAN


class ApplyEfficiencyTest(unittest.TestCase):
    setUp = reliability.ApplyReliabilityTest.setUp
    tearDown = reliability.ApplyReliabilityTest.tearDown
    run_step = reliability.ApplyReliabilityTest.run_step
    report = reliability.ApplyReliabilityTest.report

    def test_preflight_collects_errors_without_writing_or_executing(self):
        self.plan.write_text(PLAN.replace('`label.py`, `check_label.py`', 'the implementation', 1)
                             .replace('`python3 check_label.py`', 'Check `label.py`', 1))
        result = self.run_step('preflight', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Files', result.stdout)
        self.assertIn('Verification', result.stdout)
        self.assertFalse((self.change / 'runs').exists())

    def test_invalid_dispatch_does_not_freeze_baseline(self):
        self.plan.write_text(PLAN.replace('`label.py`, `check_label.py`', 'the implementation', 1))
        self.assertNotEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.assertFalse((self.change / 'runs/T1-baseline.json').exists())
        self.plan.write_text(PLAN)
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)

    def test_brief_carries_exact_verifier_context(self):
        self.repo.joinpath('check.conf').write_text('strict=true')
        self.plan.write_text(PLAN.replace('- **Files:** `label.py`, `check_label.py`',
            '- **Files:** `label.py`, `check_label.py`\n'
            '- **Verification inputs:** `check.conf`\n'
            '- **Test context:** DB-free only; use the repository configuration.', 1))
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        brief = self.change.joinpath('runs/T1-brief.md').read_text()
        self.assertIn('check.conf', brief)
        self.assertIn('DB-free only', brief)
        self.assertIn('python3 check_label.py', brief)

    def test_controller_microfix_uses_same_gates_without_worker_routing(self):
        self.plan.write_text(PLAN.replace('- **Owner:** worker',
            '- **Owner:** controller\n'
            '- **Controller justification:** One-file, one-cycle fix; handoff overhead exceeds context savings.', 1)
            .replace('- **Files:** `label.py`, `check_label.py`', '- **Files:** `label.py`', 1))
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('controller', result.stdout)
        self.assertNotIn('dispatch the worker', result.stdout)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)

    def counted_check(self):
        self.repo.joinpath('check_label.py').write_text(
            'from pathlib import Path\n'
            'p=Path("docs/specadoc/demo/runs/T1-count.log")\n'
            'p.write_text(str(int(p.read_text())+1) if p.exists() else "1")\n')

    def accepted(self):
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)

    def test_directory_child_change_invalidates_verification(self):
        self.repo.joinpath('src').mkdir()
        self.repo.joinpath('src/a.py').write_text('a=1')
        self.plan.write_text(PLAN.replace('`label.py`, `check_label.py`', '`src/`, `check_label.py`', 1))
        self.counted_check()
        self.accepted()
        self.repo.joinpath('src/a.py').write_text('a=2')
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('2', self.change.joinpath('runs/T1-count.log').read_text())

    def test_derived_and_config_changes_invalidate_reuse(self):
        self.repo.joinpath('derived.py').write_text('a=1')
        self.repo.joinpath('check.conf').write_text('strict=true')
        self.plan.write_text(PLAN.replace('- **Files:** `label.py`, `check_label.py`',
            '- **Files:** `label.py`, `check_label.py`\n'
            '- **Derived files:** `derived.py`\n'
            '- **Verification inputs:** `check.conf`', 1))
        self.counted_check()
        self.accepted()
        for path in ['derived.py', 'check.conf']:
            self.repo.joinpath(path).write_text('changed')
            if path == 'check.conf':
                result = self.run_step('amend', 'demo', 'T1', '--controller-path', path,
                                       '--reason', 'User supplied corrected verifier configuration')
                self.assertEqual(0, result.returncode, result.stdout)
            result = self.run_step('accept', 'demo', 'T1')
            self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('3', self.change.joinpath('runs/T1-count.log').read_text())

    def test_legacy_verification_record_is_not_reused(self):
        self.counted_check()
        self.accepted()
        path = self.change / 'runs/T1-baseline.json'
        state = json.loads(path.read_text())
        state['verification'].pop('inputs', None)
        path.write_text(json.dumps(state))
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('2', self.change.joinpath('runs/T1-count.log').read_text())

    def test_task_delta_is_generated_without_adopting_dirty_files(self):
        self.repo.joinpath('user-work.py').write_text('preserve=true')
        self.accepted()
        self.repo.joinpath('label.py').write_text('changed')
        result = self.run_step('manifest', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(['label.py'], payload['files_changed'])
        self.assertEqual(['- `label.py`'], payload['review_scope'])
        self.assertFalse((self.change / 'runs/T1-manifest.json').exists())

    def test_verification_inputs_cannot_be_changed_without_amendment(self):
        self.repo.joinpath('check.conf').write_text('strict=true')
        self.accepted()
        self.plan.write_text(self.plan.read_text().replace('- **Owner:** worker',
            '- **Owner:** worker\n- **Verification inputs:** `check.conf`', 1))
        result = self.run_step('accept', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('verification inputs', result.stdout)

    def test_implicit_lockfile_creation_invalidates_reuse(self):
        self.repo.joinpath('package.json').write_text('{}')
        self.plan.write_text(PLAN.replace('`label.py`, `check_label.py`',
                                         '`label.py`, `check_label.py`, `package.json`', 1))
        self.counted_check()
        self.accepted()
        self.repo.joinpath('package-lock.json').write_text('{}')
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('2', self.change.joinpath('runs/T1-count.log').read_text())

    def test_glob_addition_and_deletion_invalidate_reuse(self):
        self.repo.joinpath('src').mkdir()
        self.repo.joinpath('src/a.py').write_text('a=1')
        self.plan.write_text(PLAN.replace('`label.py`, `check_label.py`', '`src/*.py`, `check_label.py`', 1))
        self.counted_check()
        self.accepted()
        self.repo.joinpath('src/b.py').write_text('b=2')
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.repo.joinpath('src/a.py').unlink()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('3', self.change.joinpath('runs/T1-count.log').read_text())

    def test_manifest_marks_deletion_and_rejects_scope_expansion(self):
        self.accepted()
        self.repo.joinpath('label.py').unlink()
        result = self.run_step('manifest', 'demo', 'T1')
        self.assertEqual(['- `!label.py`'], json.loads(result.stdout)['review_scope'])
        self.repo.joinpath('outside.py').write_text('unapproved')
        result = self.run_step('manifest', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('outside.py', result.stdout)

    def test_changing_check_inputs_during_verification_is_not_accepted(self):
        command = '`python3 -c "open(\'label.py\', \'w\').write(\'changed\')"`'
        self.plan.write_text(PLAN.replace('`python3 check_label.py`', command, 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('inputs changed', result.stdout)

    def test_directory_symlink_outside_repo_is_blocked(self):
        self.repo.joinpath('src').mkdir()
        self.repo.joinpath('src/outside').symlink_to(self.repo.parent, target_is_directory=True)
        self.repo.joinpath('src/leak.py').symlink_to(__file__)
        self.plan.write_text(PLAN.replace('`label.py`, `check_label.py`', '`src/`, `check_label.py`', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('leaves repository', result.stdout)

    def test_derived_content_stales_dependency_evidence(self):
        self.repo.joinpath('derived.py').write_text('a=1')
        self.plan.write_text(PLAN.replace('- **Files:** `label.py`, `check_label.py`',
            '- **Files:** `label.py`, `check_label.py`\n- **Derived files:** `derived.py`', 1))
        self.accepted()
        self.repo.joinpath('derived.py').write_text('changed')
        self.plan.write_text(self.plan.read_text().replace('### T2 — String result\n',
            '### T2 — String result\n- **Depends on:** T1\n'))
        result = self.run_step('dispatch', 'demo', 'T2')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('stale', result.stdout)

    def test_controller_task_needs_no_justification_or_low_decision_risk(self):
        self.plan.write_text(PLAN.replace('- **Owner:** worker', '- **Owner:** controller', 1)
            .replace('- **Decision risk:** low', '- **Decision risk:** medium', 1))
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertNotIn('dispatch the worker', result.stdout)

    def test_worker_task_still_requires_low_decision_risk(self):
        self.plan.write_text(PLAN.replace('- **Decision risk:** low', '- **Decision risk:** medium', 1))
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('resolve material decisions', result.stdout)

    def test_controller_microfix_does_not_bypass_runtime_validation(self):
        self.plan.write_text(PLAN.replace('- **Owner:** worker',
            '- **Owner:** controller\n- **Controller justification:** One-file, one-cycle fix.', 1))
        self.repo.joinpath('.specadoc.json').write_text(json.dumps({
            'version': 1, 'roles': {'controller': {'runtime': 'codex'}}}))
        result = self.run_step('dispatch', 'demo', 'T1', '--controller-runtime', 'opencode')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('binding expects codex', result.stdout)
        self.assertFalse(self.change.joinpath('runs/T1-baseline.json').exists())

    def test_controller_files_none_is_rejected_before_baseline(self):
        self.plan.write_text(PLAN.replace('- **Owner:** worker',
            '- **Owner:** controller\n- **Controller justification:** One-file, one-cycle fix.', 1)
            .replace('`label.py`, `check_label.py`', 'None', 1))
        self.assertNotEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.assertFalse(self.change.joinpath('runs/T1-baseline.json').exists())

    def test_legacy_record_without_hash_cannot_pass_pre_review(self):
        self.accepted()
        path = self.change / 'runs/T1-baseline.json'
        state = json.loads(path.read_text())
        state['verification'].pop('inputs')
        path.write_text(json.dumps(state))
        plan = self.plan.read_text()
        for value in ['', '- **Evidence hash:** Pending\n']:
            self.plan.write_text('\n'.join(line for line in plan.splitlines()
                                          if not line.startswith('- **Evidence hash:'))
                                 .replace('### T2', value + '### T2', 1))
            result = self.run_step('pre-review', 'demo', '--dry-run')
            self.assertNotEqual(0, result.returncode)
            self.assertIn('Evidence predates', result.stdout)

    def test_bracketed_route_content_and_deletion_invalidate_checks(self):
        route = self.repo / 'app/[slug]/page.tsx'
        route.parent.mkdir(parents=True)
        route.write_text('old')
        self.plan.write_text(PLAN.replace('`label.py`, `check_label.py`',
            '`app/[slug]/page.tsx`, `check_label.py`', 1)
            .replace('- **Verification:**', '- **Verification inputs:** `check_label.py`\n- **Verification:**', 1))
        self.counted_check()
        self.accepted()
        route.write_text('new')
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        route.unlink()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        self.assertEqual('3', self.change.joinpath('runs/T1-count.log').read_text())

    def test_mutation_with_scope_failure_does_not_save_reusable_pass(self):
        command = '`python3 -c "open(\'label.py\', \'w\').write(\'changed\')"`'
        self.plan.write_text(PLAN.replace('`python3 check_label.py`', command, 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        original = self.repo.joinpath('label.py').read_bytes()
        self.repo.joinpath('outside.py').write_text('unapproved')
        self.report()
        self.assertNotEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        state = json.loads(self.change.joinpath('runs/T1-baseline.json').read_text())
        self.assertNotIn('verification', state)
        self.repo.joinpath('outside.py').unlink()
        self.repo.joinpath('label.py').write_bytes(original)
        self.assertNotEqual(0, self.run_step('accept', 'demo', 'T1').returncode)

    def test_fallback_configuration_and_environment_stale_dependencies(self):
        from unittest.mock import patch
        import os
        self.repo.joinpath('check.conf').write_text('old')
        self.accepted()
        self.plan.write_text(self.plan.read_text().replace('### T2 — String result\n',
            '### T2 — String result\n- **Depends on:** T1\n'))
        self.repo.joinpath('check.conf').write_text('new')
        result = self.run_step('dispatch', 'demo', 'T2')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('stale', result.stdout)
        self.repo.joinpath('check.conf').write_text('old')
        with patch.dict(os.environ, SPECADOC_TEST_CONTEXT='changed'):
            result = self.run_step('dispatch', 'demo', 'T2')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('stale', result.stdout)

    def test_macos_child_process_identity_is_not_verifier_configuration(self):
        from unittest.mock import patch
        import os
        self.accepted()
        with patch.dict(os.environ, XPC_SERVICE_NAME='application.fixture.identity'):
            result = self.run_step('pre-review', 'demo', '--dry-run')
        self.assertEqual(0, result.returncode, result.stdout)

    def test_new_session_identity_does_not_stale_evidence(self):
        from unittest.mock import patch
        import os
        self.accepted()
        with patch.dict(os.environ, HOST_SESSION_ID='next-session', RUNTIME_THREAD_ID='thr_next',
                        HTTPS_PROXY='http://localhost:1/next-token', TMPDIR='/tmp/next-session'):
            result = self.run_step('pre-review', 'demo', '--dry-run')
        self.assertEqual(0, result.returncode, result.stdout)

    def test_stale_environment_message_names_the_variable(self):
        from unittest.mock import patch
        import os
        self.accepted()
        with patch.dict(os.environ, SPECADOC_TEST_CONTEXT='changed'):
            result = self.run_step('pre-review', 'demo', '--dry-run')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('environment changed: SPECADOC_TEST_CONTEXT', result.stdout)

    def test_project_environment_allowlist_limits_the_digest(self):
        from unittest.mock import patch
        import os
        self.repo.joinpath('.specadoc.json').write_text(json.dumps(
            {'version': 1, 'verification': {'environment': ['PATH', 'CHECK_*']}}))
        self.accepted()
        with patch.dict(os.environ, SPECADOC_TEST_CONTEXT='changed'):
            result = self.run_step('pre-review', 'demo', '--dry-run')
        self.assertEqual(0, result.returncode, result.stdout)
        with patch.dict(os.environ, CHECK_MODE='strict'):
            result = self.run_step('pre-review', 'demo', '--dry-run')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('environment changed: CHECK_MODE', result.stdout)


if __name__ == '__main__':
    unittest.main()
