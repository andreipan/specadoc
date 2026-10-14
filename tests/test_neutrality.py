"""Guard the public plugin against host-specific vocabulary leaking back in."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCANNED = [ROOT / "skills", ROOT / "agents", ROOT / "scripts"]
FORBIDDEN = re.compile(
    r"\brtk\b|serena|\bCRG\b|code-review-graph|phpstorm|engram|\bmem_\w+|"
    r"src/Modules|artisan|phpstan|adraptor|composer|landscape\.json|\bgpt-|"
    r"repo-mcp-router|review-changes|code-writing-guideline|HARNESS\.md|"
    r"migrate:(?:fresh|refresh|reset|rollback)|db:wipe|DB_CONNECTION|DB_DATABASE|xdebug|phpunit",
    re.IGNORECASE,
)


class NeutralityTest(unittest.TestCase):
    def test_no_host_specific_terms(self) -> None:
        hits = []
        for base in SCANNED:
            for path in sorted(base.rglob("*")):
                if path.is_dir() or path.suffix not in {".md", ".py", ".yaml", ".json", ".toml"}:
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if FORBIDDEN.search(line):
                        hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual([], hits, "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
