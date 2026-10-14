from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "skills/specadoc/scripts"))

from role_routing import resolve_role, inspect_routing
from specadoc_config import load_config
from specadoc_root import resolve_root


class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.role("claude", "worker", "host", "medium")
        self.role("codex", "worker", "executor", "low")

    def role(self, runtime, role, model, effort):
        ext = "toml" if runtime == "codex" else "md"
        path = self.repo / f".{runtime}/agents/{role}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (f'model = "{model}"\nmodel_reasoning_effort = "{effort}"\n' if ext == "toml"
                else f"---\nmodel: {model}\neffort: {effort}\n---\ncontract\n")
        path.write_text(text)
        return path

    def config(self, value):
        (self.repo / ".specadoc.json").write_text(json.dumps(value))

    def test_legacy_root_and_routing_only(self):
        self.config({"root": "custom"})
        self.assertEqual(resolve_root(cwd=self.repo).path, "custom")
        self.config({"version": 1, "roles": {"worker": {"runtime": "codex"}}})
        self.assertEqual(resolve_root(cwd=self.repo).path, "docs/specadoc")
        self.assertEqual(resolve_role(self.repo, "worker", "claude")["model"], "executor")

    def test_schema_reference_is_allowed_but_other_unknown_keys_fail(self):
        self.config({"$schema": "./schema.json", "root": "custom"})
        self.assertEqual(load_config(self.repo)["root"], "custom")
        self.config({"root": "custom", "models": {}})
        with self.assertRaisesRegex(ValueError, "unknown: models"):
            load_config(self.repo)

    def test_missing_config_preserves_native_binding(self):
        route = resolve_role(self.repo, "worker", "claude")
        self.assertEqual((route["runtime"], route["model"], route["dispatch"]), ("claude", "host", "native"))

    def test_explicit_routing_does_not_read_unselected_host_registry(self):
        self.config({"version": 1, "roles": {"worker": {"runtime": "codex"}}})
        (self.repo / ".claude/agents/worker.md").write_text("unrelated invalid host role")
        self.assertEqual(resolve_role(self.repo, "worker", "claude")["model"], "executor")

    def test_config_overrides_legacy_wrapper_but_not_target_model(self):
        wrapper = self.role("claude", "worker", "cheap-wrapper", "low")
        wrapper.write_text(wrapper.read_text() + "\nDefault binding: runtime `codex`, model `legacy`, effort `high`.\n")
        self.assertEqual(resolve_role(self.repo, "worker", "claude")["model"], "legacy")
        self.config({"version": 1, "roles": {"worker": {"runtime": "codex"}}})
        route = resolve_role(self.repo, "worker", "claude")
        self.assertEqual((route["model"], route["effort"]), ("executor", "low"))
        self.assertEqual(route["sources"]["runtime"], ".specadoc.json")

    def test_approved_plan_wins_and_pending_plan_fails(self):
        self.config({"version": 1, "roles": {"worker": {"runtime": "claude"}}})
        plan = self.repo / "plan.md"
        text = "## Model handoff\n**Model checkpoint:** Approved by user\n**Worker runtime:** codex/approved-model\n**Worker effort:** high\n## Tasks\n"
        plan.write_text(text)
        route = resolve_role(self.repo, "worker", "claude", plan)
        self.assertEqual((route["model"], route["effort"]), ("approved-model", "high"))
        self.assertEqual(route, resolve_role(self.repo, "worker", "claude", Path("plan.md")))
        self.assertEqual(route["sources"]["model"], "plan.md")
        plan.write_text(text.replace("Approved by user", "Awaiting user confirmation"))
        with self.assertRaisesRegex(ValueError, "approved"):
            resolve_role(self.repo, "worker", "claude", plan)

    def test_missing_target_binding_and_controller_mismatch_fail(self):
        self.config({"version": 1, "roles": {"worker": {"runtime": "opencode"}}})
        with self.assertRaisesRegex(ValueError, "binding"):
            resolve_role(self.repo, "worker", "claude")
        self.config({"version": 1, "roles": {"controller": {"runtime": "claude"}}})
        with self.assertRaisesRegex(ValueError, "controller"):
            resolve_role(self.repo, "worker", "codex")

    def test_validation_is_strict(self):
        for value in ([], {"other": 1}, {"version": True}, {"version": 2},
                      {"roles": {}}, {"version": 1, "roles": {"verifier": {"runtime": "codex"}}},
                      {"version": 1, "roles": {"worker": {"runtime": "bad"}}},
                      {"version": 1, "roles": {"worker": {"runtime": "codex", "model": "x"}}}):
            with self.subTest(value=value):
                self.config(value)
                with self.assertRaises(ValueError):
                    load_config(self.repo)

    def test_approved_controller_override_does_not_launch_another_controller(self):
        self.config({"version": 1, "roles": {"controller": {"runtime": "claude"}}})
        plan = self.repo / "plan.md"
        plan.write_text("## Model handoff\n**Model checkpoint:** Approved by user\n**Controller runtime:** codex\n")
        route = resolve_role(self.repo, "worker", "codex", plan)
        self.assertEqual(route["dispatch"], "native")
        self.assertEqual(route["controller_source"], "plan.md")
        with self.assertRaisesRegex(ValueError, "controller"):
            resolve_role(self.repo, "worker", "claude", plan)

    def test_cli_presence_and_independence_are_separate_checks(self):
        for role in ("scout", "reviewer"):
            self.role("claude", role, "test", "high")
        report = inspect_routing(self.repo, "claude", which=lambda _: None)
        self.assertTrue(any(row["level"] == "ERROR" and "CLI" in row["message"] for row in report))
        self.assertTrue(any(row["level"] == "WARN" and "waiver" in row["message"] for row in report))
