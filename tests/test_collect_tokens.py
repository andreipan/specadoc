from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "skills" / "specadoc" / "scripts" / "collect_tokens.py"


def load_module():
    spec = importlib.util.spec_from_file_location("collect_tokens", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CollectTokensTest(unittest.TestCase):
    def test_append_replaces_only_the_selected_mode(self) -> None:
        collect = load_module()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.md"
            plan.write_text(
                "## Completion evidence\n\nExecution tokens:\n"
                "mode=explore old\n"
                "total mode=explore codex 1 run(s) unique=1 read=2\n\n"
                "Review rounds:\nPending\n",
                encoding="utf-8",
            )

            collect.append_to_plan(plan, ["mode=apply new", "total mode=apply codex"], "apply")
            collect.append_to_plan(plan, ["mode=explore replacement"], "explore")

            content = plan.read_text(encoding="utf-8")
            self.assertIn("mode=apply new", content)
            self.assertIn("mode=explore replacement", content)
            self.assertNotIn("mode=explore old", content)


if __name__ == "__main__":
    unittest.main()
