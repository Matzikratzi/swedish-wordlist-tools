from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_row_lattice import (
    blocks_between_white_bands,
    ink_extent_between_white_bands,
    proposed_missing_rows,
    typical_row_pitch,
    white_horizontal_bands,
)


class RowLatticeTests(unittest.TestCase):
    def test_white_horizontal_bands_are_hard_full_width_gaps(self) -> None:
        image = Image.new("L", (12, 20), 255)
        pixels = image.load()
        for y in (3, 4, 10, 11, 12, 17):
            for x in range(2, 10):
                pixels[x, y] = 0

        gaps = white_horizontal_bands(
            image,
            left=0,
            right=12,
            inset_x=2,
            min_height=2,
        )

        self.assertEqual(
            [(gap["top"], gap["bottom"]) for gap in gaps],
            [(0, 3), (5, 10), (13, 17), (18, 20)],
        )

    def test_one_image_pixel_white_band_is_kept(self) -> None:
        image = Image.new("L", (10, 5), 0)
        pixels = image.load()
        for x in range(1, 9):
            pixels[x, 2] = 255

        gaps = white_horizontal_bands(
            image,
            left=0,
            right=10,
            inset_x=1,
        )

        self.assertEqual([(gap["top"], gap["bottom"]) for gap in gaps], [(2, 3)])

    def test_row_pitch_ignores_one_double_gap(self) -> None:
        rows = [
            {"center_y": 10.0},
            {"center_y": 20.0},
            {"center_y": 30.0},
            {"center_y": 50.0},
            {"center_y": 60.0},
        ]
        self.assertEqual(typical_row_pitch(rows), 10.0)

    def test_gap_distance_can_imply_multiple_rows(self) -> None:
        bands = [
            {"top": 4, "bottom": 6, "center_y": 5.0},
            {"top": 14, "bottom": 16, "center_y": 15.0},
            {"top": 34, "bottom": 36, "center_y": 35.0},
        ]
        known_rows = [
            {"center_y": 10.0},
            {"center_y": 20.0},
        ]

        blocks = blocks_between_white_bands(
            bands,
            row_pitch=10.0,
            known_rows=known_rows,
        )

        self.assertEqual(blocks[0]["estimated_row_count"], 1)
        self.assertEqual(blocks[0]["missing_row_count"], 0)
        self.assertEqual(blocks[1]["estimated_row_count"], 2)
        self.assertEqual(blocks[1]["known_row_count"], 1)
        self.assertEqual(blocks[1]["missing_row_count"], 1)

    def test_ink_extent_records_vertical_white_margins(self) -> None:
        image = Image.new("L", (80, 30), 255)
        pixels = image.load()
        for y in range(8, 20):
            for x in range(25, 52):
                if (x + y) % 3:
                    pixels[x, y] = 0

        block = {
            "upper_gap_bottom": 7,
            "lower_gap_top": 21,
        }
        extent = ink_extent_between_white_bands(
            image,
            block,
            left=10,
            right=70,
            inset_x=0,
        )

        self.assertEqual(extent["ink_bbox"], [25, 8, 52, 20])
        self.assertEqual(extent["left_white_margin"], 15)
        self.assertEqual(extent["right_white_margin"], 18)

    def test_clear_one_row_ink_island_is_proposed_without_tesseract_row(self) -> None:
        image = Image.new("L", (100, 40), 255)
        pixels = image.load()
        # Synthetic short word: substantial ink, with white on all four sides.
        for y in range(12, 24):
            for x in range(30, 58):
                if (x + 2 * y) % 4:
                    pixels[x, y] = 0

        blocks = [
            {
                "upper_gap_top": 9,
                "upper_gap_bottom": 11,
                "upper_gap_center_y": 9.5,
                "lower_gap_top": 25,
                "lower_gap_bottom": 27,
                "lower_gap_center_y": 25.5,
                "distance": 16.0,
                "estimated_row_count": 1,
                "known_row_count": 0,
                "known_row_centers": [],
                "missing_row_count": 1,
            }
        ]

        proposed = proposed_missing_rows(
            image,
            blocks,
            left=10,
            right=90,
            row_pitch=17.5,
        )

        self.assertEqual(len(proposed), 1)
        self.assertEqual(proposed[0]["source"], "white-gap-ink-island")
        self.assertEqual(proposed[0]["page_top"], 12)
        self.assertEqual(proposed[0]["page_bottom"], 24)
        self.assertGreater(proposed[0]["left_white_margin"], 0)
        self.assertGreater(proposed[0]["right_white_margin"], 0)

    def test_speck_between_white_bands_is_not_proposed_as_row(self) -> None:
        image = Image.new("L", (100, 40), 255)
        pixels = image.load()
        pixels[45, 18] = 0
        blocks = [
            {
                "upper_gap_top": 9,
                "upper_gap_bottom": 11,
                "lower_gap_top": 25,
                "lower_gap_bottom": 27,
                "estimated_row_count": 1,
                "known_row_count": 0,
            }
        ]

        proposed = proposed_missing_rows(
            image,
            blocks,
            left=10,
            right=90,
            row_pitch=17.5,
        )

        self.assertEqual(proposed, [])


if __name__ == "__main__":
    unittest.main()
