from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

from swedish_wordlist_tools.ocr_row_map_words import _persistent_left_rule_x, ocr_page_row_map
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

    def test_persistent_vertical_rule_is_trimmed_before_ocr(self) -> None:
        image = Image.new("L", (90, 180), 255)
        rows = []
        for index, top in enumerate(range(10, 170, 20)):
            rows.append({
                "index": index,
                "source": "white-gap-single",
                "page_top": top,
                "page_bottom": top + 10,
                "center_y": top + 4.5,
            })
            for y in range(top, top + 10):
                image.putpixel((5, y), 0)
            for y in range(top + 2, top + 8):
                for x in range(12, 25):
                    image.putpixel((x, y), 0)
        entry = {"column": 0, "left": 0, "right": 30, "rows": rows}
        self.assertEqual(_persistent_left_rule_x(image, entry), 5)

        row_map = {"columns": [entry]}
        with patch(
            "swedish_wordlist_tools.ocr_row_map_words._run_row_tesseract",
            return_value=[],
        ) as run:
            ocr_page_row_map(image, row_map, pad_y=0)

        self.assertEqual(entry["ocr_content_left"], 7)
        first_crop = run.call_args_list[0].args[0]
        self.assertEqual(first_crop.width, 23)

    def test_aligned_headword_structure_is_not_mistaken_for_left_rule(self) -> None:
        image = Image.new("L", (90, 190), 255)
        # Running header is deliberately dark and far left. It lies outside
        # the physical body-row spans and must not influence the column start.
        for y in range(1, 6):
            for x in range(2, 24):
                image.putpixel((x, y), 0)

        rows = []
        for index, top in enumerate(range(20, 180, 20)):
            rows.append({
                "index": index,
                "source": "white-gap-single",
                "page_top": top,
                "page_bottom": top + 10,
                "center_y": top + 4.5,
            })
            # Actual first glyphs start at x=12.
            for y in range(top + 2, top + 8):
                for x in range(12, 15):
                    image.putpixel((x, y), 0)
            # Repeated internal headword structure farther right. The old
            # global search could select it and crop away the first glyphs.
            for y in range(top + 1, top + 9):
                image.putpixel((20, y), 0)
            for y in range(top + 2, top + 8):
                for x in range(22, 29):
                    image.putpixel((x, y), 0)

        entry = {"column": 0, "left": 0, "right": 35, "rows": rows}
        self.assertIsNone(_persistent_left_rule_x(image, entry))

        row_map = {"columns": [entry]}
        with patch(
            "swedish_wordlist_tools.ocr_row_map_words._run_row_tesseract",
            return_value=[],
        ):
            ocr_page_row_map(image, row_map, pad_y=0)
        self.assertIsNone(entry["ocr_content_left"])


if __name__ == "__main__":
    unittest.main()
