from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "skills" / "specadoc" / "scripts" / "review_snapshot.py"


def load_module():
    # review_snapshot imports validate_change via a relative sys.path insert,
    # so make sure that package-local import resolves the same way the real
    # script does before exec'ing this module.
    scripts_dir = MODULE_PATH.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("review_snapshot", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReviewSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.root = self.repo / "docs" / "specadoc"
        self.change = self.root / "demo"
        self.change.mkdir(parents=True)
        self.handler = self.change / "Handler.php"
        self.handler.write_text("original\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan_and_spec(self) -> None:
        (self.change / "plan.md").write_text(
            "## Review scope\n\n"
            f"- `{self.handler.relative_to(self.repo)}`\n",
            encoding="utf-8",
        )
        (self.change / "spec.md").write_text(
            "## Requirements\n\n### R1 — One\n\ntext\n\n"
            "## Acceptance scenarios\n\ntext\n\n"
            "## Constraints\n\ntext\n\n"
            "## Affected capabilities\n\ntext\n",
            encoding="utf-8",
        )

    def test_compute_is_stable_on_an_uncommitted_dirty_worktree(self) -> None:
        module = load_module()
        self.write_plan_and_spec()

        first = module.compute(self.change, self.repo)
        second = module.compute(self.change, self.repo)

        self.assertEqual(first, second)
        self.assertIn(self.handler.relative_to(self.repo).as_posix(), first)
        self.assertIn(module.CONTRACT_KEY, first)

    def test_diff_detects_a_changed_file_with_no_git_involved(self) -> None:
        module = load_module()
        self.write_plan_and_spec()
        before = module.compute(self.change, self.repo)

        self.handler.write_text("changed\n", encoding="utf-8")
        after = module.compute(self.change, self.repo)

        result = module.diff(before, after)
        self.assertEqual([self.handler.relative_to(self.repo).as_posix()], result["changed"])
        self.assertEqual([], result["added"])
        self.assertEqual([], result["removed"])

    def test_diff_detects_a_spec_requirement_edit_via_the_contract_hash(self) -> None:
        module = load_module()
        self.write_plan_and_spec()
        before = module.compute(self.change, self.repo)

        (self.change / "spec.md").write_text(
            "## Requirements\n\n### R1 — One\n\nchanged requirement text\n\n"
            "## Acceptance scenarios\n\ntext\n\n"
            "## Constraints\n\ntext\n\n"
            "## Affected capabilities\n\ntext\n",
            encoding="utf-8",
        )
        after = module.compute(self.change, self.repo)

        result = module.diff(before, after)
        self.assertEqual([module.CONTRACT_KEY], result["changed"])

    def test_contract_hash_preserves_section_boundaries(self) -> None:
        module = load_module()
        self.write_plan_and_spec()
        (self.change / "spec.md").write_text(
            "## Requirements\nalpha\n"
            "## Acceptance scenarios\nbeta\n"
            "## Constraints\ngamma\n"
            "## Affected capabilities\ndelta\n",
            encoding="utf-8",
        )
        before = module.compute(self.change, self.repo)
        (self.change / "spec.md").write_text(
            "## Requirements\n"
            "## Acceptance scenarios\nalpha\nbeta\n"
            "## Constraints\ngamma\n"
            "## Affected capabilities\ndelta\n",
            encoding="utf-8",
        )

        after = module.compute(self.change, self.repo)

        self.assertEqual([module.CONTRACT_KEY], module.diff(before, after)["changed"])

    def test_compute_raises_when_a_files_path_no_longer_resolves(self) -> None:
        module = load_module()
        self.write_plan_and_spec()

        self.handler.unlink()

        with self.assertRaises(module.SnapshotError):
            module.compute(self.change, self.repo)

    def test_verify_matches_an_unchanged_snapshot(self) -> None:
        module = load_module()
        self.write_plan_and_spec()
        manifest = module.compute(self.change, self.repo)

        result = module.diff(manifest, module.compute(self.change, self.repo))

        self.assertEqual([], result["changed"] + result["added"] + result["removed"])

    def test_latest_round_reads_the_most_recent_g_block_and_its_manifest(self) -> None:
        module = load_module()
        plan_path = self.change / "plan.md"
        plan_path.write_text(
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G2\n\n- **Type:** re-review\n- **Outcome:** PASS\n\n"
            "```json\n"
            '{"a.php": "deadbeef"}\n'
            "```\n",
            encoding="utf-8",
        )
        plan = module.Document(plan_path, "plan.md")

        entry = module.latest_round(plan)

        self.assertIsNotNone(entry)
        round_id, fields, manifest = entry
        self.assertEqual("G2", round_id)
        self.assertEqual("PASS", fields.get("Outcome"))
        self.assertEqual({"a.php": "deadbeef"}, manifest)

    def test_latest_round_is_none_when_plan_has_no_round_log(self) -> None:
        module = load_module()
        plan_path = self.change / "plan.md"
        plan_path.write_text("## Review result\n\n**Result:** Pending\n", encoding="utf-8")
        plan = module.Document(plan_path, "plan.md")

        self.assertIsNone(module.latest_round(plan))

    def test_scope_accepts_present_and_explicitly_deleted_literal_paths(self) -> None:
        module = load_module()
        deleted = self.change / "Deleted.php"
        plan_path = self.change / "plan.md"
        plan_path.write_text(
            "## Review scope\n\n"
            f"- `{self.handler.relative_to(self.repo)}`\n"
            f"- `!{deleted.relative_to(self.repo)}`\n",
            encoding="utf-8",
        )
        plan = module.Document(plan_path, "plan.md")

        scope = module.review_scope(plan, self.repo)

        self.assertEqual(
            {
                self.handler.relative_to(self.repo).as_posix(): "present",
                deleted.relative_to(self.repo).as_posix(): "deleted",
            },
            scope,
        )

    def test_scope_rejects_non_literal_or_unsafe_paths(self) -> None:
        module = load_module()
        invalid = (
            "/tmp/absolute.php",
            "../outside.php",
            "src/*.php",
            "src/{One,Two}.php",
            "Handler::execute",
        )
        for index, candidate in enumerate(invalid):
            with self.subTest(candidate=candidate):
                plan_path = self.change / f"plan-{index}.md"
                plan_path.write_text(
                    f"## Review scope\n\n- `{candidate}`\n",
                    encoding="utf-8",
                )
                plan = module.Document(plan_path, str(plan_path))

                with self.assertRaises(module.SnapshotError):
                    module.review_scope(plan, self.repo)

    def test_scope_rejects_a_directory_and_missing_present_file(self) -> None:
        module = load_module()
        for index, candidate in enumerate((self.change, self.change / "Missing.php")):
            with self.subTest(candidate=candidate):
                plan_path = self.change / f"invalid-{index}.md"
                plan_path.write_text(
                    "## Review scope\n\n"
                    f"- `{candidate.relative_to(self.repo)}`\n",
                    encoding="utf-8",
                )
                plan = module.Document(plan_path, str(plan_path))

                with self.assertRaises(module.SnapshotError):
                    module.review_scope(plan, self.repo)

    def test_diff_detects_a_review_scope_addition(self) -> None:
        module = load_module()
        self.write_plan_and_spec()
        before = module.compute(self.change, self.repo)
        added = self.change / "Added.php"
        added.write_text("new\n", encoding="utf-8")
        plan_path = self.change / "plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8")
            + f"- `{added.relative_to(self.repo)}`\n",
            encoding="utf-8",
        )

        after = module.compute(self.change, self.repo)

        self.assertEqual([added.relative_to(self.repo).as_posix()], module.diff(before, after)["added"])


if __name__ == "__main__":
    unittest.main()
