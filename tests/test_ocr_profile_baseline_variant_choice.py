from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_profile_automaton_batch import (
    _choose_same_raster_variant,
    _established_baseline_distance,
)


class ProfileBaselineVariantChoiceTest(unittest.TestCase):
    def test_nearby_established_baseline_wins(self) -> None:
        ordinary = ("u", 100, 248, 8, 0)
        superscript = ("ᵘ", 100, 253, 8, 1)
        chosen = _choose_same_raster_variant(
            [ordinary, superscript],
            {253: [object()]},
        )
        self.assertEqual(chosen, superscript)

    def test_original_rank_wins_without_established_row(self) -> None:
        first = ("u", 100, 248, 8, 0)
        second = ("ᵘ", 100, 253, 8, 1)
        chosen = _choose_same_raster_variant([first, second], {})
        self.assertEqual(chosen, first)

    def test_other_physical_row_does_not_attract(self) -> None:
        self.assertEqual(_established_baseline_distance(253, {300: [object()]}), 4)


if __name__ == "__main__":
    unittest.main()
