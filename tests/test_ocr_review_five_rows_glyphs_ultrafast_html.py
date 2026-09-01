import unittest

from swedish_wordlist_tools import ocr_review_five_rows_glyphs_fast_html as fast
from swedish_wordlist_tools import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from swedish_wordlist_tools.ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


class UltrafastFiveRowGlyphReviewTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
