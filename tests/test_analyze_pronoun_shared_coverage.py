from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_pronoun_shared_coverage import analyze
from swedish_wordlist_tools.pronoun_shared_interpreter import interpret_pronoun_row


class AnalyzePronounSharedCoverageTests(unittest.TestCase):
    def test_missing_primary_text_is_not_recovered_from_notation(self) -> None:
        record = {
            "normaliserat_ord": "någon",
            "upos": "PRON",
            "text": None,
            "notation": "något några",
        }
        self.assertIsNone(interpret_pronoun_row(record))
        report = analyze([record])
        self.assertEqual(1, report["pronoun_records"])
        self.assertEqual(0, report["text_records"])
        self.assertEqual(1, report["no_text_records"])
        self.assertEqual(0, report["shared_records"])

    def test_primary_text_is_counted_and_interpreted(self) -> None:
        record = {
            "normaliserat_ord": "din",
            "upos": "PRON",
            "text": "ditt dina",
        }
        report = analyze([record])
        self.assertEqual(1, report["text_records"])
        self.assertEqual(1, report["shared_records"])
        self.assertEqual(100.0, report["coverage_percent"])


if __name__ == "__main__":
    unittest.main()
