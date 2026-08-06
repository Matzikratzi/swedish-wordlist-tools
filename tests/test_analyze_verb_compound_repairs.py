from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_verb_compound_repairs import build_report


class AnalyzeVerbCompoundRepairsTests(unittest.TestCase):
    def write_records(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".jsonl", delete=False
        )
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_separates_direct_and_compound_repaired_records(self) -> None:
        path = self.write_records(
            [
                {
                    "normaliserat_ord": "skriva",
                    "upos": "VERB",
                    "text": "skrev, skrivit",
                    "stycke": "skriv·a",
                },
                {
                    "normaliserat_ord": "omskriva",
                    "upos": "VERB",
                    "text": "",
                    "stycke": "om|skriv·a",
                },
            ]
        )
        report = build_report(path)
        self.assertEqual(1, report["directly_interpreted_records"])
        self.assertEqual(1, report["compound_repaired_records"])
        self.assertEqual(2, report["exported_interpreted_records"])
        self.assertTrue(report["arithmetic_matches"])
        self.assertEqual("omskriva", report["records"][0]["lemma"])


if __name__ == "__main__":
    unittest.main()
