import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_open_bottom_probe import probe_open_bottom


class OpenBottomProbeTests(unittest.TestCase):
    def test_continues_after_unmatched_local_ink(self):
        model_a = GlyphModel(
            label="a",
            style="roman",
            pixels=frozenset({(0, -1), (0, 0), (1, 0)}),
            sources=3,
        )
        model_b = GlyphModel(
            label="b",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1), (0, 0), (1, 0)}),
            sources=2,
        )
        baseline = 4
        ink = {
            (1, 3), (1, 4), (2, 4),
            # Unexplained local blob between the two glyphs.
            (4, 5), (4, 6),
            (7, 2), (7, 3), (7, 4), (8, 4),
            # Extra lower-row ink is deliberately allowed.
            (10, 7), (11, 7),
        }

        result = probe_open_bottom(
            ink,
            width=12,
            height=9,
            models=[model_a, model_b],
            baseline_hint=baseline,
            baseline_radius=0,
        )

        self.assertEqual(result["baseline"], baseline)
        self.assertEqual([m.label for m in result["selected"]], ["a", "b"])
        self.assertEqual(result["covered_pixels"], 7)
        self.assertEqual(result["unmatched_below"], 4)
        self.assertEqual(result["rightmost_covered_x"], 8)

    def test_prefers_more_upper_evidence_before_deeper_coverage(self):
        upper = GlyphModel(
            label="u",
            style="roman",
            pixels=frozenset({(0, -2), (0, -1), (0, 0)}),
            sources=1,
        )
        deep = GlyphModel(
            label="d",
            style="roman",
            pixels=frozenset({(0, -1), (0, 0), (0, 1), (0, 2)}),
            sources=10,
        )
        ink = {(2, 2), (2, 3), (2, 4), (2, 5), (2, 6)}

        result = probe_open_bottom(
            ink,
            width=5,
            height=8,
            models=[upper, deep],
            baseline_hint=4,
            baseline_radius=0,
        )

        # Both are exact subsets, but the upper model explains 3 pixels at/above
        # baseline while the deeper one explains only 2.  Upward evidence wins.
        self.assertEqual([m.label for m in result["selected"]], ["u"])
        self.assertEqual(result["covered_above"], 3)

    def test_rejects_negative_baseline_radius(self):
        with self.assertRaises(ValueError):
            probe_open_bottom(set(), 1, 1, [], baseline_radius=-1)


if __name__ == "__main__":
    unittest.main()
