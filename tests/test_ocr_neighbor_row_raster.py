import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_neighbor_row_raster import add_neighbor_row_raster
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray


class NeighborRowRasterTests(unittest.TestCase):
    def test_single_row_falls_back_to_eight_pixel_probe(self):
        page = Image.new("L", (40, 60), 255)
        context = {
            "page": page,
            "threshold": 210,
            "row_map": {"columns": [{"rows": [{"page_top": 20, "page_bottom": 30}]}]},
        }
        state = {"column": 0, "row": 0, "crop_box": (5, 19, 25, 31)}
        result = add_neighbor_row_raster(context, state, probe_y=8)
        self.assertEqual(result["neighbor_raster_width"], 20)
        self.assertEqual(result["neighbor_raster_height"], 26)
        self.assertEqual(result["neighbor_core_top"], 8)
        self.assertEqual(result["neighbor_core_bottom"], 18)

    def test_three_rows_use_one_separator_per_pair(self):
        page = Image.new("L", (20, 40), 255)
        for point in ((4, 5), (5, 15), (6, 25)):
            page.putpixel(point, 0)
        rows = [
            {"page_top": 2, "page_bottom": 10},
            {"page_top": 12, "page_bottom": 20},
            {"page_top": 22, "page_bottom": 30},
        ]
        context = {
            "page": page,
            "threshold": 210,
            "row_map": {"columns": [{"rows": rows}]},
        }
        state = {"column": 0, "row": 1, "crop_box": (2, 11, 10, 21)}
        result = add_neighbor_row_raster(context, state, probe_y=8)

        self.assertEqual(result["neighbor_page_top"], 2)
        self.assertEqual(result["neighbor_page_bottom"], 30)
        self.assertEqual(result["neighbor_raster_height"], 28)
        self.assertEqual(result["neighbor_core_top"], 10)
        self.assertEqual(result["neighbor_core_bottom"], 18)
        self.assertEqual(
            result["neighbor_row_boundaries"],
            [[8, "RADGRÄNS row 0/1"], [18, "RADGRÄNS row 1/2"]],
        )
        ascii_raster = result["neighbor_raster_ascii"]
        self.assertIn("--- RADGRÄNS row 0/1 y=8 ---", ascii_raster)
        self.assertIn("--- RADGRÄNS row 1/2 y=18 ---", ascii_raster)
        self.assertNotIn("row 1 top", ascii_raster)
        self.assertGreaterEqual(ascii_raster.count("#"), 3)
        self.assertTrue(result["neighbor_raster_image"].startswith("data:image/png;base64,"))

    def test_separator_moves_below_rescued_upper_row_descender(self):
        page = Image.new("L", (20, 30), 255)
        # Provisional split is y=14, but exact ownership has rescued an upper-row
        # descender pixel on y=14. Lower-row ink does not begin until y=15, so a
        # single horizontal separator can faithfully move down to y=15.
        page.putpixel((5, 13), 0)
        page.putpixel((5, 14), 0)
        page.putpixel((8, 15), 0)
        rows = [
            {"page_top": 5, "page_bottom": 14},
            {"page_top": 15, "page_bottom": 22},
        ]
        owners = PagePixelArray.from_image(page)
        owners.assign_row_map({"columns": [{"left": 0, "right": 20, "rows": rows}]})
        owners.data[14 * owners.width + 5] = PagePixelArray.row_code(0)
        context = {
            "page": page,
            "threshold": 210,
            "pixel_owners": owners,
            "row_map": {"columns": [{"left": 0, "right": 20, "rows": rows}]},
        }
        state = {"column": 0, "row": 0, "crop_box": (0, 4, 20, 16)}

        result = add_neighbor_row_raster(context, state, probe_y=8)

        # Target row 0 has no previous physical row, so the three-row diagnostic
        # uses its eight-pixel edge probe: source_top=max(0, 5-8)=0. Effective
        # page separator y=15 is therefore also local y=15.
        self.assertIn([15, "RADGRÄNS row 0/1"], result["neighbor_row_boundaries"])
        self.assertIn("--- RADGRÄNS row 0/1 y=15 ---", result["neighbor_raster_ascii"])

    def test_support_line_is_displayed_one_pixel_below_matching_baseline(self):
        page = Image.new("L", (20, 40), 255)
        rows = [
            {"page_top": 2, "page_bottom": 10},
            {"page_top": 12, "page_bottom": 20},
            {"page_top": 22, "page_bottom": 30},
        ]
        context = {
            "page": page,
            "threshold": 210,
            "row_map": {"columns": [{"rows": rows}]},
        }
        # crop_top=11 and matcher baseline=5 -> page baseline 16; visual guide
        # belongs at page y=17, i.e. local y=15 when source_top=2.
        state = {
            "column": 0,
            "row": 1,
            "crop_box": (2, 11, 10, 21),
            "baseline": 5,
        }
        result = add_neighbor_row_raster(context, state, probe_y=8)
        self.assertIn([15, "row 1"], result["neighbor_support_lines"])
        self.assertIn([15, "STÖDLINJE row 1"], result["neighbor_row_boundaries"])
        self.assertIn("--- STÖDLINJE row 1 y=15 ---", result["neighbor_raster_ascii"])


if __name__ == "__main__":
    unittest.main()
