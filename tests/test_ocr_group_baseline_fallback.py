from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, Match
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
    def test_later_whitespace_group_may_shift_when_fully_exact(self) -> None:
        image = Image.new("L", (30, 12), 255)
        models = models_with_one_internal_blank_column()

        main = {(2, 3), (2, 4), (2, 5), (3, 5), (5, 3), (5, 4), (5, 5), (6, 5)}
        shifted = {(15, 5), (15, 6), (16, 6), (18, 5), (19, 5), (18, 6)}
        for point in main | shifted:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertEqual(result["baseline"], 5)
        self.assertTrue(result["fully_exact"])
        fallback = result["baseline_fallbacks"][0]
        self.assertEqual(fallback["delta"], 1)
        self.assertEqual(fallback["to_baseline"], 6)
        self.assertEqual(fallback["labels"], "bc")
        self.assertEqual(fallback["status"], "full-exact-local-baseline-fallback")

    def test_single_glyph_is_enough_for_exact_local_baseline(self) -> None:
        image = Image.new("L", (24, 12), 255)
        models = models_with_one_internal_blank_column()

        main = {(2, 3), (2, 4), (2, 5), (3, 5), (5, 3), (5, 4), (5, 5), (6, 5)}
        shifted_one = {(15, 5), (15, 6), (16, 6)}  # b at baseline 6
        for point in main | shifted_one:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertEqual(result["baseline"], 5)
        self.assertTrue(result["fully_exact"])
        fallback = next(item for item in result["baseline_fallbacks"] if item["labels"] == "b")
        self.assertEqual(fallback["to_baseline"], 6)
        self.assertEqual(fallback["pixels"], 3)

    def test_first_safe_group_gets_same_local_baseline_chance(self) -> None:
        image = Image.new("L", (42, 12), 255)
        models = models_with_one_internal_blank_column()

        # The leftmost group is a single b at baseline 6. A much larger group
        # later on baseline 5 makes 5 the ordinary whole-row baseline.
        shifted_first = {(2, 5), (2, 6), (3, 6)}
        main = set()
        for x in (22, 25, 28, 31):
            main.update({(x, 3), (x, 4), (x, 5), (x + 1, 5)})
        for point in shifted_first | main:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertEqual(result["baseline"], 5)
        self.assertTrue(result["fully_exact"])
        first = next(item for item in result["baseline_fallbacks"] if item["group"] == 0)
        self.assertEqual(first["labels"], "b")
        self.assertEqual(first["to_baseline"], 6)

    def test_separate_single_glyph_groups_can_each_be_exact(self) -> None:
        image = Image.new("L", (48, 12), 255)
        models = models_with_one_internal_blank_column()

        shifted_b = {(2, 5), (2, 6), (3, 6)}
        shifted_dot = {(10, 6)}
        main = set()
        for x in (28, 31, 34, 37):
            main.update({(x, 3), (x, 4), (x, 5), (x + 1, 5)})
        for point in shifted_b | shifted_dot | main:
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertTrue(result["fully_exact"])
        local = result["baseline_fallbacks"]
        self.assertEqual([item["labels"] for item in local], ["b", "."])
        self.assertTrue(all(item["to_baseline"] == 6 for item in local))

    def test_row_with_only_one_glyph_accepts_its_exact_baseline(self) -> None:
        image = Image.new("L", (12, 12), 255)
        models = models_with_one_internal_blank_column()

        for point in {(3, 5), (3, 6), (4, 6)}:  # b at baseline 6
            image.putpixel(point, 0)

        result = analyse_row_exact_grouped_with_baseline_fallback(image, models)

        self.assertTrue(result["fully_exact"])
        self.assertEqual(len(result["selected"]), 1)
        self.assertEqual(result["selected"][0].label, "b")
        self.assertEqual(result["selected"][0].baseline, 6)

    def test_reuses_exhaustive_candidates_for_local_baseline(self) -> None:
        image = Image.new("L", (8, 10), 255)
        ink = {(2, 5), (2, 6), (3, 6)}
        candidate = Match(
            label="b",
            style="roman",
            x=2,
            baseline=6,
            pixels=frozenset(ink),
            model_pixels=3,
            sources=2,
        )
        grouped_result = {
            "baseline": 5,
            "source_pixels": 3,
            "covered_pixels": 0,
            "unmatched_pixels": 3,
            "unmatched_components": [],
            "fully_exact": False,
            "candidate_count": 1,
            "selected": [],
            "ink": set(ink),
            "safe_groups": [(2, 4)],
            "safe_group_count": 1,
            "exact_fast_path": False,
            "_exact_candidates": [candidate],
        }

        with patch(
            "swedish_wordlist_tools.ocr_group_baseline_fallback.analyse_row_exact_grouped",
            return_value=grouped_result,
        ), patch(
            "swedish_wordlist_tools.ocr_group_baseline_fallback.exact_matches_by_safe_gaps",
            side_effect=AssertionError("candidate generation must not run twice"),
        ):
            result = analyse_row_exact_grouped_with_baseline_fallback(image, [])

        self.assertTrue(result["fully_exact"])
        self.assertEqual(result["baseline_candidate_source"], "reused-exhaustive-safe-groups")
        self.assertEqual(result["selected"], [candidate])


if __name__ == "__main__":
    unittest.main()
