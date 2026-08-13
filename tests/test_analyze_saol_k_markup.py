from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_k_markup import (
    build_analysis,
    classify_k_markup,
)


class AnalyzeSaolKMarkupTests(unittest.TestCase):
    def test_classifies_balanced_and_malformed_markup(self) -> None:
        self.assertIsNone(classify_k_markup("+en"))
        self.assertEqual("balanced", classify_k_markup("+en; <k>nåde</k>"))
        self.assertEqual("balanced", classify_k_markup("<k>x</k> och <k>y</k>"))
        self.assertEqual("malformed", classify_k_markup("+en; <k>nåder<"))
        self.assertEqual("malformed", classify_k_markup("+<k>s</k></k>"))
        self.assertEqual("malformed", classify_k_markup("<k>x"))

    def test_lists_every_record_with_k_markup_without_word_special_cases(self) -> None:
        analysis = build_analysis(
            [
                {
                    "subnr": 1,
                    "normaliserat_ord": "alfa",
                    "homonr": 1,
                    "upos": "NOUN",
                    "text": "+n; <k>xyz</k>",
                },
                {
                    "subnr": 2,
                    "normaliserat_ord": "beta",
                    "homonr": 1,
                    "upos": "VERB",
                    "text": "+de; <k>qrs<",
                },
                {
                    "subnr": 3,
                    "normaliserat_ord": "gamma",
                    "text": "+t",
                },
            ]
        )
        self.assertEqual(2, analysis["records_with_k_markup"])
        self.assertEqual({"balanced": 1, "malformed": 1}, analysis["classification_counts"])
        self.assertEqual(["beta", "alfa"], [row["lemma"] for row in analysis["rows"]])

    def test_deduplicates_duplicate_export_rows(self) -> None:
        record = {
            "subnr": 7,
            "normaliserat_ord": "dublett",
            "text": "+<k>x</k>",
        }
        analysis = build_analysis([record, dict(record)])
        self.assertEqual(1, analysis["records_with_k_markup"])


if __name__ == "__main__":
    unittest.main()
