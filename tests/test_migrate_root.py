from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "skills/specadoc/scripts/migrate_root.py"


def load_module():
    spec = importlib.util.spec_from_file_location("migrate_root", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MigrateRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.module = load_module()
        legacy = self.repo / "docs/agent"
        (legacy / "archive/revoke").mkdir(parents=True)
        (legacy / "specs").mkdir()
        self.record = "## Affected capabilities\n\n- `docs/agent/specs/auth.md`\n"
        (legacy / "archive/revoke/record.md").write_text(self.record, encoding="utf-8")
        (legacy / "specs/auth.md").write_text("### C1 — Revoke\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def migrate(self, **kwargs):
        return self.module.migrate_root("docs/agent", "docs/specadoc", cwd=self.repo, **kwargs)

    def test_dry_run_changes_nothing(self) -> None:
        result = self.migrate()
        self.assertEqual(1, len(result.rewrites))
        self.assertTrue((self.repo / "docs/agent/archive/revoke/record.md").is_file())
        self.assertFalse((self.repo / "docs/specadoc").exists())

    def assert_moved(self) -> None:
        self.assertFalse((self.repo / "docs/agent").exists())
        record = (self.repo / "docs/specadoc/archive/revoke/record.md").read_text(encoding="utf-8")
        self.assertIn("`docs/specadoc/specs/auth.md`", record)
        self.assertNotIn("docs/agent", record)
        self.assertTrue((self.repo / "docs/specadoc/specs/auth.md").is_file())

    def test_apply_moves_and_rewrites_outside_git(self) -> None:
        result = self.migrate(apply=True)
        self.assertFalse(result.moved_with_git)
        self.assert_moved()

    def test_apply_uses_git_mv_and_keeps_untracked_files(self) -> None:
        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

        git("init", "-q")
        git("add", "docs/agent/specs/auth.md")
        result = self.migrate(apply=True)
        self.assertTrue(result.moved_with_git)
        self.assert_moved()
        status = subprocess.run(
            ["git", "-C", str(self.repo), "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout
        self.assertIn("docs/specadoc/specs/auth.md", status)

    def test_refuses_existing_target_or_missing_source(self) -> None:
        (self.repo / "docs/specadoc").mkdir()
        with self.assertRaisesRegex(self.module.MigrationError, "already exists"):
            self.migrate(apply=True)
        with self.assertRaisesRegex(self.module.MigrationError, "nothing to migrate"):
            self.module.migrate_root("missing", "elsewhere", cwd=self.repo)


if __name__ == "__main__":
    unittest.main()
