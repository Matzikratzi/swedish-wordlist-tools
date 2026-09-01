import unittest

from swedish_wordlist_tools import ocr_review_five_rows_glyphs_fast_html as fast
from swedish_wordlist_tools import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from swedish_wordlist_tools.ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


class UltrafastFiveRowGlyphReviewTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(ultrafast._post_context, "active_position"):
            del ultrafast._post_context.active_position

    def test_fast_editor_is_patched_to_grouped_matcher(self):
        self.assertIs(ultrafast.fast, fast)
        self.assertIs(fast.analyse_row_exact, analyse_row_exact_grouped)

    def test_form_posts_to_actual_active_defect_row_not_scan_anchor(self):
        states = []
        for row in (44, 47, 50, 51, 52):
            states.append(
                {
                    "page": 1,
                    "column": 0,
                    "row": row,
                    "covered_pixels": 9,
                    "source_pixels": 10,
                    "removed_neighbor_pixels": 0,
                    "text": f"row{row}",
                    "crop_width": 20,
                    "crop_height": 10,
                    "baseline": 7,
                    "image": "data:image/png;base64,AA==",
                    "source_ink_points": [[1, 1]],
                    "items": [],
                }
            )
        positions = [(0, i) for i in range(60)]
        document = ultrafast.render_five_row_html_to_active_row(
            states,
            (0, 44),
            positions,
            mode="defects",
            anchor=(0, 15),
        )
        self.assertIn(
            'action="/?column=0&amp;row=44&amp;mode=defects&amp;anchor_column=0&amp;anchor_row=15"',
            document,
        )
        self.assertNotIn(
            'action="/?column=0&amp;row=15&amp;mode=defects',
            document,
        )

    def test_failed_post_fallback_stays_on_active_row(self):
        ultrafast._post_context.active_position = (1, 14)
        location = ultrafast.row_url_preserving_failed_post((0, 10))
        self.assertEqual(location, ultrafast._original_row_url((1, 14)))
        self.assertFalse(hasattr(ultrafast._post_context, "active_position"))

    def test_success_redirect_preserves_active_row_mode_and_anchor(self):
        ultrafast._post_context.active_position = (1, 14)
        location = ultrafast.row_url_preserving_failed_post(
            (1, 14), mode="defects", anchor=(1, 14)
        )
        self.assertEqual(
            location,
            ultrafast._original_row_url((1, 14), mode="defects", anchor=(1, 14)),
        )
        self.assertFalse(hasattr(ultrafast._post_context, "active_position"))

    def test_neighbor_raster_control_is_injected(self):
        state = {
            "page": 1,
            "column": 0,
            "row": 44,
            "crop_box": (10, 20, 30, 32),
            "row_page_top": 21,
            "row_page_bottom": 31,
            "covered_pixels": 9,
            "source_pixels": 10,
            "fully_exact": False,
            "removed_neighbor_pixels": 2,
            "text": "x",
            "markup": "<i>x</i>",
            "crop_width": 20,
            "crop_height": 10,
            "baseline": 7,
            "image": "data:image/png;base64,AA==",
            "source_ink_points": [[1, 1]],
            "items": [
                {"id": "M00", "kind": "match", "label": "]", "style": "roman", "pixels": 7, "bbox": {"left": 1, "top": 1, "right": 3, "bottom": 8}},
                {"id": "U00", "kind": "residual", "label": "?", "style": "unknown", "pixels": 1, "bbox": {"left": 4, "top": 8, "right": 5, "bottom": 9}},
            ],
            "point_sets": {},
            "matches": [],
            "neighbor_raster_image": "data:image/png;base64,AA==",
            "neighbor_raster_width": 20,
            "neighbor_raster_height": 26,
            "neighbor_core_top": 8,
            "neighbor_core_bottom": 18,
            "neighbor_probe_y": 8,
            "neighbor_page_top": 13,
            "neighbor_page_bottom": 39,
        }
        document = ultrafast.render_html_with_neighbor_raster(state)
        self.assertIn('id="showNeighbors"', document)
        self.assertIn('id="neighborRow"', document)
        self.assertIn("Grannradsraster", document)
        self.assertIn("neighbor_core_top", document)
        self.assertIn('id="copyDiagnostics"', document)
        self.assertIn("Kopiera diagnostik", document)
        self.assertIn("navigator.clipboard.writeText", document)
        self.assertIn("Same visible pixel grid as the main glyph editor", document)

        diagnostics = ultrafast.diagnostic_text(state)
        self.assertIn("page=1 column=0 row=44", diagnostics)
        self.assertIn("coverage=9/10 fully_exact=False", diagnostics)
        self.assertIn("removed_neighbor_pixels=2", diagnostics)
        self.assertIn("core_y=8..18", diagnostics)
        self.assertIn("M00 kind=match label=']' style=roman pixels=7", diagnostics)
        self.assertNotIn("data:image", diagnostics)


if __name__ == "__main__":
    unittest.main()
