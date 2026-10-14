from __future__ import annotations

import json
import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "skills" / "specadoc" / "scripts" / "run_role.py"

FAKE_CODEX = """#!/bin/sh
# Fake codex: copy stdin to prompt.seen, write the -o result, exit 0.
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; fi
  shift
done
cat > prompt.seen
printf '%s' "$FAKE_RESULT" > "$out"
"""


class RunRoleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.bin = self.repo / "bin"
        self.bin.mkdir()
        fake = self.bin / "codex"
        fake.write_text(FAKE_CODEX, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.runs = self.repo / "docs" / "specadoc" / "demo" / "runs"
        self.runs.mkdir(parents=True)
        self.brief = self.runs / "T1-brief.md"
        self.brief.write_text("do the task\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, result: dict | str = "") -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        env["FAKE_RESULT"] = result if isinstance(result, str) else json.dumps(result)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True, env=env
        )

    def start(self, result: dict | str, role: str = "worker") -> str:
        started = self.run_cli(
            "start", "--role", role, "--runtime", "codex", "--model", "m1", "--effort", "low",
            "--prompt-file", str(self.brief), "--name", "T1", result=result,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        run_file = started.stdout.strip()
        waited = self.run_cli("wait", run_file, "--timeout", "20")
        self.assertEqual(waited.returncode, 0, waited.stdout + waited.stderr)
        return run_file

    def test_codex_worker_command_is_writable_and_networked(self) -> None:
        result = self.run_cli(
            "start", "--role", "worker", "--runtime", "codex", "--model", "m1", "--effort", "low",
            "--prompt-file", str(self.brief), "--name", "T1", "--dry-run",
        )
        command = json.loads(result.stdout)
        self.assertEqual(command[:2], ["codex", "exec"])
        self.assertIn("workspace-write", command)
        self.assertIn("sandbox_workspace_write.network_access=true", command)
        self.assertIn('model_reasoning_effort="low"', command)
        self.assertEqual(command[-1], "-")

    def test_codex_reviewer_and_claude_commands_are_read_only(self) -> None:
        codex = json.loads(self.run_cli(
            "start", "--role", "reviewer", "--runtime", "codex", "--model", "m1",
            "--prompt-file", str(self.brief), "--name", "G1", "--dry-run",
        ).stdout)
        claude = json.loads(self.run_cli(
            "start", "--role", "reviewer", "--runtime", "claude", "--model", "m2", "--effort", "high",
            "--prompt-file", str(self.brief), "--name", "G1", "--dry-run",
        ).stdout)
        self.assertIn("read-only", codex)
        self.assertNotIn("sandbox_workspace_write.network_access=true", codex)
        self.assertEqual(claude[:2], ["claude", "-p"])
        self.assertEqual(claude[claude.index("--tools") + 1], "Read,Grep,Glob,Bash")
        self.assertEqual(claude[claude.index("--permission-mode") + 1], "dontAsk")

    def test_opencode_command_selects_primary_agent_and_variant(self) -> None:
        result = self.run_cli(
            "start", "--role", "worker", "--runtime", "opencode", "--model", "openai/m", "--effort", "low",
            "--prompt-file", str(self.brief), "--name", "T1", "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = json.loads(result.stdout)
        self.assertEqual(command[:2], ["opencode", "run"])
        self.assertIn("openai/m#low", command)
        self.assertIn("specadoc-external", command)
        self.assertIn("--standalone", command)

    def test_opencode_full_run_permissions_and_result(self) -> None:
        fake = self.bin / "opencode"
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
open("prompt.seen", "w").write(sys.stdin.read())
open("config.seen", "w").write(os.environ["OPENCODE_CONFIG_CONTENT"])
print("diagnostic")
print(json.dumps({"type":"reasoning", "part":{"text":"not the result"}}))
print(json.dumps({"type":"text", "part":{"messageID":"first", "text":"working"}}))
print(json.dumps({"type":"text", "part":{"messageID":"last", "text":os.environ["FAKE_RESULT"]}}))
''')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        payload = {"status": "DONE", "summary": "ok", "files_changed": [],
                   "tests": {"red": "fails", "green": "passes"}, "concerns": [], "report": "runs/report.md"}
        for role in ("worker", "reviewer"):
            started = self.run_cli("start", "--role", role, "--runtime", "opencode", "--model", "openai/m",
                                   "--prompt-file", str(self.brief), "--name", role, result=payload)
            self.assertEqual(started.returncode, 0, started.stderr)
            run_file = started.stdout.strip()
            self.assertEqual(self.run_cli("wait", run_file, "--timeout", "20").returncode, 0)
            rules = json.loads((self.repo / "config.seen").read_text())["agents"]["specadoc-external"]["permissions"]
            allowed = {r["action"] for r in rules if r["effect"] == "allow" and r["resource"] == "*"}
            self.assertEqual("shell" in allowed, role == "worker")
            self.assertEqual("edit" in allowed, role == "worker")
            shell = [(r["resource"], r["effect"]) for r in rules if r["action"] == "shell"]
            if role == "reviewer":
                self.assertIn(("git diff *", "allow"), shell)
                self.assertEqual(shell[-1], ("*--ext-diff*", "deny"))  # write guards come last
            self.assertNotIn("subagent", allowed)
            self.assertIn("JSON object matching this schema", (self.repo / "prompt.seen").read_text())
            output = self.run_cli("result", run_file)
            self.assertEqual(output.returncode, 0 if role == "worker" else 1)
            self.assertEqual(json.loads(output.stdout)["result"], payload)

    def test_opencode_rejects_conflicting_variant(self) -> None:
        output = self.run_cli("start", "--role", "worker", "--runtime", "opencode", "--model", "openai/m#high",
                              "--effort", "low", "--prompt-file", str(self.brief), "--name", "T1", "--dry-run")
        self.assertEqual(output.returncode, 2)
        self.assertIn("conflicts", output.stderr)

    def test_opencode_result_rejects_errors_and_ignores_tool_json(self) -> None:
        spec = importlib.util.spec_from_file_location("run_role", SCRIPT)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        log = self.repo / "events.log"
        record = {"runtime": "opencode", "log": str(log), "result": str(self.repo / "missing.json")}
        log.write_text(json.dumps({"type": "tool_use", "part": {"text": '{"status":"DONE"}'}}))
        with self.assertRaises(runner.RunError):
            runner._final_json(record)
        log.write_text(json.dumps({"type": "text", "part": {"text": "{}"}}) + "\n" +
                       json.dumps({"type": "error", "error": "provider failed"}))
        with self.assertRaises(runner.RunError):
            runner._final_json(record)
        log.write_text(json.dumps({"type": "text", "part": {"text": "not JSON"}}))
        with self.assertRaises(json.JSONDecodeError):
            runner._final_json(record)

    def test_full_run_passes_prompt_and_validates_result(self) -> None:
        payload = {
            "status": "DONE", "summary": "ok", "files_changed": ["src/A.php"],
            "tests": {"red": "fails", "green": "passes"}, "concerns": [], "report": "runs/T1-report.md",
        }
        run_file = self.start(payload)

        result = self.run_cli("result", run_file)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"]["status"], "DONE")
        self.assertEqual((self.repo / "prompt.seen").read_text(encoding="utf-8"), "do the task\n")

    def test_result_rejects_output_that_breaks_the_schema(self) -> None:
        run_file = self.start({"status": "COMPLETE"})

        result = self.run_cli("result", run_file)

        self.assertEqual(result.returncode, 1)
        errors = json.loads(result.stdout)["schema_errors"]
        self.assertTrue(any("status" in error for error in errors), errors)
        self.assertTrue(any("files_changed: missing" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
