from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_prefix_hypotheses import (
    build_prefix_index,
    scan_prefix_candidate_lifetimes,
)


class LeftEdgePrefixHypothesesTest(unittest.TestCase):
    def test_prefix_index_can_start_inside_glyph(self):
        glyph = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({
                (2, -4),
                (1, -3),
                (1, -2),
                (0, -1),
                (0, 0),
            }),
            sources=1,
        )
        index = build_prefix_index([glyph])
        self.assertTrue(index.candidates(((1, 0), (1, -1))))

    def test_candidate_is_tested_only_when_its_vertical_extent_finishes(self):
        short = GlyphModel(
            label="~",
            style="italic",
            pixels=frozenset({(1, 0), (0, 1)}),
            sources=1,
        )
        tall = GlyphModel(
            label="l",
            style="roman",
            pixels=frozenset({(1, 0), (0, 1), (0, 2), (0, 3)}),
            sources=1,
        )
        index = build_prefix_index([short, tall])
        rows = ((10, 51), (11, 50), (12, 50), (13, 50))
        black = {
            (51, 10), (50, 11),  # exact short model at tx=50, baseline=10
            (50, 12), (50, 13),
        }
        runs = scan_prefix_candidate_lifetimes(rows, black=black, index=index)
        self.assertEqual(1, len(runs))
        tests = runs[0].mature_tests
        short_tests = [test for test in tests if test.model.label == "~"]
        tall_tests = [test for test in tests if test.model.label == "l"]
        self.assertEqual(1, len(short_tests))
        self.assertEqual(1, short_tests[0].source_end_row)
        self.assertTrue(short_tests[0].exact)
        self.assertEqual(1, len(tall_tests))
        self.assertEqual(3, tall_tests[0].source_end_row)

    def test_full_raster_miss_rejects_mature_contour_candidate(self):
        glyph = GlyphModel(
            label="B",
            style="bold",
            pixels=frozenset({(0, 0), (0, 1), (0, 2), (2, 1)}),
            sources=1,
        )
        index = build_prefix_index([glyph])
        rows = ((20, 60), (21, 60), (22, 60))
        # Left contour is perfect, but the right-hand B pixel is absent.
        black = {(60, 20), (60, 21), (60, 22)}
        runs = scan_prefix_candidate_lifetimes(rows, black=black, index=index)
        tests = [test for run in runs for test in run.mature_tests]
        self.assertEqual(1, len(tests))
        self.assertFalse(tests[0].exact)

    def test_impossible_extension_drops_old_run_and_restarts_at_boundary(self):
        first = GlyphModel(
            label="n",
            style="roman",
            pixels=frozenset({(0, 0), (1, 1), (1, 2)}),
            sources=1,
        )
        second = GlyphModel(
            label="~",
            style="italic",
            pixels=frozenset({(1, 0), (0, 1), (2, 2)}),
            sources=1,
        )
        index = build_prefix_index([first, second])
        rows = ((10, 50), (11, 51), (12, 51), (13, 58), (14, 57), (15, 59))
        black = set()
        runs = scan_prefix_candidate_lifetimes(rows, black=black, index=index)
        self.assertGreaterEqual(len(runs), 2)
        self.assertEqual(((1, 1), (1, 0)), runs[0].relations)
        self.assertEqual(((1, -1), (1, 2)), runs[-1].relations)
        self.assertEqual(3, runs[-1].source_start_row)


if __name__ == "__main__":
    unittest.main()
