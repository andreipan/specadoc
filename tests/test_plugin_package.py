from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PluginPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__', 'dist'))

    def tearDown(self):
        self.temp.cleanup()

    def test_repository_package_contract(self):
        self.assertEqual([], load('package_plugin').validate(ROOT))
        for path, expected in load('render_roles').adapters().items():
            self.assertEqual(expected, path.read_text())

    def test_manifest_mismatch_is_rejected(self):
        path = self.root / '.claude-plugin/plugin.json'
        data = json.loads(path.read_text())
        data['version'] = '0.0.0'
        path.write_text(json.dumps(data))
        self.assertTrue(any('version' in e for e in load('package_plugin').validate(self.root)))

    def test_missing_contract_is_rejected(self):
        (self.root / 'skills/specadoc/references/roles/reviewer.md').unlink()
        self.assertTrue(load('package_plugin').validate(self.root))

    def test_zip_is_reproducible_and_contains_only_portable_resources(self):
        module = load('package_plugin')
        a, b = self.base / 'a.zip', self.base / 'b.zip'
        module.build(self.root, a)
        module.build(self.root, b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with zipfile.ZipFile(a) as archive:
            names = archive.namelist()
            self.assertIn('plugin.json', names)
            for name in module.SKILLS:
                self.assertIn(f'skills/{name}/SKILL.md', names)
            self.assertIn('skills/specadoc/references/roles/reviewer.md', names)
            self.assertFalse(any(n.startswith(('agents/', '.git', '.agents/', '.claude-plugin/', 'tests/', 'scripts/')) for n in names))
            self.assertFalse(any('__pycache__' in n or n.endswith('.pyc') for n in names))
            unpacked = self.base / 'unpacked'
            archive.extractall(unpacked)
        scripts = unpacked / 'skills/specadoc/scripts'
        for script in sorted(scripts.glob('*.py')):
            compile(script.read_text(), str(script), 'exec')
            if script.name != 'specadoc_root.py':
                result = subprocess.run([sys.executable, '-B', str(script), '--help'], cwd=unpacked, capture_output=True)
                self.assertEqual(0, result.returncode, result.stderr)
        project = self.base / 'project'
        project.mkdir()
        result = subprocess.run([sys.executable, '-B', str(scripts / 'init_change.py'), 'smoke'], cwd=project, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((project / 'docs/specadoc/smoke/spec.md').is_file())

    def test_symlink_resource_cannot_leak_into_release(self):
        (self.root / 'skills/tidy/leak.md').symlink_to(self.base / 'secret')
        with self.assertRaises(ValueError):
            load('package_plugin').build(self.root, self.base / 'leak.zip')

    def test_behavioral_eval_cases_cover_approved_scenarios(self):
        cases = json.loads((ROOT / 'tests/evals/specadoc.json').read_text())
        self.assertEqual({'direct', 'grilling-skip', 'minor-re-review', 'project-role',
                          'embedded-role', 'reviewer-unavailable', 'managed-lifecycle',
                          'native-binding-drift', 'browser-context', 'documentation-followup',
                          'direct-uninterrupted', 'bounded-loading'}, {c['id'] for c in cases})
        for case in cases:
            self.assertTrue(case['request'])
            self.assertTrue(case['expected_behavior'])


if __name__ == '__main__':
    unittest.main()
