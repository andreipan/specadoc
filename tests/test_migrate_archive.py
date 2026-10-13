from __future__ import annotations

import importlib.util
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).parents[1]
    / "skills"
    / "specadoc"
    / "scripts"
    / "migrate_archive.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("migrate_archive", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MigrateArchiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "docs" / "agent"
        self.archive = self.root / "archive"
        self.archive.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def legacy(self, slug: str = "legacy") -> Path:
        path = self.archive / slug
        path.mkdir()
        path.joinpath("spec.md").write_text("## Goal\nLegacy goal", encoding="utf-8")
        path.joinpath("plan.md").write_text(
            "## Archive summary\nLegacy delivered", encoding="utf-8"
        )
        return path

    def test_default_dry_run_reports_projection_without_writes(self) -> None:
        migrate_module = load_module()
        legacy = self.legacy()

        report = migrate_module.migrate_archive(self.root, apply=False)

        self.assertEqual(1, report.pending_count)
        self.assertTrue(legacy.joinpath("spec.md").exists())
        self.assertFalse(legacy.joinpath("record.md").exists())
        self.assertIsNone(report.backup_path)

    def test_apply_creates_verified_backup_and_compacts_archive(self) -> None:
        migrate_module = load_module()
        self.legacy()

        report = migrate_module.migrate_archive(self.root, apply=True)

        record = self.archive / "legacy" / "record.md"
        self.assertTrue(record.is_file())
        self.assertEqual(["record.md"], [path.name for path in record.parent.iterdir()])
        self.assertIsNotNone(report.backup_path)
        assert report.backup_path is not None
        self.assertTrue(report.backup_path.is_file())
        with tarfile.open(report.backup_path, "r:gz") as backup:
            self.assertIn("archive/legacy/spec.md", backup.getnames())

    def test_unknown_legacy_attachment_requires_migration_summary(self) -> None:
        migrate_module = load_module()
        legacy = self.legacy()
        legacy.joinpath("failure.txt").write_text("raw failure", encoding="utf-8")

        with self.assertRaisesRegex(migrate_module.MigrationError, "migration-summary.md"):
            migrate_module.migrate_archive(self.root, apply=True)

        self.assertTrue(legacy.joinpath("failure.txt").exists())

    def test_design_artifact_requires_migration_summary(self) -> None:
        migrate_module = load_module()
        legacy = self.legacy()
        legacy.joinpath("design.md").write_text("discarded alternative", encoding="utf-8")

        with self.assertRaisesRegex(migrate_module.MigrationError, "migration-summary.md"):
            migrate_module.migrate_archive(self.root, apply=True)

        self.assertTrue(legacy.joinpath("design.md").exists())

    def test_migration_summary_allows_unknown_attachment_compaction(self) -> None:
        migrate_module = load_module()
        legacy = self.legacy()
        legacy.joinpath("failure.txt").write_text("raw failure", encoding="utf-8")
        legacy.joinpath("migration-summary.md").write_text(
            "Failure log showed an unavailable integration fixture.",
            encoding="utf-8",
        )

        migrate_module.migrate_archive(self.root, apply=True)

        content = self.archive.joinpath("legacy", "record.md").read_text(encoding="utf-8")
        self.assertIn("failure.txt", content)
        self.assertIn("unavailable integration fixture", content)

    def test_second_run_is_idempotent_no_op(self) -> None:
        migrate_module = load_module()
        self.legacy()
        migrate_module.migrate_archive(self.root, apply=True)

        report = migrate_module.migrate_archive(self.root, apply=False)

        self.assertEqual(0, report.pending_count)
        self.assertEqual(1, report.compact_count)

    def test_publish_failure_rolls_back_and_retry_succeeds(self) -> None:
        migrate_module = load_module()
        legacy = self.legacy()
        original_rename = Path.rename

        def fail_staging_once(path: Path, target: Path):
            if path.name.startswith(".archive.compact-"):
                raise OSError("simulated publish failure")
            return original_rename(path, target)

        with patch.object(migrate_module.Path, "rename", new=fail_staging_once):
            with self.assertRaisesRegex(OSError, "simulated publish failure"):
                migrate_module.migrate_archive(self.root, apply=True)

        self.assertTrue(legacy.joinpath("spec.md").is_file())
        report = migrate_module.migrate_archive(self.root, apply=True)
        self.assertTrue(self.archive.joinpath("legacy", "record.md").is_file())
        self.assertIsNotNone(report.backup_path)


if __name__ == "__main__":
    unittest.main()
