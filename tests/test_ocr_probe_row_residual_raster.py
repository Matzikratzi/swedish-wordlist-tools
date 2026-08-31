from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_probe_row_residual_raster import (
    component_pixels,
    render_component_raster,
)


class RowResidualRasterTests(unittest.TestCase):
    def test_component_pixels_selects_only_bbox_pixels(self) -> None:
        unmatched = {(1, 1), (2, 2), (8, 8)}
        component = {"left": 1, "top": 1, "right": 3, "bottom": 3}
        self.assertEqual(component_pixels(unmatched, component), {(1, 1), (2, 2)})

    def test_render_component_raster_preserves_shape(self) -> None:
        pixels = {(0, 0), (1, 1), (0, 2)}
        self.assertEqual(
            render_component_raster(pixels, pad=0, ink="#", blank="."),
            "#.\n.#\n#.",
        )

    def test_render_component_raster_can_pad(self) -> None:
        pixels = {(0, 0)}
        self.assertEqual(
            render_component_raster(pixels, pad=1, ink="#", blank="."),
            "...\n.#.\n...",
        )


if __name__ == "__main__":
    unittest.main()
