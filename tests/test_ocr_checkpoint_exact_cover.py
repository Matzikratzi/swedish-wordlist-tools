from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_checkpoint_exact_cover import checkpoint_page_cached_exact_cover
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_cached_fast_path import bind_page_candidates
from swedish_wordlist_tools.ocr_priority_fast_path import reset_priority_stats, set_row_priority_hint


class _RoleWithTypography(str):
    def __new__(cls, role: str, typography: str):
        obj = str.__new__(cls, role)
        obj.typographic_style = typography
        return obj


class CheckpointExactCoverTests(unittest.TestCase):
    def setUp(self):
        reset_priority_stats()
        set_row_priority_hint("continuation")

    def test_checkpoint_search_returns_only_complete_exact_cover(self):
        style = _RoleWithTypography("unknown", "roman")
        models = [GlyphModel("a", style, frozenset({(0, 0), (1, 0)}), 2)]
        bind_page_candidates({}, models)
        ink = {(0, 0), (1, 0), (4, 0), (5, 0), (8, 0), (9, 0)}

        result = checkpoint_page_cached_exact_cover(
            ink, 10, 2, models, checkpoint_span=4, backtrack_span=2
        )

        self.assertIsNotNone(result)
        baseline, selected, _placements = result
        self.assertEqual(baseline, 0)
        self.assertEqual(set().union(*(m.pixels for m in selected)), ink)
        self.assertEqual([m.x for m in selected], [0, 4, 8])

    def test_checkpoint_never_freezes_through_a_glyph(self):
        style = _RoleWithTypography("unknown", "roman")
        wide = GlyphModel("w", style, frozenset((x, 0) for x in range(6)), 3)
        dot = GlyphModel(".", style, frozenset({(0, 0)}), 1)
        models = [wide, dot]
        bind_page_candidates({}, models)
        ink = set((x, 0) for x in range(6)) | {(9, 0), (13, 0), (17, 0)}

        result = checkpoint_page_cached_exact_cover(
            ink, 18, 2, models, checkpoint_span=10, backtrack_span=5
        )

        self.assertIsNotNone(result)
        _baseline, selected, _placements = result
        self.assertEqual(set().union(*(m.pixels for m in selected)), ink)
        self.assertEqual(selected[0].label, "w")
        self.assertEqual(selected[0].x, 0)

    def test_incomplete_row_is_not_accepted(self):
        style = _RoleWithTypography("unknown", "roman")
        models = [GlyphModel("a", style, frozenset({(0, 0), (1, 0)}), 2)]
        bind_page_candidates({}, models)
        ink = {(0, 0), (1, 0), (4, 0), (5, 0), (8, 0)}

        result = checkpoint_page_cached_exact_cover(
            ink, 9, 2, models, checkpoint_span=4, backtrack_span=2
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
