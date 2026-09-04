import unittest
from unittest.mock import patch

from swedish_wordlist_tools import ocr_review_page_pixel_array_shared as shared


class SharedPixelReviewTests(unittest.TestCase):
    def test_reloads_after_disconnected_glyph_repair(self):
        initial = {"fully_exact": False, "column": 1, "row": 38}
        repaired = {"fully_exact": True, "column": 1, "row": 38, "text": "anim·er·ings. ~en ~ar"}
        records = [{"decision": "lower-from-disconnected-exact-glyph"}]
        with patch.object(shared, "_base_load_review_state_pixel_array", side_effect=[initial, repaired]) as loader, \
             patch.object(shared, "repair_lower_row_disconnected_glyphs", return_value=records) as repair:
            state = shared.load_review_state_pixel_array({}, (1, 38), [object()])

        self.assertEqual(loader.call_count, 2)
        repair.assert_called_once()
        self.assertTrue(state["fully_exact"])
        self.assertEqual(state["text"], "anim·er·ings. ~en ~ar")
        self.assertEqual(state["disconnected_glyph_ownership"], records)

    def test_exact_row_skips_repair(self):
        exact = {"fully_exact": True, "column": 0, "row": 1}
        with patch.object(shared, "_base_load_review_state_pixel_array", return_value=exact), \
             patch.object(shared, "repair_lower_row_disconnected_glyphs") as repair, \
             patch.object(shared, "probe_zero_match_merge_down") as probe:
            state = shared.load_review_state_pixel_array({}, (0, 1), [object()])
        self.assertIs(state, exact)
        repair.assert_not_called()
        probe.assert_not_called()

    def test_row_with_matches_never_loads_next_row_for_merge_probe(self):
        state = {
            "fully_exact": False,
            "column": 0,
            "row": 3,
            "source_pixels": 100,
            "matches": [object()],
        }
        with patch.object(shared, "_base_load_review_state_pixel_array", return_value=state) as loader, \
             patch.object(shared, "repair_lower_row_disconnected_glyphs", return_value=[]), \
             patch.object(shared, "probe_zero_match_merge_down") as probe:
            shared.load_review_state_pixel_array(
                {"row_map": {"columns": [{"rows": [{}, {}, {}, {}, {}]}]}},
                (0, 3),
                [object()],
            )
        self.assertEqual(loader.call_count, 1)
        probe.assert_not_called()

    def test_zero_match_row_probes_lower_before_disconnected_repair(self):
        upper = {
            "fully_exact": False,
            "column": 0,
            "row": 0,
            "source_pixels": 12,
            "matches": [],
        }
        lower = {
            "fully_exact": False,
            "column": 0,
            "row": 1,
            "source_pixels": 399,
            "covered_pixels": 367,
            "matches": [object()],
        }
        proof = {
            "column": 0,
            "upper_row": 0,
            "lower_row": 1,
            "lower_covered_pixels": 367,
            "covered_pixels": 411,
            "labels": "anim·er·ings. ~en ~ar",
        }
        context = {"row_map": {"columns": [{"rows": [{}, {}]}]}, "quiet_successful_ownership": True}
        with patch.object(shared, "_base_load_review_state_pixel_array", side_effect=[upper, lower, {**upper, "source_pixels": 0}]) as loader, \
             patch.object(shared, "probe_zero_match_merge_down", return_value=proof) as probe, \
             patch.object(shared, "apply_merge_down", return_value=12), \
             patch.object(shared, "repair_lower_row_disconnected_glyphs") as repair:
            state = shared.load_review_state_pixel_array(context, (0, 0), [object()])

        self.assertEqual(loader.call_count, 3)
        probe.assert_called_once()
        repair.assert_not_called()
        self.assertTrue(state["fully_exact"])
        self.assertEqual(state["row_absorbed_by_lower"], proof)


if __name__ == "__main__":
    unittest.main()
