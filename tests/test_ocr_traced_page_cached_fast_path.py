from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_cached_fast_path import (
    bind_page_candidates,
    page_cached_prioritized_fast_exact_cover,
)
from swedish_wordlist_tools.ocr_priority_fast_path import (
    reset_priority_stats,
    set_row_priority_hint,
)
from swedish_wordlist_tools.ocr_traced_page_cached_fast_path import (
    set_trace_row,
    traced_page_cached_prioritized_fast_exact_cover,
)


class TracedPageCachedFastPathTests(unittest.TestCase):
    def setUp(self):
        reset_priority_stats()
        set_row_priority_hint("headword")
        set_trace_row(1, (0, 0))

    def test_traced_search_matches_ordinary_result(self):
        models = [
            GlyphModel("a", "headword-bold", frozenset({(0, 0), (0, 1)}), 5),
            GlyphModel("b", "headword-bold", frozenset({(0, 0), (1, 0)}), 4),
        ]
        ink = {(0, 1), (0, 2), (2, 1), (3, 1)}

        bind_page_candidates({}, models)
        ordinary = page_cached_prioritized_fast_exact_cover(ink, 4, 4, models)

        reset_priority_stats()
        set_row_priority_hint("headword")
        bind_page_candidates({}, models)
        traced = traced_page_cached_prioritized_fast_exact_cover(ink, 4, 4, models)

        self.assertIsNotNone(ordinary)
        self.assertIsNotNone(traced)
        ordinary_baseline, ordinary_matches, ordinary_placements = ordinary
        traced_baseline, traced_matches, traced_placements = traced
        self.assertEqual(traced_baseline, ordinary_baseline)
        self.assertEqual(traced_placements, ordinary_placements)
        self.assertEqual(
            [(m.label, m.x, m.baseline, m.pixels) for m in traced_matches],
            [(m.label, m.x, m.baseline, m.pixels) for m in ordinary_matches],
        )


if __name__ == "__main__":
    unittest.main()
