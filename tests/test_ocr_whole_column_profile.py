from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_whole_column_profile import (
    build_profile_fragment_index,
    profile_guided_exact_hits,
    walk_profile_row_starts,
    whole_column_left_profile,
)


def glyph(label: str, pixels: set[tuple[int, int]]) -> GlyphModel:
    return GlyphModel(label=label, style="unknown", pixels=frozenset(pixels))


def place(model: GlyphModel, *, x: int, baseline: int) -> set[tuple[int, int]]:
    return {(x + px, baseline + py) for px, py in model.pixels}


class WholeColumnProfileTest(unittest.TestCase):
    def test_dense_profile_keeps_blank_pixel_rows(self):
        black = {(9, 10), (7, 10), (8, 12), (20, 12), (4, 14)}
        profile = whole_column_left_profile(black, min_y=10, max_y=14, min_x=0, max_x=15)
        self.assertEqual((7, None, 8, None, 4), profile)

    def test_partial_profile_match_is_verified_against_full_glyph(self):
        a = glyph("a", {(0, -2), (1, -2), (0, -1), (1, 0), (2, 0)})
        black = place(a, x=57, baseline=20)
        profile = whole_column_left_profile(black, min_y=16, max_y=23, min_x=0, max_x=75)
        index = build_profile_fragment_index([a], min_rows=2, max_rows=2, min_ink_rows=2)
        hits = profile_guided_exact_hits(
            black,
            profile,
            profile_min_y=16,
            fragment_index=index,
            allowed_translate_x_ranges=((50, 64),),
            min_rows=2,
            max_rows=2,
        )
        self.assertEqual(1, len(hits))
        self.assertEqual(("a", 57, 20), (hits[0].model.label, hits[0].x, hits[0].baseline))

        missing_pixel = set(black)
        missing_pixel.remove((59, 20))
        profile2 = whole_column_left_profile(missing_pixel, min_y=16, max_y=23, min_x=0, max_x=75)
        hits2 = profile_guided_exact_hits(
            missing_pixel,
            profile2,
            profile_min_y=16,
            fragment_index=index,
            allowed_translate_x_ranges=((50, 64),),
            min_rows=2,
            max_rows=2,
        )
        self.assertEqual((), hits2)

    def test_translation_must_land_in_start_interval(self):
        a = glyph("a", {(0, -2), (0, -1), (1, 0)})
        black = place(a, x=30, baseline=20)
        profile = whole_column_left_profile(black, min_y=15, max_y=22, min_x=0, max_x=75)
        index = build_profile_fragment_index([a], min_rows=2, max_rows=3, min_ink_rows=2)
        hits = profile_guided_exact_hits(
            black,
            profile,
            profile_min_y=15,
            fragment_index=index,
            allowed_translate_x_ranges=((39, 75),),
            min_rows=2,
            max_rows=3,
        )
        self.assertEqual((), hits)

    def test_tall_late_glyph_can_appear_first_but_leftmost_same_baseline_start_wins(self):
        mark = glyph("¤", {(0, -2), (1, -2), (0, -1), (1, 0)})
        i = glyph("i", {(0, -4), (0, -3), (0, -1), (0, 0)})
        p = glyph("P", {(0, -7), (0, -6), (0, -5), (0, -4), (1, -4), (0, -3), (0, -2), (0, -1), (0, 0)})
        black = set()
        black |= place(mark, x=46, baseline=20)
        black |= place(i, x=58, baseline=20)
        black |= place(p, x=70, baseline=20)

        profile = whole_column_left_profile(black, min_y=10, max_y=25, min_x=0, max_x=75)
        # The capital is physically the first visible left-profile ink.
        self.assertEqual(70, profile[13 - 10])
        self.assertEqual(58, profile[16 - 10])
        self.assertEqual(46, profile[18 - 10])

        models = [mark, i, p]
        index = build_profile_fragment_index(models, min_rows=2, max_rows=4, min_ink_rows=2)
        hits = profile_guided_exact_hits(
            black,
            profile,
            profile_min_y=10,
            fragment_index=index,
            allowed_translate_x_ranges=((39, 53), (50, 64), (61, 75)),
            min_rows=2,
            max_rows=4,
        )
        rows = walk_profile_row_starts(hits, start_y=10, end_y=25, max_row_distance=20)
        self.assertEqual(1, len(rows))
        self.assertEqual(20, rows[0].hit.baseline)
        self.assertEqual("¤", rows[0].hit.model.label)
        self.assertEqual(46, rows[0].hit.x)

    def test_walk_continues_to_next_baseline(self):
        a = glyph("a", {(0, -2), (0, -1), (1, 0)})
        b = glyph("b", {(0, -3), (0, -2), (0, -1), (1, 0)})
        black = place(a, x=57, baseline=20) | place(b, x=57, baseline=36)
        profile = whole_column_left_profile(black, min_y=10, max_y=40, min_x=0, max_x=75)
        index = build_profile_fragment_index([a, b], min_rows=2, max_rows=4, min_ink_rows=2)
        hits = profile_guided_exact_hits(
            black,
            profile,
            profile_min_y=10,
            fragment_index=index,
            allowed_translate_x_ranges=((50, 64),),
            min_rows=2,
            max_rows=4,
        )
        rows = walk_profile_row_starts(hits, start_y=10, end_y=40, max_row_distance=20, min_baseline_delta=8)
        self.assertEqual([20, 36], [row.hit.baseline for row in rows])
        self.assertEqual(["a", "b"], [row.hit.model.label for row in rows])


if __name__ == "__main__":
    unittest.main()
