from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).parents[1]
    / "skills"
    / "specadoc"
    / "scripts"
    / "archive_change.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("archive_change", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ArchiveChangeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.root = self.repo / "docs" / "specadoc"
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def change(self, slug: str = "demo") -> Path:
        path = self.root / slug
        path.mkdir()
        return path

    def test_force_compacts_incomplete_change_to_one_bounded_record(self) -> None:
        archive_module = load_module()
        change = self.change()
        source = b"raw diagnostic\n"
        change.joinpath("failure.txt").write_bytes(source)

        result = archive_module.archive_change(self.root, "demo", force=True, dry_run=False)

        record = self.root / "archive" / "demo" / "record.md"
        self.assertFalse(change.exists())
        self.assertTrue(record.is_file())
        content = record.read_text(encoding="utf-8")
        self.assertIn("status: forced", content)
        self.assertIn("failure.txt", content)
        self.assertIn(hashlib.sha256(source).hexdigest(), content)
        self.assertNotIn("## Legacy migration summary", content)
        self.assertLessEqual(len(record.read_bytes()), archive_module.RECORD_BUDGET)
        self.assertTrue(result.forced)

    def test_dry_run_does_not_write_or_remove_source(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("note.txt").write_text("note", encoding="utf-8")

        archive_module.archive_change(self.root, "demo", force=True, dry_run=True)

        self.assertTrue(change.is_dir())
        self.assertFalse((self.root / "archive").exists())

    def test_existing_target_is_hard_error_even_with_force(self) -> None:
        archive_module = load_module()
        change = self.change()
        target = self.root / "archive" / "demo"
        target.mkdir(parents=True)
        target.joinpath("record.md").write_text("existing", encoding="utf-8")

        with self.assertRaisesRegex(archive_module.ArchiveError, "already exists"):
            archive_module.archive_change(self.root, "demo", force=True, dry_run=False)

        self.assertTrue(change.exists())
        self.assertEqual("existing", target.joinpath("record.md").read_text(encoding="utf-8"))

    def test_normal_mode_rejects_unknown_attachment(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("spec.md").write_text("## Goal\nGoal", encoding="utf-8")
        change.joinpath("plan.md").write_text("## Archive summary\nDone", encoding="utf-8")
        change.joinpath("raw.log").write_text("details", encoding="utf-8")

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            with self.assertRaisesRegex(archive_module.ArchiveError, "unknown attachment"):
                archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        self.assertTrue(change.exists())

    def test_normal_archive_collapses_runs_into_one_manifest_row(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("spec.md").write_text("## Goal\nGoal", encoding="utf-8")
        change.joinpath("plan.md").write_text("## Archive summary\nDone", encoding="utf-8")
        runs = change / "runs"
        runs.mkdir()
        runs.joinpath("T1-brief.md").write_bytes(b"brief")
        runs.joinpath("T1-baseline.json").write_bytes(b"{}")

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        content = (self.root / "archive" / "demo" / "record.md").read_text(encoding="utf-8")
        self.assertFalse(change.exists())
        self.assertEqual(1, content.count("`runs/`"))
        self.assertIn("| `runs/` (2 files) | 7 | — |", content)
        self.assertNotIn("T1-brief.md", content)

    def test_unknown_root_file_blocks_archive_without_naming_runs(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("spec.md").write_text("## Goal\nGoal", encoding="utf-8")
        change.joinpath("plan.md").write_text("## Archive summary\nDone", encoding="utf-8")
        change.joinpath("raw.log").write_text("details", encoding="utf-8")
        (change / "runs").mkdir()
        change.joinpath("runs", "T1-brief.md").write_text("brief", encoding="utf-8")

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            with self.assertRaises(archive_module.ArchiveError) as caught:
                archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        self.assertIn("raw.log", str(caught.exception))
        self.assertNotIn("T1-brief.md", str(caught.exception))
        self.assertTrue(change.exists())

    def test_normal_mode_rejects_incomplete_review_coverage(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("spec.md").write_text("## Goal\nGoal", encoding="utf-8")
        change.joinpath("plan.md").write_text("## Archive summary\nDone", encoding="utf-8")

        with patch.object(
            archive_module,
            "validate_change_gates",
            return_value=["plan.md: Review result: Reviewed requirements mismatch"],
        ):
            with self.assertRaisesRegex(archive_module.ArchiveError, "Reviewed requirements mismatch"):
                archive_module.archive_change(self.root, "demo", force=False, dry_run=True)

        self.assertTrue(change.exists())

    def test_normal_mode_archives_applied_new_capability(self) -> None:
        archive_module = load_module()
        change = self.change()
        capability = self.root / "specs" / "demo.md"
        capability.parent.mkdir()
        capability.write_text(
            "### C1 — Delivered\n\n## Provenance\n| Change |\n|---|\n| demo |\n",
            encoding="utf-8",
        )
        change.joinpath("spec.md").write_text(
            "## Affected capabilities\n"
            f"- `{capability}` (new capability)\n"
            "  - ADDED C1 — Delivered\n",
            encoding="utf-8",
        )
        change.joinpath("plan.md").write_text("## Archive summary\nDone", encoding="utf-8")

        with patch.multiple(archive_module, check_spec=lambda *args, **kwargs: [], check_plan=lambda *args: [], check_final=lambda *args: []):
            archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        self.assertTrue((self.root / "archive" / "demo" / "record.md").is_file())

    def test_normal_mode_rejects_applied_new_capability_without_requirement_or_provenance(self) -> None:
        archive_module = load_module()
        for name, content, expected in (
            ("missing-requirement", "### C2 — Different\n\n## Provenance\n| Change |\n|---|\n| demo |\n", "ADDED C1"),
            ("missing-provenance", "### C1 — Delivered\n", "provenance table"),
        ):
            with self.subTest(name=name):
                change = self.change(name)
                capability = self.root / "specs" / f"{name}.md"
                capability.parent.mkdir(exist_ok=True)
                capability.write_text(content, encoding="utf-8")
                change.joinpath("spec.md").write_text(
                    "## Affected capabilities\n"
                    f"- `{capability}` (new capability)\n"
                    "  - ADDED C1 — Delivered\n",
                    encoding="utf-8",
                )
                change.joinpath("plan.md").write_text("## Archive summary\nDone", encoding="utf-8")

                with patch.multiple(archive_module, check_spec=lambda *args, **kwargs: [], check_plan=lambda *args: [], check_final=lambda *args: []):
                    with self.assertRaisesRegex(archive_module.ArchiveError, expected):
                        archive_module.archive_change(self.root, name, force=False, dry_run=True)

    def test_normal_mode_publishes_after_gate_success(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("spec.md").write_text(
            "## Goal\nShip compact history\n\n## Affected capabilities\n- `docs/specadoc/specs/x.md`\n",
            encoding="utf-8",
        )
        change.joinpath("plan.md").write_text(
            "## Confirmed decisions\nOne record\n\n"
            "## Archive summary\nImplemented and verified\n\n"
            "## Final verification\n- tests passed\n\n"
            "## Review result\n**Result:** PASS\n\n"
            "## Completion evidence\nExecution tokens: 10\nReview rounds: 1\n",
            encoding="utf-8",
        )

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        record = self.root / "archive" / "demo" / "record.md"
        self.assertTrue(record.is_file())
        self.assertFalse(change.exists())
        self.assertIn("status: archived", record.read_text(encoding="utf-8"))

    def test_force_truncates_optional_text_but_preserves_manifest(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("spec.md").write_text(
            "## Goal\n" + ("large goal " * 10000),
            encoding="utf-8",
        )

        archive_module.archive_change(self.root, "demo", force=True, dry_run=False)

        record = self.root / "archive" / "demo" / "record.md"
        content = record.read_text(encoding="utf-8")
        self.assertLessEqual(len(record.read_bytes()), archive_module.RECORD_BUDGET)
        self.assertIn("spec.md", content)
        self.assertIn("truncated", content.lower())

    def test_normal_mode_rejects_record_over_size_budget(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("spec.md").write_text("## Goal\nGoal", encoding="utf-8")
        change.joinpath("plan.md").write_text(
            "## Archive summary\n" + ("large outcome " * 3000),
            encoding="utf-8",
        )

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            with self.assertRaisesRegex(archive_module.ArchiveError, "budget"):
                archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        self.assertTrue(change.exists())

    def test_snapshot_messages_is_a_noop_without_a_round_log(self) -> None:
        archive_module = load_module()
        change = self.change()
        change.joinpath("plan.md").write_text("## Review result\n\n**Result:** Pending\n", encoding="utf-8")
        plan = archive_module.Document(change / "plan.md", "plan.md")

        self.assertEqual([], archive_module._snapshot_messages(plan, change))

    def test_snapshot_messages_flags_a_change_since_the_recorded_pass(self) -> None:
        archive_module = load_module()
        change = self.change()
        handler = change / "Handler.php"
        handler.write_text("original\n", encoding="utf-8")
        change.joinpath("spec.md").write_text(
            "## Requirements\n\n### R1 — One\n\ntext\n\n"
            "## Acceptance scenarios\n\ntext\n\n"
            "## Constraints\n\ntext\n\n"
            "## Affected capabilities\n\ntext\n",
            encoding="utf-8",
        )
        change.joinpath("plan.md").write_text(
            "## Review scope\n\n"
            f"- `{handler.relative_to(self.repo)}`\n\n"
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** PASS\n\n"
            "```json\n"
            f'{{"{handler.relative_to(self.repo)}": "stale-hash-from-before-the-edit"}}\n'
            "```\n",
            encoding="utf-8",
        )
        plan = archive_module.Document(change / "plan.md", "plan.md")

        messages = archive_module._snapshot_messages(plan, change, self.repo)

        self.assertTrue(any("diff changed since G1's snapshot" in message for message in messages))

    def test_snapshot_messages_rejects_a_real_mismatch_even_with_a_waiver(self) -> None:
        archive_module = load_module()
        change = self.change()
        handler = change / "Handler.php"
        handler.write_text("original\n", encoding="utf-8")
        change.joinpath("spec.md").write_text(
            "## Requirements\n\n### R1 — One\n\ntext\n\n"
            "## Acceptance scenarios\n\ntext\n\n"
            "## Constraints\n\ntext\n\n"
            "## Affected capabilities\n\ntext\n",
            encoding="utf-8",
        )
        change.joinpath("plan.md").write_text(
            "## Review scope\n\n"
            f"- `{handler.relative_to(self.repo)}`\n\n"
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** PASS\n"
            "- **Snapshot waiver:** doc-only follow-up, confirmed by user\n\n"
            "```json\n"
            f'{{"{handler.relative_to(self.repo)}": "stale-hash-from-before-the-edit"}}\n'
            "```\n",
            encoding="utf-8",
        )
        plan = archive_module.Document(change / "plan.md", "plan.md")

        messages = archive_module._snapshot_messages(plan, change, self.repo)

        self.assertTrue(any("diff changed since G1's snapshot" in message for message in messages))

    def test_snapshot_messages_allows_unresolvable_scope_with_a_waiver(self) -> None:
        archive_module = load_module()
        change = self.change()
        handler = change / "Handler.php"
        handler.write_text("current\n", encoding="utf-8")
        change.joinpath("spec.md").write_text(
            "## Requirements\n\n### R1 — One\n\ntext\n",
            encoding="utf-8",
        )
        change.joinpath("plan.md").write_text(
            "## Review scope\n\n"
            f"- `{handler.relative_to(self.repo)}`\n\n"
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** PASS\n"
            "- **Snapshot waiver:** filesystem state confirmed by user\n\n"
            "```json\n{}\n```\n",
            encoding="utf-8",
        )
        plan = archive_module.Document(change / "plan.md", "plan.md")
        snapshot_module = sys.modules[archive_module.verify_latest.__module__]

        with patch.object(
            snapshot_module,
            "compute",
            side_effect=snapshot_module.SnapshotError("filesystem unavailable"),
        ):
            self.assertEqual(
                [],
                archive_module._snapshot_messages(plan, change, self.repo),
            )

    def test_final_gate_requires_a_durable_archive_summary(self) -> None:
        archive_module = load_module()
        change = self.change()
        spec_path = change / "spec.md"
        plan_path = change / "plan.md"
        spec_path.write_text("## Goal\nGoal\n", encoding="utf-8")
        plan_path.write_text(
            "## Archive summary\n\n"
            "## Review result\n**Result:** PASS\n\n"
            "## Completion evidence\n"
            "Commands:\nRequirement mapping:\nExecution tokens:\nReview rounds:\n",
            encoding="utf-8",
        )

        violations = archive_module.check_final(
            archive_module.Document(spec_path, "spec.md"),
            archive_module.Document(plan_path, "plan.md"),
        )

        self.assertTrue(
            any("Archive summary" in violation.message for violation in violations)
        )


if __name__ == "__main__":
    unittest.main()
