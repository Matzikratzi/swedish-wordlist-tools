from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_candidate_survival import run_candidate_survival
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


def glyph(label: str, pixels: set[tuple[int, int]]) -> GlyphModel:
    return GlyphModel(label=label, style="unknown", pixels=frozenset(pixels))


def place(model: GlyphModel, *, x: int, baseline: int) -> set[tuple[int, int]]:
    return {(x + px, baseline + py) for px, py in model.pixels}


class CandidateSurvivalTest(unittest.TestCase):
    def test_wrong_left_edge_dies_when_profile_changes(self):
        straight = glyph("I", {(0, -3), (0, -2), (0, -1), (0, 0)})
        bend = glyph("L", {(0, -3), (0, -2), (1, -1), (1, 0)})
        black = place(bend, x=57, baseline=20)

        result = run_candidate_survival(
            black,
            [straight, bend],
            start_y=17,
            end_y=20,
            allowed_translate_x_ranges=((50, 64),),
        )

        hits = {(hit.model.label, hit.x, hit.baseline) for hit in result.completed}
        self.assertIn(("L", 57, 20), hits)
        self.assertNotIn(("I", 57, 20), hits)
        self.assertTrue(any(step.died > 0 for step in result.steps))

    def test_horizontal_gap_must_be_blank_inside_glyph_width(self):
        i = glyph("i", {(0, -3), (0, -1), (0, 0), (1, 0)})
        clean = place(i, x=57, baseline=20)
        result = run_candidate_survival(
            clean,
            [i],
            start_y=17,
            end_y=20,
            allowed_translate_x_ranges=((50, 64),),
        )
        self.assertTrue(any(hit.x == 57 and hit.baseline == 20 for hit in result.completed))

        dirty = set(clean)
        dirty.add((58, 18))  # inside i width, in the dot/stem gap
        result2 = run_candidate_survival(
            dirty,
            [i],
            start_y=17,
            end_y=20,
            allowed_translate_x_ranges=((50, 64),),
        )
        self.assertFalse(any(hit.x == 57 and hit.baseline == 20 for hit in result2.completed))

    def test_gap_ignores_ink_beyond_glyph_width(self):
        i = glyph("i", {(0, -3), (0, -1), (0, 0), (1, 0)})
        black = place(i, x=57, baseline=20)
        black.add((61, 18))  # same y as the gap, but beyond i width

        result = run_candidate_survival(
            black,
            [i],
            start_y=17,
            end_y=20,
            allowed_translate_x_ranges=((50, 64),),
        )
        self.assertTrue(any(hit.x == 57 and hit.baseline == 20 for hit in result.completed))


if __name__ == "__main__":
    unittest.main()
