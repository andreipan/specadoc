"""Exercise packaged CLI gates end-to-end, with synthetic approval/review input.

This tests artifact mechanics, not model behavior or an actual independent PASS.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]


class LifecycleCliTest(unittest.TestCase):
    def test_packaged_lifecycle_gates_and_normal_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = importlib.util.spec_from_file_location('package_plugin', ROOT / 'scripts/package_plugin.py')
            package = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(package)
            package.build(ROOT, base / 'release.zip')
            with zipfile.ZipFile(base / 'release.zip') as archive:
                archive.extractall(base / 'plugin')
            scripts = base / 'plugin/skills/specadoc/scripts'
            project = base / 'project'
            project.mkdir()
            def cli(script, *args, expected=0):
                result = subprocess.run([sys.executable, '-B', str(scripts / script), *args], cwd=project, capture_output=True, text=True)
                self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
                return result.stdout
            cli('init_change.py', 'demo', '--risk', 'low')
            change = project / 'docs/specadoc/demo'
            change.joinpath('spec.md').write_text('''# Fixture label
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
''')
            tasks = []
            for i, outcome in enumerate(('Ready label', 'String result', 'Repeatable result'), 1):
                tasks.append(f'''### T{i} — {outcome}
- [x] Complete
- **Requirements:** R1
- **Risk:** low
- **Decision risk:** low
- **Owner:** worker
- **Owner level:** MEDIUM
- **Verification owner:** controller
- **Files:** label.py, check_label.py
- **Test first:** Assert {outcome.lower()}
- **Expected RED:** Old label is not ready
- **Implementation:** Return ready
- **Verification:** `python3 check_label.py`
- **Surface:** code
- **Delivery verification:** N/A
- **Done when:** Assertion passes
- **Evidence:** python3 check_label.py: PASS after observed RED
''')
            plan = '''# Fixture plan
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
''' + '\n'.join(tasks) + '''
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
- [x] Synthetic review artifact provided
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
            change.joinpath('plan.md').write_text(plan)
            cli('validate_change.py', 'demo', '--phase', 'spec')
            cli('validate_change.py', 'demo', '--phase', 'plan')
            project.joinpath('label.py').write_text('def label():\n    return "old"\n')
            project.joinpath('check_label.py').write_text('from label import label\nassert label() == "ready"\nassert isinstance(label(), str)\nassert label() == label()\n')
            red = subprocess.run([sys.executable, '-B', 'check_label.py'], cwd=project, capture_output=True)
            self.assertNotEqual(0, red.returncode)
            project.joinpath('label.py').write_text('def label():\n    return "ready"\n')
            green = subprocess.run([sys.executable, '-B', 'check_label.py'], cwd=project, capture_output=True)
            self.assertEqual(0, green.returncode, green.stderr)
            cli('validate_change.py', 'demo', '--phase', 'pre-review')
            snapshot = json.loads(cli('review_snapshot.py', 'compute', 'demo'))
            round_log = '\n### G1\n- **Type:** initial\n- **Previous:** none\n- **Outcome:** PASS\n- **Snapshot:** ' + snapshot['hash'] + '\n```json\n' + json.dumps(snapshot['manifest']) + '\n```\n'
            plan = plan.replace('**Result:** Pending', '**Result:** PASS').replace('## Archive summary', round_log + '\n## Archive summary')
            change.joinpath('plan.md').write_text(plan)
            capability = project / 'docs/specadoc/specs/label.md'
            capability.parent.mkdir()
            capability.write_text('### C1 — Diagnostic label is ready\nThe label SHALL equal ready.\n## Provenance\n| Change |\n|---|\n| demo |\n')
            cli('validate_change.py', 'demo', '--phase', 'final')
            cli('archive_change.py', 'demo', '--dry-run')
            self.assertTrue(change.is_dir())
            cli('archive_change.py', 'demo')
            self.assertFalse(change.exists())
            record = project / 'docs/specadoc/archive/demo/record.md'
            self.assertLessEqual(record.stat().st_size, 16 * 1024)
            self.assertIn('status: archived', record.read_text())
            cli('doctor.py', '--strict')


if __name__ == '__main__':
    unittest.main()
