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
        self.root = Path(self.temp.name) / "docs" / "specadoc"
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
        found += module.stray_delta_lines(spec, "docs/specadoc")
        found += module.check_capability_deltas(spec, "docs/specadoc")
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
            "- `docs/specadoc/specs/auth.md` (new capability)\n"
            "  - MODIFED C2 (R1) — typo\n"
            "- `docs/other/notes.md`\n"
            "  - ADDED C3 (R1) — outside specs\n"
        )
        self.assertIn("operation line before any capability path", messages)
        self.assertIn("unrecognized capability operation; use ADDED|MODIFIED|REMOVED|RENAMED C<n>", messages)
        self.assertIn("docs/other/notes.md: operations are ignored outside docs/specadoc/specs/", messages)

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
                "## Affected capabilities\n\n- `docs/specadoc/specs/auth.md`\n"
                "  - RENAMED C2 (R1)\n",
            )
            bare = [item.message for item in module.check_capability_deltas(spec, "docs/specadoc")]
            spec = self.document(
                "spec.md",
                "## Affected capabilities\n\n- `docs/specadoc/specs/auth.md`\n"
                "  - RENAMED C2 (R1) — New heading\n",
            )
            named = [item.message for item in module.check_capability_deltas(spec, "docs/specadoc")]
        finally:
            os.chdir(old_cwd)
        self.assertTrue(any("RENAMED C2 names no new heading" in message for message in bare), bare)
        self.assertFalse(any("names no new heading" in message for message in named), named)

    def collision_change(self, slug: str, ops: str) -> None:
        directory = self.root / slug
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "spec.md").write_text(
            "## Affected capabilities\n\n" + ops, encoding="utf-8"
        )
        (directory / "plan.md").write_text("# Plan\n", encoding="utf-8")

    def cross_findings(self, slug: str):
        import os

        module = load_module()
        old_cwd = Path.cwd()
        os.chdir(self.root.parents[1])
        try:
            spec = module.Document(self.root / slug / "spec.md", "spec.md")
            return module.cross_change_findings(spec, "docs/specadoc", slug)
        finally:
            os.chdir(old_cwd)

    def test_cross_change_duplicate_added_is_violation(self) -> None:
        ops = "- `docs/specadoc/specs/x.md`\n  - ADDED C4 (R1) — new\n"
        self.collision_change("alpha", ops)
        self.collision_change("beta", ops)
        violations, warnings = self.cross_findings("alpha")
        self.assertEqual(warnings, [])
        self.assertEqual(len(violations), 1)
        message = violations[0].message
        self.assertIn("beta", message)
        self.assertIn("docs/specadoc/specs/x.md", message)
        self.assertIn("C4", message)
        self.assertEqual(violations[0].line, 4)

    def test_cross_change_main_exits_nonzero_for_duplicate_added(self) -> None:
        import contextlib
        import io
        import os

        ops = "- `docs/specadoc/specs/x.md`\n  - ADDED C4 (R1) — new\n"
        self.collision_change("alpha", ops)
        self.collision_change("beta", ops)
        module = load_module()
        old_cwd = Path.cwd()
        old_argv = sys.argv
        os.chdir(self.root.parents[1])
        sys.argv = ["validate_change.py", "alpha", "--phase", "spec", "--root", "docs/specadoc"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = module.main()
        finally:
            os.chdir(old_cwd)
            sys.argv = old_argv
        self.assertNotEqual(code, 0)
        self.assertIn("also ADDED by active change beta", out.getvalue())

    def test_cross_change_different_id_or_path_is_clean(self) -> None:
        self.collision_change(
            "alpha", "- `docs/specadoc/specs/x.md`\n  - ADDED C4 (R1) — new\n"
        )
        self.collision_change(
            "beta", "- `docs/specadoc/specs/x.md`\n  - ADDED C5 (R1) — new\n"
        )
        self.collision_change(
            "gamma", "- `docs/specadoc/specs/y.md`\n  - ADDED C4 (R1) — new\n"
        )
        self.assertEqual(self.cross_findings("alpha"), ([], []))

    def test_cross_change_ignores_archive_and_specs_directories(self) -> None:
        ops = "- `docs/specadoc/specs/x.md`\n  - ADDED C4 (R1) — new\n"
        self.collision_change("alpha", ops)
        for name in ("archive/old", "specs", "contracts"):
            self.collision_change(name, ops)
        (self.root / "archive" / "x").mkdir(parents=True)
        (self.root / "archive" / "x" / "record.md").write_text(ops, encoding="utf-8")
        self.assertEqual(self.cross_findings("alpha"), ([], []))

    def run_main(self, *extra: str):
        import contextlib
        import io
        import os

        module = load_module()
        old_cwd = Path.cwd()
        old_argv = sys.argv
        os.chdir(self.root.parents[1])
        sys.argv = [
            "validate_change.py", "alpha", "--phase", "spec", "--root", "docs/specadoc", *extra
        ]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = module.main()
        finally:
            os.chdir(old_cwd)
            sys.argv = old_argv
        return code, out.getvalue(), err.getvalue()

    def test_cross_change_overlapping_modified_warns_in_json_without_exit_change(self) -> None:
        import json
        import shutil

        ops = "- `docs/specadoc/specs/x.md`\n  - MODIFIED C2 (R1) — edit\n"
        self.collision_change("alpha", ops)
        self.collision_change("beta", ops)
        code, out, err = self.run_main("--json")
        payload = json.loads(out)
        self.assertEqual(len(payload["warnings"]), 1)
        warning = payload["warnings"][0]
        for part in ("beta", "docs/specadoc/specs/x.md", "C2"):
            self.assertIn(part, warning)
        self.assertIn("warning: " + warning, err)
        shutil.rmtree(self.root / "beta")
        baseline_code, baseline_out, _ = self.run_main("--json")
        self.assertEqual(code, baseline_code)
        self.assertEqual(json.loads(baseline_out)["warnings"], [])

    def test_cross_change_warning_prints_to_stderr_in_text_mode(self) -> None:
        ops = "- `docs/specadoc/specs/x.md`\n  - MODIFIED C2 (R1) — edit\n"
        self.collision_change("alpha", ops)
        self.collision_change("beta", ops)
        _, out, err = self.run_main()
        self.assertIn("warning: ", err)
        self.assertIn("beta", err)
        self.assertNotIn("warning:", out)

    def test_cross_change_modified_vs_renamed_warns(self) -> None:
        self.collision_change("alpha", "- `docs/specadoc/specs/x.md`\n  - MODIFIED C2 (R1) — edit\n")
        self.collision_change(
            "beta", "- `docs/specadoc/specs/x.md`\n  - RENAMED C2 (R1) — New name\n"
        )
        violations, warnings = self.cross_findings("alpha")
        self.assertEqual(violations, [])
        self.assertEqual(
            warnings,
            [
                "C2 on docs/specadoc/specs/x.md: MODIFIED here, RENAMED by active change beta"
            ],
        )

    def test_cross_change_added_vs_modified_does_not_warn(self) -> None:
        self.collision_change("alpha", "- `docs/specadoc/specs/x.md`\n  - ADDED C2 (R1) — new\n")
        self.collision_change("beta", "- `docs/specadoc/specs/x.md`\n  - MODIFIED C2 (R1) — edit\n")
        self.assertEqual(self.cross_findings("alpha"), ([], []))
        self.assertEqual(self.cross_findings("beta"), ([], []))

    def test_cross_change_edits_on_different_id_do_not_warn(self) -> None:
        self.collision_change("alpha", "- `docs/specadoc/specs/x.md`\n  - MODIFIED C2 (R1) — edit\n")
        self.collision_change("beta", "- `docs/specadoc/specs/x.md`\n  - REMOVED C3 (R1)\n")
        self.assertEqual(self.cross_findings("alpha"), ([], []))

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

    def task_plan(self, *, owner: str, risk: str, files: str, mark: str = " ", extra: str = "") -> str:
        return (
            f"## Tasks\n\n### T1 — Task\n\n- [{mark}] Complete\n"
            f"- **Requirements:** R1\n- **Risk:** Low\n- **Decision risk:** {risk}\n"
            f"- **Owner:** {owner}\n- **Owner level:** EASY\n{extra}"
            f"- **Verification owner:** controller\n- **Files:** {files}\n"
            "- **Test first:** test\n- **Expected RED:** failure\n"
            "- **Implementation:** work\n- **Verification:** `rtk test`\n"
            "- **Surface:** code\n- **Delivery verification:** N/A\n"
            "- **Done when:** done\n- **Evidence:** Pending\n"
        )

    def plan_messages(self, content: str) -> list[str]:
        module = load_module()
        return [item.message for item in module.check_plan(self.document("plan.md", content), ["R1"])]

    def numbered_plan(self, count: int, extra: str = "") -> str:
        single = self.task_plan(owner="worker", risk="low", files="`src/A.php`", extra=extra)
        body = single.split("### T1", 1)[1]
        plain = self.task_plan(owner="worker", risk="low", files="`src/A.php`").split("### T1", 1)[1]
        parts = [f"### T{number}{plain}" for number in range(2, count + 1)]
        return "## Tasks\n\n" + "\n".join([f"### T1{body}"] + parts)

    def test_plan_over_max_tasks_suggests_separate_change(self) -> None:
        messages = self.plan_messages(self.numbered_plan(9))
        self.assertTrue(any("separate change" in message for message in messages), messages)

    def test_plan_under_min_tasks_keeps_count_only_message(self) -> None:
        messages = [m for m in self.plan_messages(self.numbered_plan(2)) if "tasks; a normal change" in m]
        self.assertEqual(["2 tasks; a normal change carries 3 to 8"], messages)

    def test_plan_optional_checkpoint_field_is_accepted(self) -> None:
        messages = self.plan_messages(self.numbered_plan(3, extra="- **Checkpoint:** commit after schema\n"))
        self.assertFalse(any("Checkpoint" in message for message in messages), messages)

    def test_worker_files_must_be_checkable_paths(self) -> None:
        messages = self.plan_messages(
            self.task_plan(owner="worker", risk="low", files="`src/A.php`, matching repositories")
        )
        self.assertTrue(
            any("worker task's Files" in message and "matching repositories" in message for message in messages),
            messages,
        )

    def test_worker_files_accept_paths_dirs_globs_and_annotations(self) -> None:
        messages = self.plan_messages(
            self.task_plan(
                owner="worker",
                risk="low",
                files="`src/A.php` (`handle`), `src/Support/`, `tests/{Unit,Feature}/*Test.php`; `config/app.php`",
            )
        )
        self.assertFalse(any("worker task's Files" in message for message in messages), messages)

    def test_worker_files_rule_skips_completed_tasks_and_controller(self) -> None:
        done = self.plan_messages(self.task_plan(owner="worker", risk="low", files="the module", mark="x"))
        controller = self.plan_messages(
            self.task_plan(
                owner="controller",
                risk="medium",
                files="the module",
            )
        )
        self.assertFalse(any("worker task's Files" in message for message in done + controller))

    def test_controller_low_risk_requires_justification(self) -> None:
        bare = self.plan_messages(self.task_plan(owner="controller", risk="low", files="`a.php`"))
        justified = self.plan_messages(
            self.task_plan(
                owner="controller",
                risk="low",
                files="`a.php`",
                extra="- **Controller justification:** one-file, one-cycle fix\n",
            )
        )
        self.assertTrue(any("Controller justification" in message for message in bare), bare)
        self.assertFalse(any("Controller justification" in message for message in justified), justified)

    def test_files_patterns_split_paths_symbols_and_prose(self) -> None:
        module = load_module()
        patterns, uncheckable = module.files_patterns(
            "`app/A.php` (`A::run`), `pkg/{x,y}/b.json`, `Foo::bar`, prose here"
        )
        self.assertEqual(patterns, ["app/A.php", "pkg/x/b.json", "pkg/y/b.json"])
        self.assertEqual(uncheckable, ["`Foo::bar`", "prose here"])

    def independence_messages(self, *, worker: str, reviewer: str, round_extra: str = "", owner: str = "worker") -> list[str]:
        module = load_module()
        plan = self.document(
            "plan.md",
            "## Model handoff\n\n"
            f"**Worker runtime:** {worker}  \n**Reviewer runtime:** {reviewer}  \n\n"
            f"## Tasks\n\n### T1 — One\n\n- [x] Complete\n- **Owner:** {owner}\n\n"
            "## Review result\n\n### G1\n\n- **Type:** initial\n" + round_extra,
        )
        return [item.message for item in module.check_reviewer_independence(plan)]

    def test_reviewer_on_worker_runtime_needs_waiver(self) -> None:
        same = self.independence_messages(worker="codex/m1", reviewer="codex/m2")
        waived = self.independence_messages(
            worker="codex/m1", reviewer="codex/m2", round_extra="- **Independence waiver:** only Codex is licensed\n"
        )
        other = self.independence_messages(worker="codex/m1", reviewer="claude/m3")
        round_override = self.independence_messages(
            worker="codex/m1", reviewer="claude/m3", round_extra="- **Reviewer runtime:** codex/m2\n"
        )
        self.assertTrue(any("Independence waiver" in message for message in same), same)
        self.assertEqual([], waived)
        self.assertEqual([], other)
        self.assertTrue(any("G1: reviewer runs on the worker's runtime" in message for message in round_override))

    def test_independence_is_silent_without_recorded_runtimes_or_worker_tasks(self) -> None:
        self.assertEqual([], self.independence_messages(worker="<runtime/model>", reviewer="codex/m"))
        self.assertEqual([], self.independence_messages(worker="codex/m", reviewer="codex/m", owner="controller"))

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

    def test_placeholders_ignore_disclosure_tags(self) -> None:
        plan = self.document(
            "plan.md",
            "## Round log\n"
            "<details><summary>Manifest</summary>\n"
            "<per-change placeholder text>\n"
            "<details open>\n"
            '<summary class="x">Both</summary> <another placeholder>\n',
        )
        found = plan.placeholders("Round log")
        self.assertEqual(
            [(3, "<per-change placeholder text>"), (5, "<another placeholder>")],
            found,
        )

    def test_placeholders_still_report_prose_starting_with_tag_names(self) -> None:
        plan = self.document(
            "plan.md",
            "## Round log\n<summary of the outcome>\n<details about the risk>\n",
        )
        self.assertEqual(
            [(2, "<summary of the outcome>"), (3, "<details about the risk>")],
            plan.placeholders("Round log"),
        )


if __name__ == "__main__":
    unittest.main()
