#!/usr/bin/env python3
"""Render Claude adapters from the portable role contracts; --check is read-only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def adapters(root: Path = ROOT) -> dict[Path, str]:
    metadata = json.loads((root / 'scripts/claude-roles.json').read_text())
    result = {}
    for name in ('scout', 'worker', 'reviewer'):
        front = '\n'.join(f'{key}: {value}' for key, value in metadata[name].items())
        body = (root / f'skills/specadoc/references/roles/{name}.md').read_text()
        result[root / f'agents/{name}.md'] = (
            f'---\n{front}\n---\n\n'
            '<!-- Generated adapter: edit the portable role contract, then run scripts/render_roles.py. -->\n\n'
            + body
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = []
    for path, content in adapters().items():
        if args.check:
            if not path.is_file() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content, encoding='utf-8')
    if stale:
        print('Stale adapters: ' + ', '.join(stale))
        return 1
    print('Claude role adapters: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
