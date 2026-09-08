from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_conservative_late_anchor import repair_late_baseline_anchor
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, Match


class ConservativeLateAnchorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = [
            GlyphModel("b", "roman", frozenset({(0, -1), (0, 0), (1, 0)}), 2),
            GlyphModel("H", "roman", frozenset({(0, -4), (0, 0), (1, 0)}), 2),
        ]

    def test_low_left_glyph_replaces_high_late_anchor(self) -> None:
        image = Image.new("L", (30, 12), 255)
        early = {(2, 5), (2, 6), (3, 6)}  # b, baseline 6
        late = {(20, 0), (20, 4), (21, 4)}  # H, baseline 4
        ink = early | late
        for point in ink:
            image.putpixel(point, 0)

        late_match = Match(
            label="H",
            style="roman",
            x=20,
            baseline=4,
            pixels=frozenset(late),
            model_pixels=3,
            sources=2,
        )
        result = {
            "ink": ink,
            "baseline": 4,
            "selected": [late_match],
            "covered_pixels": 3,
            "unmatched_pixels": 3,
            "fully_exact": False,
        }

        repaired, record = repair_late_baseline_anchor(result, image, self.models)

        self.assertIsNotNone(record)
        self.assertEqual(repaired["baseline"], 6)
        self.assertEqual(repaired["selected"][0].label, "b")
        self.assertEqual(record.old_left, 20)
        self.assertEqual(record.ink_left, 2)
        self.assertEqual(record.new_left, 2)

    def test_anchor_near_left_edge_is_not_changed(self) -> None:
        image = Image.new("L", (20, 12), 255)
        early = {(2, 5), (2, 6), (3, 6)}
        ink = early | {(9, 0)}
        for point in ink:
            image.putpixel(point, 0)
        match = Match(
            label="b",
            style="roman",
            x=2,
            baseline=6,
            pixels=frozenset(early),
            model_pixels=3,
            sources=2,
        )
        result = {
            "ink": ink,
            "baseline": 6,
            "selected": [match],
            "covered_pixels": 3,
            "unmatched_pixels": 1,
            "fully_exact": False,
        }

        repaired, record = repair_late_baseline_anchor(result, image, self.models)

        self.assertIsNone(record)
        self.assertIs(repaired, result)
        self.assertEqual(repaired["baseline"], 6)


if __name__ == "__main__":
    unittest.main()
