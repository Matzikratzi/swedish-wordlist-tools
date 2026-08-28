from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_prepare_sequential_page import _crop_box, _page_from_row, source_for_page
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


if __name__ == "__main__":
    unittest.main()
