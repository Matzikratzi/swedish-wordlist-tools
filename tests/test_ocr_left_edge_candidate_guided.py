from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_candidate_guided import candidate_guided_exact_hits


class CandidateGuidedLeftEdgeTests(unittest.TestCase):
    def test_walk_extends_beyond_fixed_eight_steps_when_candidate_requires_it(self) -> None:
        model = GlyphModel(
            label="g",
            style="roman",
            pixels=frozenset((x, y - 10) for y, x in enumerate((2, 1, 1, 0, 0, 1, 2, 2, 1, 0, 1))),
            sources=1,
        )
        # Translate model by (+20,+30): baseline becomes 30.
        black = {(x + 20, y + 30) for x, y in model.pixels}

        hits, stats = candidate_guided_exact_hits(black, [model], max_row_gap=1)

        self.assertTrue(hits)
        self.assertEqual(10, hits[0].matched_steps)
        self.assertEqual(20, hits[0].translate_x)
        self.assertEqual(30, hits[0].baseline)
        self.assertGreaterEqual(stats.relation_steps, 10)
        self.assertGreater(stats.expected_pixel_checks, 0)
        # Full-raster verification is no longer repeated at every contour step.
        self.assertLess(stats.exact_checks, stats.relation_steps)

    def test_candidate_dies_when_next_expected_pixel_is_missing(self) -> None:
        model = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, -4), (1, -3), (1, -2), (0, -1), (0, 0)}),
            sources=1,
        )
        # The first relation matches.  The model then predicts x=11 at y=12,
        # but only x=12 exists there, so the guided candidate stops immediately.
        black = {(10, 10), (11, 11), (12, 12), (12, 13), (12, 14)}

        hits, stats = candidate_guided_exact_hits(black, [model], max_row_gap=1)

        self.assertEqual((), hits)
        self.assertGreater(stats.expected_pixel_checks, 0)

    def test_exact_hit_from_middle_model_offset_derives_baseline(self) -> None:
        model = GlyphModel(
            label="p",
            style="roman",
            pixels=frozenset({
                (2, -6),
                (1, -5),
                (1, -4),
                (0, -3),
                (0, -2),
                (1, -1),
                (1, 0),
            }),
            sources=1,
        )
        black = {(x + 40, y + 17) for x, y in model.pixels}

        hits, _stats = candidate_guided_exact_hits(black, [model], max_row_gap=1)

        self.assertTrue(any(hit.baseline == 17 and hit.translate_x == 40 for hit in hits))
        self.assertEqual(6, max(hit.matched_steps for hit in hits))

    def test_same_track_is_not_rechecked_from_duplicate_scan_positions(self) -> None:
        model = GlyphModel(
            label="l",
            style="roman",
            pixels=frozenset({(1, -4), (0, -3), (0, -2), (0, -1), (0, 0)}),
            sources=1,
        )
        black = {(x + 20, y + 10) for x, y in model.pixels}
        # Extra ink creates additional scan_x values but must not cause the same
        # concrete model/anchor/translation track to be fully checked again.
        black.update({(18, 20), (19, 21)})

        hits, stats = candidate_guided_exact_hits(black, [model], max_row_gap=1)

        self.assertTrue(any(hit.translate_x == 20 and hit.baseline == 10 for hit in hits))
        self.assertLessEqual(stats.exact_checks, stats.started_tracks)


if __name__ == "__main__":
    unittest.main()
