from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_baseline_up import (
    BaselineUpStats,
    CompiledGlyphLibrary,
    ResidualInk,
    find_next_baseline_up,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


class BaselineUpTests(unittest.TestCase):
    def test_finds_next_glyph_with_overlapping_x_extent(self) -> None:
        previous = frozenset({(10, 8), (11, 9), (12, 10), (14, 7)})
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

    def test_equivalent_geometry_variants_do_not_create_false_ambiguity(self) -> None:
        short = GlyphModel(
            label="f",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1), (0, 0)}),
            sources=1,
        )
        rich = GlyphModel(
            label="f",
            style="roman",
            pixels=frozenset({(0, -2), (1, -2), (0, -1), (0, 0)}),
            sources=1,
        )
        placed = frozenset({(12 + x, 10 + y) for x, y in rich.pixels})
        residual = ResidualInk(placed)
        library = CompiledGlyphLibrary([short, rich])

        hit, candidates = find_next_baseline_up(
            residual.pixels,
            residual.rows,
            library,
            baseline=10,
            row_top=7,
            after_left=5,
            column_right=40,
        )

        self.assertEqual(len(candidates), 2)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.model.label, "f")
        self.assertEqual(hit.pixels, placed)

    def test_ambiguous_exact_candidates_are_filtered_by_full_live_profile(self) -> None:
        solid = GlyphModel(
            label="I",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1), (0, 0)}),
            sources=1,
        )
        changing = GlyphModel(
            label="edge-change",
            style="roman",
            pixels=frozenset({(1, -2), (0, 0)}),
            sources=1,
        )
        # Both placements are exact subsets and neither is a subset of the
        # other: I owns (12,9), edge-change owns (13,8).  The observed residual
        # front stays at x=12 on y=8..10.  I therefore matches the whole profile,
        # while edge-change requires the top edge at x=13 (and a blank middle
        # row) before returning to x=12.  Its mandatory profile change never
        # happens, so only I survives the live-profile check.
        black = {
            (12, 8),
            (13, 8),
            (12, 9),
            (12, 10),
            (20, 10),
        }
        residual = ResidualInk(black)
        library = CompiledGlyphLibrary([solid, changing])
        stats = BaselineUpStats()

        hit, candidates = find_next_baseline_up(
            residual.pixels,
            residual.rows,
            library,
            baseline=10,
            row_top=8,
            profile_bottom=10,
            after_left=5,
            column_right=40,
            stats=stats,
        )

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.model.label, "I")
        self.assertEqual([candidate.model.label for candidate in candidates], ["I"])
        self.assertEqual(stats.live_filter_calls, 1)
        self.assertEqual(stats.live_survivors, 1)

    def test_consume_updates_only_residual_rows(self) -> None:
        residual = ResidualInk({(1, 1), (2, 1), (3, 2)})
        residual.consume({(2, 1), (3, 2)})
        self.assertEqual(residual.pixels, {(1, 1)})
        self.assertEqual(residual.rows, {1: {1}})


if __name__ == "__main__":
    unittest.main()
