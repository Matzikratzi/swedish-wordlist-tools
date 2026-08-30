from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_editable_unknown_glyph_review import build_html
from swedish_wordlist_tools.ocr_sequential_page_review import _three_line_context_box


class ReviewFacsimileContextTests(unittest.TestCase):
    def test_context_box_uses_complete_column_third_and_surrounding_rows(self) -> None:
        row = {
            "five_row_context": {
                "column": 1,
                "target_index": 2,
                "bands": [
                    {"page_top": 100, "page_bottom": 112},
                    {"page_top": 120, "page_bottom": 132},
                    {"page_top": 140, "page_bottom": 152},
                    {"page_top": 160, "page_bottom": 172},
                    {"page_top": 180, "page_bottom": 192},
                ],
            }
        }
        self.assertEqual(_three_line_context_box(row, 900, 1200), (300, 116, 600, 176))

    def test_html_renders_context_image_when_present(self) -> None:
        row = {
            "expected": "abc",
            "page": 1,
            "subnr": "synthetic",
            "width": 3,
            "height": 3,
            "baseline": 2,
            "ink": [[1, 1]],
            "exact": [],
            "unexplained": [[1, 1]],
            "candidate_pixels": [[1, 1]],
            "jsonl_hint": {"text": "abc"},
            "context_image": "context/context-0000.png",
            "source": {"source_id": "synthetic"},
        }
        with tempfile.TemporaryDirectory() as td:
            facit = Path(td) / "facit.json"
            facit.write_text(json.dumps({"format": "saol14-manual-glyph-facit-v2", "glyphs": []}), encoding="utf-8")
            html = build_html([row], facit)

        self.assertIn("context/context-0000.png", html)
        self.assertIn("Facsimil · samma spalt", html)


if __name__ == "__main__":
    unittest.main()
