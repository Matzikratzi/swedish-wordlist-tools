import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import (
    GlyphModel,
    exact_matches,
    exact_sequence_cover,
    select_best_baseline_partition,
)
from swedish_wordlist_tools.ocr_glyph_gap_matcher import (
    _component_aware_candidates,
    select_best_baseline_partition_by_safe_gaps,
)


class TouchingGlyphPartitionTests(unittest.TestCase):
    def test_two_edge_touching_glyphs_can_collectively_own_one_component(self):
        # Same baseline. The rightmost pixel of t touches the leftmost pixel of ;
        # by a horizontal edge, so all source ink is one 4-connected component.
        t = GlyphModel("t", "italic", frozenset({(0, -2), (0, -1), (0, 0), (1, -1)}), 1)
        semicolon = GlyphModel(";", "italic", frozenset({(0, -1), (1, -1), (1, 0)}), 1)
        baseline = 3
        ink = {
            (1, 1), (1, 2), (1, 3), (2, 2),  # t at x=1
            (3, 2), (4, 2), (4, 3),           # ; at x=3, touches t at (2,2)-(3,2)
        }

        # A single glyph still does not own the whole connected component.
        strict = exact_matches(ink, 6, 5, [t, semicolon])
        self.assertEqual(strict, [])

        found_baseline, selected = select_best_baseline_partition(ink, 6, 5, [t, semicolon])
        self.assertEqual(found_baseline, baseline)
        self.assertEqual([match.label for match in selected], ["t", ";"])
        self.assertEqual(set().union(*(match.pixels for match in selected)), ink)

    def test_exact_sequence_cover_accepts_touching_glyphs(self):
        a = GlyphModel("a", "roman", frozenset({(0, -1), (0, 0)}), 1)
        b = GlyphModel("b", "roman", frozenset({(0, -1), (1, -1), (1, 0)}), 1)
        ink = {(0, 1), (0, 2), (1, 1), (2, 1), (2, 2)}
        cover = exact_sequence_cover(ink, 3, 3, [a, b], "ab")
        self.assertIsNotNone(cover)
        self.assertEqual([match.label for match in cover], ["a", "b"])

    def test_grouped_matcher_keeps_touching_partition(self):
        left = GlyphModel("x", "roman", frozenset({(0, -1), (0, 0), (1, 0)}), 1)
        right = GlyphModel("y", "roman", frozenset({(0, 0), (1, -1), (1, 0)}), 1)
        ink = {(2, 1), (2, 2), (3, 2), (4, 2), (5, 1), (5, 2)}
        baseline, selected, _candidates, _groups = select_best_baseline_partition_by_safe_gaps(
            ink, 7, 4, [left, right]
        )
        self.assertEqual(baseline, 2)
        self.assertEqual([match.label for match in selected], ["x", "y"])
        self.assertEqual(set().union(*(match.pixels for match in selected)), ink)

    def test_grouped_matcher_does_not_read_part_of_semicolon_as_period(self):
        # The period model is an exact subset of the semicolon's connected ink.
        # It must not be emitted unless the rest of that component is also
        # explained by selected glyphs.
        period = GlyphModel(".", "roman", frozenset({(0, 0)}), 1)
        ink = {(2, 2), (2, 3)}

        baseline, selected, _candidates, _groups = select_best_baseline_partition_by_safe_gaps(
            ink, 4, 5, [period]
        )

        self.assertIsNotNone(baseline)
        self.assertEqual(selected, [])

    def test_resolved_component_does_not_generate_partial_subset_candidates(self):
        semicolon = GlyphModel(";", "roman", frozenset({(0, -1), (0, 0)}), 1)
        period = GlyphModel(".", "roman", frozenset({(0, -1)}), 1)
        ink = {(2, 1), (2, 2)}

        candidates = _component_aware_candidates(ink, 4, 4, [semicolon, period])

        self.assertEqual([match.label for match in candidates], [";"])


if __name__ == "__main__":
    unittest.main()
