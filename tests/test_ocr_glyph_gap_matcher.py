import unittest

from swedish_wordlist_tools.ocr_glyph_gap_matcher import (
    max_internal_blank_run,
    safe_ink_groups,
    select_best_baseline_partition_by_safe_gaps,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, select_best_baseline_partition


class GlyphGapMatcherTests(unittest.TestCase):
    def test_internal_blank_run_is_measured_from_facit(self):
        models = [
            GlyphModel("k", "bold", frozenset({(0, 0), (1, 0), (4, 0)})),
            GlyphModel("i", "roman", frozenset({(0, -2), (0, 0)})),
        ]
        self.assertEqual(max_internal_blank_run(models), 2)

    def test_source_gap_wider_than_any_internal_gap_splits(self):
        ink = {(0, 0), (1, 0), (5, 0), (6, 0)}
        groups = safe_ink_groups(ink, max_internal_gap=2)
        self.assertEqual([(left, right) for left, right, _local in groups], [(0, 2), (5, 7)])
        self.assertEqual(groups[1][2], {(0, 0), (1, 0)})

    def test_gap_equal_to_internal_gap_does_not_split(self):
        ink = {(0, 0), (1, 0), (4, 0), (5, 0)}
        groups = safe_ink_groups(ink, max_internal_gap=2)
        self.assertEqual([(left, right) for left, right, _local in groups], [(0, 6)])

    def test_grouped_partition_matches_full_partition(self):
        models = [
            GlyphModel("a", "roman", frozenset({(0, 0), (1, 0)}), sources=2),
            GlyphModel("b", "roman", frozenset({(0, 0), (0, -1)}), sources=2),
            # This model proves that one blank column may occur inside a glyph.
            GlyphModel("k", "bold", frozenset({(0, 0), (2, 0)}), sources=1),
        ]
        ink = {
            (0, 1), (1, 1),       # a
            (5, 1), (5, 0),       # b, separated by a provably safe gap
        }
        full_baseline, full = select_best_baseline_partition(ink, 6, 3, models)
        grouped_baseline, grouped, _candidates, groups = select_best_baseline_partition_by_safe_gaps(
            ink, 6, 3, models
        )
        self.assertEqual(len(groups), 2)
        self.assertEqual(grouped_baseline, full_baseline)
        self.assertEqual(
            [(m.label, m.style, m.x, m.baseline, m.pixels) for m in grouped],
            [(m.label, m.style, m.x, m.baseline, m.pixels) for m in full],
        )


if __name__ == "__main__":
    unittest.main()
