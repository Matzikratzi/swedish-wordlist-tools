import unittest

from swedish_wordlist_tools.ocr_exact_glyph_review_queue_v12 import (
    _assign_components_to_rows,
    _extract_exact_rows_from_tangle,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, exact_matches


class FiveRowContextTest(unittest.TestCase):
    def test_assigns_whole_residual_components_to_target_and_neighbor_rows(self):
        bands = [
            {"top": 0, "bottom": 5},
            {"top": 10, "bottom": 15},
            {"top": 20, "bottom": 25},
            {"top": 30, "bottom": 35},
            {"top": 40, "bottom": 45},
        ]
        target_body = {(5, 21), (5, 22), (6, 22)}
        target_dot = {(5, 18), (6, 18)}
        lower_row = {(5, 31), (5, 32), (6, 32)}
        upper_row = {(5, 12), (6, 12)}
        ink = target_body | target_dot | lower_row | upper_row

        current, assigned = _assign_components_to_rows(ink, bands, 2)

        self.assertEqual(current, target_body | target_dot)
        self.assertEqual(assigned[1], upper_row)
        self.assertEqual(assigned[3], lower_row)
        self.assertTrue(all(comp.isdisjoint(current) for comp in (upper_row, lower_row)))

    def test_detached_residual_component_between_rows_goes_to_nearest_row(self):
        bands = [
            {"top": 0, "bottom": 5},
            {"top": 10, "bottom": 15},
            {"top": 20, "bottom": 25},
            {"top": 30, "bottom": 35},
            {"top": 40, "bottom": 45},
        ]
        accent = {(3, 18), (4, 18)}
        body = {(3, 21), (3, 22)}
        current, assigned = _assign_components_to_rows(accent | body, bands, 2)
        self.assertEqual(current, accent | body)
        self.assertEqual(sum(len(row) for row in assigned), len(accent | body))

    def test_extracts_two_known_glyphs_from_one_connected_cross_row_tangle(self):
        # A is horizontal on the upper row and B is vertical on the lower row.
        # Their placed rasters touch at (1,4)/(1,5), so all four black pixels
        # form one 4-connected source component although they are two glyphs.
        upper_model = GlyphModel(
            label="A",
            style="roman",
            pixels=frozenset({(0, 0), (1, 0)}),
            sources=3,
        )
        lower_model = GlyphModel(
            label="B",
            style="roman",
            pixels=frozenset({(0, 0), (0, 1)}),
            sources=3,
        )
        ink = {(0, 4), (1, 4), (1, 5), (1, 6)}
        bands = [
            {"top": 2, "bottom": 4},
            {"top": 5, "bottom": 7},
        ]

        # Conservative single-row matching must still reject a model that owns
        # only part of a connected source component.
        conservative = exact_matches(ink, 3, 8, [upper_model, lower_model])
        self.assertEqual(conservative, [])

        per_row, selected = _extract_exact_rows_from_tangle(
            ink, 3, 8, [upper_model, lower_model], bands
        )

        self.assertEqual([(m.label, m.baseline) for m in per_row[0]], [("A", 4)])
        self.assertEqual([(m.label, m.baseline) for m in per_row[1]], [("B", 5)])
        self.assertEqual({p for m in selected for p in m.pixels}, ink)


if __name__ == "__main__":
    unittest.main()
