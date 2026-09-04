from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_cached_fast_path import (
    bind_page_candidates,
    page_cached_prioritized_fast_exact_cover,
)
from swedish_wordlist_tools.ocr_priority_fast_path import (
    priority_stats,
    reset_priority_stats,
    set_row_priority_hint,
)


class _RoleWithTypography(str):
    def __new__(cls, role: str, typography: str):
        obj = str.__new__(cls, role)
        obj.typographic_style = typography
        return obj


class PageCachedFastPathTests(unittest.TestCase):
    def setUp(self):
        reset_priority_stats()

    def test_page_candidates_are_built_once_and_split_into_typography_buckets(self):
        models = [
            GlyphModel("1", "unknown", frozenset({(0, 0)}), 1),
            GlyphModel("b", _RoleWithTypography("unknown", "bold"), frozenset({(0, 0), (1, 0)}), 1),
            GlyphModel("r", _RoleWithTypography("unknown", "roman"), frozenset({(0, 0), (0, 1)}), 1),
            GlyphModel("i", _RoleWithTypography("unknown", "italic"), frozenset({(0, 0), (1, 1)}), 1),
        ]
        context = {}

        first = bind_page_candidates(context, models)
        second = bind_page_candidates(context, models)

        self.assertIs(first, second)
        self.assertEqual(priority_stats()["page_prepares"], 1)
        self.assertEqual(
            context["priority_page_bucket_counts"],
            {"homonym": 1, "bold": 1, "roman": 1, "italic": 1, "other": 0},
        )

    def test_identical_raster_still_keeps_canonical_model_on_headword_row(self):
        pixels = frozenset({(0, 0)})
        canonical = GlyphModel(
            "a", _RoleWithTypography("unknown", "roman"), pixels, 10
        )
        hinted_bold = GlyphModel(
            "z", _RoleWithTypography("unknown", "bold"), pixels, 1
        )
        models = [hinted_bold, canonical]
        bind_page_candidates({}, models)
        set_row_priority_hint("headword")

        result = page_cached_prioritized_fast_exact_cover({(0, 0)}, 1, 1, models)

        self.assertIsNotNone(result)
        _baseline, selected, _tested = result
        self.assertEqual([match.label for match in selected], ["a"])

    def test_raised_homonym_still_does_not_lock_bold_baseline(self):
        homonym = GlyphModel("1", "unknown", frozenset({(0, 0)}), 2)
        bold = GlyphModel("a", "headword-bold", frozenset({(0, 0)}), 2)
        models = [bold, homonym]
        bind_page_candidates({}, models)
        set_row_priority_hint("homonym")

        result = page_cached_prioritized_fast_exact_cover(
            {(0, 1), (2, 5)}, 3, 7, models
        )

        self.assertIsNotNone(result)
        baseline, selected, _tested = result
        self.assertEqual(baseline, 5)
        self.assertEqual(
            [(match.label, match.baseline) for match in selected],
            [("1", 1), ("a", 5)],
        )


if __name__ == "__main__":
    unittest.main()
