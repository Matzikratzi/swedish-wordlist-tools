from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_profile_gap_filter import horizontal_blank_bands_clear
from swedish_wordlist_tools.ocr_whole_column_profile import ProfileExactHit


def hit_for_i() -> ProfileExactHit:
    model = GlyphModel(
        label="i",
        style="unknown",
        pixels=frozenset({(0, -3), (0, -1), (0, 0), (1, 0)}),
    )
    return ProfileExactHit(
        model=model,
        x=57,
        baseline=20,
        profile_start_y=17,
        profile_end_y=20,
        profile_rows=4,
        profile_ink_rows=3,
    )


class ProfileGapFilterTest(unittest.TestCase):
    def test_i_gap_must_be_empty_across_glyph_width(self):
        hit = hit_for_i()
        black = {(57 + x, 20 + y) for x, y in hit.model.pixels}
        self.assertTrue(horizontal_blank_bands_clear(black, hit))

        black.add((58, 18))
        self.assertFalse(horizontal_blank_bands_clear(black, hit))

    def test_ink_beyond_glyph_width_does_not_fill_i_gap(self):
        hit = hit_for_i()
        black = {(57 + x, 20 + y) for x, y in hit.model.pixels}
        black.add((60, 18))
        self.assertTrue(horizontal_blank_bands_clear(black, hit))


if __name__ == "__main__":
    unittest.main()
