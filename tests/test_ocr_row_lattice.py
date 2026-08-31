from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_row_lattice import (
    blocks_between_white_bands,
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
            {"center_y": 5.0},
            {"center_y": 15.0},
            {"center_y": 35.0},
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


if __name__ == "__main__":
    unittest.main()
