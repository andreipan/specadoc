"""specadoc_step.py composes the gate scripts into one compact result per step."""
from __future__ import annotations

import subprocess
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / 'skills/specadoc/scripts'

SPEC = '''# Fixture label
## Goal
Deliver a stable local diagnostic label.
## Non-goals
No public API changes.
## Current context
The old diagnostic text is being replaced.
## Affected capabilities
- `docs/specadoc/specs/label.md` (new capability)
  - ADDED C1 (R1) — Diagnostic label is ready
## Requirements
### R1 — Ready label
The diagnostic label SHALL equal ready.
## Acceptance scenarios
### A1 — Read label
- **Given:** the diagnostic function
- **When:** it is called
- **Then:** it returns ready
- **Covers:** R1
## Constraints
Python standard library only.
## Assumptions
No external clients rely on the old text.
## Requirement coverage
| Requirement | Scenarios |
|---|---|
| R1 | A1 |
'''

PLAN = '''# Fixture plan
## Handoff
Read spec.md and plan.md, then continue with the next task.
## Reconnaissance evidence
label.py and check_label.py.
## Confirmed decisions
Use ready as the diagnostic label.
## Technical approach
Replace the return value without changing the interface.
## Global constraints
No dependencies.
## Files and interfaces
label.py defines label(); check_label.py verifies it.
## Tasks
### T1 — Ready label
- [x] Complete
- **Requirements:** R1
- **Risk:** low
- **Decision risk:** low
- **Owner:** worker
- **Verification owner:** controller
- **Files:** `label.py`, `check_label.py`
- **Test first:** Assert ready label
- **Expected RED:** Old label is not ready
- **Implementation:** Return ready
- **Verification:** `python3 check_label.py`
- **Surface:** code
- **Delivery verification:** N/A
- **Done when:** Assertion passes
- **Evidence:** python3 check_label.py: PASS after observed RED
### T2 — String result
- [x] Complete
- **Requirements:** R1
- **Risk:** low
- **Decision risk:** low
- **Owner:** worker
- **Verification owner:** controller
- **Files:** `label.py`, `check_label.py`
- **Test first:** Assert ready label
- **Expected RED:** Old label is not ready
- **Implementation:** Return ready
- **Verification:** `python3 check_label.py`
- **Surface:** code
- **Delivery verification:** N/A
- **Done when:** Assertion passes
- **Evidence:** python3 check_label.py: PASS after observed RED
### T3 — Repeatable result
- [x] Complete
- **Requirements:** R1
- **Risk:** low
- **Decision risk:** low
- **Owner:** worker
- **Verification owner:** controller
- **Files:** `label.py`, `check_label.py`
- **Test first:** Assert ready label
- **Expected RED:** Old label is not ready
- **Implementation:** Return ready
- **Verification:** `python3 check_label.py`
- **Surface:** code
- **Delivery verification:** N/A
- **Done when:** Assertion passes
- **Evidence:** python3 check_label.py: PASS after observed RED
## Requirement-to-check matrix
| Requirement | Scenarios | Exact check | Status |
|---|---|---|---|
| R1 | A1 | python3 check_label.py | PASS |
## Plan approval
**Status:** Approved (synthetic test fixture)
**Bindings shown:** worker claude/test/low
**Approved at:** fixture
## Review scope
- `label.py`
- `check_label.py`
## Final verification
- [x] Focused and regression checks pass
## Review result
**Result:** Pending
**Reviewed requirements:** R1
**Reviewed tasks:** T1, T2, T3
## Archive summary
Delivered the ready diagnostic label. No residual risk.
## Completion evidence
Commands: python3 check_label.py: PASS after RED
Requirement mapping: R1 -> check_label.py
Execution tokens: not applicable to synthetic CLI fixture
Review rounds: 1 synthetic fixture round
'''

