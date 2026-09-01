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
        for center in (15, 35):
            for y in range(center - 4, center + 5):
                for x in range(8, 40):
                    image.putpixel((x, y), 0)
        for y in range(71, 80):
            for x in range(8, 40):
                image.putpixel((x, y), 0)

        blocks = column_blocks(image, left=0, right=90)
        rows = rows_from_blocks(image, blocks, left=0, right=90, row_pitch=20.0)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["source"], "white-gap-single")

    def test_merged_two_row_block_is_split_by_low_ink_projection(self) -> None:
        image = Image.new("L", (90, 70), 255)
        for y in range(8, 14):
            for x in range(10, 45):
                image.putpixel((x, y), 0)
        for y in range(28, 34):
            for x in range(10, 45):
                image.putpixel((x, y), 0)
        for y in range(48, 54):
            for x in range(10, 45):
                image.putpixel((x, y), 0)
        for y in range(34, 48):
            image.putpixel((20, y), 0)

        blocks = column_blocks(image, left=0, right=90)
        rows = rows_from_blocks(image, blocks, left=0, right=90, row_pitch=20.0)
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(any(row["source"] == "white-gap-projection-split" for row in rows))

    def test_split_positions_anchor_to_ink_after_tall_upper_gap(self) -> None:
        image = Image.new("L", (90, 120), 255)
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

    def test_dense_chapter_plaque_is_structure_only_in_left_column(self) -> None:
        image = Image.new("L", (180, 140), 255)
        for column in range(3):
            x0 = column * 60 + 8
            for center in (15, 35, 115):
                for y in range(center - 4, center + 5):
                    for x in range(x0, x0 + 35):
                        image.putpixel((x, y), 0)
        for y in range(55, 100):
            for x in range(5, 55):
                image.putpixel((x, y), 0)
        for y in range(65, 90):
            image.putpixel((25, y), 255)
        for x in range(20, 31):
            image.putpixel((x, 78), 255)

        result = segment_page_rows(image)
        self.assertEqual(result["chapter_marker_count"], 1)
        self.assertEqual(result["columns"][0]["chapter_marker_count"], 1)
        self.assertEqual(result["columns"][1]["chapter_marker_count"], 0)
        self.assertEqual(result["columns"][2]["chapter_marker_count"], 0)
        self.assertTrue(
            all(not (55 <= row["center_y"] <= 100) for row in result["columns"][0]["rows"])
        )

    def test_middle_column_first_row_excludes_outer_running_heads(self) -> None:
        image = Image.new("L", (180, 130), 255)
        # Running heads exist only in the outer columns, well above body text.
        for x0 in (8, 128):
            for y in range(10, 17):
                for x in range(x0, x0 + 35):
                    image.putpixel((x, y), 0)
        # All three body columns start on the same row and continue at 20 px pitch.
        for column in range(3):
            x0 = column * 60 + 8
            for center in (55, 75, 95):
                for y in range(center - 4, center + 5):
                    for x in range(x0, x0 + 35):
                        image.putpixel((x, y), 0)

        result = segment_page_rows(image)
        self.assertEqual(result["header_row_count"], 2)
        self.assertGreaterEqual(result["content_top"], 50)
        self.assertEqual([len(entry["rows"]) for entry in result["columns"]], [3, 3, 3])
        self.assertEqual([entry["header_row_count"] for entry in result["columns"]], [1, 0, 1])

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

    def test_final_crop_boundaries_follow_real_gutters_not_page_thirds(self) -> None:
        image = Image.new("L", (210, 90), 255)
        starts = (10, 82, 152)
        for center in (15, 35, 55, 75):
            for column, x0 in enumerate(starts):
                # One long row in each of the first two columns reaches close to
                # the next printed column, while the other rows are shorter.
                right = (77 if column == 0 else 147) if center == 35 else x0 + 42
                if column == 2:
                    right = 198
                for y in range(center - 3, center + 4):
                    for x in range(x0, right):
                        image.putpixel((x, y), 0)

        result = segment_page_rows(image)
        self.assertEqual(result["format"], "saol-white-gap-row-map-v6")
        first, second = result["crop_boundaries"]
        self.assertGreater(first, 70)
        self.assertGreater(second, 140)
        self.assertLess(first, 82)
        self.assertLess(second, 152)
        for row in result["columns"][0]["rows"]:
            self.assertEqual(row["crop_right"], first)
        for row in result["columns"][1]["rows"]:
            self.assertEqual(row["crop_left"], first)
            self.assertEqual(row["crop_right"], second)


if __name__ == "__main__":
    unittest.main()
