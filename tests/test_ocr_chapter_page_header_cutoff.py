from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_column_row_segmentation import segment_page_rows


class ChapterPageHeaderCutoffTests(unittest.TestCase):
    def test_chapter_page_drops_header_but_keeps_staggered_body_start(self) -> None:
        image = Image.new("L", (180, 170), 255)

        # Outer running heads only, well above body text.
        for x0 in (8, 128):
            for y in range(10, 17):
                for x in range(x0, x0 + 35):
                    image.putpixel((x, y), 0)

        # Middle/right body starts normally at y=51; left body starts below plaque.
        for column in (1, 2):
            x0 = column * 60 + 8
            for center in (55, 75, 95, 115, 135):
                for y in range(center - 4, center + 5):
                    for x in range(x0, x0 + 35):
                        image.putpixel((x, y), 0)
        for center in (125, 145):
            for y in range(center - 4, center + 5):
                for x in range(8, 43):
                    image.putpixel((x, y), 0)

        # Dense inverse alphabet chapter plaque in the left column.
        for y in range(50, 110):
            for x in range(5, 55):
                image.putpixel((x, y), 0)
        for y in range(60, 100):
            image.putpixel((25, y), 255)
        for x in range(20, 31):
            image.putpixel((x, 80), 255)

        result = segment_page_rows(image)

        self.assertEqual(result["chapter_marker_count"], 1)
        self.assertGreaterEqual(result["content_top"], 50)
        self.assertGreaterEqual(result["header_row_count"], 2)
        left, middle, right = result["columns"]
        self.assertTrue(all(row["page_top"] >= 110 for row in left["rows"]))
        self.assertTrue(all(row["page_top"] >= 50 for row in middle["rows"]))
        self.assertTrue(all(row["page_top"] >= 50 for row in right["rows"]))
        self.assertGreaterEqual(left["header_row_count"], 1)
        self.assertEqual(middle["header_row_count"], 0)
        self.assertGreaterEqual(right["header_row_count"], 1)


if __name__ == "__main__":
    unittest.main()
