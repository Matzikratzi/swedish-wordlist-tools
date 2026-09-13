from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from swedish_wordlist_tools.ocr_conservative_row_split import apply_conservative_row_splits
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray, WHITE


class ConservativeRowSplitTests(unittest.TestCase):
    def _context(self):
        owners = PagePixelArray(width=120, height=40, data=bytearray([WHITE]) * (120 * 40))
        code0 = owners.row_code(0)
        code1 = owners.row_code(1)
        upper = {(20, y) for y in range(2, 10)}
        lower = {(34, y) for y in range(14, 28)}
        for x, y in upper | lower:
            owners.data[y * owners.width + x] = code0
        tail = {(57, y) for y in range(31, 36)}
        for x, y in tail:
            owners.data[y * owners.width + x] = code1
        context = {
            "page_number": 36,
            "pixel_owners": owners,
            "pixel_owner_revision": 0,
            "pixel_owner_row_revisions": {},
            "column_content_lefts": {0: 0},
            "positions": [(0, 0), (0, 1)],
            "row_map": {
                "row_count": 2,
                "columns": [{
                    "column": 0,
                    "left": 0,
                    "right": 120,
                    "crop_left": 0,
                    "crop_right": 120,
                    "row_pitch": 17,
                    "rows": [
                        {"page_top": 0, "page_bottom": 29, "index": 0},
                        {"page_top": 30, "page_bottom": 38, "index": 1},
                    ],
                }],
            },
        }
        return context, upper, lower, tail

    def test_exact_disjoint_partition_splits_row_and_remaps_tail(self):
        context, upper, lower, tail = self._context()
        models = [SimpleNamespace(min_y=-7, max_y=4)]
        upper_hit = SimpleNamespace(
            translate_y=9, translate_x=20, baseline=9, steps=7,
            model=SimpleNamespace(min_y=-7, pixels=frozenset({(0, 0)}), label="r", style="bold"),
        )
        lower_hit = SimpleNamespace(
            translate_y=26, translate_x=34, baseline=26, steps=7,
            model=SimpleNamespace(min_y=-12, pixels=frozenset({(0, 0)}), label="a", style="bold"),
        )
        upper_match = SimpleNamespace(pixels=frozenset(upper))
        lower_match = SimpleNamespace(pixels=frozenset(lower))

        with patch(
            "swedish_wordlist_tools.ocr_conservative_row_split.ranked_exact_local_hits",
            return_value=[upper_hit, lower_hit],
        ), patch(
            "swedish_wordlist_tools.ocr_conservative_row_split._select_at_baseline",
            side_effect=lambda black, width, height, models, baseline: [upper_match] if baseline == 9 else [lower_match],
        ):
            records = apply_conservative_row_splits(context, models)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].upper_baseline, 9)
        self.assertEqual(records[0].lower_baseline, 26)
        rows = context["row_map"]["columns"][0]["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["page_bottom"], 10)
        self.assertEqual(rows[1]["page_top"], 10)
        self.assertEqual(context["positions"], [(0, 0), (0, 1), (0, 2)])
        owners = context["pixel_owners"]
        for x, y in upper:
            self.assertEqual(owners.value(x, y), owners.row_code(0))
        for x, y in lower:
            self.assertEqual(owners.value(x, y), owners.row_code(1))
        for x, y in tail:
            self.assertEqual(owners.value(x, y), owners.row_code(2))

    def test_one_unexplained_pixel_blocks_split(self):
        context, upper, lower, _tail = self._context()
        extra = (80, 12)
        context["pixel_owners"].data[extra[1] * context["pixel_owners"].width + extra[0]] = context["pixel_owners"].row_code(0)
        models = [SimpleNamespace(min_y=-7, max_y=4)]
        upper_hit = SimpleNamespace(
            translate_y=9, translate_x=20, baseline=9, steps=7,
            model=SimpleNamespace(min_y=-7, pixels=frozenset({(0, 0)}), label="r", style="bold"),
        )
        lower_hit = SimpleNamespace(
            translate_y=26, translate_x=34, baseline=26, steps=7,
            model=SimpleNamespace(min_y=-12, pixels=frozenset({(0, 0)}), label="a", style="bold"),
        )
        with patch(
            "swedish_wordlist_tools.ocr_conservative_row_split.ranked_exact_local_hits",
            return_value=[upper_hit, lower_hit],
        ), patch(
            "swedish_wordlist_tools.ocr_conservative_row_split._select_at_baseline",
            side_effect=lambda black, width, height, models, baseline: [SimpleNamespace(pixels=frozenset(upper if baseline == 9 else lower))],
        ):
            records = apply_conservative_row_splits(context, models)
        self.assertEqual(records, [])
        self.assertEqual(len(context["row_map"]["columns"][0]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
