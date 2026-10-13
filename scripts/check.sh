#!/usr/bin/env bash
# Run the plugin test suite and, when the Claude CLI is present, validate the manifest.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/render_roles.py --check
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/package_plugin.py --check
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p 'test_*.py' -q
if command -v claude >/dev/null 2>&1 && [ -f .claude-plugin/plugin.json ]; then
  claude plugin validate . --strict
  claude plugin validate .claude-plugin/plugin.json --strict
fi
