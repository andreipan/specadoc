"""Regressions from orchestrator run 6.11-6.15 (adraptor stage 6, 2026-11-14..16)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "specadoc" / "scripts"

from test_run411_regressions import Run411Base  # noqa: E402


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_run611", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(module)
    return module


class FakeClock:
    """time.monotonic() stops while the host sleeps; time.time() does not."""

    def __init__(self, naps: list[float]):
        self.wall = time.time()
        self.mono = 0.0
        self.naps = list(naps)

    def time(self) -> float:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def sleep(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += seconds + (self.naps.pop(0) if self.naps else 0.0)


class HostSleepTest(unittest.TestCase):
    """6.14: three reviewer runs and a 51-minute worker wait were macOS idle sleep, not stalls."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.runs = Path(self.temp.name)
        self.module = load("run_role")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def running_record(self) -> Path:
        log = self.runs / "design-r2.reviewer.log"
        log.write_text('{"type":"step_start"}\n', encoding="utf-8")
        run_file = self.runs / "design-r2.reviewer.run.json"
        run_file.write_text(json.dumps(dict(
            runtime="opencode", role="reviewer", started=time.time(), pid=os.getpid(), log=str(log),
            exit=str(self.runs / "design-r2.reviewer.exit"), result=str(self.runs / "design-r2.reviewer.result.json"))))
        return run_file

    def wait(self, run_file: Path, clock: FakeClock) -> tuple[int, str]:
        lines: list[str] = []
        args = Namespace(run_file=str(run_file), timeout=5.0, shell_budget=590.0, follow=False, interval=45.0,
                         no_progress_timeout=900.0)
        with patch.object(self.module, "time", clock), patch("builtins.print", lambda *a, **k: lines.append(" ".join(map(str, a)))):
            code = self.module.wait(args)
        return code, "\n".join(lines)

    def test_wait_names_host_sleep(self) -> None:
        code, out = self.wait(self.running_record(), FakeClock([600.0]))
        self.assertEqual(self.module.STILL_RUNNING, code)
        self.assertIn("host slept 600 s", out)

    def test_sleep_is_not_reported_as_no_progress(self) -> None:
        code, out = self.wait(self.running_record(), FakeClock([1200.0]))
        self.assertNotIn("no-progress", out)
        self.assertIn("wait timed out", out)
        self.assertIn("host slept 1200 s", out)

    def test_a_stall_after_the_wake_is_still_no_progress(self) -> None:
        run_file = self.running_record()
        log = self.runs / "design-r2.reviewer.log"
        clock = FakeClock([1200.0])
        original = clock.sleep

        def sleep_then_write(seconds: float) -> None:
            first = bool(clock.naps)
            original(seconds)
            if first:  # the role wrote once right after the wake, then went silent
                os.utime(log, (clock.wall, clock.wall))
        clock.sleep = sleep_then_write
        lines: list[str] = []
        args = Namespace(run_file=str(run_file), timeout=1000.0, shell_budget=2000.0, follow=False, interval=45.0,
                         no_progress_timeout=900.0)
        with patch.object(self.module, "time", clock), patch("builtins.print", lambda *a, **k: lines.append(" ".join(map(str, a)))):
            code = self.module.wait(args)
        self.assertEqual(self.module.STILL_RUNNING, code)
        self.assertIn("no-progress", "\n".join(lines))

    def test_no_note_without_sleep(self) -> None:
        _, out = self.wait(self.running_record(), FakeClock([]))
        self.assertNotIn("host slept", out)


class StepWaitSleepTest(unittest.TestCase):
    """6.14 apply: `specadoc_step.py wait … --timeout 540` returned after 13.6 and 16.4 wall minutes."""

    def setUp(self) -> None:
        from test_apply_reliability import ApplyReliabilityTest
        ApplyReliabilityTest.setUp(self)
        self.module = load("specadoc_step")
        self.cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def wait(self, task: str, clock: FakeClock, **kwargs) -> tuple[int, str]:
        import contextlib
        import io
        out = io.StringIO()
        with patch.object(self.module, "time", clock), contextlib.redirect_stdout(out):
            code = self.module.wait_report("demo", task, None, 5.0, 1.0, **kwargs)
        return code, out.getvalue()

    def test_waiting_names_host_sleep(self) -> None:
        code, out = self.wait("T1", FakeClock([900.0]))
        self.assertEqual(2, code, out)
        self.assertIn("result: WAITING", out)
        self.assertIn("host slept 900 s", out)

    def test_tidy_waiting_names_host_sleep(self) -> None:
        _, out = self.wait("tidy", FakeClock([300.0]))
        self.assertIn("host slept 300 s", out)

    def test_shell_budget_caps_the_slice(self) -> None:
        clock = FakeClock([])
        code, out = self.wait("T1", clock, shell_budget=3.0)
        self.assertEqual(2, code, out)
        self.assertLess(clock.mono, 3.0)
        self.assertIn("within 2s", out)


