import unittest

from swedish_wordlist_tools.ocr_exact_glyph_review_queue_v12 import (
    _assign_components_to_rows,
    _baseline_row_index,
    _extract_exact_rows_from_tangle,
    _filter_target_review_residual,
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

    def test_review_filter_rejects_fragment_closer_to_previous_row(self):
        bands = [
            {"top": 28, "bottom": 40},
            {"top": 48, "bottom": 60},
            {"top": 68, "bottom": 80},
        ]
        previous_fragment = {(0, 35), (1, 35), (1, 36), (2, 36)}
        target_unknown = {(5, 51), (5, 52), (6, 52)}

        kept, rejected = _filter_target_review_residual(
            previous_fragment | target_unknown, bands, 1
        )

        self.assertEqual(kept, target_unknown)
        self.assertEqual(rejected, previous_fragment)

    def test_review_filter_keeps_detached_mark_near_target_row(self):
        bands = [
            {"top": 28, "bottom": 40},
            {"top": 48, "bottom": 60},
            {"top": 68, "bottom": 80},
        ]
        detached_mark = {(5, 45), (6, 45)}
        target_body = {(5, 51), (5, 52)}

        kept, rejected = _filter_target_review_residual(
            detached_mark | target_body, bands, 1
        )

        self.assertEqual(kept, detached_mark | target_body)
        self.assertEqual(rejected, set())

    def test_baseline_is_owned_by_exactly_one_physical_row_even_if_bands_overlap(self):
        bands = [
            {"top": 2, "bottom": 8},
            {"top": 7, "bottom": 13},
            {"top": 12, "bottom": 18},
        ]
        self.assertEqual(_baseline_row_index(5, bands), 0)
        self.assertEqual(_baseline_row_index(10, bands), 1)
        self.assertEqual(_baseline_row_index(15, bands), 2)

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
