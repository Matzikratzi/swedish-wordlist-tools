from __future__ import annotations

from dataclasses import dataclass
import unittest

from swedish_wordlist_tools.ocr_row_split_left_support import (
    first_plausible_candidate_downward,
    row_start_geometry,
    row_start_is_typographically_plausible,
    split_left_support_decision,
)


@dataclass(frozen=True)
class Candidate:
    x: int
    y: int
    steps: int
    label: str


class RowSplitLeftSupportTests(unittest.TestCase):
    def test_late_tiny_fragment_is_not_allowed_to_establish_own_row(self) -> None:
        # Apne-like geometry: the following real row starts around x=57 while
        # the tiny upper fragment is almost 30 px into the row.
        upper = {(85, 0), (85, 1), (86, 1), (87, 1), (86, 2)}
        lower = {
            (57, 4), (58, 4), (59, 4),
            (57, 5), (58, 5), (60, 5),
            (57, 6), (59, 6), (61, 6),
            (58, 7), (60, 7), (62, 7),
        }

        decision = split_left_support_decision(upper, lower)

        self.assertEqual(28, decision.start_delta)
        self.assertFalse(decision.upper_has_own_left_support)
        self.assertTrue(decision.looks_like_late_upper_fragment)

    def test_low_continuation_row_with_own_left_support_is_preserved(self) -> None:
        upper = {
            (58, 0), (59, 0), (60, 0),
            (58, 1), (60, 1), (61, 1),
            (58, 2), (59, 2), (61, 2),
            (59, 3), (60, 3), (61, 3),
        }
        lower = {
            (57, 8), (58, 8), (59, 8),
            (57, 9), (60, 9),
            (57, 10), (59, 10), (61, 10),
            (58, 11), (60, 11),
        }

        decision = split_left_support_decision(upper, lower)

        self.assertEqual(1, decision.start_delta)
        self.assertTrue(decision.upper_has_own_left_support)
        self.assertFalse(decision.looks_like_late_upper_fragment)

    def test_indented_but_real_continuation_row_is_preserved(self) -> None:
        upper = {
            (68, 0), (69, 0), (70, 0),
            (68, 1), (70, 1),
            (68, 2), (69, 2), (71, 2),
            (69, 3), (70, 3),
        }
        lower = {(57, y) for y in range(8, 13)} | {(58, y) for y in range(8, 13)}

        decision = split_left_support_decision(upper, lower)

        self.assertEqual(11, decision.start_delta)
        self.assertTrue(decision.upper_has_own_left_support)
        self.assertFalse(decision.looks_like_late_upper_fragment)

    def test_half_indent_beyond_continuation_is_hard_start_limit(self) -> None:
        geometry = row_start_geometry(46, 57, 68)

        self.assertEqual(74, geometry.late_start_limit_x)
        self.assertTrue(row_start_is_typographically_plausible(74, geometry))
        self.assertFalse(row_start_is_typographically_plausible(75, geometry))
        self.assertFalse(row_start_is_typographically_plausible(83, geometry))

    def test_downward_search_skips_apne_like_late_mark_and_finds_real_start(self) -> None:
        geometry = row_start_geometry(46, 57, 68)
        candidates = [
            Candidate(83, 1, 1, "."),
            Candidate(57, 5, 6, "a"),
            Candidate(58, 18, 9, "A"),
        ]

        hit = first_plausible_candidate_downward(
            candidates,
            start_x=lambda c: c.x,
            top_y=lambda c: c.y,
            geometry=geometry,
            previous_break_y=0,
            max_row_distance=15,
            strong_enough=lambda c: c.steps >= 3,
        )

        self.assertEqual(Candidate(57, 5, 6, "a"), hit)

    def test_downward_search_keeps_low_continuation_before_headword(self) -> None:
        geometry = row_start_geometry(46, 57, 68)
        candidates = [
            Candidate(68, 3, 4, "r"),
            Candidate(57, 9, 10, "b"),
        ]

        hit = first_plausible_candidate_downward(
            candidates,
            start_x=lambda c: c.x,
            top_y=lambda c: c.y,
            geometry=geometry,
            previous_break_y=0,
            max_row_distance=15,
            strong_enough=lambda c: c.steps >= 3,
        )

        self.assertEqual(Candidate(68, 3, 4, "r"), hit)

    def test_downward_search_does_not_reach_next_row_beyond_distance(self) -> None:
        geometry = row_start_geometry(46, 57, 68)
        candidates = [
            Candidate(83, 1, 1, "."),
            Candidate(57, 17, 10, "b"),
        ]

        hit = first_plausible_candidate_downward(
            candidates,
            start_x=lambda c: c.x,
            top_y=lambda c: c.y,
            geometry=geometry,
            previous_break_y=0,
            max_row_distance=15,
            strong_enough=lambda c: c.steps >= 3,
        )

        self.assertIsNone(hit)


if __name__ == "__main__":
    unittest.main()
