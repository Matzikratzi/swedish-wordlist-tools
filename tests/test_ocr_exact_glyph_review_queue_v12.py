import unittest

from swedish_wordlist_tools.ocr_exact_glyph_review_queue_v12 import _assign_components_to_rows


class FiveRowContextTest(unittest.TestCase):
    def test_assigns_whole_components_to_target_and_neighbor_rows(self):
        # Five physical rows with the middle one as target.  The target has a
        # detached dot above its body; the lower neighboring row has its own
        # component.  Components are assigned whole and never split.
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

    def test_detached_component_between_rows_goes_to_nearest_row(self):
        bands = [
            {"top": 0, "bottom": 5},
            {"top": 10, "bottom": 15},
            {"top": 20, "bottom": 25},
            {"top": 30, "bottom": 35},
            {"top": 40, "bottom": 45},
        ]
        # y=18 lies between rows 2 and 3 but is closer to the target row's
        # centre at 22.5 than the upper row's centre at 12.5.
        accent = {(3, 18), (4, 18)}
        body = {(3, 21), (3, 22)}
        current, assigned = _assign_components_to_rows(accent | body, bands, 2)
        self.assertEqual(current, accent | body)
        self.assertEqual(sum(len(row) for row in assigned), len(accent | body))


if __name__ == "__main__":
    unittest.main()
