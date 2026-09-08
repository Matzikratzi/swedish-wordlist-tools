from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_local_index import (
    LocalLeftEdgeIndex,
    derived_baseline_from_local,
    exact_local_model_at,
    local_relation_windows,
    source_local_signatures,
)


class LocalLeftEdgeIndexTests(unittest.TestCase):
    def test_middle_window_matches_without_glyph_top(self) -> None:
        model = GlyphModel(
            label="g",
            style="roman",
            pixels=frozenset({
                (3, -6),
                (4, -5),
                (4, -4),
                (3, -3),
                (2, -2),
                (2, -1),
                (3, 0),
            }),
            sources=1,
        )
        index = LocalLeftEdgeIndex([model], steps=3, max_row_gap=1)

        # Source observation starts in the middle of the glyph: model y=-4
        # appears at source y=20.  The model's top rows are deliberately absent
        # from the observed contour used for lookup.
        observed = {
            (14, 20),  # model (4,-4)
            (13, 21),  # model (3,-3)
            (12, 22),  # model (2,-2)
            (12, 23),  # model (2,-1)
        }
        signatures = source_local_signatures(observed, steps=3, max_row_gap=1)
        self.assertEqual(1, len(signatures))
        source_y, source_x, signature = signatures[0]
        candidates = index.candidates(signature)
        self.assertTrue(any(item.model.label == "g" and item.anchor_y == -4 for item in candidates))

        candidate = next(item for item in candidates if item.model.label == "g" and item.anchor_y == -4)
        self.assertEqual(24, derived_baseline_from_local(candidate, source_anchor_y=source_y))

    def test_white_gap_breaks_relation_instead_of_matching_large_dx(self) -> None:
        model = GlyphModel(
            label="k",
            style="roman",
            pixels=frozenset({
                (0, -5),
                (1, -4),
                # y=-3 is all white
                (18, -2),
                (17, -1),
                (17, 0),
            }),
            sources=1,
        )
        strict = local_relation_windows(model, steps=2, max_row_gap=1)
        self.assertEqual(1, len(strict))
        self.assertEqual(((1, -1), (1, 0)), strict[0].signature)
        self.assertEqual(-2, strict[0].anchor_y)

        relaxed = local_relation_windows(model, steps=2, max_row_gap=2)
        self.assertTrue(any((2, 17) in item.signature for item in relaxed))

    def test_exact_verification_checks_full_glyph_after_local_hit(self) -> None:
        model = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({
                (1, -3),
                (0, -2),
                (0, -1),
                (1, 0),
            }),
            sources=1,
        )
        index = LocalLeftEdgeIndex([model], steps=2, max_row_gap=1)
        candidate = next(item for item in index.glyphs if item.anchor_y == -2)

        black = {
            (10, 20),  # model (0,-2)
            (10, 21),  # model (0,-1)
            (11, 22),  # model (1,0)
            (11, 19),  # model (1,-3)
        }
        self.assertTrue(
            exact_local_model_at(
                black,
                candidate,
                source_anchor_y=20,
                source_anchor_x=10,
            )
        )
        self.assertFalse(
            exact_local_model_at(
                black - {(11, 19)},
                candidate,
                source_anchor_y=20,
                source_anchor_x=10,
            )
        )


if __name__ == "__main__":
    unittest.main()
