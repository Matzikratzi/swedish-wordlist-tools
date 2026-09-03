import unittest
from unittest.mock import patch

from PIL import Image

from swedish_wordlist_tools import ocr_review_page_pixel_array_glyphs_html as review


class EffectiveOneRowCropTests(unittest.TestCase):
    def test_one_row_crop_uses_same_effective_separators_as_three_row_view(self):
        context = {
            "page": Image.new("L", (100, 60), 255),
            "row_map": {
                "columns": [
                    {
                        "rows": [
                            {"page_top": 2, "page_bottom": 10},
                            {"page_top": 11, "page_bottom": 20},
                            {"page_top": 21, "page_bottom": 30},
                        ]
                    }
                ]
            },
        }

        def effective(_context, *, column, upper_row_index, left, right):
            self.assertEqual(column, 0)
            self.assertEqual((left, right), (5, 90))
            return {0: 10, 1: 22}[upper_row_index]

        with patch.object(review, "_effective_separator_page", side_effect=effective):
            box, core_top, core_bottom = review._effective_owned_row_box(
                context, 0, 1, 5, 90, pad_y=2
            )

        self.assertEqual(core_top, 10)
        self.assertEqual(core_bottom, 22)
        self.assertEqual(box, (5, 8, 90, 24))


if __name__ == "__main__":
    unittest.main()
