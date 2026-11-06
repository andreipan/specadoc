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
