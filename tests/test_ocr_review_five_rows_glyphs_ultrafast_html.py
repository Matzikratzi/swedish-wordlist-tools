import unittest

from swedish_wordlist_tools import ocr_review_five_rows_glyphs_fast_html as fast
from swedish_wordlist_tools import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from swedish_wordlist_tools.ocr_glyph_matcher import Match


class UltrafastFiveRowGlyphReviewTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(ultrafast._post_context, "active_position"):
            del ultrafast._post_context.active_position

    def test_fast_editor_is_patched_to_fallback_recording_matcher(self):
        self.assertIs(ultrafast.fast, fast)
        self.assertIs(fast.analyse_row_exact, ultrafast.analyse_row_with_fallback_recording)

    def test_residual_touching_bottom_requests_edge_retry(self):
        state = {
            "crop_height": 17,
            "items": [
                {"kind": "residual", "bbox": {"left": 20, "top": 6, "right": 30, "bottom": 17}}
            ],
        }
        self.assertEqual(ultrafast._residual_edge_side(state), "bottom")

    def test_edge_retry_accepts_same_absolute_baseline_glyph_crossing_old_bottom(self):
        initial = {
            "crop_box": (10, 20, 40, 37),
            "row_page_top": 21,
            "row_page_bottom": 36,
            "baseline": 13,
            "covered_pixels": 4,
        }
        retry_match = Match(
            label="g",
            style="roman",
            x=3,
            baseline=16,  # retry crop begins 3 px higher: absolute baseline remains 33
            pixels=frozenset({(3, 10), (3, 11), (3, 12), (3, 13), (3, 14), (3, 15), (3, 16), (3, 17), (3, 18), (3, 19), (4, 19), (5, 19), (6, 19), (6, 20)}),
            model_pixels=14,
            sources=2,
        )
        retry = {
            "crop_box": (10, 17, 40, 40),
            "matches": [retry_match],
        }
        evidence = ultrafast._edge_retry_evidence(initial, retry, "bottom")
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["status"], "accepted")
        self.assertEqual(evidence["labels"], "g")
        self.assertEqual(evidence["main_baseline_page"], 33)

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
        self.assertNotIn('action="/?column=0&amp;row=15&amp;mode=defects', document)

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

    def test_three_row_raster_control_and_copy_are_injected(self):
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
            "removed_neighbor_pixels": 3,
            "two_row_removed_pixels": 1,
            "edge_rescue": {"status": "accepted", "side": "bottom", "labels": "g"},
            "baseline_fallbacks": [
                {
                    "group": 4,
                    "from_baseline": 7,
                    "to_baseline": 8,
                    "delta": 1,
                    "labels": "ex",
                    "status": "full-exact-whitespace-fallback",
                }
            ],
            "two_row_ownership": [
                {
                    "neighbor_row": 45,
                    "status": "split",
                    "component_pixels": 19,
                    "removed_pixels": 1,
                    "partitions": 1,
                    "current_labels": "]",
                    "neighbor_labels": "l",
                    "vertical_order": "touch-or-gap",
                }
            ],
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
            "neighbor_raster_height": 30,
            "neighbor_core_top": 10,
            "neighbor_core_bottom": 20,
            "neighbor_page_top": 11,
            "neighbor_page_bottom": 41,
            "neighbor_row_boundaries": [[0, "row 43 top"], [10, "TARGET row 44 top"], [20, "TARGET row 44 bottom"], [30, "row 45 bottom"]],
            "neighbor_raster_ascii": "--- row 43 top y=0 ---\n..#..\n--- TARGET row 44 top y=10 ---\n.###.\n--- TARGET row 44 bottom y=20 ---\n..#..\n--- row 45 bottom y=30 ---",
        }
        document = ultrafast.render_html_with_neighbor_raster(state)
        self.assertIn('id="showNeighbors"', document)
        self.assertIn('id="neighborRow"', document)
        self.assertIn("Tre-radersraster", document)
        self.assertIn("neighbor_row_boundaries", document)
        self.assertIn('id="copyDiagnostics"', document)
        self.assertIn("Kopiera diagnostik + raster", document)
        self.assertIn("navigator.clipboard.writeText", document)

        diagnostics = ultrafast.diagnostic_text(state)
        self.assertIn("page=1 column=0 row=44", diagnostics)
        self.assertIn("coverage=9/10 fully_exact=False", diagnostics)
        self.assertIn("removed_neighbor_pixels=3", diagnostics)
        self.assertIn("two_row_removed_pixels=1", diagnostics)
        self.assertIn("edge_rescue:", diagnostics)
        self.assertIn('"labels": "g"', diagnostics)
        self.assertIn("baseline_fallbacks:", diagnostics)
        self.assertIn('"to_baseline": 8', diagnostics)
        self.assertIn('"status": "split"', diagnostics)
        self.assertIn('"current_labels": "]"', diagnostics)
        self.assertIn('"neighbor_labels": "l"', diagnostics)
        self.assertIn("target_core_y=10..20", diagnostics)
        self.assertIn("three_row_raster_ascii:", diagnostics)
        self.assertIn(".###.", diagnostics)
        self.assertIn("M00 kind=match label=']' style=roman pixels=7", diagnostics)
        self.assertNotIn("data:image", diagnostics)


if __name__ == "__main__":
    unittest.main()
