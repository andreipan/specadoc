#!/usr/bin/env python3
"""Opt-in offline Codex pilot in temporary HOME/CODEX_HOME; no model turns.

Installs from a release ZIP, checks fresh app-server discovery and cache helpers,
reinstalls an updated local source, then removes it. Never touches user config.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from package_plugin import ROOT, SKILLS, build

VERSION = json.loads((ROOT / 'plugin.json').read_text())['version']


def run(command, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'{command}: {result.stdout}\n{result.stderr}')
    return result.stdout


def discover(project, env, base):
    with (base / 'server.stderr').open('w') as stderr:
        process = subprocess.Popen(['codex', 'app-server', '--stdio'],
                                   cwd=project, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=stderr, text=True)
        messages = queue.Queue()
        def read():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    continue
            messages.put({'error': 'app-server exited'})
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        def rpc(identifier, method, params):
            process.stdin.write(json.dumps({'id': identifier, 'method': method, 'params': params}) + '\n')
            process.stdin.flush()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                response = messages.get(timeout=max(0.1, deadline - time.monotonic()))
                if response.get('id') == identifier:
                    if 'error' in response:
                        raise RuntimeError(f'{method}: {response["error"]}')
                    return response['result']
            raise TimeoutError(method)
        try:
            initialized = rpc(1, 'initialize', {'clientInfo': {'name': 'specadoc-pilot', 'version': VERSION},
                                               'capabilities': {'experimentalApi': True}})
            process.stdin.write('{"method":"initialized"}\n')
            process.stdin.flush()
            thread = rpc(2, 'thread/start', {'cwd': str(project), 'ephemeral': True})
            listing = rpc(3, 'skills/list', {'cwds': [str(project)], 'forceReload': True})
            skills = [s for entry in listing['data'] for s in entry['skills']
                      if s.get('pluginId') == 'specadoc@specadoc']
            return {'client': initialized['userAgent'], 'newThread': bool(thread['thread']['id']),
                    'skills': skills}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            reader.join(timeout=2)


def pilot():
    report = {'checks': [], 'gaps': ['No model inference turns or desktop UI interactions in this offline pilot.']}
    with tempfile.TemporaryDirectory(prefix='specadoc-codex-pilot-') as directory:
        base = Path(directory).resolve()
        project = base / 'project'
        project.mkdir()
        home = base / 'codex-home'
        home.mkdir()
        user = base / 'user'
        user.mkdir()
        env = dict(os.environ, HOME=str(user), CODEX_HOME=str(home))
        # Do not inherit credentials for a pilot that makes no model requests.
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
            env.pop(key, None)
        build(ROOT, base / 'release.zip')
        source = base / 'plugin'
        with zipfile.ZipFile(base / 'release.zip') as archive:
            archive.extractall(source)
        marketplace = source / '.agents/plugins'
        marketplace.mkdir(parents=True)
        (marketplace / 'marketplace.json').write_bytes((ROOT / '.agents/plugins/marketplace.json').read_bytes())
        run(['codex', 'plugin', 'marketplace', 'add', str(source)], project, env)
        installed = json.loads(run(['codex', 'plugin', 'add', 'specadoc@specadoc', '--json'], project, env))
        cache = Path(installed['installedPath'])
        assert cache.is_relative_to(home), 'cache escaped isolated CODEX_HOME'
        assert cache != source
        report['version'] = installed['version']
        report['checks'].append('Marketplace add and plugin install from release ZIP: PASS')
        found = discover(project, env, base)
        report['client'] = found['client']
        assert found['newThread']
        expected = {'specadoc:' + name for name in SKILLS}
        assert {s['name'] for s in found['skills']} == expected
        assert all(Path(s['path']).is_relative_to(cache) and s['enabled'] for s in found['skills'])
        report['skills'] = sorted(expected)
        report['checks'].append('Fresh ephemeral chat and four cache-backed skills: PASS')
        policy = cache / 'skills/specadoc/agents/openai.yaml'
        assert 'allow_implicit_invocation: false' in policy.read_text()
        report['checks'].append('Installed explicit-only policy preserved: PASS (configuration, not model routing)')
        scripts = cache / 'skills/specadoc/scripts'
        for script in sorted(scripts.glob('*.py')):
            if script.name != 'specadoc_root.py':
                run([sys.executable, '-B', str(script), '--help'], project, env)
        run([sys.executable, '-B', str(scripts / 'init_change.py'), 'pilot'], project, env)
        assert (project / 'docs/specadoc/pilot/spec.md').is_file()
        report['checks'].append('Eight cached CLI helpers and artifact initialization: PASS')
        marker = '\nLocal pilot update marker.\n'
        readme = source / 'README.md'
        readme.write_text(readme.read_text() + marker)
        assert marker not in (cache / 'README.md').read_text()
        # marketplace upgrade refreshes Git sources, not local directories.
        run(['codex', 'plugin', 'remove', 'specadoc@specadoc', '--json'], project, env)
        run(['codex', 'plugin', 'add', 'specadoc@specadoc', '--json'], project, env)
        assert marker in (cache / 'README.md').read_text()
        assert {s['name'] for s in discover(project, env, base)['skills']} == expected
        report['checks'].append('Local update/reinstall and fresh discovery: PASS')
        run(['codex', 'plugin', 'remove', 'specadoc@specadoc', '--json'], project, env)
        assert not cache.exists()
        assert not discover(project, env, base)['skills']
        run(['codex', 'plugin', 'marketplace', 'remove', 'specadoc'], project, env)
        report['checks'].append('Plugin removal, cache removal, absent discovery and marketplace removal: PASS')
        report['checks'].append('Temporary HOME/CODEX_HOME only; no public upload, no credentials: PASS')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Save concise evidence as JSON')
    args = parser.parse_args()
    report = pilot()
    text = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
