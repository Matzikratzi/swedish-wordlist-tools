from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_row_map_words import _owned_row_crop


class RowNeighborOwnershipTests(unittest.TestCase):
    def test_removes_component_owned_by_row_above(self) -> None:
        page = Image.new("L", (30, 30), 255)
        row = {"page_top": 10, "page_bottom": 18}
        box = (0, 9, 30, 19)

        # Target-row ink remains entirely inside the target span.
        for y in range(12, 16):
            for x in range(4, 8):
                page.putpixel((x, y), 0)

        # A descender from the row above reaches only into the one-pixel pad.
        # Its visible pixel at y=9 is connected to a larger component above.
        for y in range(4, 10):
            page.putpixel((20, y), 0)

        crop, removed = _owned_row_crop(page, row, box, probe_y=6)
        self.assertEqual(removed, 1)
        self.assertEqual(crop.getpixel((20, 0)), 255)
        self.assertEqual(crop.getpixel((4, 3)), 0)

    def test_removes_component_owned_by_row_below(self) -> None:
        page = Image.new("L", (30, 30), 255)
        row = {"page_top": 10, "page_bottom": 18}
        box = (0, 9, 30, 19)

        for y in range(12, 16):
            for x in range(4, 8):
                page.putpixel((x, y), 0)

        # Symmetric ascender/ink intrusion from the row below.
        for y in range(18, 24):
            page.putpixel((20, y), 0)

        crop, removed = _owned_row_crop(page, row, box, probe_y=6)
        self.assertEqual(removed, 1)
        self.assertEqual(crop.getpixel((20, 9)), 255)
        self.assertEqual(crop.getpixel((4, 3)), 0)

    def test_keeps_component_that_reaches_target_row_proper(self) -> None:
        page = Image.new("L", (30, 30), 255)
        row = {"page_top": 10, "page_bottom": 18}
        box = (0, 9, 30, 19)

        # Even though this component continues above the crop, it also has ink
        # in the target row proper, so ownership is ambiguous and we keep it.
        for y in range(4, 13):
            page.putpixel((20, y), 0)

        crop, removed = _owned_row_crop(page, row, box, probe_y=6)
        self.assertEqual(removed, 0)
        self.assertEqual(crop.getpixel((20, 0)), 0)
        self.assertEqual(crop.getpixel((20, 3)), 0)


if __name__ == "__main__":
    unittest.main()
