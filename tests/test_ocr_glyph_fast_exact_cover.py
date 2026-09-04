import unittest

from swedish_wordlist_tools.ocr_glyph_gap_matcher import fast_exact_cover
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


class FastExactCoverTests(unittest.TestCase):
    def test_internal_blank_column_does_not_split_glyph(self):
        models = [
            GlyphModel(
                label="k",
                style="bold",
                pixels=frozenset({(0, 0), (2, 0)}),
                sources=3,
            ),
            GlyphModel(
                label="i",
                style="roman",
                pixels=frozenset({(0, -1), (0, 0)}),
                sources=2,
            ),
        ]
        ink = {(1, 2), (3, 2), (5, 1), (5, 2)}

        result = fast_exact_cover(ink, width=7, height=4, models=models)

        self.assertIsNotNone(result)
        baseline, selected, placements_tested = result
        self.assertEqual(2, baseline)
        self.assertEqual("ki", "".join(match.label for match in selected))
        self.assertEqual(ink, set().union(*(match.pixels for match in selected)))
        self.assertGreater(placements_tested, 0)

    def test_incomplete_cover_is_rejected(self):
        models = [
            GlyphModel(
                label="k",
                style="bold",
                pixels=frozenset({(0, 0), (2, 0)}),
                sources=1,
            )
        ]
        ink = {(1, 2), (3, 2), (5, 2)}

        self.assertIsNone(fast_exact_cover(ink, width=7, height=4, models=models))


if __name__ == "__main__":
    unittest.main()
