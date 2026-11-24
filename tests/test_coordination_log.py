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
        result = self.run_log('decision', '--by', 'user', '--title', 'Integration before review',
                              '--quote', 'да, интеграция до ревью', text='User said yes\n- verifier runs it')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('D28', result.stdout)
        text = self.log.read_text()
        self.assertTrue(text.startswith('# Stage 3\n\n### D27 — T3 accepted\n- earlier text\n'))
        self.assertRegex(text, r'### D28 — Integration before review \[by user\] \(\d{4}-\d\d-\d\d \d\d:\d\d UTC\)\n'
                               r'- User: «да, интеграция до ревью»\n- User said yes\n- verifier runs it\n$')

    def test_user_decisions_need_the_users_words_and_a_bare_go_its_proposal(self):
        missing = self.run_log('decision', '--by', 'user', '--title', 'Reviewer', text='x')
        self.assertEqual(2, missing.returncode)
        self.assertIn('--quote', missing.stderr)
        bare = self.run_log('decision', '--by', 'user', '--title', 'Reviewer', '--quote', 'go', text='x')
        self.assertEqual(2, bare.returncode)
        self.assertIn('picks no option', bare.stderr)
        self.assertFalse(self.log.exists())
        confirmed = self.run_log('decision', '--by', 'user', '--title', 'Reviewer', '--quote', 'Go!',
                                 '--confirms', 'option 1: user writes in the controller thread', text='x')
        self.assertEqual(0, confirmed.returncode, confirmed.stderr)
        self.assertIn('- User: «Go!» to: option 1: user writes in the controller thread\n- x', self.log.read_text())

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
        result = self.run_log('decision', '--by', 'orchestrator', '--title', 'Logs', text='x' * 3000)
        self.assertEqual(2, result.returncode)
        self.assertIn('cite artifacts', result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()


class CoordinationLookupTest(unittest.TestCase):
    """4.1/4.2: the orchestrator sent D12 for D11 and D17 for D16 from memory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / 'coordination.md'
        self.log.write_text('# Stage 4\n\n### D10 — G3 round [by orchestrator] (t)\n- one extra round\n\n'
                            '### D11 — T7 PASS [by user] (t)\n- integration run\n\n## Notes\nfree text\n')

    def run_log(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], capture_output=True, text=True)

    def test_last_prints_the_newest_header(self):
        result = self.run_log('last', str(self.log))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('D11 — T7 PASS [by user] (t)', result.stdout.strip())

    def test_get_prints_one_entry_and_names_the_newest_when_missing(self):
        result = self.run_log('get', str(self.log), 'D10')
        self.assertEqual('### D10 — G3 round [by orchestrator] (t)\n- one extra round', result.stdout.strip())
        missing = self.run_log('get', str(self.log), 'D12')
        self.assertEqual(2, missing.returncode)
        self.assertIn('the newest is D11', missing.stderr)
        self.assertNotIn('free text', self.run_log('get', str(self.log), 'D11').stdout)

    def test_decision_requires_an_author(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), 'decision', str(self.log), '--title', 'x',
                                 '--file', '-'], input='y', capture_output=True, text=True)
        self.assertEqual(2, result.returncode)
        self.assertIn('--by', result.stderr)


class CapsuleTest(unittest.TestCase):
    """Week 47: orchestrator sessions compacted at 202-274k and lost their role; the capsule is what a
    host hook injects (or the orchestrator reads) after a compaction."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / 'coordination.md'

    def capsule(self, *extra):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), 'capsule', str(self.log), *extra],
                              capture_output=True, text=True)

    def write_log(self, decisions=150):
        entries = ['### D1 — run 6: 6.16-6.21 mandate, archive + stg [by user] (t)\n'
                   '- User: «Ты оркестратор, проведи шестой раздел»\n- Mandate: accept ordinary local plans\n']
        entries += [f'### D{n} — step {n} under mandate D1 [by orchestrator] (t)\n- detail {n}\n'
                    for n in range(2, decisions + 1)]
        self.log.write_text('# Stage 6\n\n## Current state\n\n<!-- current-state:begin -->\n- 6.19 in design\n'
                            '<!-- current-state:end -->\n\n' + '\n'.join(entries))

    def test_the_capsule_names_the_granting_mandate_state_and_newest_decisions(self):
        self.write_log()
        Path(self.tmp.name, 'status.md').write_text(
            '# Status\n<!-- current-state:begin -->\n- ctl-6.19 t74 design r2\n<!-- current-state:end -->\n')
        result = self.capsule()
        self.assertEqual(0, result.returncode, result.stderr)
        text = result.stdout
        self.assertIn('## Mandate\nD1 — run 6: 6.16-6.21 mandate', text)
        self.assertIn('- Mandate: accept ordinary local plans', text)
        self.assertIn('## Current state\n- 6.19 in design', text)
        self.assertIn('## Status (status.md)\n- ctl-6.19 t74 design r2', text)
        self.assertIn('- D150 — step 150 under mandate D1', text)
        self.assertNotIn('D145 —', text)
        self.assertIn('## Rules', text)
        self.assertLessEqual(len(text.splitlines()), 60)
        self.assertLessEqual(len(text.encode('utf-8')), 4096)

    def test_a_long_state_is_trimmed_to_the_limits_and_the_rules_stay(self):
        self.write_log(decisions=6)
        body = '\n'.join(f'- state line {n} ' + 'x' * 60 for n in range(80))
        self.log.write_text(self.log.read_text().replace('- 6.19 in design', body))
        result = self.capsule('--max-lines', '40')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertLessEqual(len(result.stdout.splitlines()), 40)
        self.assertLessEqual(len(result.stdout.encode('utf-8')), 4096)
        self.assertIn('- Next: run `specadoc_step.py status <slug>`', result.stdout)

    def test_a_file_that_is_not_a_coordination_record_is_refused(self):
        self.log.write_text('# Notes\n\nfree text\n')
        result = self.capsule()
        self.assertEqual(2, result.returncode)
        self.assertIn('not a coordination record', result.stderr)
