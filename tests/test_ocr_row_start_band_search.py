from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_local_index import prepare_local_fingerprint_indexes
from swedish_wordlist_tools.ocr_row_start_band_search import ranked_exact_row_start_band_hits


class RowStartBandSearchTest(unittest.TestCase):
    def test_finds_glyph_at_right_edge_of_start_band(self):
        glyph = GlyphModel(
            label="a",
            style="italic",
            pixels=frozenset({
                (0, -6),
                (1, -5),
                (1, -4),
                (2, -3),
                (2, -2),
                (1, -1),
                (0, 0),
            }),
            sources=1,
        )
        prepared = prepare_local_fingerprint_indexes([glyph], min_steps=3, max_steps=6, max_row_gap=1)
        baseline = 100
        x0 = 74
        black = {(x0 + x, baseline + y) for x, y in glyph.pixels}
        hits = ranked_exact_row_start_band_hits(
            black,
            prepared=prepared,
            start_ranges=((61, 75),),
            min_steps=3,
            max_steps=6,
            max_row_gap=1,
            observation_right_slack=12,
        )
        self.assertTrue(any(hit.translate_x == 74 and hit.baseline == 100 for hit in hits))

    def test_threshold_resynchronisation_recovers_glyph_hidden_by_left_ink(self):
        glyph = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({
                (0, -6),
                (1, -5),
                (1, -4),
                (2, -3),
                (2, -2),
                (1, -1),
                (0, 0),
            }),
            sources=1,
        )
        prepared = prepare_local_fingerprint_indexes([glyph], min_steps=3, max_steps=6, max_row_gap=1)
        baseline = 100
        x0 = 59
        black = {(x0 + x, baseline + y) for x, y in glyph.pixels}
        # Earlier ink inside the same broad typographic band masks the glyph if
        # only one left contour is built for the whole band. A threshold at x=59
        # must reveal the real glyph contour without rescanning every source pixel.
        black |= {(52, baseline + y) for y in range(-6, 1)}
        hits = ranked_exact_row_start_band_hits(
            black,
            prepared=prepared,
            start_ranges=((50, 64),),
            min_steps=3,
            max_steps=6,
            max_row_gap=1,
        )
        self.assertTrue(any(hit.translate_x == 59 and hit.baseline == 100 for hit in hits))

    def test_rejects_exact_glyph_outside_typographic_start_band(self):
        glyph = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, -3), (0, -2), (1, -1), (1, 0)}),
            sources=1,
        )
        prepared = prepare_local_fingerprint_indexes([glyph], min_steps=3, max_steps=3, max_row_gap=1)
        black = {(90 + x, 100 + y) for x, y in glyph.pixels}
        hits = ranked_exact_row_start_band_hits(
            black,
            prepared=prepared,
            start_ranges=((50, 64),),
            min_steps=3,
            max_steps=3,
            max_row_gap=1,
            observation_right_slack=40,
        )
        self.assertEqual((), hits)


if __name__ == "__main__":
    unittest.main()
