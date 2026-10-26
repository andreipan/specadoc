"""Record a review before dispatch and settle its result before asking the user."""
from __future__ import annotations

import json
import re
from pathlib import Path

from run_role import _parse_json_text, schema_errors, schema_path
from task_state import digest, safe_path
from validate_change import (Document, PENDING, check_review_round_structure, ids_in,
                             latest_review_round, minor_only_pass, review_policy_hash)
from review_snapshot import SnapshotError, compute, manifest_hash


def insert_round(change: Path, snapshot: dict, review_type: str, reason: str, decision: str | None) -> str:
    path = change / 'plan.md'
    plan = Document(path, str(path))
    latest = latest_review_round(plan)
    if latest and latest[1].get('Outcome', '').upper() not in ('PASS', 'FAIL'):
        raise ValueError(f"{latest[0]} has no recorded result; settle it before another review")
    if review_type == 're-review' and not latest:
        raise ValueError('a targeted re-review needs a previous round')
    if review_type == 're-review' and latest and reason == 'corrections' and minor_only_pass(plan, latest[0]):
        reason = 'minor-fixes'
    if review_type == 'initial' and latest and reason == 'corrections':
        raise ValueError('corrections remain re-review; do not relabel rounds')
    if decision and (PENDING.search(decision) or decision.lower() in ('none', 'n/a', '-')):
        raise ValueError('review decision must cite the actual user decision and bounded scope')
    if decision:
        decision = ' '.join(decision.split())
    ids = [int(identifier[1:]) for identifier, _, _ in plan.blocks('Review result', 'G')]
    identifier = f'G{max(ids, default=0) + 1}'
    lines = [f'### {identifier}', '', f'- **Type:** {review_type}',
             f'- **Snapshot:** {snapshot["hash"]}', f'- **Policy snapshot:** {review_policy_hash(plan)}',
             f'- **Previous:** {latest[0] if latest else "none"}', '- **Outcome:** Pending',
             f'- **Reason:** {reason}']
    if decision:
        lines += [f'- **Review decision:** {decision}', f'- **Round cap override:** {decision}',
                  f'- **Decision used:** {identifier}']
    lines += ['', '<details><summary>Manifest</summary>', '', '```json',
              json.dumps(snapshot['manifest'], ensure_ascii=False, sort_keys=True), '```', '', '</details>', '']
    if 'Review result' not in plan.sections:
        raise ValueError('plan has no Review result section')
    _, end = plan.sections['Review result']
    text = '\n'.join(plan.lines[:end] + lines + [''] + plan.lines[end:]) + '\n'
    candidate = Document(path, str(path), text=text)
    if errors := check_review_round_structure(candidate):
        raise ValueError('; '.join(error.message for error in errors))
    path.write_text(text, encoding='utf-8')
    return identifier


def record_result(change: Path, source: str) -> str:
    result_path = safe_path(source, allow_missing=False, allow_absolute=True)
    payload = _parse_json_text(result_path.read_text(encoding='utf-8'))
    if isinstance(payload, dict) and 'result' in payload and 'exit' in payload:
        if payload['exit'] != 0:
            raise ValueError('reviewer process did not exit successfully')
        payload = payload['result']
    if errors := schema_errors(payload, json.loads(schema_path('reviewer').read_text())):
        raise ValueError('invalid reviewer result: ' + '; '.join(errors))
    if payload['verdict'] == 'PASS' and any(f['severity'] in ('BLOCKER', 'IMPORTANT') for f in payload['findings']):
        raise ValueError('reviewer PASS contradicts open BLOCKER/IMPORTANT findings')
    path = change / 'plan.md'
    plan = Document(path, str(path))
    latest = latest_review_round(plan)
    if not latest or latest[2] is None:
        raise ValueError('record a pending round and manifest before review dispatch')
    identifier, fields, manifest = latest
    if fields.get('Snapshot') != manifest_hash(manifest):
        raise ValueError('stored review manifest is corrupt; inspect the original evidence')
    rounds = {key: (start, end) for key, start, end in plan.blocks('Review result', 'G')}
    start, end = rounds[identifier]
    block = '\n'.join(plan.lines[start:end])
    if fields.get('Outcome', '').upper() in ('PASS', 'FAIL'):
        if (fields.get('Reviewer verdict', fields.get('Outcome', '')).upper() == payload['verdict']
                and fields.get('Result digest') == digest(result_path)
                and f'**Result source:** `{source}`' in block):
            return identifier
        raise ValueError('settled review history is immutable; start a new round instead')
    try:
        current_manifest = compute(change, Path.cwd())
    except SnapshotError:
        current_manifest = None
    stale = (fields.get('Policy snapshot') != review_policy_hash(plan) or current_manifest != manifest)
    outcome = 'FAIL' if stale else payload['verdict']
    block = re.sub(r'(- \*\*Outcome:\*\*)[^\n]*', rf'\1 {outcome}', block, count=1)
    block += f'\n- **Reviewer verdict:** {payload["verdict"]}'
    if stale:
        block += ('\n- **Snapshot status:** stale\n'
                  f'- **Superseded by current diff:** {manifest_hash(current_manifest) if current_manifest is not None else "unresolvable; reconcile Review scope"}\n'
                  '- **Stale reason:** executable diff or approval changed during review; returned verdict is preserved but cannot accept current work.\n')
    block += f'\n- **Result source:** `{source}`\n- **Result digest:** {digest(result_path)}\n\n#### Recorded findings\n\n'
    flat = lambda value: ' '.join(value.split())
    block += '\n'.join(f"- {f['severity']} ({identifier}-{i}): {flat(f['location'])} — {flat(f['summary'])}"
                       for i, f in enumerate(payload['findings'], 1)) or '- None.'
    lines = plan.lines[:start] + block.splitlines() + [''] + plan.lines[end:]
    current = Document(path, str(path), text='\n'.join(lines))
    a, b = current.sections['Review result']
    header = '\n'.join(current.lines[a:b])
    spec = Document(change / 'spec.md', 'spec.md')
    values = {'Result': outcome,
              'Reviewed requirements': ', '.join(key for key, _, _ in spec.blocks('Requirements', 'R')),
              'Reviewed tasks': ', '.join(key for key, _, _ in plan.blocks('Tasks', 'T'))}
    for label, value in values.items():
        pattern = rf'(\*\*{label}:\*\*)[^\n]*'
        header = re.sub(pattern, lambda m: m[1] + ' ' + value, header, count=1)
    # Current findings are a projection; each immutable round retains its own findings.
    findings = '### Findings\n\n' + ('\n'.join(f"- {f['severity']}: {flat(f['location'])} — {flat(f['summary'])}" for f in payload['findings']) or '- None.') + '\n\n'
    header = re.sub(r'### Findings\n.*?(?=### |\Z)', lambda _: findings, header, count=1, flags=re.S)
    text = '\n'.join(current.lines[:a] + header.splitlines() + [''] + current.lines[b:]) + '\n'
    checkpoint = f"Review {identifier} {outcome}; " + (
        'returned verdict preserved against stale snapshot; prepare review of the current diff' if stale else
        ('fix the MINOR findings; test/doc-only fixes need no new round, executable fixes take one '
         're-review --reason minor-fixes') if outcome == 'PASS' and payload['findings'] else
        'resolve findings or record a user decision before continuing' if payload['findings'] else 'complete final evidence and archive summary')
    text = re.sub(r'(\*\*Plan checkpoint:\*\*)[^\n]*', lambda m: m[1] + ' ' + checkpoint, text, count=1)
    path.write_text(text, encoding='utf-8')
    return identifier
