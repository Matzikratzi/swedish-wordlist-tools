from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, Match
from swedish_wordlist_tools.ocr_probe_row_glyphs import (
    analyse_row_exact,
    exact_text_runs,
    render_exact_markup,
    render_exact_text,
    row_ink,
)


class RowGlyphProbeTests(unittest.TestCase):
    def test_row_ink_uses_threshold(self) -> None:
        image = Image.new("L", (4, 3), 255)
        image.putpixel((1, 1), 0)
        image.putpixel((2, 1), 220)
        self.assertEqual(row_ink(image, threshold=210), {(1, 1)})

    def test_exact_facit_model_is_selected_with_role(self) -> None:
        image = Image.new("L", (8, 8), 255)
        for x, y in ((2, 3), (3, 3), (2, 4)):
            image.putpixel((x, y), 0)
        model = GlyphModel(
            label="a",
            style="headword-bold",
            pixels=frozenset({(0, -1), (1, -1), (0, 0)}),
            sources=3,
        )
        result = analyse_row_exact(image, [model])
        self.assertTrue(result["fully_exact"])
        self.assertEqual(result["baseline"], 4)
        self.assertEqual(len(result["selected"]), 1)
        self.assertEqual(result["selected"][0].label, "a")
        self.assertEqual(result["selected"][0].style, "headword-bold")

    def test_uncovered_pixel_keeps_row_incomplete(self) -> None:
        image = Image.new("L", (8, 8), 255)
        image.putpixel((2, 3), 0)
        image.putpixel((6, 6), 0)
        model = GlyphModel(
            label=".",
            style="pos-roman",
            pixels=frozenset({(0, 0)}),
            sources=1,
        )
        result = analyse_row_exact(image, [model])
        self.assertFalse(result["fully_exact"])
        self.assertLess(result["covered_pixels"], result["source_pixels"])

    def test_mixed_style_renderer_preserves_spaces_and_literal_markers(self) -> None:
        def match(label: str, style: str, x: int) -> Match:
            return Match(
                label=label,
                style=style,
                x=x,
                baseline=7,
                pixels=frozenset({(x, 7)}),
                model_pixels=1,
                sources=1,
            )

        matches = [
            match("a", "bold", 0),
            match("b", "bold", 1),
            match("s", "roman", 5),
            match(".", "roman", 6),
            match("~", "italic", 10),
            match("n", "italic", 11),
            match("¤", "italic", 15),
            match("e", "roman", 19),
            match("n", "roman", 20),
        ]
        self.assertEqual(render_exact_text(matches), "ab s. ~n ¤ en")
        self.assertEqual(
            render_exact_markup(matches),
            "<b>ab</b> s. <i>~n</i> <i>¤</i> en",
        )
        self.assertEqual(
            exact_text_runs(matches),
            [
                {"style": "bold", "text": "ab"},
                {"style": "space", "text": " "},
                {"style": "roman", "text": "s."},
                {"style": "space", "text": " "},
                {"style": "italic", "text": "~n"},
                {"style": "space", "text": " "},
                {"style": "italic", "text": "¤"},
                {"style": "space", "text": " "},
                {"style": "roman", "text": "en"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
