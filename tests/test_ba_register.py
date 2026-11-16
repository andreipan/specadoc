"""The BA register: one numbered file of analyst questions, divergences and decisions (run 6.11-6.15)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "skills/orchestrator/scripts/ba_register.py"

REGISTER = """# Вопросы для обсуждения с BA — единый реестр

Правила реестра: номер не меняется.

# Этап 6

## 16. `balance` nullable (6.10)

**Тип:** расхождение с Confluence · **Статус:** сделано по умолчанию, ждёт BA (D85)

Текст пункта.

## 24. Delete connection (6.14)

**Тип:** расхождение с Confluence · **Статус:** открыт

# Следующие этапы

## 33. Клиент при удалении организации (8.1)

**Тип:** неясность в источнике · **Статус:** перенесён на этап 8.1
"""


class BaRegisterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ba-questions.md"
        self.path.write_text(REGISTER, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True)

    def test_add_takes_the_next_number_and_the_file_labels(self) -> None:
        result = self.run_cli("add", str(self.path), "--title", "NotFound на удаление business", "--step", "6.13",
                              "--type", "неясность в источнике", "--status", "сделано по умолчанию, ждёт BA (D98)",
                              "--section", "Этап 6", "--file", "-", stdin="Hub отвечает NotFound.\n")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("34", result.stdout)
        text = self.path.read_text(encoding="utf-8")
        item = text.split("## 34. NotFound на удаление business (6.13)", 1)[1]
        self.assertTrue(item.startswith("\n\n**Тип:** неясность в источнике · **Статус:** сделано по умолчанию, ждёт BA (D98)"))
        self.assertIn("Hub отвечает NotFound.", item.split("# Следующие этапы")[0])
        self.assertLess(text.index("## 34."), text.index("# Следующие этапы"))

    def test_status_changes_in_place_and_keeps_the_item(self) -> None:
        result = self.run_cli("status", str(self.path), "24", "--status", "закрыт BA (2026-11-20)",
                              "--note", "BA: так и оставить")
        self.assertEqual(0, result.returncode, result.stderr)
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("## 24. Delete connection (6.14)\n\n**Тип:** расхождение с Confluence · **Статус:** закрыт BA (2026-11-20)", text)
        self.assertIn("BA: так и оставить", text.split("## 24.", 1)[1].split("# Следующие этапы")[0])
        self.assertEqual(1, text.count("## 24."))

    def test_unknown_number_is_refused(self) -> None:
        result = self.run_cli("status", str(self.path), "99", "--status", "открыт")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("no item 99", result.stderr)

    def test_list_filters_by_status(self) -> None:
        result = self.run_cli("list", str(self.path), "--status", "ждёт BA")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("16.", result.stdout)
        self.assertNotIn("33.", result.stdout)

    def test_a_new_register_uses_english_labels(self) -> None:
        empty = Path(self.temp.name) / "new.md"
        empty.write_text("# Analyst register\n", encoding="utf-8")
        result = self.run_cli("add", str(empty), "--title", "Nullable balance", "--step", "6.10",
                              "--type", "divergence from the wiki", "--status", "open")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("## 1. Nullable balance (6.10)\n\n**Type:** divergence from the wiki · **Status:** open",
                      empty.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
