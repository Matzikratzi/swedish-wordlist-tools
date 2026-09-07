import unittest
from unittest.mock import patch

from swedish_wordlist_tools import ocr_review_page_pixel_array_glyphs_html as review
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray


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

    def _known_extent_fixture(self, component):
        owners = PagePixelArray(width=8, height=10, data=bytearray(80))
        upper_code = owners.row_code(0)
        lower_code = owners.row_code(1)
        for index, (x, y) in enumerate(component):
            owners.data[y * owners.width + x] = upper_code if index < 2 else lower_code
        context = {
            "row_map": {"columns": [{"rows": [{"page_top": 0, "page_bottom": 5}, {"page_top": 5, "page_bottom": 10}]}]},
            "pixel_owners": owners,
            "known_glyph_ownership_lock": review.threading.Lock(),
            "pixel_owner_revision": 0,
            "pixel_owner_row_revisions": {},
        }
        state = {
            "column": 0,
            "row": 0,
            "crop_box": (0, 0, 8, 7),
            "items": [{"id": "M00", "kind": "match"}],
            "point_sets": {"M00": frozenset({(1, 1), (1, 2), (1, 3)})},
        }
        candidate = {
            "upper_row": 0,
            "lower_row": 1,
            "upper_owned": 2,
            "lower_owned": max(1, len(component) - 2),
            "component_pixels": component,
            "pixels": len(component),
        }
        return context, state, candidate

    def test_split_component_wholly_below_known_upper_extent_moves_lower(self):
        component = [(3, 4), (3, 5), (3, 6), (4, 6)]
        context, state, candidate = self._known_extent_fixture(component)

        with patch.object(review, "_original_manual_two_row_candidates", return_value=[candidate]), \
             patch.object(review, "_ownership_success_logging", return_value=False):
            records = review._assign_split_components_below_known_extent(context, state)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["secure_separator_page_y"], 4)
        self.assertEqual(records[0]["decision"], "lower-from-known-upper-extent")
        lower_code = context["pixel_owners"].row_code(1)
        self.assertTrue(all(context["pixel_owners"].value(x, y) == lower_code for x, y in component))
        self.assertEqual(context["pixel_owner_revision"], 1)
        self.assertEqual(context["pixel_owner_row_revisions"], {(0, 0): 1, (0, 1): 1})

    def test_connected_upper_descender_above_known_extent_stays_ambiguous(self):
        component = [(3, 3), (3, 4), (3, 5), (3, 6)]
        context, state, candidate = self._known_extent_fixture(component)
        before = bytes(context["pixel_owners"].data)

        with patch.object(review, "_original_manual_two_row_candidates", return_value=[candidate]):
            records = review._assign_split_components_below_known_extent(context, state)

        self.assertEqual(records, [])
        self.assertEqual(bytes(context["pixel_owners"].data), before)
        self.assertEqual(context["pixel_owner_revision"], 0)


if __name__ == "__main__":
    unittest.main()
