from __future__ import annotations

import hashlib
import importlib.util
import shutil
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

    def coverage_change(self, goal: str, ids: tuple[str, ...] = ("R1", "R2")) -> Path:
        change = self.change()
        requirements = "\n".join(f"### {identifier} — Needed\n\nText.\n" for identifier in ids)
        change.joinpath("spec.md").write_text(
            f"## Goal\n{goal}\n\n## Requirements\n\n{requirements}",
            encoding="utf-8",
        )
        change.joinpath("plan.md").write_text("## Archive summary\nDone", encoding="utf-8")
        return change

    def test_normal_archive_and_dry_run_refuse_record_missing_requirement_id(self) -> None:
        archive_module = load_module()
        change = self.coverage_change("Covers R1 only")

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            for dry_run in (False, True):
                with self.subTest(dry_run=dry_run):
                    with self.assertRaisesRegex(archive_module.ArchiveError, "R2") as caught:
                        archive_module.archive_change(self.root, "demo", force=False, dry_run=dry_run)
                    self.assertNotIn("does not mention R1", str(caught.exception))
                    self.assertTrue(change.is_dir())
                    self.assertFalse((self.root / "archive").exists())

    def test_force_archive_lists_missing_id_under_forced_exceptions(self) -> None:
        archive_module = load_module()
        self.coverage_change("Covers R1 only")

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            result = archive_module.archive_change(self.root, "demo", force=True, dry_run=False)

        content = (self.root / "archive" / "demo" / "record.md").read_text(encoding="utf-8")
        exceptions = content.split("## Forced exceptions")[1].split("## Source manifest")[0]
        self.assertIn("R2", exceptions)
        self.assertNotIn("R1", exceptions)
        self.assertTrue(any("R2" in message for message in result.violations))

    def test_force_coverage_ignores_ids_named_only_by_gate_messages(self) -> None:
        archive_module = load_module()
        self.coverage_change("Covers R1 only")
        gate = ["R2 has no task in plan.md"]

        with patch.object(archive_module, "validate_change_gates", return_value=gate):
            result = archive_module.archive_change(self.root, "demo", force=True, dry_run=False)

        self.assertIn("record.md does not mention R2", result.violations)

    def test_complete_record_archives_normally(self) -> None:
        archive_module = load_module()
        self.coverage_change("Covers R1 and R2")

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        content = (self.root / "archive" / "demo" / "record.md").read_text(encoding="utf-8")
        self.assertIn("status: archived", content)

    def test_record_omits_verification_section(self) -> None:
        archive_module = load_module()
        for force in (False, True):
            with self.subTest(force=force):
                change = self.coverage_change("Covers R1 and R2")
                change.joinpath("plan.md").write_text(
                    "## Archive summary\nDone\n\n## Final verification\n- [x] checklist item\n\n"
                    "## Review result\nReviewed\n\n## Completion evidence\nMeasured\n",
                    encoding="utf-8",
                )
                with patch.object(archive_module, "validate_change_gates", return_value=[]):
                    archive_module.archive_change(self.root, "demo", force=force, dry_run=False)
                archive = self.root / "archive" / "demo"
                content = (archive / "record.md").read_text(encoding="utf-8")
                self.assertNotIn("## Verification", content)
                self.assertNotIn("checklist item", content)
                self.assertIn("## Review", content)
                self.assertIn("## Measurement", content)
                shutil.rmtree(archive)

    def test_measurement_keeps_totals_and_other_evidence_only(self) -> None:
        archive_module = load_module()
        rows = [
            f"mode=apply claude d0839ff{i} role=controller parent=- unique={i}00 read=1 in=2"
            for i in range(3)
        ]
        total = "total mode=apply claude 3 run(s) unique=900 read=3 controller=45%"
        commands = "- `python3 -m unittest` -> OK (R1, R2)"
        mapping = "- R2 -> archive_change.py, test_archive_change.py"
        change = self.coverage_change("Covers R1 and R2")
        change.joinpath("plan.md").write_text(
            "## Archive summary\nDone\n\n## Completion evidence\n"
            f"Commands:\n{commands}\nRequirement mapping:\n{mapping}\n"
            "Execution tokens:\n" + "\n".join(rows) + f"\n{total}\n"
            "Review rounds:\n- G1 PASS\n",
            encoding="utf-8",
        )

        with patch.object(archive_module, "validate_change_gates", return_value=[]):
            archive_module.archive_change(self.root, "demo", force=False, dry_run=False)

        content = (self.root / "archive" / "demo" / "record.md").read_text(encoding="utf-8")
        for line in (total, commands, mapping, "Review rounds:", "- G1 PASS"):
            self.assertIn(line, content)
        for row in rows:
            self.assertNotIn(row, content)
        self.assertNotIn("role=controller", content)

    def test_execution_rows_outside_token_block_are_kept(self) -> None:
        archive_module = load_module()
        stray = "mode=apply claude abc role=worker quoted as a residual risk"
        text = f"Residual risks or waivers:\n{stray}\nExecution tokens:\n{stray}\n"

        self.assertEqual(
            f"Residual risks or waivers:\n{stray}\nExecution tokens:\n",
            archive_module._token_totals_only(text),
        )

    def test_record_coverage_matches_whole_words_only(self) -> None:
        archive_module = load_module()
        change = self.coverage_change("Covers R10 only", ids=("R1", "R10"))

        messages = archive_module.record_coverage(
            change / "spec.md", "Covers R10 only", self.root.as_posix()
        )

        self.assertEqual(1, len(messages))
        self.assertIn("R1", messages[0])
        self.assertNotIn("R10", messages[0])

    def test_record_coverage_includes_capability_ids(self) -> None:
        archive_module = load_module()
        change = self.change()
        capability = self.root / "specs" / "demo.md"
        change.joinpath("spec.md").write_text(
            "## Affected capabilities\n"
            f"- `{capability}`\n"
            "  - ADDED C7 — Delivered\n",
            encoding="utf-8",
        )

        self.assertEqual(
            ["record.md does not mention C7"],
            archive_module.record_coverage(change / "spec.md", "nothing", self.root.as_posix()),
        )
        self.assertEqual(
            [], archive_module.record_coverage(change / "spec.md", "has C7.", self.root.as_posix())
        )

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
