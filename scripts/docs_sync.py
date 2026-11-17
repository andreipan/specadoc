#!/usr/bin/env python3
"""Check that the Russian documentation matches its English source, or stamp it after translation.

Every English document has a Russian counterpart at the same relative path
(docs/en/X.md -> docs/ru/X.md; README.md -> README.ru.md; CHANGELOG.md ->
CHANGELOG.ru.md). The first line of each Russian file records the SHA-256 of
the English file it was translated from:

    <!-- source-sha256: <hex> -->

When the English file changes, the hash no longer matches and --check reports
the Russian file as stale. Update the translation, then run --stamp on it.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_PAIRS = (('README.md', 'README.ru.md'), ('CHANGELOG.md', 'CHANGELOG.ru.md'))
STAMP = re.compile(r'\A<!-- source-sha256: ([0-9a-f]{64}) -->\n')


def pairs(root: Path = ROOT) -> list[tuple[Path, Path]]:
    """Return (english, russian) pairs; a missing side is still listed."""
    result = [(root / en, root / ru) for en, ru in TOP_PAIRS]
    en_docs, ru_docs = root / 'docs/en', root / 'docs/ru'
    names = {p.relative_to(en_docs) for p in en_docs.rglob('*.md')} if en_docs.is_dir() else set()
    names |= {p.relative_to(ru_docs) for p in ru_docs.rglob('*.md')} if ru_docs.is_dir() else set()
    result += [(en_docs / name, ru_docs / name) for name in sorted(names)]
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(root: Path = ROOT) -> list[str]:
    problems = []
    for en, ru in pairs(root):
        en_name, ru_name = en.relative_to(root).as_posix(), ru.relative_to(root).as_posix()
        if not en.is_file() and not ru.is_file():
            problems.append(f'{en_name}: missing, and so is {ru_name}')
            continue
        if not en.is_file():
            problems.append(f'{ru_name}: no English source {en_name}')
            continue
        if not ru.is_file():
            problems.append(f'{en_name}: no Russian translation {ru_name}')
            continue
        match = STAMP.match(ru.read_text(encoding='utf-8'))
        if not match:
            problems.append(f'{ru_name}: first line must be <!-- source-sha256: ... -->')
        elif match.group(1) != digest(en):
            problems.append(f'{ru_name}: stale, {en_name} changed after the translation')
    return problems


def stamp(ru: Path, root: Path = ROOT) -> None:
    ru = ru.resolve()
    sources = {r.resolve(): e for e, r in pairs(root)}
    if ru not in sources or not sources[ru].is_file():
        raise ValueError(f'{ru}: not a Russian document with an English source')
    text = ru.read_text(encoding='utf-8')
    body = STAMP.sub('', text, count=1)
    ru.write_text(f'<!-- source-sha256: {digest(sources[ru])} -->\n{body}', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--stamp', nargs='+', type=Path, metavar='RU_FILE',
                        help='record the current English hash in these Russian files')
    args = parser.parse_args()
    if args.stamp:
        try:
            for path in args.stamp:
                stamp(path)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
    problems = check()
    print('\n'.join(problems) if problems else 'Documentation EN/RU: OK')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
