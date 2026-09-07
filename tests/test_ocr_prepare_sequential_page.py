from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_prepare_sequential_page import (
    _active_line_context,
    _crop_box,
    _line_key,
    _page_from_row,
    _physical_lines,
    source_for_page,
)
from swedish_wordlist_tools.ocr_tsv_articles import OcrWord


class SequentialPagePreparationTests(unittest.TestCase):
    def test_page_prefers_explicit_page_image_number(self) -> None:
        row = {
            "sidnr1": 999,
            "source": "https://example.invalid/SAOL14_00042.png",
        }
        self.assertEqual(_page_from_row(row), 42)

    def test_source_for_page_uses_matching_source(self) -> None:
        rows = [
            {"sidnr1": 1, "source": "https://example.invalid/SAOL14_00001.png"},
            {"sidnr1": 2, "source": "https://example.invalid/SAOL14_00002.png"},
        ]
        self.assertEqual(
            source_for_page(rows, 2),
            "https://example.invalid/SAOL14_00002.png",
        )

    def test_crop_box_adds_vertical_safety_without_leaving_page(self) -> None:
        class Page:
            width = 100
            height = 80

        word = OcrWord(
            block=1,
            paragraph=1,
            line=1,
            word=1,
            left=0,
            top=2,
            width=12,
            height=10,
            confidence=90.0,
            text="abc",
        )
        self.assertEqual(_crop_box(word, Page(), 1, 5), (0, 0, 13, 17))

    def test_context_crop_uses_complete_column_width(self) -> None:
        class Page:
            width = 300
            height = 100

        word = OcrWord(
            block=1,
            paragraph=1,
            line=2,
            word=1,
            left=30,
            top=30,
            width=20,
            height=8,
            confidence=90.0,
            text="target",
        )
        context = {
            "column": 0,
            "column_left": 0,
            "column_right": 100,
            "target_index": 1,
            "bands_page": [
                {"top": 18, "bottom": 26},
                {"top": 30, "bottom": 38},
                {"top": 42, "bottom": 50},
            ],
        }
        self.assertEqual(_crop_box(word, Page(), 1, 5, context), (0, 13, 100, 55))

    def test_five_row_context_is_clipped_at_column_edges(self) -> None:
        page_width = 300

        def row(col: int, line: int, top: int) -> OcrWord:
            left = (col * 100) + 10
            return OcrWord(
                block=1,
                paragraph=1,
                line=line,
                word=1,
                left=left,
                top=top,
                width=20,
                height=8,
                confidence=90.0,
                text=f"c{col}r{line}",
            )

        col0 = [row(0, line, 10 + (line - 1) * 12) for line in range(1, 7)]
        col1 = [row(1, line, 10 + (line - 1) * 12) for line in range(1, 3)]
        contexts = _physical_lines(col0 + col1, page_width)

        def context_for(word: OcrWord) -> dict:
            return contexts[_line_key(word, page_width)]

        first = context_for(col0[0])
        second = context_for(col0[1])
        penultimate = context_for(col0[-2])
        last = context_for(col0[-1])

        self.assertEqual(first["target_index"], 0)
        self.assertEqual([b["text"] for b in first["bands_page"]], ["c0r1", "c0r2", "c0r3"])
        self.assertEqual(second["target_index"], 1)
        self.assertEqual(
            [b["text"] for b in second["bands_page"]],
            ["c0r1", "c0r2", "c0r3", "c0r4"],
        )
        self.assertEqual(penultimate["target_index"], 2)
        self.assertEqual(
            [b["text"] for b in penultimate["bands_page"]],
            ["c0r3", "c0r4", "c0r5", "c0r6"],
        )
        self.assertEqual(last["target_index"], 2)
        self.assertEqual([b["text"] for b in last["bands_page"]], ["c0r4", "c0r5", "c0r6"])

        for context in (first, second, penultimate, last):
            self.assertEqual(context["column"], 0)
            self.assertEqual((context["column_left"], context["column_right"]), (0, 100))
            self.assertTrue(all(str(b["text"]).startswith("c0") for b in context["bands_page"]))

    def test_outer_rows_are_hidden_when_no_component_spills_into_them(self) -> None:
        page = Image.new("L", (60, 60), 255)
        context = {
            "column": 0,
            "column_left": 0,
            "column_right": 60,
            "target_index": 2,
            "bands_page": [
                {"top": 1, "bottom": 8, "text": "-2"},
                {"top": 11, "bottom": 18, "text": "-1"},
                {"top": 21, "bottom": 28, "text": "0"},
                {"top": 31, "bottom": 38, "text": "+1"},
                {"top": 41, "bottom": 48, "text": "+2"},
            ],
        }
        active = _active_line_context(page, context, 210)
        self.assertEqual(active["source_band_indices"], [1, 2, 3])
        self.assertEqual(active["outer_support_rows"], [])
        self.assertEqual([b["text"] for b in active["bands_page"]], ["-1", "0", "+1"])
        self.assertEqual(active["target_index"], 1)

    def test_outer_row_is_activated_by_connected_spill(self) -> None:
        page = Image.new("L", (60, 60), 255)
        # Row centres are 4.5 and 14.5. A vertical 4-connected stroke crossing
        # y=9/10 therefore owns pixels on both sides of their Voronoi boundary.
        for y in (8, 9, 10, 11):
            page.putpixel((20, y), 0)
        context = {
            "column": 0,
            "column_left": 0,
            "column_right": 60,
            "target_index": 2,
            "bands_page": [
                {"top": 1, "bottom": 8, "text": "-2"},
                {"top": 11, "bottom": 18, "text": "-1"},
                {"top": 21, "bottom": 28, "text": "0"},
                {"top": 31, "bottom": 38, "text": "+1"},
                {"top": 41, "bottom": 48, "text": "+2"},
            ],
        }
        active = _active_line_context(page, context, 210)
        self.assertEqual(active["source_band_indices"], [0, 1, 2, 3])
        self.assertEqual(active["outer_support_rows"], [0])
        self.assertEqual([b["text"] for b in active["bands_page"]], ["-2", "-1", "0", "+1"])
        self.assertEqual(active["target_index"], 2)


if __name__ == "__main__":
    unittest.main()
