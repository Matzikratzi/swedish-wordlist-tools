from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from swedish_wordlist_tools.ocr_editable_unknown_glyph_review import _attach_context_images
from swedish_wordlist_tools.ocr_sequential_page_review import (
    _segment_box,
    _segment_index_for_bbox,
    _write_page_context_segments,
)


class ReviewFacsimileContextTests(unittest.TestCase):
    def test_word_center_selects_one_of_twelve_segments(self) -> None:
        self.assertEqual(_segment_index_for_bbox([10, 10, 20, 20], 900, 1200), (0, 0))
        self.assertEqual(_segment_index_for_bbox([410, 410, 20, 20], 900, 1200), (1, 1))
        self.assertEqual(_segment_index_for_bbox([810, 1010, 20, 20], 900, 1200), (2, 3))

    def test_segment_boxes_overlap_but_stay_on_page(self) -> None:
        first = _segment_box(0, 0, 900, 1200)
        second_vertical = _segment_box(0, 1, 900, 1200)
        second_column = _segment_box(1, 0, 900, 1200)

        self.assertEqual(first[0], 0)
        self.assertEqual(first[1], 0)
        self.assertGreater(first[3], second_vertical[1])
        self.assertGreater(first[2], second_column[0])
        self.assertLessEqual(first[2], 900)
        self.assertLessEqual(first[3], 1200)

    def test_writer_creates_exactly_twelve_images_and_embeds_linked_segment(self) -> None:
        rows = [
            {"target_page_word_bbox": [10, 10, 20, 20]},
            {"target_page_word_bbox": [810, 1010, 20, 20]},
        ]
        image = Image.new("L", (900, 1200), 255)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            written = _write_page_context_segments(rows, image, out)
            files = sorted((out / "context").glob("page-segment-*.png"))
            self.assertEqual(written, 12)
            self.assertEqual(len(files), 12)
            self.assertTrue(rows[0]["context_image"].startswith("data:image/png;base64,"))
            self.assertTrue(rows[1]["context_image"].startswith("data:image/png;base64,"))
            self.assertEqual(rows[0]["context_image_file"], "context/page-segment-c1-r1.png")
            self.assertEqual(rows[1]["context_image_file"], "context/page-segment-c3-r4.png")

    def test_facsimile_metadata_is_attached_to_unique_candidate_context(self) -> None:
        embedded = "data:image/png;base64,ZmFrZQ=="
        rows = [{
            "source": {"source_id": "page:1:ocr:1"},
            "context_image": embedded,
            "context_image_bbox": [280, 570, 620, 930],
        }]
        candidates = [{
            "sources": [{"source_id": "page:1:ocr:1"}],
            "context": {},
        }]
        _attach_context_images(candidates, rows)
        self.assertEqual(candidates[0]["context"]["context_image"], embedded)
        self.assertEqual(
            candidates[0]["context"]["context_image_bbox"],
            [280, 570, 620, 930],
        )


if __name__ == "__main__":
    unittest.main()
