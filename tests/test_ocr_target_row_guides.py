from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from swedish_wordlist_tools.ocr_page_row_guides import (
    augment_page_row_map_with_lattice,
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
            "unexplained": [[5, 10], [6, 10], [5, 20], [6, 20]],
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

        self.assertEqual(row_map["format"], "saol-page-row-map-v2")
        self.assertEqual(row_map["row_count"], 3)
        rows = row_map["columns"][0]["rows"]
        self.assertEqual(rows[0]["source"], "tesseract-row")
        self.assertIsNone(rows[0]["previous_center_y"])
        self.assertEqual(rows[1]["previous_baseline_hint_y"], 103)
        self.assertEqual(rows[1]["next_baseline_hint_y"], 123)
        self.assertIsNone(rows[2]["next_center_y"])

    def test_lattice_row_is_inserted_and_neighbours_recomputed(self) -> None:
        image = Image.new("L", (90, 100), 255)
        # Four ink islands at a stable 20 px pitch. Tesseract knows 10, 30 and 70;
        # the lattice must recover the isolated row centred around 50.
        for center in (10, 30, 50, 70):
            for y in range(center - 2, center + 3):
                for x in range(5, 25):
                    image.putpixel((x, y), 0)

        row_map = {
            "format": "saol-page-row-map-v2",
            "page": 1,
            "columns": [{
                "column": 0,
                "rows": [
                    {"source": "tesseract-row", "page_top": 8, "page_bottom": 13, "center_y": 10.0, "baseline_hint_y": 12, "texts": ["a"]},
                    {"source": "tesseract-row", "page_top": 28, "page_bottom": 33, "center_y": 30.0, "baseline_hint_y": 32, "texts": ["b"]},
                    {"source": "tesseract-row", "page_top": 68, "page_bottom": 73, "center_y": 70.0, "baseline_hint_y": 72, "texts": ["d"]},
                ],
            }],
            "row_count": 3,
            "tesseract_row_count": 3,
            "proposed_row_count": 0,
        }

        augmented = augment_page_row_map_with_lattice(image, row_map)
        rows = augmented["columns"][0]["rows"]
        proposed = [row for row in rows if row["source"] == "white-gap-ink-island"]

        self.assertEqual(len(proposed), 1)
        self.assertEqual(proposed[0]["page_top"], 48)
        self.assertEqual(proposed[0]["page_bottom"], 53)
        self.assertEqual(augmented["row_count"], 4)
        self.assertEqual(augmented["proposed_row_count"], 1)
        self.assertEqual(rows[1]["next_center_y"], proposed[0]["center_y"])
        self.assertEqual(proposed[0]["previous_center_y"], rows[1]["center_y"])
        self.assertEqual(proposed[0]["next_center_y"], rows[3]["center_y"])


if __name__ == "__main__":
    unittest.main()
