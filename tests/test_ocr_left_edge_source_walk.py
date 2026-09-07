from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_index import LeftEdgeIndex
from swedish_wordlist_tools.ocr_left_edge_source_walk import source_walk_hits, walk_prefixes_at


class LeftEdgeSourceWalkTests(unittest.TestCase):
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

    def test_source_pixels_drive_prefix_branching(self) -> None:
        index = LeftEdgeIndex([self.a, self.b])
        black = {(11, 20), (12, 20), (10, 21), (11, 21), (11, 22)}
        states = walk_prefixes_at(black, index, x=11, y=20, max_depth=4)
        prefixes = [prefix for prefix, _candidates in states]
        self.assertIn((0, -1, 0), prefixes)
        self.assertNotIn((0, 0, 0), prefixes)

    def test_full_raster_verification_rejects_incidental_prefix(self) -> None:
        index = LeftEdgeIndex([self.a, self.b])
        black = {
            (11, 20), (12, 20),
            (10, 21), (11, 21),
            (11, 22),
            # Extra pixels can satisfy other prefix branches but must not make a
            # different full glyph raster exact at the same start.
            (10, 20), (10, 22),
        }
        hits = source_walk_hits(black, index, max_x=11)
        exact_labels = {
            glyph.model.label
            for hit in hits
            if (hit.x, hit.y) == (11, 20)
            for glyph in hit.exact
        }
        self.assertEqual({"a"}, exact_labels)

    def test_no_baseline_is_required(self) -> None:
        index = LeftEdgeIndex([self.a])
        black = {(31, 40), (32, 40), (30, 41), (31, 41), (31, 42)}
        hits = source_walk_hits(black, index)
        self.assertTrue(
            any(
                hit.x == 31
                and hit.y == 40
                and any(glyph.model.label == "a" for glyph in hit.exact)
                for hit in hits
            )
        )


if __name__ == "__main__":
    unittest.main()
