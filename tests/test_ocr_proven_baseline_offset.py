from __future__ import annotations

import unittest
from dataclasses import dataclass

from swedish_wordlist_tools import ocr_sequential_raw_page_rows_exactmatch as exactmatch


@dataclass(frozen=True)
class _Model:
    pixels: frozenset[tuple[int, int]]
    width: int
    label: str = "x"


class ProvenBaselineOffsetTest(unittest.TestCase):
    def test_candidate_is_not_shifted_vertically_to_make_it_fit(self) -> None:
        model = _Model(
            pixels=frozenset({(0, -2), (0, -1), (1, 0)}),
            width=2,
        )
        candidates = ((model, 0, ((0, -2), (0, -1))),)

        # The raster contains the right shape, but one pixel lower than the
        # facit's own offset from the already proven baseline 10.
        shifted_raw = {(5, 9), (5, 10), (6, 11)}
        self.assertIsNone(
            exactmatch._best_subset_candidate(
                candidates,
                cursor=5,
                baseline=10,
                raw=shifted_raw,
                left=0,
                right=20,
            )
        )

        # At the facit's exact baseline-relative coordinates it is accepted.
        exact_raw = {(5, 8), (5, 9), (6, 10)}
        chosen = exactmatch._best_subset_candidate(
            candidates,
            cursor=5,
            baseline=10,
            raw=exact_raw,
            left=0,
            right=20,
        )
        self.assertIsNotNone(chosen)
        _chosen_model, placed, x0 = chosen
        self.assertEqual(x0, 5)
        self.assertEqual(placed, exact_raw)


if __name__ == "__main__":
    unittest.main()
