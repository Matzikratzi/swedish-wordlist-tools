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

    def test_verified_boundary_blocks_padding_only_across_that_cut(self) -> None:
        row_map = {
            "columns": [
                {
                    "rows": [
                        {"page_top": 10, "page_bottom": 20, "crop_left": 0, "crop_right": 100},
                        {"page_top": 20, "page_bottom": 30, "crop_left": 0, "crop_right": 100},
                    ]
                }
            ]
        }
        boundary_ui._mark_strict_boundaries(
            row_map,
            [{"column": 0, "upper_row": 0, "lower_row": 1, "corrected_boundary": 20}],
        )
        upper, lower = row_map["columns"][0]["rows"]

        upper_box = boundary_ui._row_crop_box_with_strict_boundaries(
            upper, column=0, page_width=100, page_height=100, pad_y=1, left_override=None
        )
        lower_box = boundary_ui._row_crop_box_with_strict_boundaries(
            lower, column=0, page_width=100, page_height=100, pad_y=1, left_override=None
        )

        # Upper row keeps its top padding but may not borrow y=20 from below.
        self.assertEqual(upper_box, (0, 9, 100, 20))
        # Lower row may not borrow y=19 from above, but keeps bottom padding.
        self.assertEqual(lower_box, (0, 20, 100, 31))

    def test_generation_stamp_rejects_analysis_from_old_row_geometry(self) -> None:
        start_generation = boundary_ui._current_boundary_generation()
        boundary_ui._advance_boundary_generation()
        with self.assertRaises(boundary_ui._BoundaryGenerationChanged):
            boundary_ui._stamp_generation(
                {"covered_pixels": 10, "source_pixels": 10},
                expected_generation=start_generation,
            )

    def test_public_loader_retries_when_boundary_changes_mid_analysis(self) -> None:
        original = boundary_ui._load_review_state_with_cached_boundaries_once
        calls = []

        def flaky_loader(context, position, models):
            calls.append(position)
            if len(calls) == 1:
                raise boundary_ui._BoundaryGenerationChanged
            return {
                "column": position[0],
                "row": position[1],
                "covered_pixels": 10,
                "source_pixels": 10,
                "fully_exact": True,
                "row_boundary_generation": boundary_ui._current_boundary_generation(),
            }

        boundary_ui._load_review_state_with_cached_boundaries_once = flaky_loader
        try:
            state = boundary_ui.load_review_state_with_cached_boundaries({}, (1, 28), [])
        finally:
            boundary_ui._load_review_state_with_cached_boundaries_once = original

        self.assertEqual(calls, [(1, 28), (1, 28)])
        self.assertEqual(state["row"], 28)


if __name__ == "__main__":
    unittest.main()
