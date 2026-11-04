"""The orchestrator's decision log is appended by one command, never hand-edited by heredoc scripts."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'skills/orchestrator/scripts/coordination_log.py'


class CoordinationLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / 'coordination.md'

    def run_log(self, *args, text=''):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args, str(self.log), '--file', '-'],
                              input=text, capture_output=True, text=True)

    def test_decisions_are_numbered_and_earlier_entries_stay(self):
        self.log.write_text('# Stage 3\n\n### D27 — T3 accepted\n- earlier text\n')
        result = self.run_log('decision', '--title', 'Integration before review', text='User said yes\n- verifier runs it')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('D28', result.stdout)
        text = self.log.read_text()
        self.assertTrue(text.startswith('# Stage 3\n\n### D27 — T3 accepted\n- earlier text\n'))
        self.assertRegex(text, r'### D28 — Integration before review \(\d{4}-\d\d-\d\d \d\d:\d\d UTC\)\n'
                               r'- User said yes\n- verifier runs it\n$')

    def test_state_block_is_replaced_in_place(self):
        self.log.write_text('# Stage 3\n\n### D1 — Start\n- go\n')
        self.assertEqual(0, self.run_log('state', text='T4 working in thr_a').returncode)
        self.assertEqual(0, self.run_log('state', text='T5 waiting for user').returncode)
        text = self.log.read_text()
        self.assertEqual(1, text.count('## Current state'))
        self.assertIn('- T5 waiting for user', text)
        self.assertNotIn('T4 working', text)
        self.assertLess(text.index('## Current state'), text.index('### D1'))
        self.assertIn('### D1 — Start\n- go', text)

    def test_oversized_entries_are_refused(self):
        result = self.run_log('decision', '--title', 'Logs', text='x' * 3000)
        self.assertEqual(2, result.returncode)
        self.assertIn('cite artifacts', result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
