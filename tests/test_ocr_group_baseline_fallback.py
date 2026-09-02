from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_group_baseline_fallback import (
    analyse_row_exact_grouped_with_baseline_fallback,
)


def models_with_one_internal_blank_column():
    return [
        GlyphModel("A", "roman", frozenset({(0, -2), (0, -1), (0, 0), (1, 0)}), 2),
        GlyphModel("b", "roman", frozenset({(0, -1), (0, 0), (1, 0)}), 2),
        GlyphModel("c", "roman", frozenset({(0, -1), (1, -1), (0, 0)}), 2),
        # Not present in the synthetic source. Its internal blank x=1 makes a
        # one-column inter-glyph gap non-splitting, while a real word space is
        # still a provably safe group boundary.
        GlyphModel("Z", "roman", frozenset({(0, -2), (2, 0)}), 1),
    ]


class GroupBaselineFallbackTests(unittest.TestCase):
    def test_later_whitespace_group_may_shift_down_one_pixel_when_fully_exact(self) -> None:
        image = Image.new("L", (30, 12), 255)
        models = models_with_one_internal_blank_column()

        # Main group on baseline 5. It is deliberately larger so the ordinary
        # whole-row decision remains baseline 5.
        main = {(2, 3), (2, 4), (2, 5), (3, 5), (5, 3), (5, 4), (5, 5), (6, 5)}
        # After a safe whitespace gap, two known glyphs are printed one pixel low.
        shifted = {(15, 5), (15, 6), (16, 6), (18, 5), (19, 5), (18, 6)}
        for point in main | shifted:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertEqual(result["baseline"], 5)
        self.assertTrue(result["fully_exact"])
        self.assertEqual(len(result["baseline_fallbacks"]), 1)
        fallback = result["baseline_fallbacks"][0]
        self.assertEqual(fallback["delta"], 1)
        self.assertEqual(fallback["to_baseline"], 6)
        self.assertEqual(fallback["labels"], "bc")

    def test_single_glyph_does_not_trigger_local_baseline_shift(self) -> None:
        image = Image.new("L", (24, 12), 255)
        models = models_with_one_internal_blank_column()
        main = {(2, 3), (2, 4), (2, 5), (3, 5), (5, 3), (5, 4), (5, 5), (6, 5)}
        shifted_one = {(15, 5), (15, 6), (16, 6)}
        for point in main | shifted_one:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertEqual(result["baseline"], 5)
        self.assertFalse(result["fully_exact"])
        self.assertEqual(result["baseline_fallbacks"], [])

    def test_proven_shift_rescues_immediately_preceding_single_glyph(self) -> None:
        image = Image.new("L", (36, 12), 255)
        models = models_with_one_internal_blank_column()

        main = {(2, 3), (2, 4), (2, 5), (3, 5), (5, 3), (5, 4), (5, 5), (6, 5)}
        # First shifted safe group contains only one glyph, so it may not prove
        # the shift by itself.
        shifted_first = {(15, 5), (15, 6), (16, 6)}  # b at baseline 6
        # The following safe group contains two exact glyphs and proves +1.
        shifted_proof = {
            (22, 5), (23, 5), (22, 6),
            (25, 5), (26, 5), (25, 6),
        }  # cc at baseline 6
        for point in main | shifted_first | shifted_proof:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertEqual(result["baseline"], 5)
        self.assertTrue(result["fully_exact"])
        self.assertEqual(len(result["baseline_fallbacks"]), 2)
        retro = next(
            item
            for item in result["baseline_fallbacks"]
            if item["status"] == "retroactive-preceding-group-fallback"
        )
        proof = next(
            item
            for item in result["baseline_fallbacks"]
            if item["status"] == "full-exact-whitespace-fallback"
        )
        self.assertEqual(retro["labels"], "b")
        self.assertEqual(retro["to_baseline"], 6)
        self.assertEqual(retro["proved_by_group"], proof["group"])
        self.assertEqual(proof["labels"], "cc")


if __name__ == "__main__":
    unittest.main()
