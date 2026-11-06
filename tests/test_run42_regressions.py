"""Regressions from orchestrator run 4.1 + 4.2 (organization-create-trial, organization-context)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import test_apply_reliability as fixtures


def reviewer_json(verdict='PASS', findings=None):
    return json.dumps(dict(verdict=verdict, findings=findings or [], report='Independent read-only review.'))


class Run42ReviewTest(unittest.TestCase):
    tearDown_base = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step

    def setUp(self):
        fixtures.ApplyReliabilityTest.setUp(self)
        self.home = tempfile.TemporaryDirectory()
        self.saved = os.environ.get('CLAUDE_CONFIG_DIR')
        os.environ['CLAUDE_CONFIG_DIR'] = self.home.name

    def tearDown(self):
        if self.saved is None:
            os.environ.pop('CLAUDE_CONFIG_DIR', None)
        else:
            os.environ['CLAUDE_CONFIG_DIR'] = self.saved
        self.home.cleanup()
        self.tearDown_base()

    def agent(self, agent_id, reply, handback=False):
        """A fake native subagent transcript whose final assistant message is `reply`."""
        project = Path(self.home.name) / 'projects' / 'p' / 'session-1' / 'subagents'
        project.mkdir(parents=True, exist_ok=True)
        final = ({'type': 'tool_use', 'name': 'Handback', 'input': {'message': reply}} if handback
                 else {'type': 'text', 'text': reply})
        rows = [{'type': 'user', 'message': {'content': 'Review the design.'}},
                {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Reading files.'}]}},
                {'type': 'assistant', 'message': {'content': [final]}},
                {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': ''}]}}]
        project.joinpath(f'agent-{agent_id}.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n')

    def begin(self, review_type='initial'):
        return self.run_step('pre-review', 'demo', '--review-type', review_type)

    def scope(self, *paths):
        text = self.plan.read_text()
        head, tail = text.split('## Review scope\n', 1)
        rest = tail[tail.index('## Final verification'):]
        self.plan.write_text(head + '## Review scope\n' + ''.join(f'- `{p}`\n' for p in paths) + rest)

    def test_review_scope_refuses_change_artifacts(self):
        self.scope('label.py', 'docs/specadoc/demo/plan.md')
        result = self.begin()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Specadoc artifact: docs/specadoc/demo/plan.md', result.stdout + result.stderr)
        self.assertNotIn('### G1', self.plan.read_text())

    def test_stale_result_names_the_changed_paths(self):
        self.assertEqual(0, self.begin().returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "changed"\n')
        self.agent('rev0001', 'Looks fine.\n\n```json\n' + reviewer_json() + '\n```\n')
        result = self.run_step('review-result', 'demo', '--from-agent', 'rev0001')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('stale: content changed: changed=label.py', result.stdout)
        self.assertIn('re-review', result.stdout)
        self.assertIn('**Stale reason:** content changed: changed=label.py', self.plan.read_text())

    def test_from_agent_saves_the_reply_verbatim_and_records_the_agent(self):
        self.assertEqual(0, self.begin().returncode)
        reply = 'Checked R1.\n\n```json\n' + reviewer_json() + '\n```'
        self.agent('rev0001', reply, handback=True)
        result = self.run_step('review-result', 'demo', '--from-agent', 'rev0001')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        saved = self.change / 'runs' / 'G1-reply.md'
        self.assertEqual(reply + '\n', saved.read_text())
        text = self.plan.read_text()
        self.assertIn('**Outcome:** PASS', text)
        self.assertIn('**Reviewer agent:** `rev0001`', text)

    def test_the_same_reviewer_agent_is_refused_for_the_next_round(self):
        self.agent('rev0001', reviewer_json('FAIL', [dict(severity='MINOR', location='label.py:1', summary='Name')]))
        self.assertEqual(0, self.begin().returncode)
        self.assertEqual(0, self.run_step('review-result', 'demo', '--from-agent', 'rev0001').returncode)
        self.assertEqual(0, self.begin('re-review').returncode)
        self.agent('rev0001', reviewer_json())
        refused = self.run_step('review-result', 'demo', '--from-agent', 'rev0001')
        self.assertNotEqual(0, refused.returncode)
        self.assertIn('fresh reviewer', refused.stdout + refused.stderr)
        allowed = self.run_step('review-result', 'demo', '--from-agent', 'rev0001',
                                '--same-reviewer-reason', 'delta re-review of one MINOR fix')
        self.assertEqual(0, allowed.returncode, allowed.stdout + allowed.stderr)

    def test_unknown_agent_and_outside_result_file_explain_the_fix(self):
        self.assertEqual(0, self.begin().returncode)
        missing = self.run_step('review-result', 'demo', '--from-agent', 'nosuchagent')
        self.assertIn('no transcript for agent nosuchagent', missing.stdout)
        outside = Path(self.home.name) / 'g1.json'
        outside.write_text(reviewer_json())
        result = self.run_step('review-result', 'demo', '--result-file', str(outside))
        self.assertIn('save it under docs/specadoc/demo/runs/', result.stdout)


if __name__ == '__main__':
    unittest.main()


from test_run35_regressions import OVERLAP_PLAN  # noqa: E402


class Run42ControllerFixTest(unittest.TestCase):
    """4.1/4.2: a controller MINOR fix after review sent T3 back to dispatched and refresh stopped at each task."""
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step
    report = fixtures.ApplyReliabilityTest.report

    def state(self, task):
        return json.loads(self.change.joinpath(f'runs/{task}-baseline.json').read_text())

    def accept_t1_and_t2(self, t1_status='DONE', resolved=None):
        self.plan.write_text(OVERLAP_PLAN)
        self.repo.joinpath('extra.py').write_text('x = 1\n')
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T1').returncode)
        self.report(status=t1_status)
        extra = ('--resolved', resolved) if resolved else ()
        result = self.run_step('accept', 'demo', 'T1', *extra)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(0, self.run_step('dispatch', 'demo', 'T2').returncode)
        self.repo.joinpath('extra.py').write_text('x = 2\n')
        self.report(task='T2', files=('extra.py',))
        result = self.run_step('accept', 'demo', 'T2')
        self.assertEqual(0, result.returncode, result.stdout)

    def controller_fix(self):
        # One MINOR fix touches a T1 file and a T2 file, like 4.1's Handler.php and its test.
        self.repo.joinpath('check_label.py').write_text(
            'from label import label\nassert label() == "ready", "label must be ready"\n')
        self.repo.joinpath('extra.py').write_text('x = 3\n')

    def test_refresh_without_controller_path_lists_every_failure_and_the_fix(self):
        self.accept_t1_and_t2()
        self.controller_fix()
        result = self.run_step('refresh', 'demo')
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn('T2:', result.stdout)
        self.assertIn('check_label.py', result.stdout)
        self.assertIn('--controller-path', result.stdout)
        self.assertIn('T1 accepted', result.stdout)

    def test_refresh_controller_path_reaccepts_all_tasks_in_one_call(self):
        self.accept_t1_and_t2()
        self.controller_fix()
        result = self.run_step('refresh', 'demo', '--controller-path', 'check_label.py',
                               '--controller-path', 'extra.py', '--reason', 'G1 MINOR: assertion message')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn('controller changes recorded: check_label.py', result.stdout)
        self.assertEqual('accepted', self.state('T1')['state'])
        self.assertEqual('accepted', self.state('T2')['state'])
        payload = json.loads(self.change.joinpath('runs/controller-changes.json').read_text())
        self.assertIn('check_label.py', payload['changes'])
        self.assertEqual('G1 MINOR: assertion message', payload['history'][0]['reason'])

    def test_controller_path_needs_a_reason_and_stays_outside_artifacts(self):
        self.accept_t1_and_t2()
        result = self.run_step('refresh', 'demo', '--controller-path', 'check_label.py')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('--reason', result.stdout)
        result = self.run_step('refresh', 'demo', '--controller-path', 'docs/specadoc/demo/plan.md',
                               '--reason', 'oops')
        self.assertIn('outside the artifact root', result.stdout)

    def test_amend_controller_path_keeps_an_accepted_task_accepted(self):
        self.accept_t1_and_t2()
        self.controller_fix()
        result = self.run_step('amend', 'demo', 'T2', '--controller-path', 'check_label.py',
                               '--reason', 'G1 MINOR: assertion message')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('accepted', self.state('T2')['state'])
        self.assertIn('verification', self.state('T2'))
        self.assertIn('[x] Complete', self.plan.read_text().split('### T2')[1].split('### T3')[0])

    def test_refresh_keeps_a_resolved_blocker_acceptance(self):
        self.accept_t1_and_t2(t1_status='BLOCKED', resolved='parent installed the missing extension')
        self.controller_fix()
        result = self.run_step('refresh', 'demo', '--controller-path', 'check_label.py',
                               '--controller-path', 'extra.py', '--reason', 'G1 MINOR: assertion message')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual('parent installed the missing extension',
                         self.state('T1')['blocker_resolution']['resolution'])


class Run42PlanSizeTest(unittest.TestCase):
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step

    def test_status_names_the_largest_parts_of_an_oversized_plan(self):
        text = self.plan.read_text()
        self.plan.write_text(text.replace('## Technical approach\n',
                                          '## Technical approach\n' + 'Bulky evidence line.\n' * 2000, 1))
        result = self.run_step('status', 'demo')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('size: plan.md is', result.stdout)
        self.assertIn('Largest: Technical approach', result.stdout)

    def test_token_rows_go_to_a_sidecar_and_plan_keeps_totals(self):
        import sys
        sys.path.insert(0, str(fixtures.SCRIPTS))
        import collect_tokens
        plan = self.change / 'plan.md'
        plan.write_text(plan.read_text() + '\n## Completion evidence\n\nExecution tokens:\nPending\n')
        collect_tokens.append_to_plan(plan, ['mode=apply claude a1 unique=5', 'total mode=apply claude 1 run(s)'],
                                      'apply', 'claude')
        self.assertIn('total mode=apply claude 1 run(s)', plan.read_text())
        self.assertNotIn('a1 unique=5', plan.read_text())
        self.assertIn('a1 unique=5', (self.change / 'runs/tokens.md').read_text())


class Run42TokenWindowTest(unittest.TestCase):
    """4.2: apply totals included the propose controller session and its design reviewer."""

    def test_a_session_shared_by_propose_and_apply_is_split_by_time(self):
        import contextlib
        import io
        import sys
        sys.path.insert(0, str(fixtures.SCRIPTS))
        import collect_tokens
        with tempfile.TemporaryDirectory() as directory:
            change = Path(directory) / 'docs/specadoc/demo'
            (change / 'runs').mkdir(parents=True)
            session = Path(directory) / 'home/projects/p/s1.jsonl'
            session.parent.mkdir(parents=True)

            def record(request, at, output):
                return json.dumps({'type': 'assistant', 'requestId': request, 'timestamp': at,
                                   'message': {'usage': {'input_tokens': 1, 'output_tokens': output}}})
            session.write_text('\n'.join([record('r1', '2026-11-05T10:00:00Z', 100),
                                          record('r2', '2026-11-05T11:30:00Z', 7)]) + '\n')
            reviewer = session.with_suffix('') / 'subagents' / 'agent-design.jsonl'
            reviewer.parent.mkdir(parents=True)
            reviewer.write_text(record('r3', '2026-11-05T10:30:00Z', 50) + '\n')
            (change / 'runs/sessions.json').write_text(json.dumps({'claude': [
                {'transcript': str(session), 'mode': 'propose', 'at': '2026-11-05T10:10:00+00:00'},
                {'transcript': str(session), 'mode': 'apply', 'at': '2026-11-05T11:00:00+00:00'}]}))
            apply = collect_tokens.collect_claude([session], collect_tokens.ledger_windows(change, 'apply'))
            self.assertEqual([('s1', 7)], [(e.execution_id, e.output) for e in apply])
            propose = collect_tokens.collect_claude([session], collect_tokens.ledger_windows(change, 'propose'))
            self.assertEqual({'s1': 100, 'design': 50}, {e.execution_id: e.output for e in propose})

    def test_handoff_before_dispatch_records_the_propose_mode(self):
        import os
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
            change = repo / 'docs/specadoc/demo'
            (change / 'runs').mkdir(parents=True)
            from test_specadoc_step import PLAN, SPEC
            change.joinpath('spec.md').write_text(SPEC)
            change.joinpath('plan.md').write_text(PLAN)
            home = repo / 'home'
            (home / 'projects/p').mkdir(parents=True)
            (home / 'projects/p/c1.jsonl').write_text('{}\n')
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CLAUDE_CONFIG_DIR=str(home),
                       CLAUDE_CODE_SESSION_ID='c1')
            env.pop('SPECADOC_ROOT', None)
            subprocess.run([sys.executable, '-B', str(fixtures.SCRIPTS / 'specadoc_step.py'), 'handoff', 'demo',
                            '--file', '-', '--controller-runtime', 'claude'], cwd=repo, env=env,
                           capture_output=True, text=True, input='notes\n')
            ledger = json.loads((change / 'runs/sessions.json').read_text())
            self.assertEqual(['propose'], [item['mode'] for item in ledger['claude']])
