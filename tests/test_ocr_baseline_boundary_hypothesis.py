from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_baseline_boundary_hypothesis import baseline_boundary_hypothesis
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


class BaselineBoundaryHypothesisTest(unittest.TestCase):
    def test_lower_pixels_do_not_discover_candidate(self):
        model = GlyphModel(
            label="g",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1), (0, 0), (0, 1), (0, 2), (1, 2)}),
            sources=1,
        )
        # Perfect descender below the baseline, but the body above the baseline
        # is missing.  Lower ink must never be allowed to invent the glyph.
        ink = {(4, 6), (4, 7), (5, 7)}
        result = baseline_boundary_hypothesis(
            ink, width=10, height=10, models=[model], baseline=5, probe_depth=3
        )
        self.assertEqual(result.upper_candidates, 0)
        self.assertIsNone(result.boundary)

    def test_three_row_probe_then_follows_descender(self):
        model = GlyphModel(
            label="g",
            style="roman",
            pixels=frozenset({(0, -2), (1, -2), (0, -1), (1, -1), (1, 0), (1, 1), (1, 2), (2, 3), (2, 4)}),
            sources=2,
        )
        baseline = 5
        x0 = 3
        ink = {(x0 + x, baseline + y) for x, y in model.pixels}
        result = baseline_boundary_hypothesis(
            ink, width=12, height=12, models=[model], baseline=baseline, probe_depth=3
        )
        self.assertGreaterEqual(result.upper_candidates, 1)
        self.assertGreaterEqual(result.probe_candidates, 1)
        self.assertEqual(result.proven_bottom, 9)
        self.assertEqual(result.boundary, 10)
        self.assertEqual([(p.label, p.x) for p in result.proofs], [("g", x0)])

    def test_failed_probe_does_not_follow_deeper_matching_ink(self):
        model = GlyphModel(
            label="g",
            style="roman",
            pixels=frozenset({(0, -1), (0, 0), (0, 1), (0, 2), (0, 4)}),
            sources=1,
        )
        baseline = 4
        # Body is valid and a deep pixel happens to exist, but y=baseline+2 is
        # missing.  We must stop inside the three-row probe and not claim the
        # deeper pixel as part of the glyph.
        ink = {(2, 3), (2, 4), (2, 5), (2, 8)}
        result = baseline_boundary_hypothesis(
            ink, width=8, height=10, models=[model], baseline=baseline, probe_depth=3
        )
        self.assertGreaterEqual(result.upper_candidates, 1)
        self.assertEqual(result.probe_candidates, 0)
        self.assertIsNone(result.boundary)

    def test_unrelated_lower_ink_does_not_extend_boundary(self):
        model = GlyphModel(
            label="p",
            style="roman",
            pixels=frozenset({(0, -1), (1, -1), (0, 0), (0, 1), (0, 2)}),
            sources=1,
        )
        baseline = 4
        x0 = 2
        ink = {(x0 + x, baseline + y) for x, y in model.pixels}
        ink.update({(7, 7), (7, 8), (7, 9)})  # possible next-row ink
        result = baseline_boundary_hypothesis(
            ink, width=10, height=11, models=[model], baseline=baseline, probe_depth=3
        )
        self.assertEqual(result.proven_bottom, 6)
        self.assertEqual(result.boundary, 7)


if __name__ == "__main__":
    unittest.main()
