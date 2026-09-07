from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from swedish_wordlist_tools.ocr_headword_initial_hints import (
    expected_headword_initial,
    heading_initial,
    visible_heading,
)
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray


class HeadwordInitialHintTests(unittest.TestCase):
    def test_visible_heading_ignores_homonym_markup_but_keeps_case(self):
        self.assertEqual(visible_heading("<sup>2</sup>Älg·ko"), "Älg·ko")
        self.assertEqual(heading_initial("<sup>2</sup>Älg·ko"), "Ä")

    def _context(self, jsonl: Path, *, starts: list[int]) -> dict:
        width = 20
        height = len(starts) * 3 + 1
        owners = PagePixelArray(width=width, height=height, data=bytearray(width * height))
        rows = []
        for row_index, x in enumerate(starts):
            top = row_index * 3
            bottom = top + 2
            rows.append({"page_top": top, "page_bottom": bottom})
            owners.data[top * width + x] = owners.row_code(row_index)
        return {
            "jsonl_path": jsonl,
            "page_number": 9,
            "positions": [(0, i) for i in range(len(rows))],
            "row_map": {"columns": [{"rows": rows, "left": 0, "right": width}]},
            "pixel_owners": owners,
            "column_content_lefts": {0: 0},
            "priority_headword_x_counts": {0: Counter({2: 4})},
            "priority_homonym_x_counts": {0: Counter({1: 2})},
        }

    def test_exact_count_maps_primary_jsonl_headings_to_physical_starts(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rows.jsonl"
            rows = [
                {"page": 9, "ord": "apa", "homonr": "1", "urspr_lopnr": "1", "subnr": "1"},
                # Secondary heading: same printed article, no new start row.
                {"page": 9, "ord": "ap·a", "homonr": "0", "urspr_lopnr": "1", "subnr": "1"},
                {"page": 9, "ord": "<sup>2</sup>arg", "homonr": "2", "urspr_lopnr": "2", "subnr": "2"},
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            context = self._context(path, starts=[2, 1])

            self.assertEqual(expected_headword_initial(context, (0, 0)), "a")
            self.assertEqual(expected_headword_initial(context, (0, 1)), "a")
            self.assertEqual(context["headword_initial_hint_status"], "exact-count-map")

    def test_count_mismatch_disables_letter_hint(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rows.jsonl"
            path.write_text(
                json.dumps({"page": 9, "ord": "apa", "homonr": "1"}) + "\n",
                encoding="utf-8",
            )
            context = self._context(path, starts=[2, 2])

            self.assertIsNone(expected_headword_initial(context, (0, 0)))
            self.assertEqual(context["headword_initial_hint_status"], "count-mismatch")


if __name__ == "__main__":
    unittest.main()
