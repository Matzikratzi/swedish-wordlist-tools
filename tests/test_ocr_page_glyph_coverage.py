from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_page_glyph_coverage import (
    compare_available_facit,
    glyph_coverage_report,
    reference_headword_key,
)


class PageGlyphCoverageTests(unittest.TestCase):
    def test_reference_headword_uses_homonr_as_authoritative_number(self) -> None:
        row = {
            "stycke": "<sup>9</sup>a",
            "normaliserat_ord": "a",
            "homonr": "2",
        }
        self.assertEqual(reference_headword_key(row), "2a")

    def test_reference_headword_preserves_printed_base_marks(self) -> None:
        row = {
            "stycke": "<sup>1</sup>ab·c",
            "normaliserat_ord": "abc",
            "homonr": "1",
        }
        self.assertEqual(reference_headword_key(row), "1ab·c")

    def test_null_text_headword_is_still_matched_but_not_text_verified(self) -> None:
        rows = [
            {
                "page": 1,
                "stycke": "<sup>1</sup>a",
                "homonr": "1",
                "text": "a:et; pl. a:n",
            },
            {
                "page": 1,
                "stycke": "<sup>2</sup>a",
                "homonr": "2",
                "text": "(null)",
            },
        ]
        articles = [
            {"stycke": "¹ a", "text": "a:et; pl. a:n extra", "column": 0, "start_row": 4},
            {"stycke": "² a", "text": "", "column": 0, "start_row": 5},
        ]

        report = compare_available_facit(rows, articles, 1)

        self.assertEqual(report["references_total"], 2)
        self.assertEqual(report["references_with_text"], 1)
        self.assertEqual(report["matched_headwords"], 2)
        self.assertEqual(report["matched_with_text"], 1)
        self.assertEqual(report["text_prefix_exact"], 1)
        self.assertEqual(report["unmatched_references"], 0)
        no_text = next(item for item in report["results"] if item["homonr"] == "2")
        self.assertFalse(no_text["has_text"])
        self.assertIsNone(no_text["prefix_exact"])

    def test_text_verification_stops_at_available_jsonl_prefix(self) -> None:
        expected = "x" * 49
        rows = [
            {
                "page": 1,
                "stycke": "ord",
                "homonr": "",
                "text": expected,
            }
        ]
        articles = [
            {
                "stycke": "ord",
                "text": expected + " fortsatt tryckt text som JSONL inte innehåller",
                "column": 0,
                "start_row": 1,
            }
        ]

        report = compare_available_facit(rows, articles, 1)
        self.assertEqual(report["text_prefix_exact"], 1)

    def test_glyph_coverage_counts_all_pixels_independently_of_jsonl(self) -> None:
        columns = [
            [
                {"row": 4, "source_pixels": 100, "covered_pixels": 100},
                {"row": 5, "source_pixels": 80, "covered_pixels": 70},
            ],
            [{"row": 0, "source_pixels": 20, "covered_pixels": 15}],
        ]

        report = glyph_coverage_report(columns)

        self.assertEqual(report["rows_total"], 3)
        self.assertEqual(report["rows_exact"], 1)
        self.assertEqual(report["source_pixels"], 200)
        self.assertEqual(report["covered_pixels"], 185)
        self.assertEqual(report["unknown_pixels"], 15)
        self.assertEqual(
            [(item["column"], item["row"], item["unknown_pixels"]) for item in report["misses"]],
            [(0, 5, 10), (1, 0, 5)],
        )


if __name__ == "__main__":
    unittest.main()
