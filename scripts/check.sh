#!/usr/bin/env bash
# Run the plugin test suite and, when the Claude CLI is present, validate the manifest.
set -euo pipefail
cd "$(dirname "$0")/.."
python_ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; }
if [[ -z "${PYTHON:-}" ]]; then
  for candidate in python3 python3.14 python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
      PYTHON="$candidate"
      break
    fi
  done
fi
if [[ -z "${PYTHON:-}" ]] || ! python_ok "$PYTHON"; then
  echo "error: routing checks require Python 3.11+; set PYTHON=/path/to/python3.11+" >&2
  exit 1
fi
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/render_roles.py --check
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/package_plugin.py --check
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p 'test_*.py' -q
if command -v claude >/dev/null 2>&1 && [ -f .claude-plugin/plugin.json ]; then
  claude plugin validate . --strict
  claude plugin validate .claude-plugin/plugin.json --strict
fi
