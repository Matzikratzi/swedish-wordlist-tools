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
        GlyphModel(".", "roman", frozenset({(0, 0)}), 2),
        # Not present in the synthetic source. Its internal blank x=1 makes a
        # one-column inter-glyph gap non-splitting, while a real word space is
        # still a provably safe group boundary.
        GlyphModel("Z", "roman", frozenset({(0, -2), (2, 0)}), 1),
    ]


class GroupBaselineFallbackTests(unittest.TestCase):
    def test_later_whitespace_group_may_shift_down_one_pixel_when_fully_exact(self) -> None:
        image = Image.new("L", (30, 12), 255)
        models = models_with_one_internal_blank_column()

        main = {(2, 3), (2, 4), (2, 5), (3, 5), (5, 3), (5, 4), (5, 5), (6, 5)}
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
        image = Image.new("L", (40, 12), 255)
        models = models_with_one_internal_blank_column()

        main = set()
        for x in (2, 5, 8, 11):
            main.update({(x, 3), (x, 4), (x, 5), (x + 1, 5)})
        shifted_first = {(18, 5), (18, 6), (19, 6)}
        shifted_proof = {
            (25, 5), (26, 5), (25, 6),
            (28, 5), (29, 5), (28, 6),
        }
        for point in main | shifted_first | shifted_proof:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertEqual(result["baseline"], 5)
        self.assertTrue(result["fully_exact"])
        retro = next(
            item
            for item in result["baseline_fallbacks"]
            if item["status"] == "retroactive-proven-baseline-fallback"
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
        self.assertEqual(result["baseline_segments"][1]["baseline"], 6)
        self.assertEqual(result["baseline_segments"][1]["left"], 18)

    def test_proven_shift_propagates_back_across_multiple_unresolved_groups(self) -> None:
        image = Image.new("L", (48, 12), 255)
        models = models_with_one_internal_blank_column()

        # A large main group on baseline 5 fixes the ordinary whole-row baseline.
        main = set()
        for x in (28, 31, 34, 37):
            main.update({(x, 3), (x, 4), (x, 5), (x + 1, 5)})

        # Two earlier safe groups are both one pixel low and individually too
        # weak to establish the shift: first b, then a dot.
        shifted_first = {(2, 5), (2, 6), (3, 6)}
        shifted_second = {(10, 6)}
        # The third group has two glyphs and proves baseline 6.
        shifted_proof = {
            (17, 5), (17, 6), (18, 6),
            (20, 5), (21, 5), (20, 6),
        }
        for point in main | shifted_first | shifted_second | shifted_proof:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertTrue(result["fully_exact"])
        retro = [
            item
            for item in result["baseline_fallbacks"]
            if item["status"] == "retroactive-proven-baseline-fallback"
        ]
        self.assertEqual([item["group"] for item in retro], [0, 1])
        self.assertEqual([item["labels"] for item in retro], ["b", "."])
        self.assertTrue(all(item["to_baseline"] == 6 for item in retro))
        self.assertEqual(result["baseline_segments"][1]["left"], 2)

    def test_proven_shift_persists_to_later_single_glyph_groups(self) -> None:
        image = Image.new("L", (52, 12), 255)
        models = models_with_one_internal_blank_column()

        main = set()
        for x in (2, 5, 8, 11):
            main.update({(x, 3), (x, 4), (x, 5), (x + 1, 5)})
        shifted_proof = {
            (20, 5), (20, 6), (21, 6),
            (23, 5), (24, 5), (23, 6),
        }
        later_b = {(34, 5), (34, 6), (35, 6)}
        later_dot = {(44, 6)}
        for point in main | shifted_proof | later_b | later_dot:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertTrue(result["fully_exact"])
        inherited = [
            item
            for item in result["baseline_fallbacks"]
            if item["status"] == "persistent-proven-baseline-fallback"
        ]
        self.assertEqual([item["labels"] for item in inherited], ["b", "."])
        self.assertTrue(all(item["to_baseline"] == 6 for item in inherited))
        self.assertEqual(
            result["baseline_segments"],
            [
                {"left": 0, "right": 20, "baseline": 5},
                {"left": 20, "right": 52, "baseline": 6},
            ],
        )


if __name__ == "__main__":
    unittest.main()
