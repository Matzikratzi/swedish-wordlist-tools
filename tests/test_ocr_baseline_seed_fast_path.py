from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_baseline_seed_fast_path import (
    baseline_seeded_page_cached_exact_cover,
    set_expected_headword_initial,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_cached_fast_path import bind_page_candidates
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


class BaselineSeedFastPathTests(unittest.TestCase):
    def setUp(self):
        reset_priority_stats()
        set_expected_headword_initial(None)

    def tearDown(self):
        set_expected_headword_initial(None)

    def test_unique_bold_headword_anchor_seeds_baseline(self):
        bold = GlyphModel(
            "a",
            _RoleWithTypography("unknown", "bold"),
            frozenset({(0, -1), (0, 0), (1, 0)}),
            5,
        )
        roman = GlyphModel(
            ".",
            _RoleWithTypography("unknown", "roman"),
            frozenset({(0, 0)}),
            3,
        )
        models = [bold, roman]
        bind_page_candidates({}, models)
        set_row_priority_hint("headword")
        set_expected_headword_initial("a")

        ink = {(0, 1), (0, 2), (1, 2), (3, 2)}
        result = baseline_seeded_page_cached_exact_cover(ink, 4, 5, models)

        self.assertIsNotNone(result)
        baseline, selected, _tested = result
        self.assertEqual(baseline, 2)
        self.assertEqual([match.label for match in selected], ["a", "."])
        stats = priority_stats()
        self.assertEqual(stats.get("baseline_seed_probes"), 1)
        self.assertEqual(stats.get("baseline_seed_unique"), 1)
        self.assertEqual(stats.get("baseline_seed_success"), 1)
        self.assertEqual(stats.get("baseline_seed_fallbacks", 0), 0)
        self.assertEqual(stats["calls"], 1)

    def test_known_initial_filters_other_exact_bold_anchor(self):
        a = GlyphModel(
            "a",
            _RoleWithTypography("unknown", "bold"),
            frozenset({(0, -1), (0, 0)}),
            2,
        )
        b = GlyphModel(
            "b",
            _RoleWithTypography("unknown", "bold"),
            frozenset({(0, 0)}),
            2,
        )
        tail = GlyphModel(
            ".",
            _RoleWithTypography("unknown", "roman"),
            frozenset({(0, 0)}),
            2,
        )
        models = [a, b, tail]
        bind_page_candidates({}, models)
        set_row_priority_hint("headword")
        set_expected_headword_initial("a")

        ink = {(0, 0), (0, 1), (2, 1)}
        result = baseline_seeded_page_cached_exact_cover(ink, 3, 4, models)

        self.assertIsNotNone(result)
        baseline, selected, _tested = result
        self.assertEqual(baseline, 1)
        self.assertEqual([match.label for match in selected], ["a", "."])
        self.assertEqual(priority_stats().get("baseline_seed_success"), 1)

    def test_wrong_seed_never_removes_old_solution(self):
        # Misclassified headword row: a one-pixel bold model gives a unique
        # baseline seed, but only the roman two-pixel glyph can cover the row.
        bold = GlyphModel(
            "x",
            _RoleWithTypography("unknown", "bold"),
            frozenset({(0, 0)}),
            1,
        )
        roman = GlyphModel(
            "r",
            _RoleWithTypography("unknown", "roman"),
            frozenset({(0, -1), (1, 0)}),
            5,
        )
        models = [bold, roman]
        bind_page_candidates({}, models)
        set_row_priority_hint("headword")

        result = baseline_seeded_page_cached_exact_cover({(0, 0), (1, 1)}, 2, 3, models)

        self.assertIsNotNone(result)
        baseline, selected, _tested = result
        self.assertEqual(baseline, 1)
        self.assertEqual([match.label for match in selected], ["r"])
        stats = priority_stats()
        self.assertEqual(stats.get("baseline_seed_unique"), 1)
        self.assertEqual(stats.get("baseline_seed_fallbacks"), 1)
        self.assertEqual(stats["successful_calls"], 1)

    def test_homonym_digit_does_not_become_text_baseline(self):
        digit = GlyphModel("1", "unknown", frozenset({(0, 0)}), 2)
        bold = GlyphModel(
            "a",
            _RoleWithTypography("unknown", "bold"),
            frozenset({(0, 0), (1, 0)}),
            2,
        )
        models = [digit, bold]
        bind_page_candidates({}, models)
        set_row_priority_hint("homonym")
        set_expected_headword_initial("a")

        result = baseline_seeded_page_cached_exact_cover({(0, 1), (2, 5), (3, 5)}, 4, 7, models)

        self.assertIsNotNone(result)
        baseline, selected, _tested = result
        self.assertEqual(baseline, 5)
        self.assertEqual(
            [(match.label, match.baseline) for match in selected],
            [("1", 1), ("a", 5)],
        )
        self.assertEqual(priority_stats().get("baseline_seed_success"), 1)


if __name__ == "__main__":
    unittest.main()
