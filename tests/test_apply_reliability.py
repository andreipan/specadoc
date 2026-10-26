"""Regressions from the October 2026 native-session workflow audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_specadoc_step import PLAN, SPEC, SCRIPTS


class ApplyReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        self.change = self.repo / 'docs/specadoc/demo'
        self.change.mkdir(parents=True)
        self.change.joinpath('spec.md').write_text(SPEC)
        self.plan = self.change / 'plan.md'
        self.plan.write_text(PLAN)
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"\n')
        self.repo.joinpath('check_label.py').write_text('from label import label\nassert label() == "ready"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_step(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        env.pop('CLAUDE_CODE_SESSION_ID', None)
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'specadoc_step.py'), *args],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def report(self, status='DONE', concerns=None, task='T1', files=('label.py',), report=None):
        runs = self.change / 'runs'
        runs.mkdir(exist_ok=True)
        value = dict(status=status, summary='Ready diagnostic label', files_changed=list(files),
                     tests=dict(red='old label failed', green='python3 check_label.py passed'),
                     concerns=concerns or [], report=report or f'docs/specadoc/demo/runs/{task}-report.md')
        runs.joinpath(f'{task}-report.md').write_text('# Worker report\n\n```json\n' + json.dumps(value) + '\n```\n')

    def test_dispatch_requires_approval(self):
        self.plan.write_text(PLAN.replace('Approved (synthetic test fixture)', 'Awaiting user approval'))
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('approval', result.stdout.lower())
        self.assertFalse((self.change / 'runs/T1-baseline.json').exists())

    def test_dispatch_requires_completed_dependencies(self):
        self.plan.write_text(PLAN.replace('### T1 — Ready label', '### T1 — Ready label')
                             .replace('- **Requirements:** R1', '- **Depends on:** T2\n- **Requirements:** R1', 1)
                             .replace('### T2 — String result\n- [x]', '### T2 — String result\n- [ ]'))
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('T2', result.stdout)

    def test_retry_cannot_erase_scope_violation(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        baseline = self.change / 'runs/T1-baseline.json'
        original = json.loads(baseline.read_text())['manifest']
        self.repo.joinpath('outside.py').write_text('outside = True\n')
        self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(original, json.loads(baseline.read_text())['manifest'])
        result = self.run_step('accept', 'demo', 'T1', '--verify')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('outside.py', result.stdout)

    def test_verification_without_report_is_not_acceptance(self):
        self.run_step('dispatch', 'demo', 'T1')
        result = self.run_step('accept', 'demo', 'T1', '--verify')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('report', result.stdout.lower())

    def test_blocked_and_unresolved_concerns_cannot_be_accepted(self):
        self.run_step('dispatch', 'demo', 'T1')
        for status in ('BLOCKED', 'NEEDS_CONTEXT', 'DONE_WITH_CONCERNS'):
            with self.subTest(status=status):
                self.report(status, ['Missing decision'])
                result = self.run_step('accept', 'demo', 'T1', '--verify')
                self.assertNotEqual(0, result.returncode, result.stdout)

    def test_valid_acceptance_persists_evidence_and_keeps_report(self):
        self.plan.write_text(PLAN.replace('- [x] Complete', '- [ ] Complete', 1))
        self.run_step('dispatch', 'demo', 'T1')
        self.report()
        before = self.change.joinpath('runs/T1-report.md').read_bytes()
        result = self.run_step('accept', 'demo', 'T1', '--verify')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('result: ACCEPTED', result.stdout)
        self.assertEqual(before, self.change.joinpath('runs/T1-report.md').read_bytes())
        task = self.plan.read_text().split('### T2')[0]
        self.assertIn('- [x] Complete', task)
        self.assertIn('Accepted result', task)
        record = json.loads(self.change.joinpath('runs/T1-baseline.json').read_text())
        self.assertEqual('accepted', record['state'])

    def test_scope_only_is_labelled_checked_not_accepted(self):
        self.run_step('dispatch', 'demo', 'T1')
        result = self.run_step('accept', 'demo', 'T1', '--scope-only')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('result: CHECKED', result.stdout)

    def test_scope_amendment_is_explicit_and_preserves_original_manifest(self):
        self.run_step('dispatch', 'demo', 'T1')
        path = self.change / 'runs/T1-baseline.json'
        original = json.loads(path.read_text())['manifest']
        self.repo.joinpath('wiring.py').write_text('binding = True\n')
        self.assertNotEqual(0, self.run_step('accept', 'demo', 'T1', '--scope-only').returncode)
        result = self.run_step('amend', 'demo', 'T1', '--allow', 'wiring.py',
                               '--reason', 'Controller approved required composition-root binding')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(original, json.loads(path.read_text())['manifest'])
        self.report()
        result = self.run_step('accept', 'demo', 'T1', '--verify')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_context_boundary_prevents_another_dispatch(self):
        result = self.run_step('dispatch', 'demo', 'T1', '--context-tokens', '160000')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('handoff', result.stdout.lower())

    def test_capability_application_does_not_break_resumed_dispatch(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        capability = self.repo / 'docs/specadoc/specs/label.md'
        capability.parent.mkdir(parents=True)
        capability.write_text('### C1 — Diagnostic label is ready\n')
        # The controller explicitly owns this post-review documentation edit.
        result = self.run_step('amend', 'demo', 'T1', '--controller-path', capability.relative_to(self.repo).as_posix(),
                               '--reason', 'Controller materialized the accepted capability after review')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_unaccepted_dispatch_cannot_be_hidden_by_checked_plan_boxes(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        result = self.run_step('pre-review', 'demo')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('ACCEPTED', result.stdout)

    def test_concerns_disposition_reuses_only_unchanged_verification(self):
        self.repo.joinpath('check_label.py').write_text(
            'from pathlib import Path\np=Path("docs/specadoc/demo/runs/T1-count.log")\n'
            'p.write_text(str(int(p.read_text())+1) if p.exists() else "1")\n')
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report('DONE_WITH_CONCERNS', ['One documented catalog limitation'])
        result = self.run_step('accept', 'demo', 'T1')
        self.assertIn('result: NEEDS_DECISION', result.stdout)
        self.assertNotEqual(0, result.returncode)
        result = self.run_step('accept', 'demo', 'T1', '--note', 'User accepted the documented limitation without code changes')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual('1', self.change.joinpath('runs/T1-count.log').read_text())

    def test_checked_dependency_with_unaccepted_state_is_not_ready(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.plan.write_text(self.plan.read_text().replace('### T2 — String result\n',
            '### T2 — String result\n- **Depends on:** T1\n'))
        result = self.run_step('dispatch', 'demo', 'T2')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('accepted', result.stdout.lower())

    def test_checked_dependency_with_stale_accepted_evidence_is_not_ready(self):
        self.run_step('dispatch', 'demo', 'T1')
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1', '--verify').returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "changed"\n')
        self.plan.write_text(self.plan.read_text().replace('### T2 — String result\n',
            '### T2 — String result\n- **Depends on:** T1\n'))
        result = self.run_step('dispatch', 'demo', 'T2')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('stale', result.stdout.lower())

    def test_derived_files_and_lockfiles_are_not_violations(self):
        self.plan.write_text(PLAN.replace('- **Files:** `label.py`, `check_label.py`',
                                          '- **Files:** `label.py`, `check_label.py`, `package.json`\n'
                                          '- **Derived files:** `pkg/index.ts`', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('package-lock.json').write_text('{}')
        self.repo.joinpath('pkg').mkdir()
        self.repo.joinpath('pkg/index.ts').write_text('export {}\n')
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('derived: package-lock.json, pkg/index.ts', result.stdout)

    def test_lockfile_without_manifest_in_scope_is_a_violation(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('package-lock.json').write_text('{}')
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn('package-lock.json', result.stdout)

    def test_controller_plan_edit_is_not_a_worker_violation(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.plan.write_text(self.plan.read_text().replace('## Global constraints', '## Global constraints\nController note.'))
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_scope_violation_still_runs_verification_and_reports_both(self):
        self.repo.joinpath('check_label.py').write_text(
            'from pathlib import Path\np=Path("docs/specadoc/demo/runs/T1-count.log")\n'
            'p.write_text(str(int(p.read_text())+1) if p.exists() else "1")\n')
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('outside.py').write_text('outside = True\n')
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn('outside.py', result.stdout)
        self.assertIn('verification passed', result.stdout)
        self.assertEqual('1', self.change.joinpath('runs/T1-count.log').read_text())

    def test_amend_derived_records_wiring_path(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('index.ts').write_text('export {}\n')
        self.report()
        self.assertEqual(1, self.run_step('accept', 'demo', 'T1').returncode)
        result = self.run_step('amend', 'demo', 'T1', '--derived', 'index.ts', '--reason', 'Barrel export required by T1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('- **Derived files:** `index.ts`', self.plan.read_text())
        result = self.run_step('accept', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_dispatch_reports_context_and_plan_warns_on_shared_broad_verification(self):
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertIn('context not reported', result.stdout)
        result = self.run_step('dispatch', 'demo', 'T2', '--context-tokens', '42000')
        self.assertIn('context 42000 tokens', result.stdout)
        gate = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'validate_change.py'), 'demo', '--phase', 'plan'],
                              cwd=self.repo, capture_output=True, text=True)
        self.assertIn('T1, T2, T3 share Verification', gate.stderr)

    def test_worker_cannot_rewrite_its_verification_or_approval(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "broken"\n')
        text = self.plan.read_text()
        self.plan.write_text(text.replace('- **Verification:** `python3 check_label.py`', '- **Verification:** `true`', 1))
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertNotIn('ACCEPTED', result.stdout)
        self.plan.write_text(text.replace('Approved (synthetic test fixture)', 'Approved (edited)'))
        result = self.run_step('accept', 'demo', 'T1', '--scope-only')
        self.assertEqual(1, result.returncode, result.stdout)

    def test_overlapping_dependent_tasks_stay_ready_after_later_acceptance(self):
        text = PLAN.replace('- [x] Complete', '- [ ] Complete')
        text = text.replace('### T2 — String result\n', '### T2 — String result\n- **Depends on:** T1\n')
        text = text.replace('### T3 — Repeatable result\n', '### T3 — Repeatable result\n- **Depends on:** T2\n')
        self.plan.write_text(text)
        for task, value in (('T1', 'ready'), ('T2', 'ready')):
            self.assertEqual(0, self.run_step('dispatch', 'demo', task).returncode)
            self.repo.joinpath('label.py').write_text(f'def label():\n    return "{value}"  # {task}\n')
            self.report(task=task)
            result = self.run_step('accept', 'demo', task)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        result = self.run_step('dispatch', 'demo', 'T3')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        # An unaccepted later edit is still stale evidence.
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # drift\n')
        result = self.run_step('dispatch', 'demo', 'T3')
        self.assertIn('stale', result.stdout)

    def test_bracketed_route_paths_and_absolute_result_files_are_literal_paths(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        route = self.repo / 'app/[slug]/page.tsx'
        route.parent.mkdir(parents=True)
        route.write_text('export default 1\n')
        result = self.run_step('amend', 'demo', 'T1', '--allow', 'app/[slug]/page.tsx', '--reason', 'Route file required by T1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.report(files=('label.py', 'app/[slug]/page.tsx'))
        source = self.change / 'runs/T1-report.md'
        result = self.run_step('accept', 'demo', 'T1', '--result-file', str(source.resolve()))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_lockfile_follows_the_manifest_directory(self):
        self.plan.write_text(PLAN.replace('- **Files:** `label.py`, `check_label.py`',
                                          '- **Files:** `label.py`, `check_label.py`, `web/package.json`', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('api').mkdir()
        self.repo.joinpath('api/yarn.lock').write_text('')
        self.repo.joinpath('package-lock.json').write_text('{}')
        result = self.run_step('accept', 'demo', 'T1', '--scope-only')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn('api/yarn.lock', result.stdout)
        self.assertNotIn('package-lock.json (', result.stdout)

    def test_repeated_ui_accept_keeps_observed_records_once(self):
        self.plan.write_text(PLAN.replace('- **Surface:** code\n- **Delivery verification:** N/A',
                                          '- **Surface:** ui\n- **Delivery verification:** build, typecheck, browser', 1).replace(
            '- **Evidence:** python3 check_label.py: PASS after observed RED',
            '- **Evidence:** Build: PASS; Typecheck: PASS; Browser: URL: http://localhost/ State: ready', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        for _ in range(2):
            self.assertEqual(0, self.run_step('accept', 'demo', 'T1').returncode)
        task = self.plan.read_text().split('### T2')[0]
        evidence = next(line for line in task.splitlines() if line.startswith('- **Evidence:**'))
        self.assertEqual(1, evidence.count('python3 check_label.py'))
        self.assertEqual(1, evidence.count('Browser: URL'))
        self.assertIn('Build: PASS', evidence)

    def claude_session(self, context):
        home = self.repo / 'claude-home'
        transcript = home / 'projects/-x/session-1.jsonl'
        transcript.parent.mkdir(parents=True)
        usage = dict(input_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=context - 10)
        transcript.write_text(json.dumps(dict(type='assistant', requestId='r', message=dict(usage=usage))) + '\n')
        return dict(CLAUDE_CONFIG_DIR=str(home), CLAUDE_CODE_SESSION_ID='session-1')

    def run_step_env(self, extra, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **extra)
        env.pop('SPECADOC_ROOT', None)
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'specadoc_step.py'), *args],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def test_dispatch_reads_this_claude_sessions_context(self):
        env = self.claude_session(170000)
        result = self.run_step_env(env, 'dispatch', 'demo', 'T1')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('170000', result.stdout)
        self.assertIn('session-1.jsonl', result.stdout)
        result = self.run_step_env(env, 'dispatch', 'demo', 'T1', '--context-tokens', '40000')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('context 40000 tokens (reported)', result.stdout)

    def test_accept_lists_amendments(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('wiring.py').write_text('x = 1\n')
        self.run_step('amend', 'demo', 'T1', '--allow', 'wiring.py', '--reason', 'Composition root binding')
        self.report()
        result = self.run_step('accept', 'demo', 'T1')
        self.assertIn('amendments: Composition root binding (wiring.py)', result.stdout)

    def test_same_stem_lockfile_follows_its_manifest(self):
        self.plan.write_text(PLAN.replace('- **Files:** `label.py`, `check_label.py`',
                                          '- **Files:** `label.py`, `check_label.py`, `api/Gemfile`', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.repo.joinpath('api').mkdir()
        self.repo.joinpath('api/Gemfile.lock').write_text('')
        self.repo.joinpath('Other.lock').write_text('')
        result = self.run_step('accept', 'demo', 'T1', '--scope-only')
        self.assertIn('Other.lock', result.stdout)
        self.assertNotIn('api/Gemfile.lock (', result.stdout)

    def test_update_task_is_idempotent_and_replaces_continuation_lines(self):
        sys.path.insert(0, str(SCRIPTS))
        from task_state import update_task
        from validate_change import Document
        self.plan.write_text(PLAN.replace('- **Evidence:** python3 check_label.py: PASS after observed RED\n### T2',
                                          '- **Evidence hash:** Pending; optional\n  continuation of the template\n\n### T2', 1))
        texts = []
        for _ in range(3):
            plan = Document(self.plan, str(self.plan))
            self.plan.write_text(update_task(plan, 'T1', {'Evidence hash': 'abc', 'Accepted result': 'ok'}, complete=True))
            texts.append(self.plan.read_text())
        self.assertEqual(texts[0], texts[2])
        task = texts[2].split('### T2')[0]
        self.assertNotIn('continuation of the template', task)
        self.assertNotIn('\n\n- **', task)
        self.assertTrue(task.endswith('- **Accepted result:** ok\n\n'), repr(task[-80:]))

    def test_reopen_starts_a_new_attempt_after_later_tasks(self):
        self.plan.write_text(PLAN.replace('- [x] Complete', '- [ ] Complete', 1))
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report()
        self.assertEqual(0, self.run_step('accept', 'demo', 'T1', '--verify').returncode)
        self.repo.joinpath('later_task.py').write_text('later = True\n')
        result = self.run_step('dispatch', 'demo', 'T1', '--reopen', 'Fix review finding G1-1 in label.py')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = json.loads(self.change.joinpath('runs/T1-baseline.json').read_text())
        self.assertEqual(1, len(record['attempts']))
        self.assertEqual('accepted', record['attempts'][0]['state'])
        self.assertIn('later_task.py', record['manifest'])
        self.assertIn('- [ ] Complete', self.plan.read_text().split('### T2')[0])
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # fixed\n')
        self.report()
        result = self.run_step('accept', 'demo', 'T1', '--verify')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn('later_task.py', result.stdout)

    def test_reopen_requires_a_reason(self):
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        result = self.run_step('dispatch', 'demo', 'T1', '--reopen', 'TBD')
        self.assertNotEqual(0, result.returncode)

    def test_legacy_baseline_recovers_capability_content_only_with_matching_hash(self):
        spec_path = self.change / 'spec.md'
        spec_path.write_text(SPEC.replace(' (new capability)', ''))
        capability = self.repo / 'docs/specadoc/specs/label.md'
        capability.parent.mkdir(parents=True)
        capability.write_text('### C0 — Previous capability\n')
        subprocess.run(['git', 'add', 'docs/specadoc/specs/label.md'], cwd=self.repo, check=True)
        subprocess.run(['git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '-qm', 'Capability baseline'], cwd=self.repo, check=True)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        baseline_path = self.change / 'runs/T1-baseline.json'
        state = json.loads(baseline_path.read_text())
        state.pop('capabilities')
        state.pop('schema')
        baseline_path.write_text(json.dumps(state))
        capability.write_text('### C0 — Previous capability\n### C1 — Diagnostic label is ready\n')
        result = self.run_step('amend', 'demo', 'T1', '--controller-path', capability.relative_to(self.repo).as_posix(),
                               '--reason', 'Controller applied the reviewed capability delta')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        result = self.run_step('dispatch', 'demo', 'T1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
