"""`list_changes.py` gives every active change's `status --json` in one read-only call."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from test_run411_regressions import Run411Base
from test_specadoc_step import SCRIPTS


class ListChangesTest(Run411Base):
    def list(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'list_changes.py'), *args],
                                cwd=self.repo, env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_lists_active_changes_with_their_status(self):
        data = self.list()
        self.assertEqual('docs/specadoc', data['root'])
        self.assertEqual(0, data['archived'])
        (item,) = data['active']
        status = json.loads(self.run_step('status', 'demo', '--json', '--context-tokens', '0').stdout)
        self.assertEqual(status, {k: v for k, v in item.items() if k != 'updated_at'})
        self.assertIsInstance(item['updated_at'], int)

    def test_skips_reserved_and_planless_dirs_and_counts_archive(self):
        root = self.repo / 'docs/specadoc'
        (root / 'specs').mkdir()
        (root / 'specs' / 'plan.md').write_text('# not a change\n')
        (root / 'draft').mkdir()
        (root / 'archive' / 'old').mkdir(parents=True)
        (root / 'archive' / 'old' / 'record.md').write_text('# record\n')
        data = self.list()
        self.assertEqual(['demo'], [item['change'] for item in data['active']])
        self.assertEqual(1, data['archived'])

    def test_a_broken_change_does_not_hide_the_others(self):
        broken = self.repo / 'docs/specadoc/broken'
        broken.mkdir()
        broken.joinpath('plan.md').write_bytes(b'\xff\xfe not utf-8')
        data = self.list()
        by_name = {item['change']: item for item in data['active']}
        self.assertEqual('error', by_name['broken']['result'])
        self.assertEqual('active', by_name['demo']['result'])

    def test_writes_nothing(self):
        before = sorted(p.relative_to(self.repo) for p in self.repo.rglob('*') if '.git' not in p.parts)
        self.list()
        after = sorted(p.relative_to(self.repo) for p in self.repo.rglob('*') if '.git' not in p.parts)
        self.assertEqual(before, after)

    def test_missing_root_lists_nothing(self):
        data = self.list('--root', 'nowhere')
        self.assertEqual({'root': 'nowhere', 'active': [], 'archived': 0}, data)


if __name__ == '__main__':
    import unittest
    unittest.main()
