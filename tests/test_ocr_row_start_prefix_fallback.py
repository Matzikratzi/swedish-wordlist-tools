from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_row_start_prefix_fallback import exact_mature_prefix_row_starts


class RowStartPrefixFallbackTest(unittest.TestCase):
    def test_shallow_exact_glyph_can_establish_fallback_start(self):
        tilde = GlyphModel(
            label="~",
            style="italic",
            pixels=frozenset({(1, -1), (0, 0)}),
            sources=1,
        )
        black = {(67, 99), (66, 100), (75, 94), (75, 95), (75, 96)}
        starts = exact_mature_prefix_row_starts(
            black,
            [tilde],
            start_ranges=((61, 75),),
        )
        self.assertTrue(
            any(
                start.label == "~"
                and start.x == 66
                and start.baseline == 100
                and start.steps == 1
                for start in starts
            )
        )

    def test_exact_start_outside_typographic_ranges_is_rejected(self):
        tilde = GlyphModel(
            label="~",
            style="italic",
            pixels=frozenset({(1, -1), (0, 0)}),
            sources=1,
        )
        black = {(91, 99), (90, 100)}
        starts = exact_mature_prefix_row_starts(
            black,
            [tilde],
            start_ranges=((61, 75),),
        )
        self.assertEqual((), starts)


if __name__ == "__main__":
    unittest.main()
