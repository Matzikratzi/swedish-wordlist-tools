from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_baseline_up import BaselineMatch
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_live_profile_candidates import (
    check_live_candidate,
    pick_unique_live_semantic,
)


def model(label: str, pixels: set[tuple[int, int]]) -> GlyphModel:
    return GlyphModel(label=label, style="unknown", pixels=frozenset(pixels), sources=1)


def placed(hit_model: GlyphModel, *, tx: int, baseline: int) -> frozenset[tuple[int, int]]:
    return frozenset((tx + x, baseline + y) for x, y in hit_model.pixels)


def hit(hit_model: GlyphModel, *, tx: int, baseline: int) -> BaselineMatch:
    return BaselineMatch(
        model=hit_model,
        tx=tx,
        baseline=baseline,
        pixels=placed(hit_model, tx=tx, baseline=baseline),
        discovered_y=baseline,
    )


def rows(pixels: set[tuple[int, int]]) -> dict[int, set[int]]:
    out: dict[int, set[int]] = {}
    for x, y in pixels:
        out.setdefault(y, set()).add(x)
    return out


class LiveProfileCandidateTests(unittest.TestCase):
    def test_candidate_survives_when_another_glyph_is_farther_left(self) -> None:
        glyph = model("x", {(2, -2), (0, -1), (1, 0)})
        candidate = hit(glyph, tx=20, baseline=10)
        residual = set(candidate.pixels)
        residual.add((19, 9))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
        )

        self.assertTrue(check.alive)
        self.assertEqual(check.hidden_rows, 1)
        self.assertEqual(check.front_rows, 2)

    def test_candidate_dies_when_front_moves_right_of_expected_pixel(self) -> None:
        glyph = model("x", {(0, -1), (0, 0)})
        candidate = hit(glyph, tx=20, baseline=10)
        residual = {(20, 9), (21, 10)}

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
        )

        self.assertFalse(check.alive)
        self.assertEqual(check.contradiction_y, 10)

    def test_internal_gap_must_be_blank_inside_candidate_span(self) -> None:
        glyph = model("i", {(0, -3), (0, -1), (1, 0)})
        candidate = hit(glyph, tx=20, baseline=10)
        residual = set(candidate.pixels)
        residual.add((21, 8))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
        )

        self.assertFalse(check.alive)
        self.assertEqual(check.contradiction_y, 8)

    def test_short_dot_is_not_accepted_while_i_is_still_possible(self) -> None:
        dot = model(".", {(0, -3)})
        i_glyph = model("i", {(0, -3), (0, -1), (0, 0)})
        dot_hit = hit(dot, tx=20, baseline=10)
        i_hit = hit(i_glyph, tx=20, baseline=10)
        residual = set(i_hit.pixels)

        selected, survivors = pick_unique_live_semantic(
            (dot_hit, i_hit),
            rows(residual),
            after_left=10,
            column_right=40,
        )

        self.assertIsNone(selected)
        self.assertEqual({".", "i"}, {check.candidate.model.label for check in survivors})

    def test_profile_contradiction_can_reduce_ambiguity_to_one_glyph(self) -> None:
        right_bending = model("r", {(0, -1), (1, 0)})
        straight = model("f", {(1, -1), (0, 0)})
        r_hit = hit(right_bending, tx=20, baseline=10)
        f_hit = hit(straight, tx=20, baseline=10)
        residual = set(f_hit.pixels)
        residual.add((19, 9))

        selected, survivors = pick_unique_live_semantic(
            (r_hit, f_hit),
            rows(residual),
            after_left=10,
            column_right=40,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual("f", selected.model.label)
        self.assertEqual(["f"], [check.candidate.model.label for check in survivors])

    def test_candidate_dies_when_required_profile_change_never_happens(self) -> None:
        r_glyph = model("r", {(0, -1), (1, 0)})
        r_hit = hit(r_glyph, tx=20, baseline=10)
        residual = set(r_hit.pixels)
        residual.add((20, 10))

        check = check_live_candidate(
            r_hit,
            rows(residual),
            after_left=10,
            column_right=40,
        )

        self.assertFalse(check.alive)
        self.assertEqual(10, check.contradiction_y)

    def test_short_candidate_dies_when_front_continues_above_its_top(self) -> None:
        short = model("r", {(0, -1), (1, 0)})
        candidate = hit(short, tx=20, baseline=10)
        residual = set(candidate.pixels)
        residual.add((20, 8))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
            row_top=7,
        )

        self.assertFalse(check.alive)
        self.assertEqual(8, check.contradiction_y)

    def test_short_candidate_can_end_when_front_moves_right_of_its_span(self) -> None:
        short = model("r", {(0, -1), (1, 0)})
        candidate = hit(short, tx=20, baseline=10)
        residual = set(candidate.pixels)
        residual.add((25, 8))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
            row_top=7,
        )

        self.assertTrue(check.alive)

    def test_candidate_touching_row_top_needs_no_upward_terminal_event(self) -> None:
        glyph = model("top", {(0, -2), (1, -1), (0, 0)})
        candidate = hit(glyph, tx=20, baseline=10)
        residual = set(candidate.pixels)
        # This would contradict an upward terminal event, but y=7 is above the
        # known row boundary because candidate_top == row_top == 8.
        residual.add((20, 7))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
            row_top=8,
        )

        self.assertTrue(check.alive)

    def test_candidate_ending_inside_known_bottom_requires_downward_terminal_event(self) -> None:
        glyph = model("short", {(0, -1), (2, 0)})
        candidate = hit(glyph, tx=20, baseline=10)
        residual = set(candidate.pixels)
        # Candidate ends at y=10, but y=11 was already known. Its next profile
        # pixel stays inside x=20..22 instead of moving right of the glyph.
        residual.add((21, 11))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
            known_bottom_before=12,
        )

        self.assertFalse(check.alive)
        self.assertEqual(11, check.contradiction_y)

    def test_candidate_reaching_old_bottom_needs_no_downward_terminal_event(self) -> None:
        glyph = model("deep", {(0, -1), (2, 0)})
        candidate = hit(glyph, tx=20, baseline=10)
        residual = set(candidate.pixels)
        # y=11 is newly exposed territory. It must not be used to demand a
        # terminal event because the previous known bottom was only y=10.
        residual.add((21, 11))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
            known_bottom_before=10,
        )

        self.assertTrue(check.alive)

    def test_known_downward_terminal_event_can_move_right(self) -> None:
        glyph = model("short", {(0, -1), (2, 0)})
        candidate = hit(glyph, tx=20, baseline=10)
        residual = set(candidate.pixels)
        residual.add((25, 11))

        check = check_live_candidate(
            candidate,
            rows(residual),
            after_left=10,
            column_right=40,
            known_bottom_before=12,
        )

        self.assertTrue(check.alive)


if __name__ == "__main__":
    unittest.main()
