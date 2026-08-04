from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_verb_forms import build_verb_forms


class ExportVerbFormsTests(unittest.TestCase):
    def write_jsonl(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return Path(handle.name)

    def test_default_export_is_saol_only(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "skriva",
                "text": "skrev, skrivit, skriven skrivet skrivna, pres. skriver",
                "stycke": "skriva",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])
        self.addCleanup(path.unlink)

        words, report = build_verb_forms(path)

        self.assertEqual("SAOL14", report["source"])
        self.assertFalse(report["include_saldo"])
        self.assertIn("skriva", words)
        self.assertIn("skrev", words)
        self.assertIn("skrivit", words)
        self.assertIn("skriven", words)
        self.assertIn("skrivet", words)
        self.assertIn("skrivna", words)
        self.assertIn("skriver", words)
        self.assertNotIn("saldo", report["unique_forms_by_provenance"])

    def test_rejects_multiword_and_nonalphabetic_forms_for_game_export(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "loma av",
                "text": None,
                "stycke": "loma",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])
        self.addCleanup(path.unlink)

        words, report = build_verb_forms(path)

        self.assertEqual([], words)
        self.assertEqual(0, report["unique_playable_forms"])


if __name__ == "__main__":
    unittest.main()
