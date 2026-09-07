from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_index import (
    LeftEdgeIndex,
    derived_baseline,
    exact_model_at,
)


class LeftEdgeIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(1, -2), (2, -2), (0, -1), (1, -1), (1, 0)}),
            sources=1,
        )
        self.b = GlyphModel(
            label="b",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1), (0, 0), (1, 0)}),
            sources=1,
        )

    def test_prefix_lookup_narrows_models(self) -> None:
        index = LeftEdgeIndex([self.a, self.b])
        self.assertEqual(2, len(index.candidates((0,))))
        candidates = index.candidates((0, -1))
        self.assertEqual(["a"], [item.model.label for item in candidates])

    def test_exact_verification_and_baseline_are_translation_independent(self) -> None:
        index = LeftEdgeIndex([self.a])
        glyph = index.glyphs[0]
        black = {(11, 20), (12, 20), (10, 21), (11, 21), (11, 22), (30, 30)}
        self.assertTrue(exact_model_at(black, glyph, x=11, y=20))
        self.assertEqual(22, derived_baseline(glyph, source_top_y=20))
        self.assertFalse(exact_model_at(black - {(11, 22)}, glyph, x=11, y=20))


if __name__ == "__main__":
    unittest.main()
