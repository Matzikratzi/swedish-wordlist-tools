from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_page_row_guides import (
    build_page_row_map,
    component_touches_target_row,
    target_unknown_groups,
)


class TargetRowGuideTests(unittest.TestCase):
    def _row(self) -> dict:
        return {
            "width": 20,
            "height": 24,
            "baseline": 10,
            "unexplained": [
                [5, 10], [6, 10],
                [5, 20], [6, 20],
            ],
            "five_row_context": {
                "column": 0,
                "source_target_index": 1,
                "source_bands": [
                    {"top": -4, "bottom": 4, "page_top": 96, "page_bottom": 104, "text": "prev"},
                    {"top": 6, "bottom": 14, "page_top": 106, "page_bottom": 114, "text": "target"},
                    {"top": 16, "bottom": 24, "page_top": 116, "page_bottom": 124, "text": "next"},
                ],
            },
        }

    def test_disconnected_next_row_component_is_not_candidate(self) -> None:
        groups = target_unknown_groups(self._row())
        self.assertEqual(groups, [{(5, 10), (6, 10)}])

    def test_connected_component_crossing_boundary_is_retained(self) -> None:
        row = self._row()
        crossing = {(5, y) for y in range(11, 18)}
        self.assertTrue(component_touches_target_row(row, crossing))

    def test_page_row_map_keeps_previous_and_next_guides(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            debug = {
                "page": 1,
                "five_row_context": {
                    "column": 0,
                    "source_target_index": 1,
                    "source_bands": [
                        {"top": -4, "bottom": 4, "page_top": 96, "page_bottom": 104, "text": "prev"},
                        {"top": 6, "bottom": 14, "page_top": 106, "page_bottom": 114, "text": "target"},
                        {"top": 16, "bottom": 24, "page_top": 116, "page_bottom": 124, "text": "next"},
                    ],
                },
            }
            (root / "saol14-word-debug-p00001-0000.json").write_text(
                json.dumps(debug), encoding="utf-8"
            )

            row_map = build_page_row_map(root)

        self.assertEqual(row_map["format"], "saol-page-row-map-v1")
        self.assertEqual(row_map["row_count"], 3)
        rows = row_map["columns"][0]["rows"]
        self.assertIsNone(rows[0]["previous_center_y"])
        self.assertEqual(rows[1]["previous_baseline_hint_y"], 103)
        self.assertEqual(rows[1]["next_baseline_hint_y"], 123)
        self.assertIsNone(rows[2]["next_center_y"])


if __name__ == "__main__":
    unittest.main()
