from __future__ import annotations

import unittest

from swedish_wordlist_tools import ocr_review_five_rows_glyphs_boundary_html as boundary_ui


class BoundaryAwareStateCacheTests(unittest.TestCase):
    def test_learned_boundary_invalidates_even_old_exact_state(self) -> None:
        start_generation = boundary_ui._current_boundary_generation()

        def loader(position):
            return {
                "column": position[0],
                "row": position[1],
                "covered_pixels": 10,
                "source_pixels": 10,
                "fully_exact": True,
                "row_boundary_generation": boundary_ui._current_boundary_generation(),
            }

        cache = boundary_ui.BoundaryAwareStateCache(loader)
        first = cache.get((1, 27))
        self.assertEqual(first["row_boundary_generation"], start_generation)

        boundary_ui._advance_boundary_generation()
        second = cache.get((1, 27))
        self.assertEqual(second["row_boundary_generation"], start_generation + 1)
        self.assertIsNot(first, second)

    def test_edge_selects_only_adjacent_boundaries(self) -> None:
        self.assertEqual(boundary_ui._candidate_boundaries_for_edge("top", 27, 50), [26])
        self.assertEqual(boundary_ui._candidate_boundaries_for_edge("bottom", 27, 50), [27])
        self.assertEqual(boundary_ui._candidate_boundaries_for_edge("both", 27, 50), [26, 27])
        self.assertEqual(boundary_ui._candidate_boundaries_for_edge("top", 0, 50), [])
        self.assertEqual(boundary_ui._candidate_boundaries_for_edge("bottom", 49, 50), [])


if __name__ == "__main__":
    unittest.main()
