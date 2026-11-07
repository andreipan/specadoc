"""`finalize --run` records verification.final against the Review scope snapshot; `validate --phase final`
requires a fresh passing record; `status --json` gives a driver the same facts with `next.kind`."""
from __future__ import annotations

import json

from test_run411_regressions import Run411Base

CONFIG = {'version': 1, 'verification': {'final': ['python3 check_label.py']}}


class FinalRunTest(Run411Base):
    def configure(self, commands=None):
        config = dict(CONFIG, verification={'final': commands or CONFIG['verification']['final']})
        self.repo.joinpath('.specadoc.json').write_text(json.dumps(config))

    def status(self):
        result = self.run_step('status', 'demo', '--json')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def record(self):
        return json.loads((self.change / 'runs' / 'final-verification.json').read_text())

    def test_run_without_config_is_blocked(self):
        result = self.run_step('finalize', 'demo', '--run')
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn('sets no verification.final', result.stdout)
        self.assertIn('--observed', result.stdout)

    def test_run_records_and_validate_accepts_until_code_changes(self):
        self.configure()
        self.assertEqual('final-run', self.status()['next']['kind'])  # before the first review
        result = self.run_step('finalize', 'demo', '--run')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('verification.final PASS', result.stdout)
        record = self.record()
        self.assertTrue(record['passed'])
        self.assertEqual(['python3 check_label.py'], record['commands'])
        self.assertTrue(record['snapshot'].startswith('sha256:'))
        self.assertIn('finalize --run', self.plan.read_text())
        state = self.status()
        self.assertEqual('pre-review', state['next']['kind'])
        self.assertTrue(state['final_run']['ok'])
        self.pass_round()
        self.assertNotIn('verification.final:', self.validate().stdout)

        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # after the run\n')
        output = self.validate().stdout
        self.assertIn('verification.final: Review scope or spec contract changed after the run', output)
        self.assertIn('finalize demo --run', output)
        self.assertFalse(self.status()['final_run']['ok'])

    def test_failed_run_is_recorded_and_refused(self):
        self.configure(['python3 check_label.py', 'python3 -c "raise SystemExit(3)"'])
        result = self.run_step('finalize', 'demo', '--run')
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn('result: FAIL', result.stdout)
        self.assertIn('exit 3', result.stdout)
        self.assertFalse(self.record()['passed'])
        self.assertEqual([0, 3], [item['exit'] for item in self.record()['results']])
        self.assertNotIn('finalize --run', self.plan.read_text())
        self.assertIn('the recorded run failed: `python3 -c "raise SystemExit(3)"` exited 3', self.validate().stdout)

    def test_validate_requires_a_record_when_configured(self):
        self.configure()
        self.assertIn('verification.final: no `finalize --run` record', self.validate().stdout)

    def test_validate_ignores_projects_without_the_key(self):
        self.assertNotIn('verification.final:', self.validate().stdout)


class StatusJsonTest(Run411Base):
    def test_json_matches_the_text_next_step(self):
        text = self.run_step('status', 'demo')
        data = json.loads(self.run_step('status', 'demo', '--json').stdout)
        next_line = next(line for line in text.stdout.splitlines() if line.startswith('next: '))
        self.assertEqual(next_line[len('next: '):], data['next']['text'])
        self.assertEqual('active', data['result'])
        self.assertEqual({'id', 'owner', 'state', 'stale'}, set(data['tasks'][0]))
        self.assertIsNone(data['final_run'])
        self.assertIsInstance(data['approval']['changed'], list)

    def test_json_for_a_change_that_does_not_exist(self):
        data = json.loads(self.run_step('status', 'nothing', '--json').stdout)
        self.assertEqual('not-started', data['result'])
        self.assertEqual('explore', data['next']['kind'])


if __name__ == '__main__':
    import unittest
    unittest.main()