class WaitSettlesResultTest(unittest.TestCase):
    """6.12 fix and 6.15: `wait` said finished, then reading runs/<name>.reviewer.result.json failed."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.runs = Path(self.temp.name)
        self.module = load("run_role")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def finished_record(self, payload: dict) -> Path:
        log = self.runs / "G1.reviewer.log"
        log.write_text(json.dumps(dict(structured_output=payload, usage=dict(input_tokens=77))), encoding="utf-8")
        (self.runs / "G1.reviewer.exit").write_text("0")
        run_file = self.runs / "G1.reviewer.run.json"
        run_file.write_text(json.dumps(dict(
            runtime="claude", role="reviewer", started=time.time() - 5, pid=os.getpid(), log=str(log),
            exit=str(self.runs / "G1.reviewer.exit"), result=str(self.runs / "G1.reviewer.result.json"))))
        return run_file

    def test_wait_writes_the_result_file(self) -> None:
        run_file = self.finished_record(dict(verdict="PASS", findings=[], report="Verified"))
        lines: list[str] = []
        args = Namespace(run_file=str(run_file), timeout=5.0, shell_budget=590.0, follow=False, interval=45.0,
                         no_progress_timeout=None)
        with patch("builtins.print", lambda *a, **k: lines.append(" ".join(map(str, a)))):
            self.assertEqual(0, self.module.wait(args))
        result = self.runs / "G1.reviewer.result.json"
        self.assertTrue(result.is_file(), lines)
        self.assertEqual("PASS", json.loads(result.read_text())["verdict"])
        self.assertIn(str(result), "\n".join(lines))
        record = json.loads(run_file.read_text())
        self.assertEqual(77, record["usage"]["input_tokens"])
        with patch("builtins.print"):
            self.assertEqual(0, self.module.result(Namespace(run_file=str(run_file))))

    def test_wait_leaves_an_invalid_result_to_result(self) -> None:
        run_file = self.finished_record(dict(verdict="MAYBE"))
        lines: list[str] = []
        args = Namespace(run_file=str(run_file), timeout=5.0, shell_budget=590.0, follow=False, interval=45.0,
                         no_progress_timeout=None)
        with patch("builtins.print", lambda *a, **k: lines.append(" ".join(map(str, a)))):
            self.assertEqual(0, self.module.wait(args))
        self.assertFalse((self.runs / "G1.reviewer.result.json").exists())
        self.assertIn("run result", "\n".join(lines))


class ReviewResultRunRecordTest(Run411Base):
    """6.14 apply: `review-result --result-file runs/G1.reviewer.run.json` answered "reviewer process did
    not exit successfully" while the reviewer had exited 0; design-review already took a run record."""

    def finished_run(self, verdict: str = "PASS") -> str:
        runs = self.change / "runs"
        runs.mkdir(exist_ok=True)
        log = runs / "G1.reviewer.log"
        log.write_text(json.dumps(dict(structured_output=dict(verdict=verdict, findings=[], report="Read-only review."),
                                       usage=dict(input_tokens=5))), encoding="utf-8")
        (runs / "G1.reviewer.exit").write_text("0")
        run_file = runs / "G1.reviewer.run.json"
        run_file.write_text(json.dumps(dict(runtime="claude", role="reviewer", started=time.time() - 5,
                                            pid=os.getpid(), log=str(log), exit=str(runs / "G1.reviewer.exit"),
                                            result=str(runs / "G1.reviewer.result.json"))))
        return "docs/specadoc/demo/runs/G1.reviewer.run.json"

    def test_review_result_takes_the_run_record(self) -> None:
        self.commit_all()
        self.assertEqual(0, self.run_step("pre-review", "demo").returncode)
        result = self.run_step("review-result", "demo", "--result-file", self.finished_run())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((self.change / "runs" / "G1.reviewer.result.json").is_file())


from test_run35_regressions import INVENTORY_PLAN  # noqa: E402
from test_run610_regressions import Base as DesignBase  # noqa: E402

