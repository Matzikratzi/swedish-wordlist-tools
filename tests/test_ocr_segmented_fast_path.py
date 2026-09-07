from __future__ import annotations

import unittest

from swedish_wordlist_tools import ocr_priority_fast_path as priority
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_cached_fast_path import _build_page_candidates
from swedish_wordlist_tools.ocr_segmented_fast_path import (
    safe_x_segments,
    segmented_page_cached_prioritized_fast_exact_cover,
)


class SegmentedFastPathTest(unittest.TestCase):
    def setUp(self) -> None:
        priority.reset_priority_stats()
        priority.set_row_priority_hint("unknown")
        if hasattr(priority._tls, "page_candidates"):
            delattr(priority._tls, "page_candidates")

    def test_safe_gap_splits_only_beyond_max_model_span(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, 0), (1, 0)}), 1),
            GlyphModel("b", "roman", frozenset({(0, 0), (1, 0), (2, 0)}), 1),
        ]
        candidates = _build_page_candidates(models)
        ink = {(0, 1), (1, 1), (5, 1), (6, 1)}
        parts = safe_x_segments(ink, candidates)
        self.assertEqual(2, len(parts))
        self.assertEqual({(0, 1), (1, 1)}, set(parts[0]))
        self.assertEqual({(5, 1), (6, 1)}, set(parts[1]))

    def test_segmented_cover_keeps_one_baseline_across_parts(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, 0), (1, 0)}), 3),
            GlyphModel("b", "roman", frozenset({(0, 0)}), 2),
        ]
        ink = {(0, 2), (1, 2), (10, 2)}
        result = segmented_page_cached_prioritized_fast_exact_cover(
            ink,
            width=12,
            height=5,
            models=models,
        )
        self.assertIsNotNone(result)
        baseline, selected, _placements = result
        self.assertEqual(2, baseline)
        self.assertEqual(["a", "b"], [match.label for match in selected])
        self.assertEqual({2}, {match.baseline for match in selected})
        stats = priority.priority_stats()
        self.assertEqual(1, stats.get("segmented_success"))
        self.assertEqual(1, stats.get("segmented_probes"))
        self.assertEqual(2, stats.get("segmented_parts"))

    def test_no_safe_gap_uses_unsplit_search(self) -> None:
        models = [GlyphModel("a", "roman", frozenset({(0, 0), (1, 0)}), 1)]
        ink = {(0, 1), (1, 1)}
        result = segmented_page_cached_prioritized_fast_exact_cover(
            ink,
            width=2,
            height=3,
            models=models,
        )
        self.assertIsNotNone(result)
        self.assertEqual(0, priority.priority_stats().get("segmented_probes", 0))


if __name__ == "__main__":
    unittest.main()
