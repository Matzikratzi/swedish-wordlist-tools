from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_prepare_sequential_page import _crop_box
from swedish_wordlist_tools.ocr_sequential_page_review_target_first import (
    _target_first_line_context,
)
from swedish_wordlist_tools.ocr_tsv_articles import OcrWord


class TargetFirstRowContextTests(unittest.TestCase):
    def _context(self) -> dict:
        return {
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

    def test_isolated_target_uses_only_middle_row(self) -> None:
        page = Image.new("L", (60, 60), 255)
        for y in range(22, 28):
            page.putpixel((20, y), 0)
        active = _target_first_line_context(page, self._context(), 210)
        self.assertEqual(active["source_band_indices"], [2])
        self.assertEqual(active["neighbor_support_rows"], [])
        self.assertEqual(active["outer_support_rows"], [])
        self.assertEqual([b["text"] for b in active["bands_page"]], ["0"])
        self.assertEqual(active["target_index"], 0)

    def test_connected_spill_activates_only_needed_immediate_neighbour(self) -> None:
        page = Image.new("L", (60, 60), 255)
        # Target/next-row centres are 24.5 and 34.5, so y=29/30 straddles
        # their Voronoi boundary. One connected vertical stroke requires +1.
        for y in (27, 28, 29, 30, 31):
            page.putpixel((20, y), 0)
        active = _target_first_line_context(page, self._context(), 210)
        self.assertEqual(active["source_band_indices"], [2, 3])
        self.assertEqual(active["neighbor_support_rows"], [3])
        self.assertEqual(active["outer_support_rows"], [])

    def test_outer_row_requires_nearer_neighbour_first(self) -> None:
        page = Image.new("L", (60, 60), 255)
        # Cross target -> +1 and then +1 -> +2 with one long component.
        for y in range(27, 43):
            page.putpixel((20, y), 0)
        active = _target_first_line_context(page, self._context(), 210)
        self.assertEqual(active["source_band_indices"], [2, 3, 4])
        self.assertEqual(active["neighbor_support_rows"], [3])
        self.assertEqual(active["outer_support_rows"], [4])

    def test_abonnera_like_lower_row_after_white_gap_is_not_in_crop(self) -> None:
        page = Image.new("L", (80, 40), 255)
        # Target ink finishes around its baseline/box. Foreign lower-row ink is
        # separated by seven blank raster rows, like the reported abonn·era case.
        for x in range(8, 32):
            page.putpixel((x, 12), 0)
        for x in range(20, 28):
            page.putpixel((x, 25), 0)

        context = {
            "column": 0,
            "column_left": 0,
            "column_right": 80,
            "target_index": 1,
            "bands_page": [
                {"top": 1, "bottom": 8, "text": "-1"},
                {"top": 8, "bottom": 13, "text": "0"},
                {"top": 20, "bottom": 26, "text": "+1"},
            ],
        }
        active = _target_first_line_context(page, context, 210)
        self.assertEqual(active["source_band_indices"], [1])

        word = OcrWord(
            block=1,
            paragraph=1,
            line=1,
            word=1,
            left=8,
            top=8,
            width=24,
            height=5,
            confidence=90.0,
            text="abonnera",
        )
        # With normal pad_y=5 the target-only crop ends at y=18; the unrelated
        # lower-row pixels at y=25 can therefore never become review candidates.
        self.assertEqual(_crop_box(word, page, 1, 5, active), (0, 3, 80, 18))


if __name__ == "__main__":
    unittest.main()
