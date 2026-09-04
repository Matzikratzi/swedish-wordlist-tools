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
             patch.object(shared, "repair_lower_row_disconnected_glyphs") as repair:
            state = shared.load_review_state_pixel_array({}, (0, 1), [object()])
        self.assertIs(state, exact)
        repair.assert_not_called()


if __name__ == "__main__":
    unittest.main()
