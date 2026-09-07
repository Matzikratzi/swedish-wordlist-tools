from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_neighbor_row_raster import _verified_white_safety_left
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray, WHITE


class VerifiedWhiteReviewMarginTests(unittest.TestCase):
    def _context(self) -> tuple[dict, dict, PagePixelArray]:
        width, height = 40, 10
        owners = PagePixelArray(width=width, height=height, data=bytearray([WHITE] * (width * height)))
        context = {
            "pixel_owners": owners,
            "row_map": {
                "columns": [
                    {
                        "crop_left": 0,
                        "crop_right": width,
                        "rows": [{"page_top": 0, "page_bottom": height}],
                    }
                ]
            },
        }
        state = {"column": 0, "row": 0, "crop_box": (0, 0, width, height)}
        return context, state, owners

    def test_takes_full_ten_columns_when_they_are_white(self) -> None:
        context, state, owners = self._context()
        # A black page/column structure sits just outside the requested ten
        # white safety columns. It must never be included.
        owners.data[5 * owners.width + 9] = owners.row_code(0)

        self.assertEqual(_verified_white_safety_left(context, state, 20), 10)

    def test_stops_immediately_after_black_structure(self) -> None:
        context, state, owners = self._context()
        # Only x=13..19 are safely white. x=12 is ink owned by the row, so the
        # crop must stop at x=13 rather than blindly applying ten pixels.
        owners.data[5 * owners.width + 12] = owners.row_code(0)

        self.assertEqual(_verified_white_safety_left(context, state, 20), 13)


if __name__ == "__main__":
    unittest.main()
