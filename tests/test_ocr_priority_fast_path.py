from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_priority_fast_path import (
    classify_row_start,
    observe_row_layout,
    prioritized_fast_exact_cover,
    reset_priority_stats,
    set_row_priority_hint,
)


class _Owners:
    width = 20
    height = 10

    def __init__(self):
        self.data = bytearray(self.width * self.height)

    @staticmethod
    def row_code(row: int) -> int:
        return row + 1


class PriorityFastPathTests(unittest.TestCase):
    def test_priority_changes_order_not_result(self):
        bold_wrong = GlyphModel(
            label="X",
            style="headword-bold",
            pixels=frozenset({(0, 0), (1, 0)}),
            sources=10,
        )
        roman_right = GlyphModel(
            label="a",
            style="definition-roman",
            pixels=frozenset({(0, 0)}),
            sources=1,
        )
        ink = {(0, 0)}

        reset_priority_stats()
        set_row_priority_hint("headword")
        result = prioritized_fast_exact_cover(ink, 1, 1, [bold_wrong, roman_right])

        self.assertIsNotNone(result)
        _baseline, selected, _tested = result
        self.assertEqual([(m.label, m.style) for m in selected], [("a", "definition-roman")])

    def test_layout_learning_headword_homonym_and_continuation(self):
        context = {
            "row_map": {
                "columns": [
                    {
                        "crop_left": 0,
                        "crop_right": 20,
                        "rows": [
                            {"page_top": 0, "page_bottom": 2},
                            {"page_top": 2, "page_bottom": 4},
                            {"page_top": 4, "page_bottom": 6},
                        ],
                    }
                ]
            },
            "column_content_lefts": {0: 0},
            "pixel_owners": _Owners(),
        }
        owners = context["pixel_owners"]
        owners.data[0 * owners.width + 5] = owners.row_code(0)
        owners.data[2 * owners.width + 2] = owners.row_code(1)
        owners.data[4 * owners.width + 9] = owners.row_code(2)

        class M:
            def __init__(self, label, style, x):
                self.label = label
                self.style = style
                self.x = x
                self.baseline = 0

        observe_row_layout(
            context,
            {
                "column": 0,
                "crop_box": (0, 0, 20, 2),
                "matches": [M("a", "headword-bold", 5)],
            },
        )
        observe_row_layout(
            context,
            {
                "column": 0,
                "crop_box": (0, 2, 20, 4),
                "matches": [M("1", "unknown", 2), M("b", "headword-bold", 5)],
            },
        )

        self.assertEqual(classify_row_start(context, (0, 0)), "headword")
        self.assertEqual(classify_row_start(context, (0, 1)), "homonym")
        self.assertEqual(classify_row_start(context, (0, 2)), "continuation")


if __name__ == "__main__":
    unittest.main()
