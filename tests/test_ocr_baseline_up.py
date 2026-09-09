from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_baseline_up import (
    CompiledGlyphLibrary,
    ResidualInk,
    find_next_baseline_up,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


class BaselineUpTests(unittest.TestCase):
    def test_finds_next_glyph_with_overlapping_x_extent(self) -> None:
        # Previous glyph owns x=10..14.  Its bbox overlaps the next glyph at
        # x=14, but the two glyphs do not share an actual black pixel.
        previous = frozenset({(10, 8), (11, 9), (12, 10), (14, 7)})
        # Next glyph begins at physical x=14, i.e. one x-column overlaps the
        # previous glyph's bounding box, but no actual black pixel is shared.
        model = GlyphModel(
            label="r",
            style="italic",
            pixels=frozenset({(0, -2), (0, -1), (1, -1), (0, 0), (2, 0)}),
            sources=3,
        )
        placed = frozenset({(14 + x, 10 + y) for x, y in model.pixels})
        residual = ResidualInk(previous | placed)
        residual.consume(previous)
        library = CompiledGlyphLibrary([model])

        hit, candidates = find_next_baseline_up(
            residual.pixels,
            residual.rows,
            library,
            baseline=10,
            row_top=7,
            after_left=10,
            column_right=40,
        )

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.model.label, "r")
        self.assertEqual(hit.left, 14)
        self.assertEqual(hit.right, 16)
        self.assertEqual(hit.pixels, placed)
        self.assertEqual(len(candidates), 1)

    def test_does_not_skip_left_glyph_without_baseline_pixel(self) -> None:
        # A detached mark at x=12 has no baseline pixel. A later glyph at x=20
        # does. Walking baseline-up must still choose the physically leftmost
        # exact glyph after the whole short vertical interval has been checked.
        dot = GlyphModel(
            label="·",
            style="roman",
            pixels=frozenset({(0, -3), (0, -2)}),
            sources=2,
        )
        later = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, -1), (1, -1), (0, 0), (1, 0)}),
            sources=2,
        )
        dot_pixels = frozenset({(12 + x, 10 + y) for x, y in dot.pixels})
        later_pixels = frozenset({(20 + x, 10 + y) for x, y in later.pixels})
        residual = ResidualInk(dot_pixels | later_pixels)
        library = CompiledGlyphLibrary([dot, later])

        hit, candidates = find_next_baseline_up(
            residual.pixels,
            residual.rows,
            library,
            baseline=10,
            row_top=6,
            after_left=5,
            column_right=40,
        )

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.model.label, "·")
        self.assertEqual(hit.left, 12)
        self.assertGreaterEqual(len(candidates), 2)

    def test_consume_updates_only_residual_rows(self) -> None:
        residual = ResidualInk({(1, 1), (2, 1), (3, 2)})
        residual.consume({(2, 1), (3, 2)})
        self.assertEqual(residual.pixels, {(1, 1)})
        self.assertEqual(residual.rows, {1: {1}})


if __name__ == "__main__":
    unittest.main()
