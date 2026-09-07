from __future__ import annotations

import unittest
from types import SimpleNamespace

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, exact_matches
from swedish_wordlist_tools.ocr_group_baseline_fallback import (
    _anchor_missing_baseline,
    _anchor_scan_key,
    _baseline_anchor_candidates,
)


class MissingBaselineAnchorTest(unittest.TestCase):
    def test_scan_order_is_top_then_left_and_baseline_comes_from_model(self):
        marker = GlyphModel(
            label="¤",
            style="roman",
            pixels=frozenset({(0, -2), (1, -2), (0, -1)}),
            sources=3,
        )
        later = GlyphModel(
            label="x",
            style="roman",
            pixels=frozenset({(0, -1), (1, -1)}),
            sources=2,
        )
        ink = {
            (7, 0),
            (1, 2), (2, 2), (1, 3),
            (8, 4), (9, 4),
        }
        anchors = _baseline_anchor_candidates(ink, 12, 7, [marker, later])
        self.assertTrue(anchors)
        self.assertEqual(anchors[0].label, "¤")
        self.assertEqual(anchors[0].baseline, 4)

    def test_lazy_scan_matches_old_global_sort_order(self):
        marker = GlyphModel(
            label="¤",
            style="roman",
            pixels=frozenset({(0, -2), (1, -2), (0, -1)}),
            sources=3,
        )
        bar = GlyphModel(
            label="|",
            style="unknown",
            pixels=frozenset({(0, -3), (0, -2), (0, -1)}),
            sources=1,
        )
        follower = GlyphModel(
            label="a",
            style="bold",
            pixels=frozenset({(0, -1), (1, -1), (1, 0)}),
            sources=4,
        )
        models = [marker, bar, follower]
        ink = {
            (1, 2), (2, 2), (1, 3),
            (6, 1), (6, 2), (6, 3),
            (9, 3), (10, 3), (10, 4),
        }
        expected = sorted(
            exact_matches(
                ink,
                14,
                7,
                models,
                require_whole_components=False,
            ),
            key=_anchor_scan_key,
        )
        actual = _baseline_anchor_candidates(ink, 14, 7, models)
        self.assertEqual(actual, expected)

    def test_anchor_recovers_missing_baseline_and_keeps_anchor_in_partition(self):
        marker = GlyphModel(
            label="¤",
            style="roman",
            pixels=frozenset({(0, -2), (1, -2), (0, -1)}),
            sources=4,
        )
        follower = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, -1), (1, -1), (1, 0)}),
            sources=4,
        )
        ink = {
            (1, 2), (2, 2), (1, 3),
            (5, 3), (6, 3), (6, 4),
        }
        result = {
            "baseline": None,
            "ink": ink,
            "selected": [],
            "covered_pixels": 0,
            "unmatched_pixels": len(ink),
            "fully_exact": False,
        }
        crop = SimpleNamespace(width=10, height=7)

        recovered = _anchor_missing_baseline(result, crop, [marker, follower])

        self.assertEqual(recovered["baseline"], 4)
        self.assertEqual(recovered["baseline_anchor"]["label"], "¤")
        self.assertEqual(recovered["baseline_anchor"]["top"], 2)
        self.assertEqual(recovered["covered_pixels"], len(ink))
        self.assertEqual("".join(match.label for match in recovered["selected"]), "¤a")
        self.assertTrue(recovered["fully_exact"])

    def test_line_start_window_can_exclude_far_right_match(self):
        marker = GlyphModel(
            label="¤",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1)}),
            sources=2,
        )
        ink = {(8, 1), (8, 2)}
        anchors = _baseline_anchor_candidates(
            ink,
            12,
            6,
            [marker],
            line_start_left=0,
            line_start_right=6,
        )
        self.assertEqual(anchors, [])


if __name__ == "__main__":
    unittest.main()
