from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_candidate_survival import (
    glyph_left_profile,
    run_candidate_survival,
    vertical_blank_columns,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


def glyph(label: str, pixels: set[tuple[int, int]]) -> GlyphModel:
    return GlyphModel(label=label, style="unknown", pixels=frozenset(pixels))


def place(model: GlyphModel, *, x: int, baseline: int) -> set[tuple[int, int]]:
    return {(x + px, baseline + py) for px, py in model.pixels}


class CandidateSurvivalTest(unittest.TestCase):
    def test_normalized_glyph_profile_can_go_negative_below_top(self):
        a = glyph(
            "a",
            {
                (2, 0),
                (0, 1),
                (1, 2),
                (3, 3),
                (0, 4),
                (0, 5),
                (0, 6),
                (1, 7),
            },
        )
        self.assertEqual((0, -2, -1, 1, -2, -2, -2, -1), glyph_left_profile(a))

    def test_vertical_gap_only_needs_to_be_blank_through_baseline(self):
        black = {
            (10, 5),
            (10, 6),
            (12, 5),
            (12, 8),
            (11, 9),  # below baseline: must not spoil x=11 as separator
        }
        self.assertEqual(
            (11,),
            vertical_blank_columns(
                black,
                start_x=10,
                end_x=12,
                top_y=5,
                baseline=8,
            ),
        )

    def test_vertical_gap_is_not_blank_if_baseline_pixel_exists(self):
        black = {(11, 8), (11, 9)}
        self.assertEqual(
            (),
            vertical_blank_columns(
                black,
                start_x=11,
                end_x=11,
                top_y=5,
                baseline=8,
            ),
        )

    def test_descender_may_reenter_separator_below_baseline_and_complete_glyph(self):
        # x=57 is a perfectly blank separator through baseline=20.  The glyph
        # itself starts to its right, but its descender bends left into x=57 at
        # baseline+1.  Separator detection must still accept x=57, and glyph
        # verification must continue below baseline and use that pixel.
        j = glyph(
            "j",
            {
                (1, -3),
                (1, -2),
                (1, -1),
                (1, 0),
                (0, 1),
            },
        )
        black = place(j, x=57, baseline=20)

        self.assertEqual(
            (57,),
            vertical_blank_columns(
                black,
                start_x=57,
                end_x=57,
                top_y=17,
                baseline=20,
            ),
        )

        result = run_candidate_survival(
            black,
            [j],
            start_y=17,
            end_y=21,
            allowed_translate_x_ranges=((50, 64),),
        )
        self.assertEqual(
            [("j", 57, 20, 21)],
            [
                (hit.model.label, hit.x, hit.baseline, hit.survived_to_y)
                for hit in result.completed
            ],
        )

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

    def test_candidate_survives_when_another_glyph_owns_front_temporarily(self):
        model = glyph("x", {(2, -2), (0, -1), (1, 0)})
        black = place(model, x=57, baseline=20)
        black.add((56, 19))
        black.add((70, 18))

        result = run_candidate_survival(
            black,
            [model],
            start_y=18,
            end_y=20,
            allowed_translate_x_ranges=((50, 64),),
        )

        self.assertEqual(1, len(result.completed))
        hit = result.completed[0]
        self.assertEqual((57, 20), (hit.x, hit.baseline))
        self.assertEqual(2, hit.front_rows)
        self.assertEqual(1, hit.hidden_rows)

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
        dirty.add((58, 18))
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
        black.add((61, 18))

        result = run_candidate_survival(
            black,
            [i],
            start_y=17,
            end_y=20,
            allowed_translate_x_ranges=((50, 64),),
        )
        self.assertTrue(any(hit.x == 57 and hit.baseline == 20 for hit in result.completed))

    def test_candidate_is_born_only_at_model_top_not_from_internal_rows(self):
        tall = glyph("T", {(0, -4), (0, -3), (0, -2), (0, -1), (0, 0)})
        black = place(tall, x=57, baseline=20)

        result = run_candidate_survival(
            black,
            [tall],
            start_y=16,
            end_y=20,
            allowed_translate_x_ranges=((50, 64),),
        )

        self.assertEqual(1, result.seeded)
        self.assertEqual([1, 0, 0, 0, 0], [step.born for step in result.steps])
        self.assertEqual([(57, 20)], [(hit.x, hit.baseline) for hit in result.completed])


if __name__ == "__main__":
    unittest.main()
