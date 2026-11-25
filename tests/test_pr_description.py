"""`pr_description.py` turns archive records and the diff into a request description."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'skills/specadoc/scripts/pr_description.py'

RECORD = """---
schema: specadoc.archive/v1
slug: {slug}
status: archived
---

# {slug}

## Goal

Members read one widget
in a single request.

## Outcome

Outcome: `GET /widgets/{{id}}` answers one widget.

Residual risks: none beyond the cache.

## Decisions

- D1 keep the route unnamed.

## Review

**Result:** PASS

### Findings

- None.

## Measurement

```text
Commands:
lint: exit 0 (3 s)

Requirement mapping:
R1 -> A1 / `run-tests tests/widget_get_test.txt`: PASS
R2 -> A2 / `run-tests tests/widget_get_test.txt`; `run-tests tests/widget_list_test.txt`

Review rounds:
G1 initial: FAIL, 1 finding(s)
G2 re-review: PASS
```
"""


class PrDescriptionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Test')
        (self.repo / 'README.md').write_text('base\n')
        self.commit('base')

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)
        return self.git('rev-parse', 'HEAD').strip()

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def add_change(self, slug, *extra):
        self.write(f'docs/specadoc/archive/{slug}/record.md', RECORD.format(slug=slug))
        self.write(f'src/{slug}.txt', 'one\ntwo\n')
        for path in extra:
            self.write(path, 'x\n')
        return self.commit(slug)

    def run_script(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.repo, env=env,
                              capture_output=True, text=True)

    def test_range_renders_record_and_diff_facts(self):
        self.add_change('widget-get')
        result = self.run_script('--range', 'main~1..main')
        self.assertEqual(0, result.returncode, result.stderr)
        text = result.stdout
        self.assertNotIn('### widget-get', text)
        self.assertIn('**Goal.** Members read one widget in a single request.', text)
        self.assertIn('**Changes.** `GET /widgets/{id}` answers one widget.', text)
        self.assertIn('- lint: exit 0 (3 s)', text)
        self.assertIn('- Requirement mapping: 2 requirements, 1 PASS; no recorded result for R2.', text)
        self.assertIn('`run-tests tests/widget_get_test.txt`, `run-tests tests/widget_list_test.txt`.', text)
        self.assertIn('- Review rounds: G1 initial: FAIL, 1 finding(s); G2 re-review: PASS.', text)
        self.assertIn('- Final review: PASS.', text)
        self.assertIn('**Residual risks.** none beyond the cache.', text)
        self.assertIn('**Record:** `docs/specadoc/archive/widget-get/record.md`', text)
        self.assertIn('- Diff: 2 files, +', text)
        self.assertIn('- Migrations: none.', text)
        self.assertIn('- Rollback: revert the request; it touches no migration.', text)

    def test_migrations_lock_files_and_config_change_the_rollback_note(self):
        self.add_change('widget-store', 'db/migrations/001_widgets.sql', 'app.lock', 'config/widgets.ini')
        text = self.run_script('--range', 'main~1..main').stdout
        self.assertIn('- Migrations: `db/migrations/001_widgets.sql`.', text)
        self.assertIn('- Lock files: `app.lock`.', text)
        self.assertIn('- Configuration: `config/widgets.ini`.', text)
        self.assertIn('A revert does not undo applied migrations', text)

    def test_several_records_get_headings_and_one_diff_block(self):
        self.add_change('widget-get')
        self.add_change('widget-list')
        text = self.run_script('--range', 'main~2..main').stdout
        self.assertIn('### widget-get', text)
        self.assertIn('### widget-list', text)
        self.assertEqual(1, text.count('### Deploy and rollback'))

    def test_record_is_read_at_head_not_from_the_working_tree(self):
        self.add_change('widget-get')
        self.write('docs/specadoc/archive/widget-get/record.md', '## Goal\n\nEdited later.\n')
        text = self.run_script('--range', 'main~1..main').stdout
        self.assertIn('Members read one widget', text)
        self.assertNotIn('Edited later', text)

    def test_slug_reads_the_working_tree_without_diff_facts(self):
        self.add_change('widget-get')
        out = self.repo / 'out.md'
        result = self.run_script('--slug', 'widget-get', '--output', str(out))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('', result.stdout)
        text = out.read_text()
        self.assertIn('**Goal.**', text)
        self.assertNotIn('Deploy and rollback', text)

    def test_range_without_record_fails(self):
        self.write('src/plain.txt', 'x\n')
        self.commit('plain')
        result = self.run_script('--range', 'main~1..main')
        self.assertEqual(1, result.returncode)
        self.assertIn('no docs/specadoc/archive/<slug>/record.md', result.stderr)

    def test_bad_range_and_missing_slug_fail(self):
        self.assertEqual(1, self.run_script('--range', 'main...main').returncode)
        self.assertEqual(1, self.run_script('--slug', 'absent').returncode)
        self.assertEqual(2, self.run_script().returncode)


if __name__ == '__main__':
    unittest.main()
