from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "skills/specadoc/scripts/specadoc_root.py"


def load_module():
    spec = importlib.util.spec_from_file_location("specadoc_root", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ResolveRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.module = load_module()
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("SPECADOC_ROOT", None)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def resolve(self, cli: str | None = None):
        return self.module.resolve_root(cli, self.repo)

    def config(self, text: str) -> None:
        (self.repo / ".specadoc.json").write_text(text, encoding="utf-8")

    def test_default_when_nothing_exists(self) -> None:
        self.assertEqual(("docs/specadoc", "default"), tuple(self.resolve()))

    def test_legacy_only_when_new_root_is_absent(self) -> None:
        (self.repo / "docs/agent").mkdir(parents=True)
        choice = self.resolve()
        self.assertEqual(("docs/agent", "legacy"), tuple(choice))
        self.assertIn("migrate_root.py", self.module.legacy_warning(choice))

        (self.repo / "docs/specadoc").mkdir()
        choice = self.resolve()
        self.assertEqual(("docs/specadoc", "default"), tuple(choice))
        self.assertIsNone(self.module.legacy_warning(choice))

    def test_precedence_cli_env_config(self) -> None:
        (self.repo / "docs/agent").mkdir(parents=True)
        self.config('{"root": "specs/sd/"}')
        self.assertEqual(("specs/sd", "config"), tuple(self.resolve()))

        os.environ["SPECADOC_ROOT"] = "from-env"
        self.assertEqual(("from-env", "env"), tuple(self.resolve()))

        self.assertEqual(("from-cli", "cli"), tuple(self.resolve("from-cli/")))

    def test_broken_config_is_an_error(self) -> None:
        self.config("{not json")
        with self.assertRaisesRegex(ValueError, "cannot read Specadoc config"):
            self.resolve()
        self.config('{"other": 1}')
        with self.assertRaisesRegex(ValueError, "expected"):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
