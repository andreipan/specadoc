#!/usr/bin/env python3
"""Validate the portable package and build a deterministic, allowlisted ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('specadoc', 'tidy', 'codebase-design', 'domain-modeling')
TOP_FILES = ('plugin.json', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise ValueError(f'{path}: missing frontmatter')
    front = text.split('---\n', 2)[1]
    return {k.strip(): v.strip().strip('"\'') for k, _, v in
            (line.partition(':') for line in front.splitlines())}


def resources(root: Path) -> list[Path]:
    paths = [root / name for name in TOP_FILES]
    for name in SKILLS:
        for path in sorted((root / 'skills' / name).rglob('*')):
            relative = path.relative_to(root)
            if '__pycache__' in relative.parts or path.name == '.DS_Store' or path.suffix == '.pyc':
                continue
            if path.is_symlink():
                raise ValueError(f'non-portable symlink: {relative}')
            if path.is_file():
                paths.append(path)
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'missing or non-portable resource: {path.relative_to(root)}')
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def validate(root: Path = ROOT) -> list[str]:
    errors = []
    try:
        manifest = json.loads((root / 'plugin.json').read_text())
        claude = json.loads((root / '.claude-plugin/plugin.json').read_text())
        for field in ('name', 'version', 'description', 'author', 'license', 'keywords'):
            if not manifest.get(field) or manifest[field] != claude.get(field):
                errors.append(f'manifest mismatch or missing {field}')
        if manifest.get('$schema') != 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json':
            errors.append('unsupported portable schema')
        if not re.fullmatch(r'\d+\.\d+\.\d+', manifest.get('version', '')):
            errors.append('version must be SemVer')
        extension = manifest.get('extensions', {}).get('com.openai', {})
        if any(key in extension for key in ('hooks', 'apps', 'mcpServers')):
            errors.append('skills-only package must not declare hooks or MCP')
        interface = extension.get('interface', {})
        for field in ('displayName', 'shortDescription', 'developerName', 'category'):
            if not interface.get(field):
                errors.append(f'missing interface.{field}')
        marketplace = json.loads((root / '.agents/plugins/marketplace.json').read_text())
        entries = marketplace.get('plugins', [])
        if marketplace.get('name') != 'specadoc' or len(entries) != 1:
            errors.append('expected one specadoc marketplace entry')
        else:
            entry = entries[0]
            if (entry.get('name') != manifest['name'] or
                    entry.get('source') != {'source': 'local', 'path': './'} or
                    entry.get('policy') != {'installation': 'AVAILABLE', 'authentication': 'ON_USE'} or
                    entry.get('category') != 'Productivity'):
                errors.append('invalid marketplace source/policy/category')
        if {p.name for p in (root / 'skills').iterdir() if p.is_dir()} != set(SKILLS):
            errors.append('unexpected skill bundle')
        for name in SKILLS:
            skill = root / 'skills' / name
            meta = frontmatter(skill / 'SKILL.md')
            if meta.get('name') != name or not meta.get('description'):
                errors.append(f'{name}: invalid name/description')
            for path in skill.rglob('*.md'):
                for ref in re.findall(r'`((?:references|scripts|assets|roles)/[^`\s<>]+)`', path.read_text()):
                    base = path.parent if ref.startswith('roles/') else skill
                    if not (base / ref).is_file():
                        errors.append(f'{path.relative_to(root)}: missing {ref}')
        policy = (root / 'skills/specadoc/agents/openai.yaml').read_text()
        if not re.search(r'allow_implicit_invocation:\s*false\b', policy):
            errors.append('Specadoc must remain explicit-only')
        for role in ('scout', 'worker', 'reviewer'):
            if not (root / f'skills/specadoc/references/roles/{role}.md').is_file():
                errors.append(f'missing portable {role} contract')
        resources(root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
    return errors


def build(root: Path, destination: Path) -> str:
    errors = validate(root)
    if errors:
        raise ValueError('\n'.join(errors))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in resources(root):
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100644 << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without writing a ZIP')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    errors = validate()
    if errors:
        print('\n'.join(errors))
        return 1
    if args.check:
        print('Portable plugin and marketplace: OK')
    else:
        version = json.loads((ROOT / 'plugin.json').read_text())['version']
        destination = args.output or ROOT / 'dist' / f'specadoc-{version}.zip'
        digest = build(ROOT, destination)
        print(f'{destination}\nsha256:{digest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
