from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_verb_hv import build_report


class AnalyzeVerbHvTests(unittest.TestCase):
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

    def test_matches_hv_form_to_generated_verb_form(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "glädjas",
                "homonr": "1",
                "ordkl": "v.",
                "upos": "VERB",
                "text": "gladdes, glatts, pres. gläds, imper. gläds",
                "stycke": "glädjas",
                "ord": "glädjas",
            },
            {
                "normaliserat_ord": "glädjas",
                "homonr": "0",
                "ordkl": "(hv)",
                "upos": "X",
                "text": "(null)",
                "stycke": "gladdes",
                "ord": "gladdes",
            },
        ])

        report = build_report(path)

        self.assertEqual(1, report["verb_targeted_hv_records"])
        self.assertEqual(1, report["matched_generated_verb_forms"])
        self.assertEqual(100.0, report["coverage_percent"])
        self.assertEqual("matched_generated_verb_form", report["records"][0]["status"])

    def test_reports_missing_hv_form_without_adding_it(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "testa",
                "homonr": "1",
                "ordkl": "v.",
                "upos": "VERB",
                "text": "+de +t",
                "stycke": "testa",
                "ord": "testa",
            },
            {
                "normaliserat_ord": "testa",
                "homonr": "0",
                "ordkl": "(hv)",
                "upos": "X",
                "text": "(null)",
                "stycke": "testades",
                "ord": "testades",
            },
        ])

        report = build_report(path)

        self.assertEqual(0, report["matched_generated_verb_forms"])
        self.assertEqual(
            "missing_from_generated_verb_forms",
            report["records"][0]["status"],
        )
        self.assertNotIn("testades", report["records"][0]["generated_forms"])

    def test_ignores_hv_targeting_nonverb_lemma(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "akne",
                "homonr": "1",
                "ordkl": "(hv)",
                "upos": "X",
                "text": "(null)",
                "stycke": "acne",
                "ord": "acne",
            }
        ])

        report = build_report(path)
        self.assertEqual(0, report["verb_targeted_hv_records"])


if __name__ == "__main__":
    unittest.main()
