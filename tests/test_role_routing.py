from __future__ import annotations

import json
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "skills/specadoc/scripts"))

import role_routing
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

    def cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["role_routing", "--cwd", str(self.repo),
                                        "--controller-runtime", "claude", *args]), contextlib.redirect_stdout(output):
            code = role_routing.main()
        return code, json.loads(output.getvalue())

    def test_compact_cli_checks_only_selected_role_once(self):
        with patch.object(role_routing, "resolve_role", wraps=resolve_role) as resolve, \
                patch.object(role_routing.shutil, "which", return_value="/bin/claude"):
            code, data = self.cli("--role", "worker", "--check-cli", "--compact")
        self.assertEqual(code, 0)
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(data["routes"][0]["model"], "host")
        self.assertNotIn("config", data["routes"][0])
        self.assertIn("fingerprint", data["routes"][0])

    def test_binding_check_is_fresh_and_shared_by_native_and_external_dispatch(self):
        binding = self.repo / "bindings.json"
        route = resolve_role(self.repo, "worker", "claude")
        binding.write_text(json.dumps({"routes": [route]}))
        code, _ = self.cli("--role", "worker", "--binding-file", str(binding), "--compact")
        self.assertEqual(code, 0)
        self.role("claude", "worker", "changed", "medium")
        with self.assertRaisesRegex(ValueError, "approved binding changed"):
            role_routing.approved_role(self.repo, "worker", "claude", binding)

    def test_compact_output_keeps_fingerprint_for_revalidation(self):
        _, data = self.cli("--role", "worker", "--compact")
        binding = self.repo / "bindings.json"
        binding.write_text(json.dumps(data))
        self.assertEqual(role_routing.approved_role(self.repo, "worker", "claude", binding)["model"], "host")

    def test_codex_registry_with_unsupported_python_fails_explicitly(self):
        with patch.object(role_routing, "tomllib", None):
            with self.assertRaisesRegex(ValueError, "Python 3.11"):
                resolve_role(self.repo, "worker", "codex")

    def test_approval_rejects_effort_config_and_malformed_snapshots(self):
        route = resolve_role(self.repo, "worker", "claude")
        binding = self.repo / "bindings.json"
        for value in ([], {"routes": None}, {"routes": [None]}, {"routes": []},
                      {"routes": [route, route]}):
            with self.subTest(snapshot=value):
                binding.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    role_routing.approved_role(self.repo, "worker", "claude", binding)
        binding.write_text(json.dumps({"routes": [route]}))
        self.role("claude", "worker", "host", "high")
        with self.assertRaisesRegex(ValueError, "binding changed"):
            role_routing.approved_role(self.repo, "worker", "claude", binding)
        self.role("claude", "worker", "host", "medium")
        self.config({"version": 1, "roles": {"worker": {"runtime": "codex"}}})
        with self.assertRaisesRegex(ValueError, "binding changed"):
            role_routing.approved_role(self.repo, "worker", "claude", binding)

    def test_all_role_cli_checks_do_not_resolve_twice_and_missing_cli_fails(self):
        for role in ("scout", "reviewer"):
            self.role("claude", role, "test", "high")
        with patch.object(role_routing, "resolve_role", wraps=resolve_role) as resolve, \
                patch.object(role_routing.shutil, "which", return_value=None):
            code, data = self.cli("--check-cli", "--compact")
        self.assertEqual(resolve.call_count, 3)
        self.assertEqual(code, 1)
        self.assertEqual(sum(row["level"] == "ERROR" for row in data["findings"]), 3)
