from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_local_index import ranked_exact_local_hits


class RankedLocalLeftEdgeTests(unittest.TestCase):
    def test_longer_exact_fingerprint_is_ranked_before_shorter_placement(self) -> None:
        long_model = GlyphModel(
            label="L",
            style="roman",
            pixels=frozenset({
                (2, -5),
                (1, -4),
                (1, -3),
                (0, -2),
                (0, -1),
                (1, 0),
            }),
            sources=1,
        )
        short_model = GlyphModel(
            label="s",
            style="roman",
            pixels=frozenset({
                (0, -2),
                (0, -1),
                (1, 0),
            }),
            sources=1,
        )
        black = {
            (12, 20), (11, 21), (11, 22), (10, 23), (10, 24), (11, 25),
            (30, 30), (30, 31), (31, 32),
        }
        hits = ranked_exact_local_hits(
            black,
            [short_model, long_model],
            max_steps=5,
            max_row_gap=1,
        )
        self.assertTrue(hits)
        self.assertEqual("L", hits[0].model.label)
        self.assertEqual(5, hits[0].steps)
        self.assertEqual((10, 25), (hits[0].translate_x, hits[0].baseline))

    def test_same_placement_found_by_many_windows_is_kept_once_at_longest_length(self) -> None:
        model = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({
                (1, -4), (0, -3), (0, -2), (1, -1), (1, 0),
            }),
            sources=1,
        )
        black = {(11, 20), (10, 21), (10, 22), (11, 23), (11, 24)}
        hits = ranked_exact_local_hits(black, [model], max_steps=4, max_row_gap=1)
        placements = [hit for hit in hits if hit.model.label == "a"]
        self.assertEqual(1, len(placements))
        self.assertEqual(4, placements[0].steps)

    def test_single_row_punctuation_is_only_zero_step_fallback(self) -> None:
        letter = GlyphModel(
            label="i",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1), (0, 0)}),
            sources=1,
        )
        dash = GlyphModel(
            label="-",
            style="roman",
            pixels=frozenset({(0, 0), (1, 0), (2, 0)}),
            sources=1,
        )
        black = {(10, 20), (10, 21), (10, 22), (30, 30), (31, 30), (32, 30)}
        hits = ranked_exact_local_hits(black, [dash, letter], max_steps=2, max_row_gap=1)
        self.assertEqual("i", hits[0].model.label)
        dash_hits = [hit for hit in hits if hit.model.label == "-"]
        self.assertTrue(dash_hits)
        self.assertTrue(all(hit.steps == 0 for hit in dash_hits))
        self.assertGreater(hits.index(dash_hits[0]), 0)


if __name__ == "__main__":
    unittest.main()
