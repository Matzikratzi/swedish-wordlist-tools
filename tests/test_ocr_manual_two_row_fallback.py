from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_review_delete import manual_two_row_candidates
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray


class ManualTwoRowFallbackTest(unittest.TestCase):
    def test_diagonal_residual_bridge_becomes_manual_candidate(self):
        image = Image.new("L", (12, 10), 255)
        pixels = image.load()
        # Upper-row residual with one diagonally touching pixel below the separator.
        for point in ((4, 4), (5, 4), (6, 5)):
            pixels[point] = 0

        owners = PagePixelArray.from_image(image, threshold=210)
        row_map = {
            "columns": [
                {
                    "crop_left": 0,
                    "crop_right": 12,
                    "rows": [
                        {"page_top": 0, "page_bottom": 5},
                        {"page_top": 5, "page_bottom": 10},
                    ],
                }
            ]
        }
        owners.assign_row_map(row_map)
        context = {
            "pixel_gray_page": image,
            "pixel_owners": owners,
            "row_map": row_map,
            "threshold": 210,
        }
        state = {
            "column": 0,
            "row": 0,
            "crop_box": (0, 0, 12, 7),
            "covered_pixels": 0,
            "source_pixels": 2,
            "items": [
                {
                    "id": "U00",
                    "kind": "residual",
                    "bbox": {"left": 4, "top": 4, "right": 6, "bottom": 5},
                }
            ],
            "point_sets": {"U00": frozenset({(4, 4), (5, 4)})},
            "neighbor_page_top": 0,
        }

        candidates = manual_two_row_candidates(context, state)

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual((candidate["upper_row"], candidate["lower_row"]), (0, 1))
        self.assertEqual(candidate["pixels"], 3)
        self.assertEqual(candidate["upper_owned"], 2)
        self.assertEqual(candidate["lower_owned"], 1)
        self.assertIn((6, 5), candidate["component_pixels"])

    def test_no_cross_boundary_link_means_no_candidate(self):
        image = Image.new("L", (12, 10), 255)
        image.putpixel((4, 4), 0)
        owners = PagePixelArray.from_image(image, threshold=210)
        row_map = {
            "columns": [
                {
                    "crop_left": 0,
                    "crop_right": 12,
                    "rows": [
                        {"page_top": 0, "page_bottom": 5},
                        {"page_top": 5, "page_bottom": 10},
                    ],
                }
            ]
        }
        owners.assign_row_map(row_map)
        context = {
            "pixel_gray_page": image,
            "pixel_owners": owners,
            "row_map": row_map,
            "threshold": 210,
        }
        state = {
            "column": 0,
            "row": 0,
            "crop_box": (0, 0, 12, 7),
            "covered_pixels": 0,
            "source_pixels": 1,
            "items": [{"id": "U00", "kind": "residual"}],
            "point_sets": {"U00": frozenset({(4, 4)})},
        }

        self.assertEqual(manual_two_row_candidates(context, state), [])


if __name__ == "__main__":
    unittest.main()
