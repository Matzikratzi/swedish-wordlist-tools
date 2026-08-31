from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

from swedish_wordlist_tools.ocr_row_map_words import ocr_page_row_map
from swedish_wordlist_tools.ocr_tsv_articles import OcrWord


class RowMapWordTests(unittest.TestCase):
    def test_lattice_row_is_ocrd_from_physical_row_geometry(self) -> None:
        image = Image.new("L", (90, 100), 255)
        row_map = {
            "columns": [
                {
                    "column": 1,
                    "rows": [
                        {
                            "index": 7,
                            "source": "white-gap-ink-island",
                            "page_top": 48,
                            "page_bottom": 63,
                            "center_y": 55.0,
                        }
                    ],
                }
            ]
        }
        word = OcrWord(
            block=1,
            paragraph=1,
            line=1,
            word=1,
            left=8,
            top=2,
            width=31,
            height=12,
            confidence=93.0,
            text="stjärna",
        )

        with patch(
            "swedish_wordlist_tools.ocr_row_map_words._run_row_tesseract",
            return_value=[word],
        ) as run:
            records = ocr_page_row_map(image, row_map, pad_y=1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "stjärna")
        self.assertEqual(records[0]["row_source"], "white-gap-ink-island")
        self.assertEqual(records[0]["row_crop_box"], [30, 47, 60, 64])
        self.assertEqual(records[0]["bbox"], [38, 49, 31, 12])
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
