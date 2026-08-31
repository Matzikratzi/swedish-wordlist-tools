from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_column_row_segmentation import segment_page_rows


class ChapterPageHeaderCutoffTests(unittest.TestCase):
    def test_chapter_page_skips_middle_column_running_head_cutoff(self) -> None:
        image = Image.new("L", (180, 150), 255)

        # Ordinary rows establish a 20 px pitch in all columns.
        for column in range(3):
            x0 = column * 60 + 8
            for center in (15, 35, 125):
                for y in range(center - 4, center + 5):
                    for x in range(x0, x0 + 35):
                        image.putpixel((x, y), 0)

        # Dense inverse alphabet chapter plaque in the left column.
        for y in range(55, 105):
            for x in range(5, 55):
                image.putpixel((x, y), 0)
        for y in range(65, 95):
            image.putpixel((25, y), 255)
        for x in range(20, 31):
            image.putpixel((x, 80), 255)

        result = segment_page_rows(image)

        self.assertEqual(result["chapter_marker_count"], 1)
        self.assertIsNone(result["content_top"])
        self.assertEqual(result["header_row_count"], 0)
        self.assertEqual(
            [entry["header_row_count"] for entry in result["columns"]],
            [0, 0, 0],
        )


if __name__ == "__main__":
    unittest.main()
