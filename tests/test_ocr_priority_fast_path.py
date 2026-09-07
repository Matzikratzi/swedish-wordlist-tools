from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_priority_fast_path import (
    classify_row_start,
    observe_row_layout,
    prioritized_fast_exact_cover,
    priority_stats,
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


class _RoleWithTypography(str):
    def __new__(cls, role: str, typography: str):
        obj = str.__new__(cls, role)
        obj.typographic_style = typography
        return obj


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

    def test_candidate_order_is_built_once_per_context(self):
        roman = GlyphModel(
            label="a",
            style="definition-roman",
            pixels=frozenset({(0, 0)}),
            sources=1,
        )

        reset_priority_stats()
        set_row_priority_hint("continuation")
        result = prioritized_fast_exact_cover(
            {(0, 0), (2, 0), (4, 0)},
            5,
            1,
            [roman],
        )

        self.assertIsNotNone(result)
        self.assertEqual(priority_stats()["order_builds"], 2)

    def test_identical_rasters_keep_old_canonical_model_order(self):
        pixels = frozenset({(0, 0)})
        canonical = GlyphModel(
            label="a",
            style=_RoleWithTypography("unknown", "roman"),
            pixels=pixels,
            sources=10,
        )
        hinted_bold = GlyphModel(
            label="z",
            style=_RoleWithTypography("unknown", "bold"),
            pixels=pixels,
            sources=1,
        )

        reset_priority_stats()
        set_row_priority_hint("headword")
        result = prioritized_fast_exact_cover({(0, 0)}, 1, 1, [hinted_bold, canonical])

        self.assertIsNotNone(result)
        _baseline, selected, _tested = result
        self.assertEqual([(m.label, str(m.style)) for m in selected], [("a", "unknown")])

    def test_raised_homonym_does_not_lock_headword_baseline(self):
        homonym = GlyphModel(
            label="1",
            style="unknown",
            pixels=frozenset({(0, 0)}),
            sources=2,
        )
        bold = GlyphModel(
            label="a",
            style="headword-bold",
            pixels=frozenset({(0, 0)}),
            sources=2,
        )
        ink = {(0, 1), (2, 5)}

        reset_priority_stats()
        set_row_priority_hint("homonym")
        result = prioritized_fast_exact_cover(ink, 3, 7, [bold, homonym])

        self.assertIsNotNone(result)
        baseline, selected, _tested = result
        self.assertEqual(baseline, 5)
        self.assertEqual(
            [(m.label, m.baseline) for m in selected],
            [("1", 1), ("a", 5)],
        )

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
            def __init__(self, label, style, x, baseline):
                self.label = label
                self.style = style
                self.x = x
                self.baseline = baseline

        observe_row_layout(
            context,
            {
                "column": 0,
                "crop_box": (0, 0, 20, 2),
                "matches": [M("a", "headword-bold", 5, 10)],
            },
        )
        observe_row_layout(
            context,
            {
                "column": 0,
                "crop_box": (0, 2, 20, 4),
                "matches": [
                    M("1", "unknown", 2, 6),
                    M("b", "headword-bold", 5, 10),
                ],
            },
        )

        self.assertEqual(classify_row_start(context, (0, 0)), "headword")
        self.assertEqual(classify_row_start(context, (0, 1)), "homonym")
        self.assertEqual(classify_row_start(context, (0, 2)), "continuation")

    def test_unknown_role_uses_known_bold_typography_for_layout(self):
        context = {}

        class M:
            label = "a"
            style = _RoleWithTypography("unknown", "bold")
            x = 7
            baseline = 12

        observe_row_layout(
            context,
            {
                "column": 2,
                "crop_box": (100, 0, 120, 20),
                "matches": [M()],
            },
        )
        self.assertEqual(context["priority_headword_x_counts"][2][107], 1)

    def test_layout_observation_ignores_non_match_test_doubles(self):
        context = {}
        observe_row_layout(context, {"matches": [object()]})
        self.assertNotIn("priority_headword_x_counts", context)
        self.assertNotIn("priority_homonym_x_counts", context)


if __name__ == "__main__":
    unittest.main()
