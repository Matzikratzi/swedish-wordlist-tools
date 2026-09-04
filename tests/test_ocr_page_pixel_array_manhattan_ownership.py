import unittest
from unittest.mock import patch

from swedish_wordlist_tools import ocr_review_page_pixel_array_glyphs_html as review


class ManhattanOwnershipTests(unittest.TestCase):
    def test_manhattan_isolation_does_not_reassign_row_pixels(self):
        context = {
            "pixel_owner_revision": 7,
            "pixel_owner_row_revisions": {(1, 1): 3, (1, 2): 4},
        }
        state = {"column": 1, "row": 1}
        candidate = {
            "upper_row": 1,
            "lower_row": 2,
            "pixels": 9,
            "component_pixels": [(10, 10), (10, 11)],
        }
        proof = {
            "min_manhattan_distance": 8,
            "component_bottom": 11,
            "lower_row_top_ink": 20,
        }

        with patch.object(review, "_original_manual_two_row_candidates", return_value=[candidate]), \
             patch.object(review, "_isolated_above_lower_row", return_value=proof), \
             patch.object(review, "_ownership_success_logging", return_value=False):
            records = review._auto_assign_isolated_descenders(context, state)

        self.assertEqual(records, [])
        self.assertEqual(context["pixel_owner_revision"], 7)
        self.assertEqual(context["pixel_owner_row_revisions"], {(1, 1): 3, (1, 2): 4})
        self.assertEqual(
            context["ambiguous_two_row_ownership"],
            [{
                "column": 1,
                "upper_row": 1,
                "lower_row": 2,
                "pixels": 9,
                "decision": "ambiguous-manhattan-only",
                **proof,
            }],
        )


if __name__ == "__main__":
    unittest.main()
