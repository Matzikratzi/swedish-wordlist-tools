import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.saldo_form_artifact import (
    build_form_index,
    is_saldo_word_form,
    read_saldo_forms,
)


class SaldoFormArtifactFilteringTests(unittest.TestCase):
    def test_only_trailing_hyphen_is_rejected(self):
        self.assertFalse(is_saldo_word_form("fot-"))
        self.assertFalse(is_saldo_word_form("fots-"))
        self.assertTrue(is_saldo_word_form("g:et"))
        self.assertTrue(is_saldo_word_form("g-et"))
        self.assertTrue(is_saldo_word_form("cd-rom"))

    def test_reader_filters_old_artifacts_defensively(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saldo.jsonl"
            path.write_text(json.dumps({
                "id": "x",
                "upos": "NOUN",
                "lemmas": ["fot"],
                "forms": ["fot", "foten", "fot-", "fots-", "g:et"],
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            saldo = read_saldo_forms(path)
            forms = next(iter(saldo["fot"]))["forms"] if False else saldo["fot"][0]["forms"]
            self.assertEqual({"fot", "foten", "g:et"}, forms)
            index = build_form_index(saldo)
            self.assertNotIn("fot-", index)
            self.assertNotIn("fots-", index)
            self.assertIn("fot", index)


if __name__ == "__main__":
    unittest.main()
