"""Keep the human documentation in step with the skill and with its translation."""
from __future__ import annotations

import importlib.util
import os
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
LINK = re.compile(r'\]\(([^)\s]+)\)')
MODE = re.compile(r'^- `(\w+) <', re.MULTILINE)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def documents() -> list[Path]:
    top = [ROOT / name for name in ('README.md', 'README.ru.md', 'CHANGELOG.md', 'CHANGELOG.ru.md')]
    return [p for p in top if p.is_file()] + sorted((ROOT / 'docs').rglob('*.md'))


def anchors(path: Path) -> set[str]:
    """GitHub heading anchors of a Markdown file, with -1, -2 suffixes for repeats."""
    text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.DOTALL)
    seen: dict[str, int] = {}
    result = set()
    for heading in re.findall(r'^#{1,6} +(.+?) *#*$', text, re.MULTILINE):
        heading = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', heading)
        slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug if count == 0 else f'{slug}-{count}')
    return result


class DocsTest(unittest.TestCase):
    def test_russian_translation_is_complete_and_current(self):
        problems = load('docs_sync').check(ROOT)
        self.assertEqual([], problems, '\n'.join(problems))

    def test_stale_translation_is_reported_and_stamp_fixes_it(self):
        sync = load('docs_sync')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'docs/en').mkdir(parents=True)
            (root / 'docs/ru').mkdir(parents=True)
            for name in ('README', 'CHANGELOG'):
                (root / f'{name}.md').write_text('# EN\n')
                (root / f'{name}.ru.md').write_text('# RU\n')
                sync.stamp(root / f'{name}.ru.md', root)
            (root / 'docs/en/a.md').write_text('# A\n')
            (root / 'docs/ru/a.md').write_text('# А\n')
            self.assertEqual(['docs/ru/a.md: first line must be <!-- source-sha256: ... -->'], sync.check(root))
            sync.stamp(root / 'docs/ru/a.md', root)
            self.assertEqual([], sync.check(root))
            (root / 'docs/en/a.md').write_text('# A changed\n')
            self.assertEqual(['docs/ru/a.md: stale, docs/en/a.md changed after the translation'], sync.check(root))
            (root / 'docs/en/b.md').write_text('# B\n')
            self.assertIn('docs/en/b.md: no Russian translation docs/ru/b.md', sync.check(root))

    def test_every_script_has_a_reference_entry(self):
        reference = (ROOT / 'docs/en/reference/scripts.md').read_text(encoding='utf-8')
        scripts = sorted((ROOT / 'skills/specadoc/scripts').glob('*.py'))
        scripts += sorted((ROOT / 'skills/orchestrator/scripts').glob('*.py'))
        missing = [p.name for p in scripts if f'## {p.name}' not in reference]
        self.assertEqual([], missing, 'add a "## <name>.py" section to docs/en/reference/scripts.md')

    def test_every_mode_is_documented(self):
        modes = MODE.findall((ROOT / 'skills/specadoc/SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('light', modes)
        for path in (ROOT / 'README.md', ROOT / 'docs/en/reference/modes.md'):
            text = path.read_text(encoding='utf-8')
            missing = [m for m in modes if f'`{m}' not in text]
            self.assertEqual([], missing, f'{path.relative_to(ROOT)} misses modes')

    def test_relative_links_and_anchors_resolve(self):
        broken = []
        for path in documents():
            text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.DOTALL)
            for target in LINK.findall(text):
                if target.startswith(('http://', 'https://', 'mailto:')):
                    continue
                file_part, _, anchor = target.partition('#')
                linked = (path.parent / file_part) if file_part else path
                if not linked.exists():
                    broken.append(f'{path.relative_to(ROOT)}: {target}')
                elif anchor and linked.suffix == '.md' and anchor not in anchors(linked):
                    broken.append(f'{path.relative_to(ROOT)}: {target} (no such heading)')
        self.assertEqual([], broken, '\n'.join(broken))

    def test_each_document_links_its_other_language(self):
        sync = load('docs_sync')
        missing = []
        for en, ru in sync.pairs(ROOT):
            for source, other in ((en, ru), (ru, en)):
                if not source.is_file():
                    continue
                head = '\n'.join(source.read_text(encoding='utf-8').splitlines()[:6])
                if os.path.relpath(other, source.parent) not in head:
                    missing.append(source.relative_to(ROOT).as_posix())
        self.assertEqual([], missing, 'put the language switch link near the top')


if __name__ == '__main__':
    unittest.main()
