import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_neighbor_row_raster import add_neighbor_row_raster


class NeighborRowRasterTests(unittest.TestCase):
    def test_raster_extends_eight_pixels_around_target_row(self):
        page = Image.new("L", (40, 60), 255)
        context = {
            "page": page,
            "row_map": {
                "columns": [
                    {"rows": [{"page_top": 20, "page_bottom": 30}]},
                ]
            },
        }
        state = {
            "column": 0,
            "row": 0,
            "crop_box": (5, 19, 25, 31),
        }
        result = add_neighbor_row_raster(context, state, probe_y=8)
        self.assertEqual(result["neighbor_raster_width"], 20)
        self.assertEqual(result["neighbor_raster_height"], 26)
        self.assertEqual(result["neighbor_core_top"], 8)
        self.assertEqual(result["neighbor_core_bottom"], 18)
        self.assertEqual(result["neighbor_page_top"], 12)
        self.assertEqual(result["neighbor_page_bottom"], 38)
        self.assertTrue(result["neighbor_raster_image"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
