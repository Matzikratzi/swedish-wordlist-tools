from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_column_row_segmentation import (
    column_blocks,
    estimate_row_pitch,
    rows_from_blocks,
    segment_page_rows,
)


class ColumnRowSegmentationTests(unittest.TestCase):
    def test_modal_gap_distance_estimates_row_pitch(self) -> None:
        blocks = [
            {"distance": 17.5, "ink_height": 10},
            {"distance": 17.5, "ink_height": 11},
            {"distance": 18.0, "ink_height": 11},
            {"distance": 35.0, "ink_height": 25},
        ]
        self.assertEqual(estimate_row_pitch(blocks), 17.5)

    def test_clear_single_rows_need_no_tesseract_geometry(self) -> None:
        image = Image.new("L", (90, 80), 255)
        for center in (15, 35, 55):
            for y in range(center - 4, center + 5):
                for x in range(8, 40):
                    image.putpixel((x, y), 0)

        blocks = column_blocks(image, left=0, right=90)
        pitch = estimate_row_pitch(blocks)
        self.assertIsNotNone(pitch)
        rows = rows_from_blocks(image, blocks, left=0, right=90, row_pitch=float(pitch))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["source"] == "white-gap-single" for row in rows))

    def test_merged_two_row_block_is_split_by_low_ink_projection(self) -> None:
        image = Image.new("L", (90, 70), 255)
        # First ordinary row establishes the 20 px pitch.
        for y in range(8, 14):
            for x in range(10, 45):
                image.putpixel((x, y), 0)
        # Two following rows. A thin vertical stroke bridges their otherwise
        # white separator, so there is no hard full-width white band between them.
        for y in range(28, 34):
            for x in range(10, 45):
                image.putpixel((x, y), 0)
        for y in range(48, 54):
            for x in range(10, 45):
                image.putpixel((x, y), 0)
        for y in range(34, 48):
            image.putpixel((20, y), 0)

        blocks = column_blocks(image, left=0, right=90)
        # Feed the known printed pitch explicitly: the test is about splitting,
        # not estimating pitch from this deliberately tiny sample.
        rows = rows_from_blocks(image, blocks, left=0, right=90, row_pitch=20.0)
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(any(row["source"] == "white-gap-projection-split" for row in rows))

    def test_page_is_split_into_three_columns_before_rows(self) -> None:
        image = Image.new("L", (90, 60), 255)
        for column in range(3):
            x0 = column * 30 + 5
            for center in (15, 35):
                for y in range(center - 3, center + 4):
                    for x in range(x0, x0 + 15):
                        image.putpixel((x, y), 0)

        result = segment_page_rows(image)
        self.assertEqual(result["column_count"], 3)
        self.assertEqual([entry["left"] for entry in result["columns"]], [0, 30, 60])
        self.assertEqual([entry["right"] for entry in result["columns"]], [30, 60, 90])
        self.assertEqual(result["row_count"], 6)


if __name__ == "__main__":
    unittest.main()