LEGACY_PLAN = (
    PLAN.replace('## Handoff\nRead spec.md and plan.md, then continue with the next task.\n',
                 '## Model handoff\nModel and execution level approved in this synthetic fixture.\n'
                 '**Worker runtime:** codex/m1\n**Reviewer runtime:** codex/m2\n')
    .replace('- **Owner:** worker\n', '- **Owner:** worker\n- **Owner level:** MEDIUM\n')
    .replace('**Bindings shown:** worker claude/test/low\n', '**Approved profile:** MEDIUM\n')
    .replace('## Archive summary', '### Round log\n### G1\n- **Type:** initial\n- **Previous:** none\n'
             '- **Reviewer runtime:** codex/m2\n- **Independence waiver:** reviewer on another vendor\n'
             '- **Outcome:** Pending\n## Archive summary')
)

# Created by the old template and left unfilled at the old model checkpoint.
PARTIAL_LEGACY_PLAN = (
    LEGACY_PLAN.replace('**Worker runtime:** codex/m1\n',
                        '**Worker runtime:** <runtime/model>\n**Recommended execution level:** Pending\n')
    .replace('- **Owner level:** MEDIUM\n', '- **Owner level:** <EASY|MEDIUM|HIGH, or the approved alternative>\n')
    .replace('**Approved profile:** MEDIUM\n', '**Approved profile:** Pending\n')
    .replace('- **Independence waiver:** reviewer on another vendor\n', '- **Independence waiver:** Pending\n')
)


class SpecadocStepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q'], cwd=self.project, check=True)
        self.script('init_change.py', 'demo', '--risk', 'low')
        change = self.project / 'docs/specadoc/demo'
        change.joinpath('spec.md').write_text(SPEC)
        change.joinpath('plan.md').write_text(PLAN)
        self.project.joinpath('label.py').write_text('def label():\n    return "old"\n')
        self.project.joinpath('check_label.py').write_text('from label import label\nassert label() == "ready"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def script(self, name, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPTS / name), *args], cwd=self.project, capture_output=True, text=True
        )

    def step(self, *args, expected):
        result = self.script('specadoc_step.py', *args)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        fields = dict(line.split(': ', 1) for line in result.stdout.splitlines()[:5])
        self.assertEqual(['checked', 'result', 'changed files', 'blocking reason', 'next'], list(fields))
        return fields, result.stdout

    def test_dispatch_writes_baseline_and_brief(self):
        fields, _ = self.step('dispatch', 'demo', 'T1', expected=0)
        self.assertEqual('PASS', fields['result'])
        runs = self.project / 'docs/specadoc/demo/runs'
        self.assertTrue((runs / 'T1-baseline.json').is_file())
        self.assertTrue((runs / 'T1-brief.md').is_file())
        self.assertIn('T1-report.md', fields['next'])

    def test_routed_dispatch_needs_controller_and_reports_fresh_resolution(self):
        (self.project / '.specadoc.json').write_text(json.dumps({'version': 1, 'roles': {'worker': {'runtime': 'codex'}}}))
        role = self.project / '.codex/agents/worker.toml'
        role.parent.mkdir(parents=True)
        role.write_text('model = "test-model"\nmodel_reasoning_effort = "low"\n')
        fields, _ = self.step('dispatch', 'demo', 'T1', expected=2)
        self.assertIn('controller-runtime', fields['blocking reason'])
        runs = self.project / 'docs/specadoc/demo/runs'
        self.assertFalse((runs / 'T1-baseline.json').exists())
        fields, _ = self.step('dispatch', 'demo', 'T1', '--controller-runtime', 'claude', expected=0)
        self.assertIn('resolved worker codex/test-model/low', fields['checked'])
        role.write_text('model = "changed-model"\nmodel_reasoning_effort = "high"\n')
        fields, _ = self.step('dispatch', 'demo', 'T1', '--controller-runtime', 'claude', expected=0)
        self.assertIn('resolved worker codex/changed-model/high', fields['checked'])

    def test_binding_file_is_a_usage_error(self):
        for step in (('dispatch', 'demo', 'T1'), ('pre-review', 'demo')):
            result = self.script('specadoc_step.py', *step, '--binding-file', 'x.json')
            self.assertEqual(2, result.returncode)
            self.assertIn('--binding-file', result.stderr)

    def test_accept_without_baseline_is_blocked(self):
        fields, _ = self.step('accept', 'demo', 'T1', expected=2)
        self.assertEqual('BLOCKED', fields['result'])

    def test_accept_flags_out_of_scope_change(self):
        self.step('dispatch', 'demo', 'T1', expected=0)
        self.project.joinpath('other.py').write_text('x = 1\n')
        fields, _ = self.step('accept', 'demo', 'T1', expected=1)
        self.assertIn('other.py', fields['changed files'])

    def test_accept_runs_verification(self):
        self.step('dispatch', 'demo', 'T1', expected=0)
        fields, output = self.step('accept', 'demo', 'T1', '--verify', expected=1)
        self.assertIn('python3 check_label.py', fields['blocking reason'])
        self.assertIn('AssertionError', output)
        self.project.joinpath('label.py').write_text('def label():\n    return "ready"\n')
        fields, _ = self.step('accept', 'demo', 'T1', '--verify', expected=0)
        self.assertEqual('check-scope; python3 check_label.py; check-scope after verification', fields['checked'])

    def test_successful_accept_lists_actual_delta(self):
        self.step('dispatch', 'demo', 'T1', expected=0)
        self.project.joinpath('label.py').write_text('def label():\n    return "ready"\n')
        fields, _ = self.step('accept', 'demo', 'T1', expected=0)
        self.assertEqual('label.py', fields['changed files'])

    def test_ambiguous_verification_does_not_execute_inline_spans(self):
        plan = self.project / 'docs/specadoc/demo/plan.md'
        plan.write_text(PLAN.replace('`python3 check_label.py`', 'Check `label.py` with `python3 check_label.py`'))
        self.step('dispatch', 'demo', 'T1', expected=0)
        fields, _ = self.step('accept', 'demo', 'T1', '--verify', expected=2)
        self.assertIn('Verification', fields['blocking reason'])

    def test_scope_is_checked_again_after_verification(self):
        plan = self.project / 'docs/specadoc/demo/plan.md'
        command = """`python3 -c "open('other.py', 'w').write('oops')"`"""
        plan.write_text(PLAN.replace('`python3 check_label.py`', command))
        self.step('dispatch', 'demo', 'T1', expected=0)
        fields, _ = self.step('accept', 'demo', 'T1', '--verify', expected=1)
        self.assertIn('other.py', fields['changed files'])

    def test_uncheckable_scope_cannot_be_accepted(self):
        plan = self.project / 'docs/specadoc/demo/plan.md'
        plan.write_text(PLAN.replace('`label.py`, `check_label.py`', 'the label implementation'))
        self.step('dispatch', 'demo', 'T1', expected=1)
        self.step('accept', 'demo', 'T1', expected=2)

    def test_malformed_baseline_is_blocked_without_traceback(self):
        self.step('dispatch', 'demo', 'T1', expected=0)
        (self.project / 'docs/specadoc/demo/runs/T1-baseline.json').write_text('{')
        fields, output = self.step('accept', 'demo', 'T1', expected=2)
        self.assertEqual('BLOCKED', fields['result'])
        self.assertNotIn('Traceback', output)

    def test_custom_root_is_forwarded_to_all_steps(self):
        old = self.project / 'docs/specadoc'
        old.rename(self.project / 'changes')
        spec = self.project / 'changes/demo/spec.md'
        spec.write_text(SPEC.replace('docs/specadoc', 'changes'))
        self.step('--root', 'changes', 'dispatch', 'demo', 'T1', expected=0)
        self.step('--root', 'changes', 'accept', 'demo', 'T1', expected=0)
        self.step('--root', 'changes', 'pre-review', 'demo', expected=0)

    def test_new_and_legacy_plans_pass_plan_and_pre_review(self):
        plan = self.project / 'docs/specadoc/demo/plan.md'
        for name, content in (('new', PLAN), ('legacy', LEGACY_PLAN)):
            with self.subTest(name):
                plan.write_text(content)
                result = self.script('validate_change.py', 'demo', '--phase', 'plan')
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.step('pre-review', 'demo', expected=0)

    def test_unfilled_legacy_fields_never_fail_a_gate(self):
        plan = self.project / 'docs/specadoc/demo/plan.md'
        plan.write_text(PARTIAL_LEGACY_PLAN)
        result = self.script('validate_change.py', 'demo', '--phase', 'plan')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.step('pre-review', 'demo', expected=0)
        final = self.script('validate_change.py', 'demo', '--phase', 'final')
        output = final.stdout + final.stderr
        self.assertEqual(1, final.returncode, output)
        self.assertNotIn('Traceback', output)
        self.assertIn('Review result', output)
        for field in ('Worker runtime', 'Recommended execution level', 'Owner level',
                      'Approved profile', 'Independence waiver', '<runtime/model>', '<EASY'):
            self.assertNotIn(field, output)

    def test_pre_review_refuses_incomplete_plan(self):
        plan = self.project / 'docs/specadoc/demo/plan.md'
        plan.write_text(PLAN.replace('- [x] Complete', '- [ ] Complete'))
        fields, output = self.step('pre-review', 'demo', expected=1)
        self.assertEqual('FAIL', fields['result'])
        self.assertNotIn('snapshot:', output)

    def test_pre_review_prints_snapshot_for_round(self):
        fields, output = self.step('pre-review', 'demo', expected=0)
        self.assertEqual('check_label.py, label.py', fields['changed files'])
        snapshot = self.script('review_snapshot.py', 'compute', 'demo')
        self.assertIn('"hash": "', snapshot.stdout)
        digest = snapshot.stdout.split('"hash": "', 1)[1].split('"', 1)[0]
        self.assertIn(f'snapshot: {digest}', output)

    def test_documentation_followup_refuses_changed_disk_snapshot_before_dispatch(self):
        _, output = self.step('pre-review', 'demo', expected=0)
        digest = next(line.split(': ', 1)[1] for line in output.splitlines() if line.startswith('snapshot: '))
        policy = next(line.split(': ', 1)[1] for line in output.splitlines() if line.startswith('policy snapshot: '))
        rounds = ('### G1\n- **Type:** initial\n- **Outcome:** FAIL\n'
                  '### G2\n- **Type:** re-review\n- **Outcome:** FAIL\n'
                  '- **Remaining findings:** documentation-only\n'
                  f'- **Snapshot:** {digest}\n- **Policy snapshot:** {policy}\n'
                  '### G3\n- **Type:** re-review\n- **Scope:** documentation-only\n'
                  '- **Previous:** G2\n- **Outcome:** Pending\n'
                  f'- **Snapshot:** {digest}\n- **Policy snapshot:** {policy}\n')
        plan = self.project / 'docs/specadoc/demo/plan.md'
        plan.write_text(PLAN.replace('## Archive summary', rounds + '\n## Archive summary'))
        self.step('pre-review', 'demo', expected=0)
        self.project.joinpath('label.py').write_text('def label():\n    return "changed"\n')
        fields, _ = self.step('pre-review', 'demo', expected=1)
        self.assertIn('documentation-only', fields['blocking reason'])

    def test_routed_reviewer_resolution_is_reported_before_pre_review(self):
        (self.project / '.specadoc.json').write_text(json.dumps({'version': 1, 'roles': {'reviewer': {'runtime': 'codex'}}}))
        role = self.project / '.codex/agents/reviewer.toml'
        role.parent.mkdir(parents=True)
        role.write_text('model = "test-reviewer"\nmodel_reasoning_effort = "high"\n')
        fields, output = self.step('pre-review', 'demo', expected=2)
        self.assertIn('controller-runtime', fields['blocking reason'])
        self.assertNotIn('snapshot:', output)
        fields, output = self.step('pre-review', 'demo', '--controller-runtime', 'claude', expected=0)
        self.assertIn('resolved reviewer codex/test-reviewer/high', fields['checked'])
        self.assertIn('snapshot:', output)


if __name__ == '__main__':
    unittest.main()
