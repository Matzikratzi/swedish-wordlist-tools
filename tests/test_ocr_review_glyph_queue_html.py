from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_find_unreviewed_glyph_rows import QUEUE_FORMAT
from swedish_wordlist_tools.ocr_review_glyph_queue_html import (
    _inject_queue_navigation,
    load_queue,
)


class GlyphReviewQueueHtmlTests(unittest.TestCase):
    def test_load_queue_keeps_order_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            path.write_text(
                json.dumps(
                    {
                        "format": QUEUE_FORMAT,
                        "rows": [
                            {"page": 29, "column": 1, "row": 37},
                            {"page": 29, "column": 1, "row": 38},
                            {"page": 29, "column": 1, "row": 37},
                            {"page": 30, "column": 0, "row": 46},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                load_queue(path),
                [(29, 1, 37), (29, 1, 38), (30, 0, 46)],
            )

    def test_navigation_mentions_queue_position_and_cross_page_next(self):
        document = "<html><head></head><body><h1>Editor</h1></body></html>"
        rendered = _inject_queue_navigation(
            document,
            index=1,
            rows=[(29, 1, 37), (29, 1, 38), (30, 0, 46)],
        )
        self.assertIn("2/3 · sida 29 · kolumn 1 · rad 38", rendered)
        self.assertIn('href="/?i=0"', rendered)
        self.assertIn('href="/?i=2"', rendered)
        self.assertIn("Nästa kö-rad", rendered)


if __name__ == "__main__":
    unittest.main()
