"""Exercise durable review transitions through the public step CLI."""
from __future__ import annotations

import json
import unittest

import test_apply_reliability as fixtures


class ReviewStateTest(unittest.TestCase):
    setUp = fixtures.ApplyReliabilityTest.setUp
    tearDown = fixtures.ApplyReliabilityTest.tearDown
    run_step = fixtures.ApplyReliabilityTest.run_step

    def result(self, verdict='PASS', findings=None):
        runs = self.change / 'runs'
        runs.mkdir(exist_ok=True)
        path = runs / 'review.json'
        path.write_text(json.dumps(dict(verdict=verdict, findings=findings or [], report='Independent read-only review.')))
        return path.relative_to(self.repo).as_posix()

    def begin(self, review_type='initial', *extra):
        return self.run_step('pre-review', 'demo', '--review-type', review_type, '--record-round', *extra)

    def test_result_is_persisted_before_question_and_header_agrees(self):
        result = self.begin()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('### G1', self.plan.read_text())
        self.assertIn('**Outcome:** Pending', self.plan.read_text())
        result = self.run_step('review-result', 'demo', '--result-file', self.result())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        text = self.plan.read_text()
        self.assertIn('**Outcome:** PASS', text)
        self.assertIn('**Result:** PASS', text)
        self.assertIn('**Reviewed tasks:** T1, T2, T3', text)

    def test_cannot_start_another_round_while_result_is_missing(self):
        self.assertEqual(0, self.begin().returncode)
        self.assertNotEqual(0, self.begin().returncode)
        self.assertEqual(1, self.plan.read_text().count('### G1'))

    def test_changed_executable_snapshot_cannot_receive_stale_pass(self):
        self.assertEqual(0, self.begin().returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "changed"\n')
        result = self.run_step('review-result', 'demo', '--result-file', self.result())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        text = self.plan.read_text()
        self.assertIn('**Outcome:** FAIL', text)
        self.assertIn('**Reviewer verdict:** PASS', text)
        self.assertIn('**Snapshot status:** stale', text)
        self.assertEqual(0, self.begin('re-review').returncode)

    def test_single_extra_round_approval_is_consumed(self):
        for _ in range(3):
            self.assertEqual(0, self.begin().returncode)
            self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', self.result()).returncode)
        self.assertNotEqual(0, self.begin().returncode)

        result = self.begin('initial', '--review-decision', 'User explicitly approved exactly one extra round for the corrected integration')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', self.result()).returncode)
        self.assertNotEqual(0, self.begin().returncode)

    def test_deleted_file_can_settle_stale_round_without_restoring_old_content(self):
        self.assertEqual(0, self.begin().returncode)
        self.repo.joinpath('label.py').unlink()
        result = self.run_step('review-result', 'demo', '--result-file', self.result('FAIL'))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('**Snapshot status:** stale', self.plan.read_text())

    def test_pass_with_important_findings_is_contradictory(self):
        self.assertEqual(0, self.begin().returncode)
        result = self.run_step('review-result', 'demo', '--result-file', self.result(findings=[
            dict(severity='IMPORTANT', location='label.py:1', summary='Unmet requirement')]))
        self.assertNotEqual(0, result.returncode)

    def test_targeted_correction_round_is_recorded_without_relabelling(self):
        self.assertEqual(0, self.begin().returncode)
        self.run_step('review-result', 'demo', '--result-file', self.result('FAIL', [
            dict(severity='MINOR', location='label.py:1', summary='Add boundary assertion')]))
        result = self.begin('re-review')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('### G2\n\n- **Type:** re-review', self.plan.read_text())

    def test_settled_history_is_idempotent_but_not_replaceable(self):
        self.assertEqual(0, self.begin().returncode)
        source = self.result()
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', source).returncode)
        original = self.plan.read_text()
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', source).returncode)
        self.assertEqual(original, self.plan.read_text())
        self.result(findings=[dict(severity='MINOR', location='label.py:1', summary='New observation')])
        result = self.run_step('review-result', 'demo', '--result-file', source)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(original, self.plan.read_text())


    def with_test_and_doc_scope(self):
        self.repo.joinpath('tests').mkdir()
        self.repo.joinpath('tests/test_label.py').write_text('assert True\n')
        self.repo.joinpath('NOTES.md').write_text('notes\n')
        self.plan.write_text(self.plan.read_text().replace(
            '## Review scope\n', '## Review scope\n- `tests/test_label.py`\n- `NOTES.md`\n'))

    def final_output(self):
        result = self.run_step_script('validate_change.py', 'demo', '--phase', 'final')
        return result.stdout + result.stderr

    def run_step_script(self, name, *args):
        import os, subprocess, sys
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('SPECADOC_ROOT', None)
        return subprocess.run([sys.executable, '-B', str(fixtures.SCRIPTS / name), *args],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    MINOR = [dict(severity='MINOR', location='tests/test_label.py:1', summary='Clarify assertion message')]

    def test_pass_with_minor_accepts_non_executable_fixes_without_new_round(self):
        self.with_test_and_doc_scope()
        self.assertEqual(0, self.begin().returncode)
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR)).returncode)
        self.repo.joinpath('tests/test_label.py').write_text('assert True, "label ready"\n')
        self.repo.joinpath('NOTES.md').write_text('notes updated\n')
        output = self.final_output()
        self.assertNotIn('diff changed since', output)
        self.assertIn('MINOR fixes', output)

    def test_pass_with_minor_executable_fix_needs_one_uncapped_re_review(self):
        self.with_test_and_doc_scope()
        self.assertEqual(0, self.begin().returncode)
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR)).returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # clarified\n')
        output = self.final_output()
        self.assertIn('diff changed since', output)
        self.assertIn('minor-fixes', output)
        result = self.begin('re-review')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('**Reason:** minor-fixes', self.plan.read_text())
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR)).returncode)
        # A second MINOR-only pass is deferred, not another round.
        self.assertNotEqual(0, self.begin('re-review').returncode)

    def test_minor_fixes_round_does_not_consume_the_correction_re_review(self):
        self.assertEqual(0, self.begin().returncode)
        self.run_step('review-result', 'demo', '--result-file', self.result('FAIL', [
            dict(severity='IMPORTANT', location='label.py:1', summary='Wrong label')]))
        self.assertEqual(0, self.begin('re-review').returncode)
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR)).returncode)
        result = self.begin('re-review')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


    def test_dependency_manifest_is_not_a_non_executable_minor_fix(self):
        self.with_test_and_doc_scope()
        self.repo.joinpath('requirements.txt').write_text('a==1\n')
        self.plan.write_text(self.plan.read_text().replace('## Review scope\n', '## Review scope\n- `requirements.txt`\n'))
        self.assertEqual(0, self.begin().returncode)
        self.assertEqual(0, self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR)).returncode)
        self.repo.joinpath('requirements.txt').write_text('a==2\n')
        self.assertIn('diff changed since', self.final_output())

    def test_after_minor_fixes_round_hint_names_residual_risk_not_another_round(self):
        self.with_test_and_doc_scope()
        self.assertEqual(0, self.begin().returncode)
        self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR))
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # a\n')
        self.assertEqual(0, self.begin('re-review').returncode)
        self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR))
        self.repo.joinpath('label.py').write_text('def label():\n    return "ready"  # b\n')
        output = self.final_output()
        self.assertIn('diff changed since', output)
        self.assertNotIn('--reason minor-fixes', output)

    def test_snapshot_diff_accepts_round_id(self):
        self.assertEqual(0, self.begin().returncode)
        self.repo.joinpath('label.py').write_text('def label():\n    return "changed"\n')
        result = self.run_step_script('review_snapshot.py', 'diff', 'demo', '--previous', 'G1')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(['label.py'], json.loads(result.stdout)['changed'])
        missing = self.run_step_script('review_snapshot.py', 'diff', 'demo', '--previous', 'G9')
        self.assertEqual(2, missing.returncode)
        self.assertNotIn('Traceback', missing.stderr)

    def test_reviewed_id_ranges_are_expanded(self):
        self.plan.write_text(self.plan.read_text().replace('**Reviewed tasks:** T1, T2, T3', '**Reviewed tasks:** T1–T3'))
        output = self.final_output()
        self.assertNotIn('Reviewed tasks', output)

    def test_minor_pass_checkpoint_names_the_next_step(self):
        self.plan.write_text(self.plan.read_text().replace('## Handoff\n', '## Handoff\n**Plan checkpoint:** None\n'))
        self.assertEqual(0, self.begin().returncode)
        self.run_step('review-result', 'demo', '--result-file', self.result('PASS', self.MINOR))
        self.assertIn('minor-fixes', self.plan.read_text())


if __name__ == '__main__':
    unittest.main()
