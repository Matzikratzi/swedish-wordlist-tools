import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray
from swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_html import _pair_has_ink_bridge


class PagePixelArrayBoundaryGateTests(unittest.TestCase):
    def _context(self, page):
        owners = PagePixelArray.from_image(page)
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": page.width,
                    "crop_left": 0,
                    "crop_right": page.width,
                    "rows": [
                        {"page_top": 2, "page_bottom": 8},
                        {"page_top": 8, "page_bottom": 14},
                    ],
                }
            ]
        }
        owners.assign_row_map(row_map)
        return {"row_map": row_map, "pixel_owners": owners}

    def test_clean_white_separator_skips_glyph_analysis(self):
        page = Image.new("L", (20, 16), 255)
        for y in range(3, 7):
            page.putpixel((5, y), 0)
        for y in range(9, 13):
            page.putpixel((12, y), 0)

        self.assertFalse(_pair_has_ink_bridge(self._context(page), (0, 0)))

    def test_touching_ink_reaches_glyph_analysis(self):
        page = Image.new("L", (20, 16), 255)
        # Provisional boundary is y=8. These pixels are vertically connected
        # across it and therefore require exact-glyph ownership analysis.
        page.putpixel((7, 7), 0)
        page.putpixel((7, 8), 0)

        self.assertTrue(_pair_has_ink_bridge(self._context(page), (0, 0)))


if __name__ == "__main__":
    unittest.main()
