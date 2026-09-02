from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_facit_audit import (
    exact_mask_duplicate_groups,
    height_distribution,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


class GlyphFacitAuditTests(unittest.TestCase):
    def test_identical_mask_across_styles_is_reported(self) -> None:
        pixels = frozenset({(0, -1), (0, 0)})
        models = [
            GlyphModel(";", "roman", pixels, 2),
            GlyphModel(";", "italic", pixels, 1),
            GlyphModel("x", "roman", frozenset({(0, 0)}), 3),
        ]
        groups = exact_mask_duplicate_groups(models)
        self.assertEqual(len(groups), 1)
        self.assertEqual({(m.label, m.style) for m in groups[0]}, {(";", "roman"), (";", "italic")})

    def test_same_identity_repeated_is_not_cross_identity_duplicate(self) -> None:
        pixels = frozenset({(0, -1), (0, 0)})
        models = [
            GlyphModel(";", "roman", pixels, 2),
            GlyphModel(";", "roman", pixels, 1),
        ]
        self.assertEqual(exact_mask_duplicate_groups(models), [])

    def test_height_distribution_is_baseline_relative(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1),
            GlyphModel("g", "roman", frozenset({(0, -4), (0, 2)}), 1),
            GlyphModel("a", "italic", frozenset({(0, -5), (0, 0)}), 1),
        ]
        dist = height_distribution(models)
        self.assertEqual(dist["roman"][(-4, 0, 5)], 1)
        self.assertEqual(dist["roman"][(-4, 2, 7)], 1)
        self.assertEqual(dist["italic"][(-5, 0, 6)], 1)


if __name__ == "__main__":
    unittest.main()
