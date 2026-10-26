from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "skills" / "specadoc" / "scripts" / "collect_tokens.py"


def load_module():
    spec = importlib.util.spec_from_file_location("collect_tokens", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CollectTokensTest(unittest.TestCase):
    def write_jsonl(self, path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(record) + "\n" for record in records))

    def claude_record(self, output=3):
        return {"type": "assistant", "requestId": "request", "message": {
            "usage": {"input_tokens": 2, "output_tokens": output,
                      "cache_read_input_tokens": 10}}}

    def test_claude_duplicate_sources_and_child_keep_attribution(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "controller-full-id.jsonl"
            child = root.with_suffix("") / "subagents" / "agent-full-child-id.jsonl"
            self.write_jsonl(root, [self.claude_record()])
            self.write_jsonl(child, [self.claude_record()])
            child.with_suffix(".meta.json").write_text('{"agentType": "reviewer"}')
            alias = Path(directory) / "alias.jsonl"
            alias.symlink_to(child)
            executions = collect.collect_claude([alias, child, root, root, Path(directory)])
            self.assertEqual(len(executions), 2)
            agent = next(item for item in executions if item.role == "reviewer")
            self.assertEqual(agent.execution_id, "full-child-id")
            self.assertEqual(agent.parent, "controller-full-id")

    def test_claude_without_paths_uses_newest_project_transcript_once(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "work" / "proj.x"
            project.mkdir(parents=True)
            sessions = Path(directory) / "home" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project.resolve()))
            old, new = sessions / "old.jsonl", sessions / "new.jsonl"
            self.write_jsonl(old, [self.claude_record(100)])
            self.write_jsonl(new, [self.claude_record()])
            self.write_jsonl(new.with_suffix("") / "subagents" / "agent-child.jsonl", [self.claude_record()])
            os.utime(old, (1, 1))
            argv = ["collect_tokens", "change", "--harness", "claude", "--mode", "apply", "--project", str(project)]
            with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(Path(directory) / "home")}), \
                    patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(collect.main(), 0)
            self.assertIn("new.jsonl", errors.getvalue())
            self.assertIn("claude 2 run(s)", output.getvalue())

    def test_claude_streaming_uses_max_usage_per_request(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            self.write_jsonl(path, [self.claude_record(1), self.claude_record(9),
                                   self.claude_record(3)])
            execution, = collect.collect_claude([path])
            self.assertEqual((execution.uncached_input, execution.output,
                              execution.cached_input, execution.requests), (2, 9, 10, 1))

    def make_db(self, path, tables):
        with contextlib.closing(sqlite3.connect(path)) as connection, connection:
            for table, rows in tables.items():
                connection.execute(f"CREATE TABLE {table} (id TEXT, parent_id TEXT, "
                                   "agent TEXT, directory TEXT, tokens_input INTEGER, "
                                   "tokens_output INTEGER, tokens_reasoning INTEGER, "
                                   "tokens_cache_read INTEGER, tokens_cache_write INTEGER, "
                                   "cost REAL, time_created INTEGER)")
                connection.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)

    def db_row(self, ident, parent=None, value=5):
        return (ident, parent, None, "/project", value, 3, 1, 100, 2, .1, 1)

    def test_opencode_v2_authoritative_full_ids_and_root_filter(self):
        collect = load_module()
        root = "ses_sameprefix_root"
        child = "ses_sameprefix_child"
        resumed = "ses_resumed_root"
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "db"
            self.make_db(db, {"session": [self.db_row(root, value=999)],
                                "session_v2": [self.db_row(root), self.db_row(child, root),
                                               self.db_row("unrelated"), self.db_row(resumed)]})
            rows = collect.collect_opencode("/project", db, [root, resumed])
            self.assertEqual({item.execution_id for item in rows}, {root, child, resumed})
            self.assertEqual(next(item for item in rows if item.execution_id == child).parent, root)
            self.assertEqual(sum(item.uncached_input for item in rows), 15)
            self.assertEqual(sum(item.cached_input for item in rows), 300)

    def test_opencode_legacy_and_v2_only(self):
        collect = load_module()
        for table in ("session", "session_v2"):
            with self.subTest(table=table), tempfile.TemporaryDirectory() as directory:
                db = Path(directory) / "db"
                self.make_db(db, {table: [self.db_row("root")]})
                with contextlib.redirect_stderr(io.StringIO()):
                    rows = collect.collect_opencode("/project", db)
                self.assertEqual(rows[0].unique, 10)

    def test_opencode_unknown_root_is_not_silent(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "db"
            self.make_db(db, {"session_v2": [self.db_row("root")]})
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(collect.collect_opencode("/project", db, ["missing"]), [])
            self.assertIn("missing", errors.getvalue())

    def test_opencode_legacy_copy_cannot_override_v2_directory_or_zero_usage(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "db"
            moved = list(self.db_row("moved"))
            moved[3] = "/elsewhere"
            self.make_db(db, {"session": [self.db_row("moved"), self.db_row("zero", value=999)],
                                "session_v2": [moved, self.db_row("zero", value=0)]})
            with contextlib.redirect_stderr(io.StringIO()):
                rows = collect.collect_opencode("/project", db)
            self.assertEqual([item.execution_id for item in rows], ["zero"])
            self.assertEqual(rows[0].uncached_input, 0)

    def test_codex_final_snapshots_dedup_sources_and_resumed_runs(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"run-{number}.jsonl" for number in range(2)]
            for path in paths:
                self.write_jsonl(path, [
                    {"type": "session_meta", "payload": {"session_id": "resumed", "cwd": "/project"}},
                    *[{"payload": {"info": {"total_token_usage": {
                        "input_tokens": value, "cached_input_tokens": 5, "output_tokens": 2}}}}
                      for value in (10, 20)],
                ])
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                rows = collect.collect_codex([*paths, paths[0], Path(directory)])
            self.assertEqual(len(rows), 2)
            self.assertEqual(len({item.execution_id for item in rows}), 2)
            self.assertEqual(sum(item.unique for item in rows), 34)
            self.assertIn("resumed", errors.getvalue())

    def external_record(self, directory, runtime, usage):
        path = Path(directory) / f"{runtime}.run.json"
        exit_path = path.with_suffix(".exit")
        result = path.with_suffix(".result.json")
        exit_path.write_text("0\n")
        result.write_text("{}")
        record = {"runtime": runtime, "role": "reviewer", "cwd": "/project",
                  "started": 123, "pid": 42, "exit": str(exit_path),
                  "result": str(result), "usage": usage}
        path.write_text(json.dumps(record))
        return path

    def test_external_runs_runtime_cache_semantics_and_dedup(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            codex = self.external_record(directory, "codex", {
                "input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 5})
            claude = self.external_record(directory, "claude", {
                "input_tokens": 20, "cache_read_input_tokens": 80,
                "cache_creation_input_tokens": 2, "output_tokens": 5,
                "output_tokens_details.thinking_tokens": 4})
            opencode = self.external_record(directory, "opencode", {
                "input": 20, "cache.read": 80, "cache.write": 2,
                "output": 5, "reasoning": 3})
            copy = Path(directory) / "copy.run.json"
            copy.write_text(codex.read_text())
            rows = collect.collect_external_runs([codex, codex, copy, claude, opencode])
            self.assertEqual(len(rows), 3)
            self.assertEqual([item.uncached_input for item in rows], [20, 20, 20])
            self.assertEqual([item.cached_input for item in rows], [80, 80, 80])
            self.assertEqual([item.unique for item in rows], [25, 27, 27])
            self.assertEqual([item.reasoning for item in rows], [0, 4, 3])
            self.assertTrue(all(item.role == "reviewer" for item in rows))
            self.assertTrue(all(item.parent != "-" for item in rows), 'external roles are not controllers')
            self.assertTrue(all(str(Path(directory)) in item.execution_id for item in rows))

    def test_external_missing_usage_or_unfinished_warns(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = self.external_record(directory, "codex", {})
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(collect.collect_external_runs([path]), [])
            self.assertIn("usage", errors.getvalue())
            path = self.external_record(directory, "codex", {"input_tokens": 1})
            path.with_suffix(".exit").unlink()
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(collect.collect_external_runs([path]), [])
            self.assertIn("warning", errors.getvalue())

    def test_external_missing_failed_or_malformed_evidence_warns(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            for failure in ("missing", "invalid_json", "failed", "missing_result", "bad_usage"):
                with self.subTest(failure=failure):
                    path = self.external_record(directory, "opencode", {"input": 20, "cache.read": 80})
                    if failure == "missing":
                        path.unlink()
                    elif failure == "invalid_json":
                        path.write_text("{")
                    elif failure == "failed":
                        path.with_suffix(".exit").write_text("1")
                    elif failure == "missing_result":
                        path.with_suffix(".result.json").unlink()
                    else:
                        record = json.loads(path.read_text())
                        record["usage"]["cache.read"] = "unknown"
                        path.write_text(json.dumps(record))
                    with contextlib.redirect_stderr(io.StringIO()) as errors:
                        self.assertEqual(collect.collect_external_runs([path]), [])
                    self.assertIn("warning", errors.getvalue())

    def test_cli_external_only_has_timestamp_and_status(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = self.external_record(directory, "codex", {"input_tokens": 10})
            argv = ["collect_tokens", "change", "--harness", "claude", "--mode", "apply",
                    "--external-run", str(path), "--final", "--project", "/project"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(collect.main(), 0)
            self.assertIn("collected_at=", output.getvalue())
            self.assertIn("status=final", output.getvalue())
            self.assertIn("total mode=apply claude", output.getvalue())
            self.assertIn("controller=0%", output.getvalue())

    def test_final_collection_refuses_skipped_explicit_inputs(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = self.external_record(directory, "codex", {"input_tokens": 10})
            argv = ["collect_tokens", "change", "--harness", "claude", "--mode", "apply",
                    "--external-run", str(path), "--external-run", str(Path(directory) / 'missing.run.json'),
                    "--final", "--project", "/project"]
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertNotEqual(0, collect.main())
            self.assertNotIn('status=final', output.getvalue())
            self.assertIn('warning', errors.getvalue())

    def test_cli_default_provisional_and_explicit_resumed_roots(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "db"
            self.make_db(db, {"session_v2": [self.db_row("first"), self.db_row("resumed"),
                                               self.db_row("unrelated")]})
            argv = ["collect_tokens", "change", "--harness", "opencode", "--mode", "apply",
                    "--directory", "/project", "--project", "/project", "--db", str(db),
                    "--session", "first", "--root-session", "resumed"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(collect.main(), 0)
            text = output.getvalue()
            self.assertIn("status=provisional", text)
            self.assertIn("opencode 2 run(s)", text)
            self.assertNotIn("unrelated", text)

    def test_cli_append_persists_collection_metadata_and_preserves_other_ledger(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = self.external_record(directory, "codex", {"input_tokens": 10})
            plan = Path(directory) / "change" / "plan.md"
            plan.parent.mkdir()
            plan.write_text("Execution tokens:\nmode=apply codex keep\n\n")
            argv = ["collect_tokens", "change", "--harness", "claude", "--mode", "apply",
                    "--external-run", str(path), "--project", "/project", "--append"]
            with (patch.object(sys, "argv", argv),
                  patch.object(collect, "resolve_root", return_value=SimpleNamespace(path=directory)),
                  patch.object(collect, "legacy_warning", return_value=None),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(collect.main(), 0)
                self.assertEqual(collect.main(), 0)
            content = plan.read_text()
            self.assertIn("mode=apply codex keep", content)
            self.assertIn("status=provisional", content)
            self.assertIn("collected_at=", content)
            self.assertEqual(content.count("external:"), 1)
            self.assertEqual(content.count("total mode=apply claude"), 1)

    def test_append_preserves_other_harness_and_modes(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.md"
            plan.write_text("Execution tokens:\nmode=apply codex old\n"
                            "total mode=apply codex old\nmode=apply claude keep\n"
                            "total mode=apply claude keep\nmode=explore codex keep\n\n")
            collect.append_to_plan(plan, ["mode=apply codex new", "total mode=apply codex new"],
                                   "apply", "codex")
            content = plan.read_text()
            self.assertNotIn("codex old", content)
            self.assertIn("mode=apply claude keep", content)
            self.assertIn("total mode=apply claude keep", content)
            self.assertIn("mode=explore codex keep", content)

    def test_append_refuses_archive(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "archive" / "change" / "plan.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("Execution tokens:\nold\n\n")
            with self.assertRaises(SystemExit):
                collect.append_to_plan(plan, ["mode=apply codex new"], "apply", "codex")
            self.assertEqual(plan.read_text(), "Execution tokens:\nold\n\n")

    def test_append_mixed_runtime_ledger_uses_controller_owner(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.md"
            plan.write_text("Execution tokens:\nmode=apply claude native ledger=claude\n"
                            "mode=apply codex external ledger=claude\n"
                            "total mode=apply claude old ledger=claude\n"
                            "mode=apply codex native ledger=codex\n\n")
            collect.append_to_plan(plan, ["mode=apply claude new ledger=claude"], "apply", "claude")
            content = plan.read_text()
            self.assertNotIn("external", content)
            self.assertNotIn("claude old", content)
            self.assertIn("mode=apply codex native ledger=codex", content)

    def test_append_infers_harness_for_legacy_api(self):
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.md"
            plan.write_text("Execution tokens:\nmode=apply claude keep\nmode=apply codex old\n\n")
            collect.append_to_plan(plan, ["mode=apply codex new"], "apply")
            self.assertIn("claude keep", plan.read_text())
            self.assertNotIn("codex old", plan.read_text())

    def test_append_replaces_only_the_selected_mode(self) -> None:
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.md"
            plan.write_text(
                "## Completion evidence\n\nExecution tokens:\n"
                "mode=explore old\n"
                "total mode=explore codex 1 run(s) unique=1 read=2\n\n"
                "Review rounds:\nPending\n",
                encoding="utf-8",
            )

            collect.append_to_plan(plan, ["mode=apply new", "total mode=apply codex"], "apply")
            collect.append_to_plan(plan, ["mode=explore replacement"], "explore")

            content = plan.read_text(encoding="utf-8")
            self.assertIn("mode=apply new", content)
            self.assertIn("mode=explore replacement", content)
            self.assertNotIn("mode=explore old", content)

    def test_append_drops_template_placeholder(self) -> None:
        collect = load_module()
        placeholder = "<per-execution totals collected by collect_tokens.py>"
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.md"
            plan.write_text(
                f"## Completion evidence\n\nExecution tokens:\n{placeholder}\n"
                "<!-- note -->\nmode=explore keep\n\nReview rounds:\nPending\n",
                encoding="utf-8",
            )

            collect.append_to_plan(plan, ["mode=apply new", "total mode=apply codex"], "apply")

            content = plan.read_text(encoding="utf-8")
            self.assertNotIn(placeholder, content)
            self.assertIn("mode=explore keep", content)
            self.assertIn("<!-- note -->", content)
            self.assertIn("mode=apply new", content)
            self.assertIn("total mode=apply codex", content)


if __name__ == "__main__":
    unittest.main()
