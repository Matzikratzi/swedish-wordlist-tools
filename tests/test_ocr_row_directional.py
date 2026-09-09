from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_baseline_up import CompiledGlyphLibrary, ResidualInk
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_row_directional import first_glyph_top_down


class RowDirectionalTests(unittest.TestCase):
    def test_ignores_ink_before_valid_start_x(self) -> None:
        model = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, -2), (1, -2), (0, -1), (1, 0)}),
            sources=3,
        )
        placed = frozenset({(10 + x, 8 + y) for x, y in model.pixels})
        unrelated = {(30, 3), (31, 4), (32, 5)}
        black = set(placed) | unrelated
        rows = ResidualInk(black).rows
        library = CompiledGlyphLibrary([model])

        hit, search = first_glyph_top_down(
            black,
            rows,
            library,
            row_top=2,
            row_bottom=12,
            allowed_translate_x_ranges=((8, 12),),
        )

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.model.label, "a")
        self.assertEqual(hit.tx, 10)
        self.assertEqual(hit.baseline, 8)
        self.assertEqual(search.y, 6)

    def test_stays_passive_until_a_valid_origin_can_be_proposed(self) -> None:
        model = GlyphModel(
            label="x",
            style="roman",
            pixels=frozenset({(2, -2), (0, -1), (1, 0)}),
            sources=1,
        )
        placed = frozenset({(20 + x, 12 + y) for x, y in model.pixels})
        # Early ink is close in page x but cannot produce tx=20 for the model's
        # top row, so it must not create a live candidate.
        black = {(19, 4), (19, 5)} | set(placed)
        rows = ResidualInk(black).rows
        library = CompiledGlyphLibrary([model])

        hit, search = first_glyph_top_down(
            black,
            rows,
            library,
            row_top=3,
            row_bottom=16,
            allowed_translate_x_ranges=((20, 20),),
        )

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.tx, 20)
        self.assertEqual(search.y, 10)

    def test_later_ascender_does_not_beat_textual_first_glyph(self) -> None:
        first = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, -2), (1, -2), (0, -1), (1, 0)}),
            sources=3,
        )
        later = GlyphModel(
            label="k",
            style="roman",
            pixels=frozenset({(0, -5), (0, -4), (0, -3), (0, -2), (1, -1), (2, 0)}),
            sources=3,
        )
        first_pixels = frozenset({(10 + x, 12 + y) for x, y in first.pixels})
        later_pixels = frozenset({(20 + x, 12 + y) for x, y in later.pixels})
        black = set(first_pixels | later_pixels)
        rows = ResidualInk(black).rows
        library = CompiledGlyphLibrary([first, later])

        hit, search = first_glyph_top_down(
            black,
            rows,
            library,
            row_top=6,
            row_bottom=14,
            allowed_translate_x_ranges=((8, 22),),
        )

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.model.label, "a")
        self.assertEqual(hit.left, 10)
        self.assertEqual(search.y, 10)


if __name__ == "__main__":
    unittest.main()
