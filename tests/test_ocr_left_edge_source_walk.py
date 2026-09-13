from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_index import LeftEdgeIndex
from swedish_wordlist_tools.ocr_left_edge_source_walk import (
    is_strong_anchor,
    source_walk_hits,
    source_walk_hits_with_resync,
    source_walk_hits_with_top_retry,
    stable_left_contour_start,
    walk_prefixes_at,
)


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

    def test_source_pixels_drive_actual_left_edge(self) -> None:
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

    def test_top_retry_can_skip_taller_following_glyph_ink(self) -> None:
        low = GlyphModel(
            label="x",
            style="roman",
            pixels=frozenset({(0, -1), (1, -1), (0, 0), (1, 0)}),
            sources=1,
        )
        tall_following = {
            (15, 10),
            (15, 11),
            (15, 12),
            (10, 12), (11, 12),
            (10, 13), (11, 13),
        }
        index = LeftEdgeIndex([low])
        hits = source_walk_hits_with_top_retry(
            tall_following,
            index,
            max_x=14,
            max_skip_rows=4,
        )
        self.assertTrue(hits)
        self.assertTrue(any(hit.x == 10 and hit.y == 12 for hit in hits))
        self.assertEqual(2, min(hit.skipped_top_rows for hit in hits))

    def test_horizontal_resync_skips_unknown_leading_glyph(self) -> None:
        known = GlyphModel(
            label="x",
            style="roman",
            pixels=frozenset({
                (0, -3), (1, -3),
                (0, -2), (1, -2),
                (0, -1), (1, -1),
                (0, 0), (1, 0),
            }),
            sources=1,
        )
        black = {
            (3, 20), (4, 20), (5, 20),
            (3, 21), (5, 21),
            (4, 22),
            (10, 19), (11, 19),
            (10, 20), (11, 20),
            (10, 21), (11, 21),
            (10, 22), (11, 22),
        }
        index = LeftEdgeIndex([known])
        hits = source_walk_hits_with_resync(black, index, max_skip_rows=4)
        self.assertTrue(hits)
        self.assertTrue(any(hit.x == 10 and hit.y == 19 for hit in hits))
        self.assertEqual(7, min(hit.skipped_left_columns for hit in hits))

    def test_horizontal_resync_skips_weak_dash_before_strong_letter(self) -> None:
        dash = GlyphModel(
            label="-",
            style="roman",
            pixels=frozenset({(0, 0), (1, 0), (2, 0)}),
            sources=1,
        )
        letter = GlyphModel(
            label="p",
            style="roman",
            pixels=frozenset({
                (0, -4), (1, -4),
                (0, -3), (2, -3),
                (0, -2), (1, -2), (2, -2),
                (0, -1), (2, -1),
                (0, 0), (1, 0), (2, 0),
            }),
            sources=1,
        )
        black = {
            (3, 25), (4, 25), (5, 25),
            (10, 20), (11, 20),
            (10, 21), (12, 21),
            (10, 22), (11, 22), (12, 22),
            (10, 23), (12, 23),
            (10, 24), (11, 24), (12, 24),
        }
        index = LeftEdgeIndex([dash, letter])
        hits = source_walk_hits_with_resync(black, index, max_skip_rows=8)
        self.assertTrue(hits)
        self.assertTrue(any(glyph.model.label == "p" for hit in hits for glyph in hit.exact))
        self.assertTrue(all(hit.x == 10 for hit in hits))
        self.assertTrue(all(is_strong_anchor(hit) for hit in hits))

    def test_only_weak_anchor_is_not_accepted_as_strong_baseline_source(self) -> None:
        dash = GlyphModel(
            label="-",
            style="roman",
            pixels=frozenset({(0, 0), (1, 0), (2, 0)}),
            sources=1,
        )
        black = {(3, 7), (4, 7), (5, 7)}
        hits = source_walk_hits_with_resync(black, LeftEdgeIndex([dash]))
        self.assertTrue(hits)
        self.assertTrue(all(not is_strong_anchor(hit) for hit in hits))

    def test_strong_anchor_derives_model_baseline_without_row_baseline(self) -> None:
        letter = GlyphModel(
            label="t",
            style="roman",
            pixels=frozenset({
                (0, -6), (1, -6),
                (0, -5),
                (0, -4), (1, -4),
                (0, -3),
                (0, -2),
                (0, -1),
                (0, 0), (1, 0),
            }),
            sources=1,
        )
        baseline = 15
        x0 = 22
        black = {(x0 + x, baseline + y) for x, y in letter.pixels}
        hits = source_walk_hits_with_resync(black, LeftEdgeIndex([letter]))
        strong = [hit for hit in hits if is_strong_anchor(hit)]
        self.assertTrue(strong)
        derived = {
            hit.y - glyph.model.min_y
            for hit in strong
            for glyph in hit.exact
        }
        self.assertEqual({baseline}, derived)

    def test_stable_left_contour_can_ignore_far_right_top_ink(self) -> None:
        black = {
            (85, 2),
            (84, 3),
            (60, 4), (61, 4),
            (59, 5), (60, 5),
            (60, 6),
            (59, 7),
        }
        contour = stable_left_contour_start(black)
        self.assertIsNotNone(contour)
        assert contour is not None
        self.assertEqual((2, 85), contour.observations[0])
        self.assertEqual(4, contour.chosen_y)
        self.assertEqual(60, contour.chosen_x)
        self.assertEqual(2, contour.skipped_ink_rows)

    def test_stable_left_contour_keeps_top_when_no_large_shift_exists(self) -> None:
        black = {(10, 2), (11, 3), (10, 4), (9, 5), (10, 6)}
        contour = stable_left_contour_start(black)
        self.assertIsNotNone(contour)
        assert contour is not None
        self.assertEqual(2, contour.chosen_y)
        self.assertEqual(10, contour.chosen_x)
        self.assertEqual(0, contour.skipped_ink_rows)


if __name__ == "__main__":
    unittest.main()
