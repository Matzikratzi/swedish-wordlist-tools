from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, Match
from swedish_wordlist_tools.ocr_probe_row_glyphs import (
    analyse_row_exact,
    exact_text_runs,
    infer_space_gap,
    jsonl_like_fields,
    render_exact_markup,
    render_exact_text,
    row_ink,
    text_boundary,
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

    @staticmethod
    def match(label: str, style: str, x: int, width: int = 1) -> Match:
        return Match(
            label=label,
            style=style,
            x=x,
            baseline=7,
            pixels=frozenset((x + dx, 7) for dx in range(width)),
            model_pixels=width,
            sources=1,
        )

    def test_mixed_style_renderer_changes_format_only_when_style_changes(self) -> None:
        matches = [
            self.match("a", "bold", 0),
            self.match("b", "bold", 1),
            self.match("s", "roman", 5),
            self.match(".", "roman", 6),
            self.match("~", "italic", 10),
            self.match("n", "italic", 11),
            self.match("¤", "italic", 15),
            self.match("e", "roman", 19),
            self.match("n", "roman", 20),
        ]
        self.assertEqual(render_exact_text(matches), "ab s. ~n ¤ en")
        self.assertEqual(
            render_exact_markup(matches),
            "<b>ab</b> s. <i>~n</i> ¤ en",
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
                {"style": "plain", "text": "¤"},
                {"style": "space", "text": " "},
                {"style": "roman", "text": "en"},
            ],
        )

    def test_row_local_space_gap_does_not_split_wide_headword_letters(self) -> None:
        matches = [
            self.match("a", "bold", 0, width=7),
            self.match("b", "bold", 10, width=7),  # three blank columns: letter spacing
            self.match("s", "roman", 21, width=4),  # four blank columns: word space
        ]
        self.assertEqual(infer_space_gap(matches), 4)
        self.assertEqual(render_exact_text(matches), "ab s")
        self.assertEqual(render_exact_markup(matches), "<b>ab</b> s")

    def test_unmatched_source_ink_is_not_rendered_as_whitespace(self) -> None:
        matches = [
            self.match("a", "roman", 0, width=2),
            self.match("b", "roman", 8, width=2),
        ]
        source_ink = set().union(*(match.pixels for match in matches))
        source_ink.add((5, 7))  # unknown glyph between the two exact matches
        self.assertEqual(render_exact_text(matches, space_gap=3, source_ink=source_ink), "ab")

    def test_explanation_marker_ends_jsonl_text(self) -> None:
        matches = [
            self.match("a", "bold", 0),
            self.match("b", "bold", 1),
            self.match("s", "roman", 5),
            self.match(".", "roman", 6),
            self.match("~", "italic", 10),
            self.match("n", "italic", 11),
            self.match("¤", "italic", 15),
            self.match("e", "roman", 19),
            self.match("n", "roman", 20),
        ]
        fields = jsonl_like_fields(matches)
        self.assertEqual(fields["stycke"], "ab")
        self.assertEqual(fields["ordkl"], "s. <i>~n</i>")
        self.assertEqual(fields["text"], "~n")
        self.assertEqual(fields["boundary"], "explanation-marker")
        self.assertEqual(fields["remainder"], "¤ en")

    def test_number_ends_jsonl_text_as_numbered_explanation(self) -> None:
        matches = [
            self.match("a", "bold", 0),
            self.match("s", "roman", 4),
            self.match(".", "roman", 5),
            self.match("~", "italic", 9),
            self.match("n", "italic", 10),
            self.match("1", "roman", 14),
            self.match("x", "roman", 18),
        ]
        boundary_index, reason = text_boundary(matches)
        self.assertEqual(boundary_index, 5)
        self.assertEqual(reason, "numbered-explanation")
        fields = jsonl_like_fields(matches)
        self.assertEqual(fields["text"], "~n")
        self.assertEqual(fields["remainder"], "1 x")

    def test_new_bold_headword_ends_current_article(self) -> None:
        matches = [
            self.match("a", "bold", 0),
            self.match("s", "roman", 4),
            self.match(".", "roman", 5),
            self.match("~", "italic", 9),
            self.match("n", "italic", 10),
            self.match("b", "bold", 15),
            self.match("s", "roman", 19),
            self.match(".", "roman", 20),
        ]
        fields = jsonl_like_fields(matches)
        self.assertEqual(fields["boundary"], "next-headword")
        self.assertEqual(fields["stycke"], "a")
        self.assertEqual(fields["ordkl"], "s. <i>~n</i>")
        self.assertEqual(fields["text"], "~n")
        self.assertEqual(fields["remainder"], "<b>b</b> s.")


if __name__ == "__main__":
    unittest.main()
