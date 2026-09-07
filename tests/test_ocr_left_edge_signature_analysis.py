from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_signature_analysis import (
    left_edge_signature,
    signature_prefix,
)


class LeftEdgeSignatureTest(unittest.TestCase):
    def test_signature_is_relative_to_top_row_left_edge_and_keeps_empty_rows(self) -> None:
        model = GlyphModel(
            label="x",
            style="roman",
            pixels=frozenset(
                {
                    (5, -4),
                    (6, -4),
                    # y=-3 deliberately empty
                    (3, -2),
                    (4, -2),
                    (7, -1),
                    (8, -1),
                }
            ),
            sources=1,
        )
        self.assertEqual((0, None, -2, 2), left_edge_signature(model))

    def test_signature_is_translation_invariant(self) -> None:
        a = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(2, -2), (3, -2), (1, -1), (2, -1), (2, 0)}),
            sources=1,
        )
        b = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(9, 3), (10, 3), (8, 4), (9, 4), (9, 5)}),
            sources=1,
        )
        self.assertEqual(left_edge_signature(a), left_edge_signature(b))

    def test_prefix_is_conservative_and_has_no_end_marker(self) -> None:
        signature = (0, 1, None, -1)
        self.assertEqual((0,), signature_prefix(signature, 1))
        self.assertEqual((0, 1, None), signature_prefix(signature, 3))
        self.assertEqual(signature, signature_prefix(signature, 99))
        with self.assertRaises(ValueError):
            signature_prefix(signature, 0)


if __name__ == "__main__":
    unittest.main()
