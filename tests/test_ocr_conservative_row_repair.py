from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from swedish_wordlist_tools.ocr_conservative_row_repair import apply_conservative_row_repairs
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray, WHITE


class ConservativeRowRepairTests(unittest.TestCase):
    def _context(self, *, upper_x: int = 83):
        owners = PagePixelArray(width=120, height=30, data=bytearray([WHITE]) * (120 * 30))
        upper_code = owners.row_code(0)
        lower_code = owners.row_code(1)
        upper_points = {(upper_x, 2), (upper_x + 1, 2), (upper_x + 2, 3)}
        lower_points = {(57, y) for y in range(4, 12)} | {(58, y) for y in range(5, 12)}
        for x, y in upper_points:
            owners.data[y * owners.width + x] = upper_code
        for x, y in lower_points:
            owners.data[y * owners.width + x] = lower_code
        return {
            "page_number": 39,
            "pixel_owners": owners,
            "pixel_owner_revision": 0,
            "pixel_owner_row_revisions": {},
            "column_content_lefts": {0: 0},
            "positions": [(0, 0), (0, 1)],
            "row_map": {
                "row_count": 2,
                "columns": [
                    {
                        "column": 0,
                        "left": 0,
                        "right": 120,
                        "crop_left": 0,
                        "crop_right": 120,
                        "row_pitch": 17,
                        "rows": [
                            {"index": 0, "source": "old", "page_top": 0, "page_bottom": 4},
                            {"index": 1, "source": "old", "page_top": 4, "page_bottom": 16},
                        ],
                    }
                ]
            },
        }, upper_points, lower_points

    def test_tiny_late_upper_is_geometrically_merged_and_reindexed(self):
        context, upper_points, lower_points = self._context(upper_x=83)
        models = [SimpleNamespace(min_y=-10, max_y=5)]
        hit = SimpleNamespace(
            translate_y=10,
            translate_x=57,
            baseline=10,
            steps=7,
            model=SimpleNamespace(min_y=-6, pixels=frozenset({(0, 0)}), label="a", style="bold"),
        )
        combined = {(x, y) for x, y in upper_points | lower_points}
        match = SimpleNamespace(pixels=frozenset(combined))
        with patch(
            "swedish_wordlist_tools.ocr_conservative_row_repair.ranked_exact_local_hits",
            return_value=[hit],
        ), patch(
            "swedish_wordlist_tools.ocr_conservative_row_repair._select_at_baseline",
            return_value=[match],
        ):
            records = apply_conservative_row_repairs(context, models)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].upper_row, 0)
        self.assertEqual(records[0].lower_row, 1)
        self.assertEqual(records[0].moved_pixels, len(upper_points))
        self.assertEqual(context["positions"], [(0, 0)])
        self.assertEqual(context["row_map"]["row_count"], 1)
        merged = context["row_map"]["columns"][0]["rows"][0]
        self.assertEqual(merged["index"], 0)
        self.assertEqual(merged["page_top"], 0)
        self.assertEqual(merged["page_bottom"], 16)
        self.assertEqual(merged["source"], "conservative-merged-row")
        self.assertEqual(merged["conservative_merged_from"], [0, 1])
        owners = context["pixel_owners"]
        merged_code = owners.row_code(0)
        for x, y in upper_points | lower_points:
            self.assertEqual(owners.value(x, y), merged_code)

    def test_compaction_remaps_following_owner_codes(self):
        context, upper_points, lower_points = self._context(upper_x=83)
        entry = context["row_map"]["columns"][0]
        entry["rows"].append({"index": 2, "source": "old", "page_top": 16, "page_bottom": 24})
        context["positions"].append((0, 2))
        context["row_map"]["row_count"] = 3
        owners = context["pixel_owners"]
        following = {(70, 18), (71, 19)}
        for x, y in following:
            owners.data[y * owners.width + x] = owners.row_code(2)

        models = [SimpleNamespace(min_y=-10, max_y=5)]
        hit = SimpleNamespace(
            translate_y=10,
            translate_x=57,
            baseline=10,
            steps=7,
            model=SimpleNamespace(min_y=-6, pixels=frozenset({(0, 0)}), label="a", style="bold"),
        )
        combined = {(x, y) for x, y in upper_points | lower_points}
        match = SimpleNamespace(pixels=frozenset(combined))
        with patch(
            "swedish_wordlist_tools.ocr_conservative_row_repair.ranked_exact_local_hits",
            return_value=[hit],
        ), patch(
            "swedish_wordlist_tools.ocr_conservative_row_repair._select_at_baseline",
            return_value=[match],
        ):
            apply_conservative_row_repairs(context, models)

        self.assertEqual(context["positions"], [(0, 0), (0, 1)])
        for x, y in following:
            self.assertEqual(owners.value(x, y), owners.row_code(1))

    def test_small_upper_at_legal_start_is_never_repaired(self):
        context, upper_points, _lower_points = self._context(upper_x=70)
        models = [SimpleNamespace(min_y=-10, max_y=5)]
        with patch(
            "swedish_wordlist_tools.ocr_conservative_row_repair.ranked_exact_local_hits"
        ) as ranked:
            records = apply_conservative_row_repairs(context, models)
        self.assertEqual(records, [])
        ranked.assert_not_called()
        self.assertEqual(context["positions"], [(0, 0), (0, 1)])
        owners = context["pixel_owners"]
        upper_code = owners.row_code(0)
        for x, y in upper_points:
            self.assertEqual(owners.value(x, y), upper_code)

    def test_repair_pass_is_idempotent(self):
        context, _upper_points, _lower_points = self._context(upper_x=70)
        models = [SimpleNamespace(min_y=-10, max_y=5)]
        first = apply_conservative_row_repairs(context, models)
        second = apply_conservative_row_repairs(context, models)
        self.assertEqual(first, second)
        self.assertTrue(context["conservative_row_repairs_applied"])


if __name__ == "__main__":
    unittest.main()
