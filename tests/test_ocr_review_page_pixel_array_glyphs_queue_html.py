from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_queue_html import (
    QUEUE_FORMAT,
    load_queue,
)


class QueueLoadTests(unittest.TestCase):
    def _write(self, payload) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        path = Path(td.name) / "queue.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_cross_page_rows_in_order_and_deduplicates(self) -> None:
        path = self._write(
            {
                "format": QUEUE_FORMAT,
                "rows": [
                    {"page": 36, "column": 2, "row": 48, "covered_pixels": 123},
                    {"page": 39, "column": 0, "row": 26},
                    {"page": 39, "column": 0, "row": 26},
                    {"page": 75, "column": 0, "row": 24},
                ],
            }
        )
        self.assertEqual(
            [(36, 2, 48), (39, 0, 26), (75, 0, 24)],
            load_queue(path),
        )

    def test_rejects_wrong_format(self) -> None:
        path = self._write({"format": "other", "rows": []})
        with self.assertRaisesRegex(ValueError, "unsupported review queue format"):
            load_queue(path)

    def test_rejects_invalid_position(self) -> None:
        path = self._write(
            {"format": QUEUE_FORMAT, "rows": [{"page": 39, "column": 3, "row": 1}]}
        )
        with self.assertRaisesRegex(ValueError, "invalid review queue position"):
            load_queue(path)

    def test_rejects_empty_queue(self) -> None:
        path = self._write({"format": QUEUE_FORMAT, "rows": []})
        with self.assertRaisesRegex(ValueError, "review queue is empty"):
            load_queue(path)


if __name__ == "__main__":
    unittest.main()
