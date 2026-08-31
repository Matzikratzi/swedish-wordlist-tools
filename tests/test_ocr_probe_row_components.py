from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_probe_row_components import connected_ink_components


class RowComponentProbeTests(unittest.TestCase):
    def test_separate_letters_are_separate_components(self) -> None:
        image = Image.new("L", (30, 15), 255)
        for x0 in (2, 12):
            for y in range(4, 11):
                for x in range(x0, x0 + 4):
                    image.putpixel((x, y), 0)
        components = connected_ink_components(image)
        self.assertEqual(len(components), 2)
        self.assertEqual([(c["left"], c["right"]) for c in components], [(2, 6), (12, 16)])

    def test_touching_letters_remain_one_component(self) -> None:
        image = Image.new("L", (25, 15), 255)
        for y in range(4, 11):
            for x in range(2, 7):
                image.putpixel((x, y), 0)
            for x in range(8, 13):
                image.putpixel((x, y), 0)
        image.putpixel((7, 7), 0)
        components = connected_ink_components(image)
        self.assertEqual(len(components), 1)
        self.assertEqual((components[0]["left"], components[0]["right"]), (2, 13))

    def test_detached_dot_is_not_forced_into_stem(self) -> None:
        image = Image.new("L", (15, 15), 255)
        for y in range(6, 13):
            for x in range(5, 8):
                image.putpixel((x, y), 0)
        image.putpixel((6, 2), 0)
        components = connected_ink_components(image)
        self.assertEqual(len(components), 2)
        self.assertEqual(sorted(c["pixels"] for c in components), [1, 21])


if __name__ == "__main__":
    unittest.main()
