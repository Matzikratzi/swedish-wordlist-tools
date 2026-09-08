from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_prefix_hypotheses import (
    branch_source_left_contour,
    build_prefix_index,
)


class LeftEdgePrefixHypothesesTest(unittest.TestCase):
    def test_prefix_index_can_start_inside_glyph(self):
        glyph = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({
                (2, -4),
                (1, -3),
                (1, -2),
                (0, -1),
                (0, 0),
            }),
            sources=1,
        )
        index = build_prefix_index([glyph])
        # Relations beginning at the second occupied row are indexed too.
        self.assertTrue(index.candidates(((1, 0), (1, -1))))

    def test_impossible_extension_preserves_old_track_and_restarts(self):
        normal = GlyphModel(
            label="n",
            style="roman",
            pixels=frozenset({
                (0, 0),
                (1, 1),
                (1, 2),
                (2, 3),
            }),
            sources=1,
        )
        tiny = GlyphModel(
            label="~",
            style="italic",
            pixels=frozenset({
                (1, 0),
                (0, 1),
                (2, 2),
            }),
            sources=1,
        )
        index = build_prefix_index([normal, tiny])
        # First two relations fit normal: +1, 0.  The next jump (+7) cannot
        # continue it.  That failed extension is kept as a boundary, then the
        # following two relations form the tiny glyph hypothesis.
        rows = ((10, 50), (11, 51), (12, 51), (13, 58), (14, 57), (15, 59))
        tracks = branch_source_left_contour(rows, index=index)
        self.assertGreaterEqual(len(tracks), 2)
        self.assertEqual(((1, 1), (1, 0)), tracks[0].relations)
        self.assertEqual(((1, -1), (1, 2)), tracks[-1].relations)

    def test_unknown_single_relation_does_not_destroy_later_track(self):
        glyph = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, 0), (0, 1), (1, 2), (1, 3)}),
            sources=1,
        )
        index = build_prefix_index([glyph])
        rows = ((0, 20), (1, 40), (2, 10), (3, 10), (4, 11), (5, 11))
        tracks = branch_source_left_contour(rows, index=index)
        self.assertTrue(any(track.relations == ((1, 0), (1, 1), (1, 0)) for track in tracks))


if __name__ == "__main__":
    unittest.main()
