from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_editable_unknown_glyph_review import _attach_context_images
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

    def test_context_box_is_clipped_at_page_edges(self) -> None:
        row = {
            "five_row_context": {
                "column": 0,
                "target_index": 0,
                "bands": [
                    {"page_top": 1, "page_bottom": 12},
                    {"page_top": 20, "page_bottom": 32},
                ],
            }
        }
        self.assertEqual(_three_line_context_box(row, 900, 1200), (0, 0, 300, 36))

    def test_facsimile_metadata_is_attached_to_unique_candidate_context(self) -> None:
        rows = [{
            "source": {"source_id": "page:1:ocr:1"},
            "context_image": "context/context-0000.png",
            "context_image_bbox": [0, 10, 300, 70],
        }]
        candidates = [{
            "sources": [{"source_id": "page:1:ocr:1"}],
            "context": {},
        }]
        _attach_context_images(candidates, rows)
        self.assertEqual(candidates[0]["context"]["context_image"], "context/context-0000.png")
        self.assertEqual(candidates[0]["context"]["context_image_bbox"], [0, 10, 300, 70])


if __name__ == "__main__":
    unittest.main()
