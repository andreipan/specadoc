from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "skills" / "specadoc" / "scripts" / "validate_change.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_change", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ValidateChangeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "docs" / "agent"
        self.change = self.root / "demo"
        self.change.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def document(self, name: str, content: str):
        path = self.change / name
        path.write_text(content, encoding="utf-8")
        module = load_module()
        return module.Document(path, name)

    def spec_messages(self, content: str) -> list[str]:
        module = load_module()
        spec = self.document("spec.md", content)
        requirements = spec.blocks("Requirements", "R")
        scenarios = spec.blocks("Acceptance scenarios", "A")
        found = module.check_spec_content(spec, requirements, scenarios)
        found += module.stray_delta_lines(spec, "docs/agent")
        found += module.check_capability_deltas(spec, "docs/agent")
        return [item.message for item in found]

    def test_spec_content_rejects_empty_and_unfinished_goal(self) -> None:
        self.assertIn("Goal is empty", self.spec_messages("## Goal\n\n## Requirements\n"))
        self.assertIn(
            "Goal still contains TBD/TODO",
            self.spec_messages("## Goal\n\nShip it, TODO decide scope\n"),
        )
        self.assertNotIn(
            "Goal still contains TBD/TODO",
            self.spec_messages("## Goal\n\nRename the `TODO` column\n"),
        )

    def test_spec_content_rejects_unfinished_requirement(self) -> None:
        messages = self.spec_messages("## Requirements\n\n### R1 — Limit\n\nThe limit is TBD.\n")
        self.assertIn("R1: still contains TBD/TODO", messages)

    def test_spec_content_rejects_duplicate_requirement_titles(self) -> None:
        messages = self.spec_messages(
            "## Requirements\n\n### R1 — Token  Refresh\n\nx\n\n### R2 — token refresh\n\ny\n"
            "\n### R2 — Other\n\nz\n"
        )
        self.assertIn("R2: requirement title duplicates R1 (case/whitespace-insensitive)", messages)
        self.assertIn("R2: duplicate requirement id", messages)

    def test_spec_content_rejects_empty_scenario_steps(self) -> None:
        messages = self.spec_messages(
            "## Acceptance scenarios\n\n### A1 — Login\n\n- **Given:** a user\n- **When:**\n- **Then:**   \n"
        )
        self.assertIn("A1: empty When", messages)
        self.assertIn("A1: empty Then", messages)
        self.assertNotIn("A1: empty Given", messages)

    def test_capability_deltas_reject_stray_and_unpaired_operations(self) -> None:
        messages = self.spec_messages(
            "## Affected capabilities\n\n"
            "  - ADDED C1 (R1) — before any path\n"
            "- `docs/agent/specs/auth.md` (new capability)\n"
            "  - MODIFED C2 (R1) — typo\n"
            "- `docs/other/notes.md`\n"
            "  - ADDED C3 (R1) — outside specs\n"
        )
        self.assertIn("operation line before any capability path", messages)
        self.assertIn("unrecognized capability operation; use ADDED|MODIFIED|REMOVED|RENAMED C<n>", messages)
        self.assertIn("docs/other/notes.md: operations are ignored outside docs/agent/specs/", messages)

    def test_renamed_requires_new_heading(self) -> None:
        capability = self.root / "specs" / "auth.md"
        capability.parent.mkdir(parents=True)
        capability.write_text("### C2 — Old\n", encoding="utf-8")
        module = load_module()
        old_cwd = Path.cwd()
        import os
        os.chdir(self.root.parents[1])
        try:
            spec = self.document(
                "spec.md",
                "## Affected capabilities\n\n- `docs/agent/specs/auth.md`\n"
                "  - RENAMED C2 (R1)\n",
            )
            bare = [item.message for item in module.check_capability_deltas(spec, "docs/agent")]
            spec = self.document(
                "spec.md",
                "## Affected capabilities\n\n- `docs/agent/specs/auth.md`\n"
                "  - RENAMED C2 (R1) — New heading\n",
            )
            named = [item.message for item in module.check_capability_deltas(spec, "docs/agent")]
        finally:
            os.chdir(old_cwd)
        self.assertTrue(any("RENAMED C2 names no new heading" in message for message in bare), bare)
        self.assertFalse(any("names no new heading" in message for message in named), named)

    def test_pre_review_rejects_ui_task_without_browser_evidence(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — UI\n\n- [x] Complete\n"
            "- **Surface:** ui\n- **Evidence:** Build: passed\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertIn(
            "T1: UI evidence must record final Build: PASS, Typecheck: PASS, and Browser: URL/state results",
            messages,
        )

    def test_pre_review_rejects_unobserved_browser_check(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — UI\n\n- [x] Complete\n"
            "- **Surface:** ui\n"
            "- **Evidence:** Build: passed; Browser: not performed\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertIn(
            "T1: UI evidence must record final Build: PASS, Typecheck: PASS, and Browser: URL/state results",
            messages,
        )

    def test_pre_review_rejects_non_passing_build_or_typecheck(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — UI\n\n- [x] Complete\n"
            "- **Surface:** ui\n"
            "- **Evidence:** Build: not PASS; Typecheck: not PASS; "
            "Browser: URL: http://localhost; State: form visible\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertIn(
            "T1: UI evidence must record final Build: PASS, Typecheck: PASS, and Browser: URL/state results",
            messages,
        )

    def test_plan_rejects_unknown_task_surface(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Task\n\n- [ ] Complete\n"
            "- **Requirements:** R1\n- **Risk:** Low\n- **Decision risk:** low\n"
            "- **Owner:** controller\n- **Owner level:** EASY\n"
            "- **Verification owner:** controller\n- **Files:** file\n"
            "- **Test first:** test\n- **Expected RED:** failure\n"
            "- **Implementation:** work\n- **Verification:** `rtk test`\n"
            "- **Surface:** browser-only\n- **Delivery verification:** N/A\n"
            "- **Done when:** done\n- **Evidence:** Pending\n",
        )

        messages = [item.message for item in module.check_plan(plan, ["R1"])]

        self.assertIn("T1: Surface must be one of code, ui, mixed", messages)

    def test_final_rejects_review_that_omits_current_requirement(self) -> None:
        module = load_module()
        spec = self.document("spec.md", "## Requirements\n\n### R1 — One\n\ntext\n")
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — One\n\n- [x] Complete\n"
            "- **Surface:** code\n- **Evidence:** done\n\n"
            "## Final verification\n\n"
            "## Review result\n\n**Result:** PASS\n"
            "**Reviewed requirements:** R2\n**Reviewed tasks:** T1\n",
        )

        messages = [item.message for item in module.check_final(spec, plan)]

        self.assertIn(
            "Review result: Reviewed requirements mismatch (missing: R1; extra: R2)",
            messages,
        )

    def test_pre_review_rejects_empty_code_surface_evidence(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            "- **Surface:** code\n"
            "- **Evidence:** Pending; keep final evidence to one or two lines.\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertIn(
            "T1: Evidence is missing or still the template placeholder; "
            "record the command and result",
            messages,
        )

    def test_pre_review_accepts_recorded_code_surface_evidence(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            "- **Surface:** code\n- **Evidence:** rtk php artisan test --compact: passed\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertFalse(any("Evidence is missing" in message for message in messages))

    def test_pre_review_rejects_evidence_stale_against_files_hash(self) -> None:
        module = load_module()
        target = self.change / "Handler.php"
        target.write_text("original\n", encoding="utf-8")
        recorded_hash = module.files_field_hash(str(target))
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            f"- **Surface:** code\n- **Files:** {target}\n"
            "- **Evidence:** rtk php artisan test --compact: passed\n"
            f"- **Evidence hash:** {recorded_hash}\n",
        )
        target.write_text("changed after evidence was recorded\n", encoding="utf-8")

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertIn(
            "T1: Evidence predates a later change to one of its Files; "
            "re-verify and re-record Evidence and Evidence hash",
            messages,
        )

    def test_pre_review_accepts_evidence_hash_matching_current_files(self) -> None:
        module = load_module()
        target = self.change / "Handler.php"
        target.write_text("stable content\n", encoding="utf-8")
        recorded_hash = module.files_field_hash(str(target))
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            f"- **Surface:** code\n- **Files:** {target}\n"
            "- **Evidence:** rtk php artisan test --compact: passed\n"
            f"- **Evidence hash:** {recorded_hash}\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertFalse(any("predates a later change" in message for message in messages))

    def test_pre_review_blocks_a_fourth_new_diff_round_without_override(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G2\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G3\n\n- **Type:** initial\n- **Outcome:** FAIL\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertTrue(any("new-diff review rounds recorded" in message for message in messages))

    def test_pre_review_allows_a_fourth_round_with_override(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G2\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G3\n\n- **Type:** initial\n- **Outcome:** FAIL\n"
            "- **Round cap override:** user accepted a 4th round, unrelated regressions found\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertFalse(any("new-diff review rounds recorded" in message for message in messages))

    def test_pre_review_does_not_count_one_re_review_against_the_cap(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G2\n\n- **Type:** re-review\n- **Outcome:** PASS\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertFalse(any("new-diff review rounds recorded" in message for message in messages))

    def test_pre_review_rejects_missing_or_unknown_round_type(self) -> None:
        module = load_module()
        for value in ("", "typo"):
            with self.subTest(value=value):
                type_line = f"- **Type:** {value}\n" if value else ""
                plan = self.document(
                    "plan.md",
                    "## Review result\n\n### G1\n\n"
                    + type_line
                    + "- **Outcome:** FAIL\n",
                )

                messages = [item.message for item in module.check_pre_review(plan)]

                self.assertTrue(any("Type must be initial or re-review" in message for message in messages))

    def test_pre_review_rejects_more_than_one_re_review_after_an_initial(self) -> None:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Review result\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G2\n\n- **Type:** re-review\n- **Outcome:** FAIL\n\n"
            "### G3\n\n- **Type:** re-review\n- **Outcome:** PASS\n",
        )

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertTrue(any("at most one re-review" in message for message in messages))

    def test_pre_review_rejects_evidence_hash_when_a_file_was_deleted(self) -> None:
        module = load_module()
        target = self.change / "Handler.php"
        target.write_text("original\n", encoding="utf-8")
        recorded_hash = module.files_field_hash(str(target))
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            f"- **Surface:** code\n- **Files:** {target}\n"
            "- **Evidence:** tests passed\n"
            f"- **Evidence hash:** {recorded_hash}\n",
        )
        target.unlink()

        messages = [item.message for item in module.check_pre_review(plan)]

        self.assertTrue(any("Evidence predates a later change" in message for message in messages))

    def test_final_allows_third_initial_round_to_finish_with_pass(self) -> None:
        module = load_module()
        snapshot = module.review_manifest_hash({})
        spec = self.document("spec.md", "## Requirements\n\n### R1 — One\n\ntext\n")
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            "- **Surface:** code\n- **Evidence:** tests passed\n\n"
            "## Final verification\n\n"
            "## Review result\n\n**Result:** PASS\n"
            "**Reviewed requirements:** R1\n**Reviewed tasks:** T1\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G2\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "### G3\n\n- **Type:** initial\n- **Outcome:** PASS\n"
            f"- **Snapshot:** {snapshot}\n\n```json\n{{}}\n```\n\n"
            "## Archive summary\n\nDone\n\n"
            "## Completion evidence\n\n"
            "Commands:\nRequirement mapping:\nExecution tokens:\nReview rounds:\n",
        )

        messages = [item.message for item in module.check_final(spec, plan)]

        self.assertEqual([], messages)

    def test_final_rejects_latest_failed_round_even_when_header_says_pass(self) -> None:
        module = load_module()
        spec = self.document("spec.md", "## Requirements\n\n### R1 — One\n\ntext\n")
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            "- **Surface:** code\n- **Evidence:** tests passed\n\n"
            "## Final verification\n\n"
            "## Review result\n\n**Result:** PASS\n"
            "**Reviewed requirements:** R1\n**Reviewed tasks:** T1\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** FAIL\n\n"
            "## Archive summary\n\nDone\n",
        )

        messages = [item.message for item in module.check_final(spec, plan)]

        self.assertTrue(any("latest round G1 outcome is FAIL" in message for message in messages))

    def test_final_rejects_latest_pass_without_manifest(self) -> None:
        module = load_module()
        spec = self.document("spec.md", "## Requirements\n\n### R1 — One\n\ntext\n")
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            "- **Surface:** code\n- **Evidence:** tests passed\n\n"
            "## Final verification\n\n"
            "## Review result\n\n**Result:** PASS\n"
            "**Reviewed requirements:** R1\n**Reviewed tasks:** T1\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** PASS\n"
            "- **Snapshot:** sha256:missing\n\n"
            "## Archive summary\n\nDone\n",
        )

        messages = [item.message for item in module.check_final(spec, plan)]

        self.assertTrue(any("latest round G1 has no valid manifest" in message for message in messages))

    def test_final_rejects_snapshot_hash_that_does_not_match_manifest(self) -> None:
        module = load_module()
        spec = self.document("spec.md", "## Requirements\n\n### R1 — One\n\ntext\n")
        plan = self.document(
            "plan.md",
            "## Tasks\n\n### T1 — Code\n\n- [x] Complete\n"
            "- **Surface:** code\n- **Evidence:** tests passed\n\n"
            "## Final verification\n\n"
            "## Review result\n\n**Result:** PASS\n"
            "**Reviewed requirements:** R1\n**Reviewed tasks:** T1\n\n"
            "### G1\n\n- **Type:** initial\n- **Outcome:** PASS\n"
            "- **Snapshot:** sha256:not-the-manifest-hash\n\n"
            "```json\n{\"src/A.php\": \"abc\"}\n```\n\n"
            "## Archive summary\n\nDone\n",
        )

        messages = [item.message for item in module.check_final(spec, plan)]

        self.assertTrue(any("Snapshot does not match its manifest hash" in message for message in messages))

    def test_capability_operation_without_requirement_citation_is_rejected(self) -> None:
        module = load_module()
        capability = self.root / "specs" / "demo.md"
        capability.parent.mkdir()
        capability.write_text("### C12 — Existing\n\n## Provenance\n| Change |\n|---|\n| demo |\n", encoding="utf-8")
        spec = self.document(
            "spec.md",
            "## Requirements\n\n### R7 — One\n\ntext\n\n"
            "## Affected capabilities\n\n"
            f"- `{capability}`\n"
            "  - MODIFIED C12 — no citation here\n",
        )

        messages = [
            item.message
            for item in module.check_capability_deltas(spec, str(self.root), requirement_ids=["R7"])
        ]

        self.assertTrue(any("cites no requirement" in message for message in messages))

    def test_capability_operation_with_requirement_citation_passes(self) -> None:
        module = load_module()
        capability = self.root / "specs" / "demo.md"
        capability.parent.mkdir()
        capability.write_text("### C12 — Existing\n\n## Provenance\n| Change |\n|---|\n| demo |\n", encoding="utf-8")
        spec = self.document(
            "spec.md",
            "## Requirements\n\n### R7 — One\n\ntext\n\n"
            "## Affected capabilities\n\n"
            f"- `{capability}`\n"
            "  - MODIFIED C12 (R7) — cited correctly\n",
        )

        messages = [
            item.message
            for item in module.check_capability_deltas(spec, str(self.root), requirement_ids=["R7"])
        ]

        self.assertEqual([], messages)

    def test_capability_operation_citing_unknown_requirement_is_rejected(self) -> None:
        module = load_module()
        capability = self.root / "specs" / "demo.md"
        capability.parent.mkdir()
        capability.write_text("### C12 — Existing\n\n## Provenance\n| Change |\n|---|\n| demo |\n", encoding="utf-8")
        spec = self.document(
            "spec.md",
            "## Requirements\n\n### R7 — One\n\ntext\n\n"
            "## Affected capabilities\n\n"
            f"- `{capability}`\n"
            "  - MODIFIED C12 (R99) — cites a requirement that does not exist\n",
        )

        messages = [
            item.message
            for item in module.check_capability_deltas(spec, str(self.root), requirement_ids=["R7"])
        ]

        self.assertTrue(any("cites unknown requirement R99" in message for message in messages))

    def test_new_capability_is_allowed_only_after_application(self) -> None:
        module = load_module()
        capability = self.root / "specs" / "demo.md"
        capability.parent.mkdir()
        capability.write_text("### C1 — Delivered\n\n## Provenance\n| Change |\n|---|\n| demo |\n", encoding="utf-8")
        spec = self.document(
            "spec.md",
            "## Affected capabilities\n\n"
            f"- `{capability}` (new capability)\n"
            "  - ADDED C1 — Delivered\n",
        )

        before = [item.message for item in module.check_capability_deltas(spec, str(self.root))]
        after = [
            item.message
            for item in module.check_capability_deltas(
                spec, str(self.root), expect_applied=True
            )
        ]

        self.assertTrue(any("marked `(new capability)`" in message for message in before))
        self.assertEqual([], after)


if __name__ == "__main__":
    unittest.main()