IMPORTANT = [dict(severity="IMPORTANT", location="spec.md A3", summary="the lock order is not stated",
                  items=["state the order of the services and accounts locks"])]


class DesignRoundCapTest(DesignBase):
    """6.12 took six design rounds and 6.14 seven; nothing bounded them and the orchestrator asked the user
    for each extra round."""

    def review(self, verdict, findings):
        path = self.repo / "design.json"
        path.write_text(json.dumps({"verdict": verdict, "report": "r", "findings": findings}))
        return self.run_step("design-review", "demo", "--result-file", "design.json")

    def resolve_all(self):
        plan = self.plan.read_text()
        ids = sorted(set(__import__("re").findall(r"  - (F\d+\.\d+): ", plan)))
        self.repo.joinpath("resolutions.txt").write_text(
            "".join(f"{item}: resolved: plan.md T1\n" for item in ids))
        return self.run_step("design-resolve", "demo", "--file", "resolutions.txt")

    def fail_rounds(self, count, findings=IMPORTANT):
        self.plan.write_text(INVENTORY_PLAN)
        for number in range(count):
            if number:
                self.resolve_all()
            brief = self.run_step("design-brief", "demo")
            self.assertEqual(0, brief.returncode, brief.stdout)
            self.assertEqual(1, self.review("FAIL", findings).returncode)
        self.resolve_all()

    def test_round_five_needs_a_decision(self):
        self.fail_rounds(4)
        blocked = self.run_step("design-brief", "demo")
        self.assertEqual(2, blocked.returncode, blocked.stdout)
        self.assertIn("--attempt-decision", blocked.stdout)
        allowed = self.run_step("design-brief", "demo", "--attempt-decision", "continue: orchestrator D7 under mandate")
        self.assertEqual(0, allowed.returncode, allowed.stdout)
        brief = (self.change / "runs" / "design-brief.md").read_text()
        self.assertIn("Round authorization: round 5, continue — orchestrator D7 under mandate", brief)

    def test_a_continue_decision_is_kept_in_plan_once(self):
        self.fail_rounds(4)
        refused = self.run_step("design-brief", "demo", "--attempt-decision", "maybe")
        self.assertNotEqual(0, refused.returncode)
        for _ in range(2):
            self.assertEqual(0, self.run_step("design-brief", "demo", "--attempt-decision",
                                              "continue: orchestrator D7 under mandate").returncode)
        plan = self.plan.read_text()
        self.assertEqual(1, plan.count("- Design round authorization: round 5, continue — orchestrator D7 under mandate"))
        state = json.loads((self.change / "runs" / "design-round.json").read_text())
        self.assertEqual(1, len(state["decisions"]))

    def test_status_shows_an_accepted_gate(self):
        self.fail_rounds(4)
        self.run_step("design-brief", "demo", "--attempt-decision", "accept: orchestrator D8")
        self.assertIn("ACCEPTED (orchestrator D8", self.run_step("status", "demo").stdout)

    def test_four_rounds_need_no_decision(self):
        self.fail_rounds(3)
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)

    def test_accept_turns_open_items_into_apply_obligations(self):
        self.fail_rounds(4)
        accepted = self.run_step("design-brief", "demo", "--attempt-decision",
                                 "accept: orchestrator D8 takes the remaining items into apply")
        self.assertEqual(0, accepted.returncode, accepted.stdout)
        plan = self.plan.read_text()
        self.assertIn("**Result:** ACCEPTED", plan)
        self.assertIn("Design obligation F1.1", plan)
        status = self.run_step("status", "demo")
        self.assertNotIn("design review FAIL", status.stdout)

    def test_accept_refuses_an_open_blocker(self):
        self.fail_rounds(4, [dict(severity="BLOCKER", location="plan.md T1", summary="the lock is released early")])
        refused = self.run_step("design-brief", "demo", "--attempt-decision", "accept: orchestrator D9")
        self.assertNotEqual(0, refused.returncode, refused.stdout)
        self.assertIn("BLOCKER", refused.stdout + refused.stderr)

    def test_a_decision_needs_its_kind_and_source(self):
        self.fail_rounds(4)
        refused = self.run_step("design-brief", "demo", "--attempt-decision", "maybe")
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("continue: <source>", refused.stdout + refused.stderr)


