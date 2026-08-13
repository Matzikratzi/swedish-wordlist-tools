from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_upos_x import analyze


class AnalyzeSaolUposXTests(unittest.TestCase):
    def test_separates_reference_entries_from_other_x_rows(self) -> None:
        records = [
            {
                "normaliserat_ord": "den",
                "homonr": "0",
                "ordkl": "(hv)",
                "text": "(null)",
                "upos": "X",
                "ord": "de",
                "urspr_lopnr": 10,
                "subnr": 10,
            },
            {
                "normaliserat_ord": "något",
                "homonr": "1",
                "ordkl": "interj.",
                "text": "(null)",
                "upos": "X",
                "ord": "något",
                "urspr_lopnr": 11,
                "subnr": 11,
            },
        ]
        summary, rows = analyze(records)
        self.assertEqual(2, summary["x_rows"])
        self.assertEqual(1, summary["hv_rows"])
        self.assertEqual(1, summary["non_hv_rows"])
        by_word = {row["ord"]: row for row in rows}
        self.assertEqual("reference_entry_zero", by_word["de"]["zero_context"])
        self.assertEqual("not_zero", by_word["något"]["zero_context"])

    def test_zero_row_with_nonzero_same_id_is_variant_context(self) -> None:
        records = [
            {
                "normaliserat_ord": "amarant",
                "homonr": "2",
                "ordkl": "s. +en",
                "text": "+en",
                "upos": "NOUN",
                "ord": "amarant",
                "urspr_lopnr": 20,
                "subnr": 20,
            },
            {
                "normaliserat_ord": "amarant",
                "homonr": "0",
                "ordkl": "(hv)",
                "text": "(null)",
                "upos": "X",
                "ord": "Amarant",
                "urspr_lopnr": 20,
                "subnr": 20,
            },
        ]
        _, rows = analyze(records)
        self.assertEqual("article_variant_zero", rows[0]["zero_context"])


if __name__ == "__main__":
    unittest.main()
