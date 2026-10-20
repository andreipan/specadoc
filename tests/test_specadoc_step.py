"""specadoc_step.py composes the gate scripts into one compact result per step."""
from __future__ import annotations

import subprocess
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
## Model handoff
Model and execution level approved in this synthetic fixture.
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
- **Owner level:** MEDIUM
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
- **Owner level:** MEDIUM
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
- **Owner level:** MEDIUM
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
**Approved profile:** MEDIUM
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


if __name__ == '__main__':
    unittest.main()
