import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import (
    GlyphModel,
    select_best_baseline_partition,
)


class GenericPartitionTests(unittest.TestCase):
    def test_whole_glyph_beats_fragment_mosaic(self):
        # Whole W uses all six pixels. Two smaller exact fragments can also fit
        # inside the same raster, but the whole exact glyph must dominate.
        w = GlyphModel("W", "bold", frozenset({(0, -1), (0, 0), (1, 0), (2, 0), (3, -1), (3, 0)}), 1)
        left = GlyphModel("|", "bold", frozenset({(0, -1), (0, 0)}), 1)
        right = GlyphModel("|", "bold", frozenset({(0, -1), (0, 0)}), 1)
        ink = {(0, 0), (0, 1), (1, 1), (2, 1), (3, 0), (3, 1)}

        baseline, selected = select_best_baseline_partition(ink, 4, 2, [left, right, w])

        self.assertEqual(baseline, 1)
        self.assertEqual([(m.label, m.x) for m in selected], [("W", 0)])

    def test_x_overlap_is_allowed_when_pixels_do_not_overlap(self):
        # Simulate an italic f reaching into the next glyph's x span. Their
        # bounding x ranges overlap, but their black pixels are disjoint.
        f = GlyphModel("f", "italic", frozenset({(0, -2), (0, -1), (0, 0), (2, -2)}), 1)
        o = GlyphModel("o", "italic", frozenset({(0, -1), (1, -1), (0, 0), (1, 0)}), 1)
        ink = {(0, 0), (0, 1), (0, 2), (2, 0), (1, 1), (2, 1), (1, 2), (2, 2)}

        baseline, selected = select_best_baseline_partition(ink, 3, 3, [f, o])

        self.assertEqual(baseline, 2)
        self.assertEqual([m.label for m in selected], ["f", "o"])
        self.assertEqual(len(set().union(*(m.pixels for m in selected))), len(ink))


if __name__ == "__main__":
    unittest.main()
