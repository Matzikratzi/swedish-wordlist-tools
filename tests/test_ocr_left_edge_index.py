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

    def test_internal_white_gap_adds_restart_fingerprint(self) -> None:
        k_like = GlyphModel(
            label="k",
            style="roman",
            pixels=frozenset({
                (0, -5), (1, -5),
                (0, -4),
                # y=-3 deliberately all white inside the glyph
                (1, -2), (2, -2),
                (0, -1), (1, -1),
                (0, 0),
            }),
            sources=1,
        )
        index = LeftEdgeIndex([k_like])
        variants = [glyph for glyph in index.glyphs if glyph.model.label == "k"]
        self.assertEqual(2, len(variants))
        self.assertEqual({"full", "after-gap--2"}, {glyph.variant for glyph in variants})

        lower = next(glyph for glyph in variants if glyph.variant != "full")
        black = {
            (20, 30), (21, 30),
            (20, 31),
            # source row 32 can contain unrelated following-glyph ink
            (30, 32),
            (21, 33), (22, 33),
            (20, 34), (21, 34),
            (20, 35),
        }
        # The lower fingerprint starts at model y=-2, source (21,33), but exact
        # verification still checks every pixel of the complete k-like glyph.
        self.assertTrue(exact_model_at(black, lower, x=21, y=33))
        self.assertEqual(35, derived_baseline(lower, source_top_y=33))


if __name__ == "__main__":
    unittest.main()
