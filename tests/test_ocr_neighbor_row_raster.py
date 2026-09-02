import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_neighbor_row_raster import add_neighbor_row_raster


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

    def test_three_rows_and_ascii_pixels_are_included(self):
        page = Image.new("L", (20, 40), 255)
        # One black pixel in each physical row.
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
        ascii_raster = result["neighbor_raster_ascii"]
        self.assertIn("--- row 0 top y=0 ---", ascii_raster)
        self.assertIn("--- TARGET row 1 top y=10 ---", ascii_raster)
        self.assertIn("--- row 2 bottom y=28 ---", ascii_raster)
        self.assertGreaterEqual(ascii_raster.count("#"), 3)
        self.assertIn(".", ascii_raster)
        self.assertTrue(result["neighbor_raster_image"].startswith("data:image/png;base64,"))

    def test_three_row_raster_shows_target_and_projected_neighbor_support_lines(self):
        page = Image.new("L", (20, 50), 255)
        rows = [
            {"page_top": 2, "page_bottom": 12, "center_y": 6.5},
            {"page_top": 12, "page_bottom": 22, "center_y": 16.5},
            {"page_top": 22, "page_bottom": 32, "center_y": 26.5},
        ]
        context = {
            "page": page,
            "threshold": 210,
            "row_map": {"columns": [{"rows": rows}]},
        }
        # crop top 11 + baseline 8 => target baseline page y=19.
        state = {
            "column": 0,
            "row": 1,
            "crop_box": (2, 11, 10, 23),
            "baseline": 8,
        }
        result = add_neighbor_row_raster(context, state, probe_y=8)

        # Diagnostic raster starts at previous.page_top == 2.  Row centres are
        # 10 px apart, therefore the visible support lines are y=7,17,27.
        self.assertEqual(
            result["neighbor_support_lines"],
            [
                [7, "SUPPORT row 0 (projected)"],
                [17, "SUPPORT row 1 (exact)"],
                [27, "SUPPORT row 2 (projected)"],
            ],
        )
        ascii_raster = result["neighbor_raster_ascii"]
        self.assertIn("--- SUPPORT row 0 (projected) y=7 ---", ascii_raster)
        self.assertIn("--- SUPPORT row 1 (exact) y=17 ---", ascii_raster)
        self.assertIn("--- SUPPORT row 2 (projected) y=27 ---", ascii_raster)
        self.assertIn([7, "SUPPORT row 0 (projected)"], result["neighbor_row_boundaries"])


if __name__ == "__main__":
    unittest.main()