from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_review_row_glyphs_html import _trim_leading_white_columns


class ReviewRowGlyphTrimTests(unittest.TestCase):
    def test_trims_empty_left_margin_but_keeps_two_columns(self) -> None:
        image = Image.new("L", (20, 8), 255)
        image.putpixel((9, 3), 0)
        image.putpixel((10, 3), 0)

        crop, trimmed = _trim_leading_white_columns(image, threshold=210, keep=2)

        self.assertEqual(trimmed, 7)
        self.assertEqual(crop.width, 13)
        self.assertEqual(crop.getpixel((2, 3)), 0)

    def test_blank_row_is_not_trimmed(self) -> None:
        image = Image.new("L", (20, 8), 255)
        crop, trimmed = _trim_leading_white_columns(image, threshold=210, keep=2)
        self.assertEqual(trimmed, 0)
        self.assertEqual(crop.size, image.size)


if __name__ == "__main__":
    unittest.main()
