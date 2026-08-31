from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_column_row_segmentation import (
    _split_positions,
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

    def test_large_gap_with_only_one_row_of_ink_is_not_split(self) -> None:
        image = Image.new("L", (90, 100), 255)
        # Two ordinary rows establish a 20 px pitch.
        for center in (15, 35):
            for y in range(center - 4, center + 5):
                for x in range(8, 40):
                    image.putpixel((x, y), 0)
        # A final ordinary-height row sits after extra vertical white space.
        # Gap-centre distance alone would suggest multiple rows here.
        for y in range(71, 80):
            for x in range(8, 40):
                image.putpixel((x, y), 0)

        blocks = column_blocks(image, left=0, right=90)
        rows = rows_from_blocks(image, blocks, left=0, right=90, row_pitch=20.0)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["source"], "white-gap-single")

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

    def test_split_positions_anchor_to_ink_after_tall_upper_gap(self) -> None:
        image = Image.new("L", (90, 120), 255)
        # The first 50 pixels are white. Three rows of ink start only at y=60,
        # with a one-pixel bridge preventing hard white separators between them.
        for top in (60, 80, 100):
            for y in range(top, top + 6):
                for x in range(10, 45):
                    image.putpixel((x, y), 0)
        for y in range(66, 100):
            image.putpixel((20, y), 0)
        block = {
            "upper_gap_bottom": 50,
            "lower_gap_top": 110,
            "upper_gap_center_y": 25.0,
            "ink_bbox": [10, 60, 45, 106],
        }
        splits = _split_positions(
            image,
            block,
            row_count=3,
            row_pitch=20.0,
            left=0,
            right=90,
            threshold=210,
        )
        self.assertEqual(len(splits), 2)
        self.assertGreaterEqual(splits[0], 74)
        self.assertLessEqual(splits[0], 86)
        self.assertGreaterEqual(splits[1], 94)
        self.assertLessEqual(splits[1], 106)

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
