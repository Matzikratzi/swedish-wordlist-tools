from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from swedish_wordlist_tools.ocr_neighbor_row_raster import _effective_separator_page
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray


class EffectiveRowSeparatorTests(unittest.TestCase):
    def _context(self, *, upper_points, lower_points, provisional=8):
        owners = PagePixelArray(width=8, height=12, data=bytearray(8 * 12))
        upper_code = owners.row_code(0)
        lower_code = owners.row_code(1)
        for x, y in upper_points:
            owners.data[y * owners.width + x] = upper_code
        for x, y in lower_points:
            owners.data[y * owners.width + x] = lower_code
        return {
            "pixel_owners": owners,
            "row_map": {
                "columns": [
                    {
                        "rows": [
                            {"page_top": 1, "page_bottom": provisional},
                            {"page_top": 4, "page_bottom": 11},
                        ]
                    }
                ]
            },
        }

    def test_separator_is_first_line_after_upper_rows_last_pixel(self):
        context = self._context(
            upper_points={(2, 2), (2, 3), (3, 4)},
            lower_points={(4, 6), (4, 7)},
        )

        separator = _effective_separator_page(
            context, column=0, upper_row_index=0, left=0, right=8
        )

        self.assertEqual(separator, 5)
        self.assertNotIn("row_overlap_warnings", context)

    def test_lower_row_overlap_warns_but_does_not_move_separator(self):
        context = self._context(
            upper_points={(2, 2), (2, 3), (3, 5)},
            lower_points={(6, 4), (6, 7)},
        )
        output = io.StringIO()

        with redirect_stdout(output):
            first = _effective_separator_page(
                context, column=0, upper_row_index=0, left=0, right=8
            )
            second = _effective_separator_page(
                context, column=0, upper_row_index=0, left=0, right=8
            )

        self.assertEqual(first, 6)
        self.assertEqual(second, 6)
        warning = context["row_overlap_warnings"][(0, 0)]
        self.assertEqual(warning["separator"], 6)
        self.assertEqual(warning["lower_top"], 4)
        self.assertEqual(warning["overlap_pixels_y"], 2)
        self.assertEqual(warning["provisional_separator"], 8)
        self.assertEqual(output.getvalue().count("VARNING överlappande rader"), 1)


if __name__ == "__main__":
    unittest.main()