class StaleDesignBriefTest(DesignBase):
    """6.12 and 6.13: a reviewer started on the previous round's brief and the run had to be stopped."""

    def test_a_reviewer_that_read_an_older_brief_is_refused(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.assertEqual(0, self.run_step("design-brief", "demo").returncode)
        brief = self.change / "runs" / "design-brief.md"
        runs = self.change / "runs"
        stale = __import__("hashlib").sha256(b"the previous round's brief").hexdigest()
        (runs / "design-r2.reviewer.result.json").write_text(json.dumps({"verdict": "PASS", "report": "r", "findings": []}))
        (runs / "design-r2.reviewer.run.json").write_text(json.dumps(dict(
            prompt_sha256=stale, prompt_file=str(brief), result=str(runs / "design-r2.reviewer.result.json"))))
        result = self.run_step("design-review", "demo", "--result-file", "docs/specadoc/demo/runs/design-r2.reviewer.result.json")
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("stale brief", result.stdout + result.stderr)

    def test_resolve_refusals_show_the_expected_line(self):
        self.plan.write_text(INVENTORY_PLAN)
        self.run_step("design-brief", "demo")
        path = self.repo / "design.json"
        path.write_text(json.dumps({"verdict": "FAIL", "report": "r", "findings": IMPORTANT}))
        self.run_step("design-review", "demo", "--result-file", "design.json")
        self.repo.joinpath("r.txt").write_text("F1.1: resolved: fixed it\n")
        refused = self.run_step("design-resolve", "demo", "--file", "r.txt")
        self.assertIn("e.g. `F1.1: resolved: plan.md T2`", refused.stdout + refused.stderr)
        blocked = self.run_step("design-brief", "demo")
        self.assertIn("e.g. `F1.1: resolved: plan.md T2`", blocked.stdout)


class ApproveStatusLinesTest(DesignBase):
    """6.15: after `approve` the controller set the top Status and the Plan checkpoint by `sed`."""

    def test_approve_updates_the_status_and_the_checkpoint(self):
        from test_specadoc_step import PLAN
        head = ("# Implementation plan: demo\n\n**Status:** Plan checkpoint  \n**Mode:** Propose  \n\n"
                "## Handoff\n\n**Plan checkpoint:** Not ready\n\n")
        body = PLAN.split("\n", 1)[1] if PLAN.startswith("# ") else PLAN
        self.plan.write_text(head + body.replace("**Status:** Approved (synthetic test fixture)",
                                                 "**Status:** Awaiting approval"))
        result = self.run_step("approve", "demo", "--by", "orchestrator", "--source", "mandate D80, decision D112",
                               "--bindings", "worker claude/sonnet/medium")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        text = self.plan.read_text()
        self.assertIn("**Status:** Approved, apply not started", text.split("## Handoff")[0])
        self.assertIn("**Plan checkpoint:** Approved (mandate D80, decision D112)", text)


class FinalizeNamesMissingEvidenceTest(Run411Base):
    """6.13 and 6.15: `finalize --run` left Completion evidence Pending and the controller filled plan.md by
    hand with a heredoc."""

    def test_finalize_names_the_command_for_each_pending_label(self):
        import re
        from test_run52_regressions import EVIDENCE
        from test_specadoc_step import PLAN
        evidence = EVIDENCE.replace("Review rounds:\nPending\n",
                                    "Review rounds:\nPending\n\nResidual risks or waivers:\nPending\n")
        plan = PLAN.replace("| R1 | A1 | python3 check_label.py | PASS |", "| R1 | A1 | python3 check_label.py | Pending |")
        self.plan.write_text(re.sub(r"## Completion evidence\n.*\Z", evidence, plan, flags=re.S))
        result = self.run_step("finalize", "demo")
        next_line = next(line for line in result.stdout.splitlines() if line.startswith("next:"))
        self.assertIn("finalize demo --residual", next_line)
        self.assertIn("finalize demo --requirements", next_line)
        self.assertIn("collect_tokens.py demo", next_line)
        self.assertIn("no hand edits of plan.md", next_line)


class FinalizeCollectsTokensTest(Run411Base):
    """6.13: tokens were collected by hand, and the first --append missed the controller transcript because an
    external run was passed too."""

    def step_with_session(self, *args, config: Path, session: str):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CLAUDE_CODE_SESSION_ID=session,
                   CLAUDE_CONFIG_DIR=str(config))
        env.pop("SPECADOC_ROOT", None)
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "specadoc_step.py"), *args],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def test_finalize_appends_the_session_and_external_runs_then_final_passes(self):
        import re
        from test_run52_regressions import EVIDENCE
        from test_specadoc_step import PLAN
        evidence = EVIDENCE.replace("Review rounds:\nPending\n",
                                    "Review rounds:\nPending\n\nResidual risks or waivers:\nPending\n")
        self.plan.write_text(re.sub(r"## Completion evidence\n.*\Z", evidence, PLAN, flags=re.S))
        config = self.repo / "claude-config"
        transcript = config / "projects" / "-repo" / "s611.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"type": "assistant", "requestId": "r1", "message": {
            "usage": {"input_tokens": 2, "output_tokens": 3, "cache_read_input_tokens": 10}}}) + "\n")
        runs = self.change / "runs"
        runs.mkdir(exist_ok=True)
        (runs / "G1.reviewer.exit").write_text("0\n")
        (runs / "G1.reviewer.result.json").write_text("{}")
        (runs / "G1.reviewer.run.json").write_text(json.dumps(dict(
            runtime="opencode", role="reviewer", cwd=str(self.repo), started=123, pid=42, settled=124,
            exit=str(runs / "G1.reviewer.exit"), result=str(runs / "G1.reviewer.result.json"),
            usage={"input": 40, "output": 5})))
        self.repo.joinpath(".specadoc.json").write_text(json.dumps(
            {"version": 1, "verification": {"final": ["python3 check_label.py"]}}))
        self.commit_all()
        self.pass_round()
        result = self.step_with_session("finalize", "demo", "--run", "--residual", "none", config=config,
                                        session="s611")
        self.assertIn("execution tokens collected", result.stdout, result.stdout + result.stderr)
        text = self.plan.read_text()
        tokens = text.split("Execution tokens:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("claude", tokens)
        self.assertNotIn("Pending", tokens)
        sidecar = (runs / "tokens.md").read_text() if (runs / "tokens.md").exists() else ""
        self.assertIn("opencode", tokens + sidecar)
        final = self.validate("final")
        self.assertEqual(0, final.returncode, final.stdout + final.stderr)

    def test_finalize_without_a_session_only_names_the_command(self):
        result = self.run_step("finalize", "demo")
        self.assertNotIn("execution tokens collected", result.stdout)


class AcceptStaleInventoryTest(DesignRoundCapTest):
    """Review of the 6.11-6.15 fixes: accept after an inventory change printed PASS, approve then blocked and the
    next design-brief ran past the cap without a decision."""

    def test_accept_refuses_a_changed_inventory(self):
        self.fail_rounds(4)
        self.plan.write_text(self.plan.read_text().replace("R1 needs a label source port", "R1 needs a label source port and cache"))
        refused = self.run_step("design-brief", "demo", "--attempt-decision", "accept: orchestrator D8")
        self.assertNotEqual(0, refused.returncode, refused.stdout)
        self.assertIn("continue:", refused.stdout + refused.stderr)
        self.assertIn("**Result:** FAIL", self.plan.read_text())

    def test_approve_passes_after_a_valid_accept(self):
        self.fail_rounds(4)
        self.assertEqual(0, self.run_step("design-brief", "demo", "--attempt-decision", "accept: orchestrator D8").returncode)
        approve = ("approve", "demo", "--by", "orchestrator", "--source", "mandate D80, decision D8",
                   "--bindings", "worker claude/sonnet/medium")
        # An accepted obligation is met by a named task (run 6.17: deferred items had no owner).
        refused = self.run_step(*approve)
        self.assertEqual(2, refused.returncode, refused.stdout)
        self.assertIn("F1.1 in Global constraints are named by no task", refused.stdout)
        self.plan.write_text(self.plan.read_text().replace(
            "- **Implementation:** Return ready", "- **Implementation:** Return ready\n- **Obligations:** F1.1", 1))
        approved = self.run_step(*approve)
        self.assertEqual(0, approved.returncode, approved.stdout + approved.stderr)


class WorkerBriefRulesTest(Run411Base):
    """6.13: a worker invented a warning text the design fixed; 6.14: pint got the file list as one quoted
    string and rewrote five config files; 6.13: mutants were made by `sed` on production code and restored
    from a copy in /tmp."""

    def test_the_brief_carries_the_three_rules(self):
        result = self.run_step("dispatch", "demo", "T1")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        brief = (self.change / "runs" / "T1-brief.md").read_text()
        self.assertIn("word for word", brief)
        self.assertIn("each changed file as its own argument", brief)
        self.assertIn("git diff --stat", brief)
        self.assertLess(len(brief.encode()), 16000)


if __name__ == "__main__":
    unittest.main()
