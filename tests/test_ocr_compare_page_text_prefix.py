from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_compare_page_text_prefix import (
    canonical_printed_text,
    compare_page,
    text_prefix_matches,
)


class PageTextPrefixComparisonTests(unittest.TestCase):
    def test_canonicalises_jsonl_plus_to_printed_tilde(self) -> None:
        self.assertEqual(canonical_printed_text("+n  abborrar"), "~n abborrar")
        self.assertEqual(canonical_printed_text("<i>+n</i>"), "~n")

    def test_available_jsonl_text_must_match_recovered_prefix(self) -> None:
        self.assertTrue(text_prefix_matches("~n abborrar extra", "+n abborrar"))
        self.assertFalse(text_prefix_matches("~n abborrar", "+n abborrar extra"))
        self.assertFalse(text_prefix_matches("~n abborrar", ""))

    def test_compare_page_matches_headword_and_counts_prefixes(self) -> None:
        rows = [
            {"page": 1, "stycke": "abborre", "text": "+n abborrar"},
            {"page": 1, "stycke": "abessini·er", "text": "+n; pl. +"},
            {"page": 1, "stycke": "saknad", "text": "+en"},
            {"page": 2, "stycke": "annan", "text": "+en"},
        ]
        articles = [
            {"stycke": "abborre", "text": "~n abborrar", "column": 0, "start_row": 1, "fully_exact": True},
            {"stycke": "abessini·er", "text": "~n; pl. ~ mer", "column": 1, "start_row": 2, "fully_exact": True},
        ]
        report = compare_page(rows, articles, 1)
        self.assertEqual(report["references_with_text"], 3)
        self.assertEqual(report["matched_headwords"], 2)
        self.assertEqual(report["text_prefix_exact"], 2)
        self.assertEqual(report["unmatched_references"], 1)


if __name__ == "__main__":
    unittest.main()
