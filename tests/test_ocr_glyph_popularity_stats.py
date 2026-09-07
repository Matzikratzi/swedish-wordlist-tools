from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_glyph_popularity_stats import (
    popularity_report,
    record_model_hit,
    register_bucket,
    reset_popularity_stats,
)


class GlyphPopularityStatsTests(unittest.TestCase):
    def setUp(self):
        reset_popularity_stats()

    def test_reports_current_and_popularity_weighted_rank(self):
        a = GlyphModel("a", "roman", frozenset({(0, 0)}), 1)
        b = GlyphModel("b", "roman", frozenset({(0, 0), (1, 0)}), 1)
        c = GlyphModel("c", "roman", frozenset({(0, 0), (0, 1)}), 1)
        rows = (
            (a, 0, ((0, 0),)),
            (b, 0, ((0, 0),)),
            (c, 0, ((0, 0),)),
        )
        register_bucket("roman", rows, typography_of=str)
        for _ in range(1):
            record_model_hit(a)
        for _ in range(2):
            record_model_hit(b)
        for _ in range(7):
            record_model_hit(c)

        report = popularity_report(top_n=3)

        self.assertEqual(len(report), 1)
        row = report[0]
        self.assertEqual(row["bucket"], "roman")
        self.assertEqual(row["hits"], 10)
        self.assertAlmostEqual(row["current_avg_rank"], 2.6)
        self.assertAlmostEqual(row["popularity_avg_rank"], 1.4)
        self.assertAlmostEqual(row["rank_factor"], 2.6 / 1.4)
        self.assertEqual(
            [(item["label"], item["hits"], item["current_rank"], item["popularity_rank"]) for item in row["top"]],
            [("c", 7, 3, 1), ("b", 2, 2, 2), ("a", 1, 1, 3)],
        )


if __name__ == "__main__":
    unittest.main()
