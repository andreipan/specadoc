from __future__ import annotations

import json
import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import time
import threading
from argparse import Namespace
from unittest.mock import patch
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
    def test_status_and_result_cannot_overwrite_settled_usage(self):
        spec = importlib.util.spec_from_file_location('run_role_concurrent', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        run_file = self.runs / 'G1.reviewer.run.json'
        log = self.runs / 'G1.reviewer.log'
        exit_file = self.runs / 'G1.reviewer.exit'
        output = self.runs / 'G1.reviewer.result.json'
        log.write_text(json.dumps(dict(structured_output=dict(verdict='PASS', findings=[], report='Verified'),
                                       usage=dict(input_tokens=12345), padding='x' * 16000)))
        exit_file.write_text('0')
        run_file.write_text(json.dumps(dict(runtime='claude', role='reviewer', started=time.time()-10,
                                            pid=os.getpid(), log=str(log), exit=str(exit_file), result=str(output))))
        entered, release, settled = threading.Event(), threading.Event(), threading.Event()
        original = module._status
        errors = []
        def stalled_status(record, timeout=None):
            value = original(record, timeout)
            entered.set()
            release.wait(5)
            return value
        def call_status():
            try:
                module.status(Namespace(run_file=str(run_file), no_progress_timeout=None))
            except Exception as exc:
                errors.append(exc)
        def call_result():
            try:
                module.result(Namespace(run_file=str(run_file)))
                settled.set()
            except Exception as exc:
                errors.append(exc)
        with patch.object(module, '_status', side_effect=stalled_status), patch('builtins.print'):
            first = threading.Thread(target=call_status)
            second = threading.Thread(target=call_result)
            first.start()
            self.assertTrue(entered.wait(2))
            second.start()
            premature = settled.wait(0.1)
            release.set()
            first.join(5)
            second.join(5)
        self.assertFalse(premature, 'result must wait for status to release the shared record lock')
        self.assertFalse(errors, errors)
        record = json.loads(run_file.read_text())
        self.assertEqual(12345, record['usage']['input_tokens'])
        self.assertIn('settled', record)

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

    def run_cli(self, *args: str, result: dict | str = "", path: str | None = None) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PATH"] = path if path is not None else f"{self.bin}{os.pathsep}{env['PATH']}"
        env["FAKE_RESULT"] = result if isinstance(result, str) else json.dumps(result)
        env.setdefault("XDG_DATA_HOME", str(self.repo / "xdg"))
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

    def test_dry_run_preserves_results_and_creates_no_output_directory(self):
        result_path = self.runs / "T1.worker.result.json"
        result_path.write_text("previous result")
        args = ("start", "--role", "worker", "--runtime", "codex", "--model", "m1",
                "--prompt-file", str(self.brief), "--name", "T1", "--dry-run")
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result_path.read_text(), "previous result")
        target = self.repo / "not-created"
        result = self.run_cli(*args, "--out-dir", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())

    def routed_worker(self, model: str = "m1", effort: str = "low") -> Path:
        (self.repo / ".specadoc.json").write_text(json.dumps({"version": 1, "roles": {"worker": {"runtime": "codex"}}}))
        role = self.repo / ".codex/agents/worker.toml"
        role.parent.mkdir(parents=True, exist_ok=True)
        role.write_text(f'model = "{model}"\nmodel_reasoning_effort = "{effort}"\n')
        return role

    def launch(self, name: str, *extra: str, result: dict | str = "") -> dict:
        started = self.run_cli("start", "--role", "worker", "--controller-runtime", "claude", *extra,
                               "--prompt-file", str(self.brief), "--name", name, result=result)
        self.assertEqual(started.returncode, 0, started.stderr)
        run_file = started.stdout.strip()
        self.assertEqual(self.run_cli("wait", run_file, "--timeout", "20").returncode, 0)
        return json.loads(Path(run_file).read_text())

    def test_project_routing_uses_executor_model_and_follows_role_file_edits(self):
        role = self.routed_worker("executor", "low")
        args = ("start", "--role", "worker", "--controller-runtime", "claude",
                "--prompt-file", str(self.brief), "--name", "T1", "--dry-run")
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("executor", json.loads(result.stdout))
        role.write_text(role.read_text().replace("executor", "changed").replace("low", "high"))
        command = json.loads(self.run_cli(*args).stdout)
        self.assertIn("changed", command)
        self.assertIn('model_reasoning_effort="high"', command)

    def test_routing_requires_explicit_controller_for_launch(self):
        (self.repo / ".specadoc.json").write_text(json.dumps({"version": 1, "roles": {}}))
        result = self.run_cli("start", "--role", "worker", "--runtime", "codex", "--model", "m1",
                              "--prompt-file", str(self.brief), "--name", "T1", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("controller-runtime", result.stderr)
        self.routed_worker()
        result = self.run_cli("start", "--role", "worker", "--controller-runtime", "claude", "--model", "other",
                              "--prompt-file", str(self.brief), "--name", "T1", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicts with the resolved binding", result.stderr)

    def test_routed_launch_without_snapshot_records_binding_and_validates_result(self):
        self.routed_worker()
        payload = {"status": "DONE", "summary": "smoke", "files_changed": [],
                   "tests": {"red": "N/A", "green": "transport"}, "concerns": [], "report": "smoke.md"}
        started = self.run_cli("start", "--role", "worker", "--controller-runtime", "claude",
                               "--prompt-file", str(self.brief), "--name", "T1", result=payload)
        self.assertEqual(started.returncode, 0, started.stderr)
        run_file = started.stdout.strip()
        self.assertEqual(self.run_cli("wait", run_file, "--timeout", "20").returncode, 0)
        self.assertEqual(self.run_cli("result", run_file).returncode, 0)
        record = json.loads(Path(run_file).read_text())
        self.assertEqual((record["runtime"], record["model"], record["effort"]), ("codex", "m1", "low"))
        self.assertEqual(record["binding"]["dispatch"], "external")
        self.assertNotIn("fingerprint", record["binding"])

    def test_role_file_edit_between_starts_changes_the_second_run(self):
        role = self.routed_worker("m1", "medium")
        first = self.launch("T1")
        role.write_text('model = "m2"\nmodel_reasoning_effort = "high"\n')
        second = self.launch("T2")
        self.assertEqual((first["model"], first["effort"]), ("m1", "medium"))
        self.assertEqual((second["model"], second["effort"]), ("m2", "high"))
        self.assertEqual(second["binding"]["effort"], "high")

    def test_removed_options_are_usage_errors_and_explicit_flags_still_launch(self):
        base = ("start", "--role", "worker", "--prompt-file", str(self.brief), "--name", "T1")
        for option in ("--binding-file", "--plan"):
            result = self.run_cli(*base, "--controller-runtime", "claude", option, "x.json", "--dry-run")
            self.assertEqual(result.returncode, 2)
            self.assertIn(option, result.stderr)
        run_file = self.start({"status": "DONE"})
        self.assertIsNone(json.loads(Path(run_file).read_text())["binding"])

    def test_missing_routed_cli_names_runtime_and_role_without_fallback(self):
        (self.repo / ".specadoc.json").write_text(json.dumps({"version": 1, "roles": {"reviewer": {"runtime": "opencode"}}}))
        role = self.repo / ".opencode/agents/reviewer.md"
        role.parent.mkdir(parents=True)
        role.write_text("---\nmodel: openai/m\nvariant: low\n---\n")
        result = self.run_cli("start", "--role", "reviewer", "--controller-runtime", "codex",
                              "--prompt-file", str(self.brief), "--name", "G1", path=str(self.bin))
        self.assertEqual(result.returncode, 2)
        self.assertIn("opencode", result.stderr)
        self.assertIn("reviewer", result.stderr)
        self.assertFalse((self.runs / "G1.reviewer.run.json").exists())

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
        with self.assertRaises(ValueError):
            runner._final_json(record)

    def test_final_message_may_be_fenced_or_surrounded_by_prose(self) -> None:
        spec = importlib.util.spec_from_file_location("run_role", SCRIPT)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        payload = {"status": "DONE", "summary": "braces { } inside", "files_changed": []}
        text = json.dumps(payload)
        self.assertEqual(runner._parse_json_text(text), payload)
        self.assertEqual(runner._parse_json_text(f"```json\n{text}\n```"), payload)
        self.assertEqual(runner._parse_json_text(f"Done.\n{text}\nThanks"), payload)
        self.assertEqual(runner._parse_json_text('{"a": 1}\n' + text), payload)  # last object wins
        with self.assertRaises(ValueError):
            runner._parse_json_text("no object here")
        log = self.repo / "fenced.log"
        record = {"runtime": "opencode", "log": str(log), "result": str(self.repo / "missing.json")}
        log.write_text(json.dumps({"type": "text", "part": {"messageID": "m", "text": f"```json\n{text}\n```"}}))
        self.assertEqual(runner._final_json(record), payload)

    def test_wait_follow_prints_opencode_progress(self) -> None:
        sleeper = subprocess.Popen(["sleep", "5"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait()))
        log = self.runs / "T1.worker.log"
        events = [{"type": "tool_use", "part": {"tool": "read"}}, {"type": "step_finish"},
                  {"type": "tool_use", "part": {"tool": "shell"}}]
        log.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        record = self.runs / "T1.worker.run.json"
        record.write_text(json.dumps({
            "role": "worker", "runtime": "opencode", "pid": sleeper.pid, "started": 0,
            "exit": str(self.runs / "T1.worker.exit"), "log": str(log), "result": str(self.runs / "T1.worker.result.json"),
        }))
        waited = self.run_cli("wait", str(record), "--timeout", "2", "--follow", "--interval", "0.5")
        self.assertEqual(waited.returncode, 3, waited.stdout + waited.stderr)
        self.assertIn("2 tool calls, last: shell", waited.stdout)
        plain = self.run_cli("wait", str(record), "--timeout", "1")
        self.assertEqual(plain.returncode, 3)
        self.assertIn("call wait again", plain.stdout)

    def test_opencode_start_explains_unwritable_log(self) -> None:
        fake = self.bin / "opencode"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        data = self.repo / "readonly"
        (data / "opencode" / "log").mkdir(parents=True)
        (data / "opencode" / "log").chmod(0o500)
        os.environ["XDG_DATA_HOME"] = str(data)
        try:
            result = self.run_cli("start", "--role", "worker", "--runtime", "opencode", "--model", "openai/m",
                                  "--prompt-file", str(self.brief), "--name", "T1")
        finally:
            os.environ.pop("XDG_DATA_HOME")
            (data / "opencode" / "log").chmod(0o700)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot write its log", result.stderr)
        self.assertFalse((self.runs / "T1.worker.run.json").exists())

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

    def test_prompt_is_not_copied_and_runs_is_git_ignored(self) -> None:
        self.start({"status": "COMPLETE"})
        self.assertEqual([], sorted(path.name for path in self.runs.glob("*.prompt.md")))
        self.assertEqual("*\n", (self.runs / ".gitignore").read_text(encoding="utf-8"))

    def noisy_codex(self) -> None:
        """A codex that streams two usage events and a large log before writing its result."""
        fake = self.bin / "codex"
        fake.write_text(FAKE_CODEX.replace("cat > prompt.seen\n", "cat > prompt.seen\n" + "\n".join([
            """echo '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":7}}'""",
            "i=0; while [ $i -lt 400 ]; do echo '{\"type\":\"item.completed\",\"item\":\"" + "x" * 80 + "\"}'; i=$((i+1)); done",
            """echo '{"type":"turn.completed","usage":{"input_tokens":20,"cached_input_tokens":0,"output_tokens":3}}'""",
        ]) + "\n"), encoding="utf-8")

    def test_successful_result_moves_usage_to_run_file_and_cuts_the_log(self) -> None:
        self.noisy_codex()
        payload = {"status": "DONE", "summary": "ok", "files_changed": [],
                   "tests": {"red": "fails", "green": "passes"}, "concerns": [], "report": "runs/T1-report.md"}
        run_file = self.start(payload)
        log = self.runs / "T1.worker.log"
        full = log.stat().st_size
        self.assertEqual(0, self.run_cli("result", run_file).returncode)
        record = json.loads(Path(run_file).read_text(encoding="utf-8"))
        self.assertEqual({"input_tokens": 120, "cached_input_tokens": 40, "output_tokens": 10}, record["usage"])
        self.assertEqual(full, record["log_bytes"])
        self.assertLess(log.stat().st_size, 8192 + 200)
        self.assertTrue(log.read_text(encoding="utf-8").startswith("[specadoc: log cut"))
        again = self.run_cli("result", run_file)
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual(payload, json.loads(again.stdout)["result"])

    def test_failed_result_keeps_the_full_log(self) -> None:
        self.noisy_codex()
        run_file = self.start({"status": "COMPLETE"})
        log = self.runs / "T1.worker.log"
        full = log.stat().st_size
        self.assertEqual(1, self.run_cli("result", run_file).returncode)
        self.assertEqual(full, log.stat().st_size)
        self.assertNotIn("usage", json.loads(Path(run_file).read_text(encoding="utf-8")))

    def test_result_rejects_output_that_breaks_the_schema(self) -> None:
        run_file = self.start({"status": "COMPLETE"})

        result = self.run_cli("result", run_file)

        self.assertEqual(result.returncode, 1)
        errors = json.loads(result.stdout)["schema_errors"]
        self.assertTrue(any("status" in error for error in errors), errors)
        self.assertTrue(any("files_changed: missing" in error for error in errors), errors)

    def dispatch(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli("start", "--role", "worker", "--runtime", "codex", "--model", "m1",
                            "--effort", "low", "--prompt-file", str(self.brief), "--name", "T1", *extra)

    def test_repeated_completed_dispatch_preserves_record_and_artifacts(self):
        run_file = self.start({"status": "DONE"})
        paths = [Path(run_file), self.runs / "T1.worker.exit", self.runs / "T1.worker.result.json"]
        before = [path.read_bytes() for path in paths]
        repeated = self.dispatch()
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(repeated.stdout.strip(), run_file)
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertIn("completed", repeated.stderr)
        record = json.loads(paths[0].read_text())
        self.assertEqual(len(record["prompt_sha256"]), 64)
        self.assertEqual(record["invocation"]["cwd"], str(self.repo.resolve()))

    def test_repeated_active_dispatch_does_not_launch_another_process(self):
        fake = self.bin / "codex"
        fake.write_text(FAKE_CODEX.replace("cat > prompt.seen", "cat > prompt.seen\n"
                        "echo launch >> launches\n"
                        "i=0; while [ ! -f release ] && [ $i -lt 100 ]; do sleep 0.05; i=$((i+1)); done"))
        first = self.dispatch()
        self.assertEqual(first.returncode, 0, first.stderr)
        run_file = Path(first.stdout.strip())
        before = run_file.read_bytes()
        try:
            repeated = self.dispatch()
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(run_file.read_bytes(), before)
            self.assertIn("running", repeated.stderr)
        finally:
            (self.repo / "release").touch()
            self.run_cli("wait", str(run_file), "--timeout", "10")
        self.assertEqual((self.repo / "launches").read_text(), "launch\n")

    def test_conflicting_binding_or_cwd_and_orphan_artifacts_are_preserved(self):
        run_file = self.start({"status": "DONE"})
        before = Path(run_file).read_bytes()
        other = self.repo / "other"
        other.mkdir()
        for extra in (("--model", "different"), ("--effort", "high"),
                      ("--cwd", str(other), "--out-dir", str(self.runs))):
            with self.subTest(extra=extra):
                refused = self.dispatch(*extra)
                self.assertEqual(refused.returncode, 2)
                self.assertIn("new --name", refused.stderr)
                self.assertEqual(Path(run_file).read_bytes(), before)
        Path(run_file).unlink()  # Simulate an old interrupted launch with orphan artifacts.
        result_path = self.runs / "T1.worker.result.json"
        saved = result_path.read_bytes()
        refused = self.dispatch()
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(result_path.read_bytes(), saved)

    def test_conflicting_dispatch_and_legacy_record_refuse_without_erasing(self):
        run_file = self.start({"status": "DONE"})
        before = Path(run_file).read_bytes()
        self.brief.write_text("different prompt")
        refused = self.dispatch()
        self.assertEqual(refused.returncode, 2)
        self.assertIn("new --name", refused.stderr)
        self.assertEqual(Path(run_file).read_bytes(), before)
        self.brief.write_text("do the task\n")
        record = json.loads(before)
        record.pop("prompt_sha256", None)
        record.pop("invocation", None)
        Path(run_file).write_text(json.dumps(record))
        refused = self.dispatch()
        self.assertEqual(refused.returncode, 2)
        self.assertIn("new --name", refused.stderr)
        self.assertTrue(Path(record["exit"]).exists())
        legacy_status = self.run_cli("status", run_file)
        self.assertEqual(legacy_status.returncode, 0, legacy_status.stderr)
        self.assertEqual(json.loads(legacy_status.stdout)["status"], "completed")

    def live_record(self, runtime="codex", text=""):
        log = self.runs / "live.log"
        log.write_text(text)
        old = time.time() - 100
        os.utime(log, (old, old))
        record = self.runs / "live.run.json"
        record.write_text(json.dumps({"role": "worker", "runtime": runtime, "pid": os.getpid(),
                                     "started": old, "exit": str(self.runs / "live.exit"),
                                     "log": str(log), "result": str(self.runs / "live.result.json")}))
        return record

    def test_status_distinguishes_no_progress_from_buffered_claude_and_transport_error(self):
        for runtime, text, expected, observable in (
                ("codex", "", "no-progress", True), ("claude", "", "running", False),
                ("claude", '{"type":"result","is_error":true,"result":"API error: connection reset"}', "failed", False)):
            with self.subTest(runtime=runtime, expected=expected):
                record = self.live_record(runtime, text)
                checked = self.run_cli("status", str(record), "--no-progress-timeout", "10")
                self.assertEqual(checked.returncode, 0, checked.stderr)
                state = json.loads(checked.stdout)
                self.assertEqual(state["status"], expected)
                self.assertEqual(state["progress"]["observable"], observable)
                self.assertGreaterEqual(state["elapsed_seconds"], 99)
                self.assertFalse(state["retry"]["safe"])
                if expected == "failed":
                    self.assertIn("connection reset", state["transport_error"])

    def test_wait_shell_budget_and_timeout_are_not_role_status(self):
        record = self.live_record("claude")
        before = time.monotonic()
        waited = self.run_cli("wait", str(record), "--timeout", "30", "--shell-budget", "0.3")
        self.assertEqual(waited.returncode, 3, waited.stderr)
        self.assertLess(time.monotonic() - before, 2)
        self.assertIn("wait timed out", waited.stdout)
        checked = json.loads(self.run_cli("status", str(record)).stdout)
        self.assertEqual(checked["status"], "running")
        spec = importlib.util.spec_from_file_location("run_role_defaults", SCRIPT)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        self.assertLessEqual(runner.build_parser().parse_args(["wait", str(record)]).timeout, 120)

    def test_no_progress_wait_is_non_destructive_and_can_be_disabled(self):
        record = self.live_record()
        before = time.monotonic()
        waited = self.run_cli("wait", str(record), "--timeout", "10", "--no-progress-timeout", "1")
        self.assertLess(time.monotonic() - before, 2)
        self.assertEqual(waited.returncode, 3, waited.stderr)
        self.assertIn("no-progress", waited.stdout)
        self.assertIn("not stopped", waited.stdout)
        checked = json.loads(self.run_cli("status", str(record), "--no-progress-timeout", "0").stdout)
        self.assertEqual(checked["status"], "running")
        self.assertTrue(checked["alive"])

    def test_status_does_not_confuse_role_or_tool_output_with_transport_failure(self):
        record = self.live_record("codex", json.dumps({"type": "item.completed", "item": {
            "text": "test reproduced connection refused; role reports API error: handled"}}))
        checked = json.loads(self.run_cli("status", str(record)).stdout)
        self.assertEqual(checked["status"], "running")
        self.assertIsNone(checked["transport_error"])
        (self.runs / "live.result.json").write_text('{"status":"BLOCKED"}')
        (self.runs / "live.exit").write_text("0\n")
        checked = json.loads(self.run_cli("status", str(record)).stdout)
        self.assertEqual(checked["status"], "completed")
        self.assertEqual(checked["role_status"], "BLOCKED")

    def test_transient_reconnect_error_is_not_failure(self):
        reconnect = "\n".join(json.dumps(event) for event in (
            {"type": "thread.started"},
            {"type": "error", "message": "Reconnecting... 1/5 (stream disconnected before completion)"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "{}"}}))
        record = self.live_record("codex", reconnect)
        checked = json.loads(self.run_cli("status", str(record), "--no-progress-timeout", "0").stdout)
        self.assertEqual(checked["status"], "running")
        self.assertIsNone(checked["transport_error"])
        self.assertTrue(checked["warnings"])
        (self.runs / "live.result.json").write_text('{"status":"DONE"}')
        (self.runs / "live.exit").write_text("0\n")
        checked = json.loads(self.run_cli("status", str(record)).stdout)
        self.assertEqual(checked["status"], "completed")
        self.assertFalse(checked["retry"]["safe"])

    def test_live_retrying_process_is_running_whatever_its_last_line(self):
        for text in ("ERROR: stream error: 429 Too Many Requests; will try again",
                     json.dumps({"type": "error", "message": "overloaded"}),
                     '{"type":"error","message":"overloaded"}'):
            with self.subTest(text=text):
                record = self.live_record("codex", text)
                checked = json.loads(self.run_cli("status", str(record), "--no-progress-timeout", "0").stdout)
                self.assertEqual(checked["status"], "running")
                self.assertTrue(checked["warnings"])

    def test_error_followed_by_progress_is_a_warning_not_failure(self):
        text = "\n".join(json.dumps(event) for event in (
            {"type": "error", "message": "rate limited"}, {"type": "turn.started"}))
        record = self.live_record("codex", text)
        (self.runs / "live.exit").write_text("0\n")
        checked = json.loads(self.run_cli("status", str(record)).stdout)
        self.assertEqual(checked["status"], "completed")
        self.assertIn("rate limited", checked["warnings"][0])

    def test_wait_reports_terminal_failure_of_live_process_as_failure(self):
        record = self.live_record("claude", '{"type":"result","is_error":true,"result":"API error: connection reset"}')
        waited = self.run_cli("wait", str(record), "--timeout", "5")
        self.assertEqual(waited.returncode, 1, waited.stdout)
        self.assertIn("failed", waited.stdout)

    def test_failed_transport_status_and_invalid_timeout_options(self):
        record = self.live_record()
        (self.runs / "live.exit").write_text("7\n")
        checked = json.loads(self.run_cli("status", str(record)).stdout)
        self.assertEqual(checked["status"], "failed")
        self.assertEqual(checked["exit"], 7)
        self.assertTrue(checked["retry"]["safe"])
        for flag, value in (("--timeout", "nan"), ("--shell-budget", "0"),
                            ("--no-progress-timeout", "-1")):
            result = self.run_cli("wait", str(record), flag, value)
            self.assertEqual(result.returncode, 2)

    def test_status_completion_and_settlement_metrics_are_idempotent(self):
        payload = {"status": "DONE", "summary": "ok", "files_changed": [],
                   "tests": {"red": "fails", "green": "passes"}, "concerns": [], "report": "report.md"}
        self.noisy_codex()
        run_file = self.start(payload)
        state = json.loads(self.run_cli("status", run_file).stdout)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["role_status"], "DONE")
        self.assertEqual(self.run_cli("result", run_file).returncode, 0)
        first = json.loads(Path(run_file).read_text())
        self.assertGreaterEqual(first["completed"], first["started"])
        self.assertGreaterEqual(first["elapsed_seconds"], 0)
        self.assertEqual(self.run_cli("result", run_file).returncode, 0)
        self.assertEqual(json.loads(Path(run_file).read_text()), first)


if __name__ == "__main__":
    unittest.main()
