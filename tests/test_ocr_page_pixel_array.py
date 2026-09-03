import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_page_pixel_array import (
    PagePixelArray,
    UNASSIGNED_INK,
    WHITE,
)


class PagePixelArrayTests(unittest.TestCase):
    def test_from_image_uses_zero_for_white_and_255_for_unknown_ink(self):
        page = Image.new("L", (4, 3), 255)
        page.putpixel((1, 1), 0)
        page.putpixel((2, 1), 209)
        page.putpixel((3, 1), 210)

        pixels = PagePixelArray.from_image(page, threshold=210)

        self.assertEqual(pixels.value(0, 0), WHITE)
        self.assertEqual(pixels.value(1, 1), UNASSIGNED_INK)
        self.assertEqual(pixels.value(2, 1), UNASSIGNED_INK)
        self.assertEqual(pixels.value(3, 1), WHITE)

    def test_dense_black_section_rectangle_is_masked_completely(self):
        page = Image.new("L", (50, 50), 255)
        # Dense black section marker with a white letter-shaped hole.
        for y in range(8, 42):
            for x in range(7, 43):
                page.putpixel((x, y), 0)
        for y in range(16, 34):
            page.putpixel((24, y), 255)
            page.putpixel((25, y), 255)
        # Ordinary text-like pixels elsewhere must survive.
        page.putpixel((2, 2), 0)
        page.putpixel((3, 2), 0)

        pixels = PagePixelArray.from_image(page)
        regions = pixels.mask_dense_black_rectangles(
            min_width=20,
            min_height=20,
            min_ink_pixels=500,
            min_density=0.5,
        )

        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["box"], (7, 8, 43, 42))
        for y in range(8, 42):
            for x in range(7, 43):
                self.assertEqual(pixels.value(x, y), WHITE)
        self.assertEqual(pixels.value(2, 2), UNASSIGNED_INK)
        self.assertEqual(pixels.value(3, 2), UNASSIGNED_INK)

    def test_exact_row_geometry_assigns_touching_rows_without_padding_leak(self):
        page = Image.new("L", (8, 8), 255)
        # Upper row has ink on its final raster line; lower row starts directly
        # below it.  This is the case where the old +/-1 crop padding leaked.
        page.putpixel((2, 3), 0)
        page.putpixel((3, 3), 0)
        page.putpixel((2, 4), 0)
        page.putpixel((3, 4), 0)
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 8,
                    "rows": [
                        {"page_top": 1, "page_bottom": 4},
                        {"page_top": 4, "page_bottom": 7},
                    ],
                }
            ]
        }

        pixels = PagePixelArray.from_image(page)
        pixels.assign_row_map(row_map)

        self.assertEqual(pixels.value(2, 3), PagePixelArray.row_code(0))
        self.assertEqual(pixels.value(2, 4), PagePixelArray.row_code(1))

        # Deliberately ask for a padded crop spanning both physical rows.  The
        # rendered lower-row image must still contain only lower-row ownership.
        lower = pixels.render_owner_crop(row_index=1, box=(0, 3, 8, 7))
        self.assertEqual(lower.getpixel((2, 0)), 255)
        self.assertEqual(lower.getpixel((2, 1)), 0)

    def test_single_separator_gives_gap_ink_to_following_row(self):
        page = Image.new("L", (8, 10), 255)
        page.putpixel((2, 3), 0)  # last upper-row ink
        page.putpixel((2, 5), 0)  # protruding lower-row ink before its tight top
        page.putpixel((2, 7), 0)  # ordinary lower-row ink
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 8,
                    "rows": [
                        {"page_top": 1, "page_bottom": 4},
                        {"page_top": 7, "page_bottom": 9},
                    ],
                }
            ]
        }

        pixels = PagePixelArray.from_image(page)
        pixels.assign_row_map(row_map)

        self.assertEqual(pixels.value(2, 3), PagePixelArray.row_code(0))
        # There is no second boundary at row 1's tight page_top=7. Everything
        # from the separator y=4 belongs to row 1, including this y=5 pixel.
        self.assertEqual(pixels.value(2, 5), PagePixelArray.row_code(1))
        self.assertEqual(pixels.value(2, 7), PagePixelArray.row_code(1))

    def test_ink_outside_row_geometry_stays_unassigned(self):
        page = Image.new("L", (6, 6), 255)
        page.putpixel((2, 0), 0)
        page.putpixel((2, 2), 0)
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 6,
                    "rows": [{"page_top": 1, "page_bottom": 4}],
                }
            ]
        }

        pixels = PagePixelArray.from_image(page)
        assigned = pixels.assign_row_map(row_map)

        self.assertEqual(assigned, 1)
        self.assertEqual(pixels.value(2, 0), UNASSIGNED_INK)
        self.assertEqual(pixels.value(2, 2), PagePixelArray.row_code(0))
        self.assertEqual(
            pixels.counts(),
            {"white": 34, "unassigned_ink": 1, "assigned_ink": 1},
        )

    def test_column_bounds_prevent_cross_column_ownership(self):
        page = Image.new("L", (10, 5), 255)
        page.putpixel((4, 2), 0)
        page.putpixel((5, 2), 0)
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 5,
                    "rows": [{"page_top": 1, "page_bottom": 4}],
                },
                {
                    "left": 5,
                    "right": 10,
                    "rows": [{"page_top": 1, "page_bottom": 4}],
                },
            ]
        }

        pixels = PagePixelArray.from_image(page)
        pixels.assign_row_map(row_map)

        # Row indexes are local to a column, so both are row code 1; the column
        # rectangle is what keeps the two ownership regions disjoint.
        self.assertEqual(pixels.value(4, 2), PagePixelArray.row_code(0))
        self.assertEqual(pixels.value(5, 2), PagePixelArray.row_code(0))


if __name__ == "__main__":
    unittest.main()
