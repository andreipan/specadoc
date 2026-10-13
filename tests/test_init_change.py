from __future__ import annotations

import errno
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / 'skills/specadoc/scripts/init_change.py'
spec = importlib.util.spec_from_file_location('init_change', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InitChangeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.target = self.base / 'docs/specadoc/demo'
        self.files = []
        for name in ('spec', 'plan', 'design'):
            template = self.base / (name + '-template.md')
            template.write_text(name + ' __CHANGE_TITLE__ __RISK__ __DATE__')
            self.files.append((template, self.target / (name + '.md')))

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, files=None, force=False):
        module.publish_templates(files or self.files, 'Demo', 'low', force)

    def test_success_renders_all_files(self):
        self.publish()
        for _, path in self.files:
            self.assertIn('Demo Low', path.read_text())
            self.assertNotIn('__DATE__', path.read_text())
        self.assertEqual({'spec.md', 'plan.md', 'design.md'}, {p.name for p in self.target.iterdir()})

    def test_later_collisions_leave_existing_tree_unchanged(self):
        for name in ('plan.md', 'design.md'):
            with self.subTest(name=name):
                self.target.mkdir(parents=True, exist_ok=True)
                old = self.target / name
                old.write_bytes(b'approved\x00plan')
                with self.assertRaises(FileExistsError):
                    self.publish()
                self.assertEqual([name], [p.name for p in self.target.iterdir()])
                self.assertEqual(b'approved\x00plan', old.read_bytes())
                old.unlink()

    def test_missing_template_creates_no_directories(self):
        self.files[-1][0].unlink()
        with self.assertRaises(FileNotFoundError):
            self.publish()
        self.assertFalse((self.base / 'docs').exists())

    def test_force_replaces_only_selected_files(self):
        self.target.mkdir(parents=True)
        (self.target / 'spec.md').write_text('old')
        (self.target / 'notes.md').write_text('keep')
        self.publish(force=True)
        self.assertIn('Demo Low', (self.target / 'spec.md').read_text())
        self.assertEqual('keep', (self.target / 'notes.md').read_text())

    def test_failed_publication_removes_new_files_and_directories(self):
        link = module.os.link
        count = 0
        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected write failure')
            return link(*args, **kwargs)
        with patch.object(module.os, 'link', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.publish()
        self.assertFalse((self.base / 'docs').exists())

    def test_force_failure_restores_bytes_and_removes_new_file(self):
        self.target.mkdir(parents=True)
        old = self.target / 'spec.md'
        old.write_bytes(b'old\x00spec')
        replace = module.os.replace
        count = 0
        def fail_third(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError('injected write failure')
            return replace(*args, **kwargs)
        with patch.object(module.os, 'replace', side_effect=fail_third):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.publish(force=True)
        self.assertEqual(b'old\x00spec', old.read_bytes())
        self.assertEqual(['spec.md'], [p.name for p in self.target.iterdir()])

    def test_force_refuses_symlink_without_touching_target(self):
        self.target.mkdir(parents=True)
        external = self.base / 'external'
        external.write_text('keep')
        (self.target / 'plan.md').symlink_to(external)
        with self.assertRaises(OSError):
            self.publish(force=True)
        self.assertEqual('keep', external.read_text())
        self.assertFalse((self.target / 'spec.md').exists())

    def test_post_preflight_collision_does_not_clobber_concurrent_file(self):
        link = module.os.link
        def concurrent_file(source, destination):
            if destination.name == 'plan.md':
                destination.write_text('concurrent plan')
            return link(source, destination)
        with patch.object(module.os, 'link', side_effect=concurrent_file):
            with self.assertRaises(FileExistsError):
                self.publish()
        self.assertFalse((self.target / 'spec.md').exists())
        self.assertEqual('concurrent plan', (self.target / 'plan.md').read_text())
        self.assertEqual(['plan.md'], [p.name for p in self.target.iterdir()])

    def test_unsupported_hard_links_fall_back_to_exclusive_create(self):
        unsupported = OSError(errno.ENOTSUP, 'hard links not supported')
        with patch.object(module.os, 'link', side_effect=unsupported):
            self.publish()
        for _, path in self.files:
            self.assertIn('Demo Low', path.read_text())
        self.assertEqual({'spec.md', 'plan.md', 'design.md'}, {p.name for p in self.target.iterdir()})

    def test_fallback_does_not_clobber_concurrent_file(self):
        def concurrent_file(source, destination):
            if destination.name == 'plan.md':
                destination.write_text('concurrent plan')
            raise OSError(errno.ENOTSUP, 'hard links not supported')
        with patch.object(module.os, 'link', side_effect=concurrent_file):
            with self.assertRaises(FileExistsError):
                self.publish()
        self.assertEqual('concurrent plan', (self.target / 'plan.md').read_text())
        self.assertEqual(['plan.md'], [p.name for p in self.target.iterdir()])

    def test_rollback_failure_retains_original_backups(self):
        self.target.mkdir(parents=True)
        self.target.joinpath('spec.md').write_bytes(b'original')
        replace = module.os.replace
        count = 0
        def fail_publication_and_restore(*args, **kwargs):
            nonlocal count
            count += 1
            if count >= 2:
                raise OSError('injected failure')
            return replace(*args, **kwargs)
        with patch.object(module.os, 'replace', side_effect=fail_publication_and_restore):
            with self.assertRaisesRegex(OSError, 'recovery files:'):
                self.publish(force=True)
        retained = list(self.target.glob('.specadoc-init-*'))
        self.assertEqual(1, len(retained))
        self.assertEqual(b'original', (retained[0] / 'old-0').read_bytes())


if __name__ == '__main__':
    unittest.main()
