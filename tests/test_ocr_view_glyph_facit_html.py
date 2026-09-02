from pathlib import Path
import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_view_glyph_facit_html import (
    _global_y_range,
    _glyph_svg,
    build_vertical_summary,
    render_page,
)


class GlyphFacitViewerTests(unittest.TestCase):
    def model(self, label, style, pixels):
        return GlyphModel(label=label, style=style, pixels=frozenset(pixels), sources=1)

    def test_global_y_range_includes_all_models_and_margin(self):
        models = [
            self.model("o", "roman", {(0, -5), (1, 0)}),
            self.model("j", "roman", {(0, -7), (0, 3)}),
        ]
        self.assertEqual((-8, 4), _global_y_range(models))

    def test_shared_range_gives_same_svg_height(self):
        o = self.model("o", "roman", {(0, -5), (1, 0)})
        j = self.model("j", "roman", {(0, -7), (0, 3)})
        shared = _global_y_range([o, j])
        o_svg = _glyph_svg(o, pixel=10, shared_y_range=shared)
        j_svg = _glyph_svg(j, pixel=10, shared_y_range=shared)
        self.assertIn('height="120"', o_svg)
        self.assertIn('height="120"', j_svg)
        self.assertIn("y=-5..0", o_svg)
        self.assertIn("↑5 ↓0", o_svg)
        self.assertIn("y=-7..3", j_svg)
        self.assertIn("↑7 ↓3", j_svg)

    def test_vertical_summary_keeps_italic_f_visible_as_raw_extent(self):
        models = [
            self.model("f", "italic", {(0, -8), (1, 2)}),
            self.model("g", "italic", {(0, -5), (1, 3)}),
            self.model("o", "roman", {(0, -5), (1, 0)}),
            self.model("E", "roman", {(0, -8), (1, 0)}),
        ]
        page = build_vertical_summary(models)
        self.assertIn("särskilt", page)
        self.assertIn("-8..2", page)
        self.assertIn("-5..3", page)
        self.assertIn("jämförelse", page)
        self.assertIn("-8..0", page)
        self.assertIn("-5..0", page)

    def test_render_page_explains_shared_vertical_coordinates(self):
        models = [self.model("o", "roman", {(0, -5), (1, 0)})]
        page = render_page(models, Path("facit.json"), pixel=8)
        self.assertIn("gemensamt y=-6..1", page)
        self.assertIn("Vertikala mått relativt baslinjen", page)
        self.assertIn("klassificerar inte storlek", page)


if __name__ == "__main__":
    unittest.main()
