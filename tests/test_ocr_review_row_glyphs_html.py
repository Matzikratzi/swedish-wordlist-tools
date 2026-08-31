from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_review_row_glyphs_html import (
    glyph_from_points,
    normalize_points,
    relabel_exact_model,
    selected_points,
)


class RowGlyphHtmlReviewTests(unittest.TestCase):
    def test_normalize_points_uses_left_edge_and_support_baseline(self) -> None:
        self.assertEqual(
            normalize_points({(12, 3), (10, 5), (10, 4)}, baseline=6),
            [[0, -2], [0, -1], [2, -3]],
        )

    def test_glyph_can_combine_matched_body_and_residual_accent(self) -> None:
        glyph = glyph_from_points(
            "å",
            "roman",
            {(2, 5), (3, 5), (3, 1)},
            baseline=6,
            source={"page": 1, "review_selection": ["M05", "U01"]},
        )
        self.assertEqual(glyph["label"], "å")
        self.assertEqual(glyph["pixels_relative_to_baseline"], [[0, -1], [1, -5], [1, -1]])

    def test_selected_points_unions_matches_and_residuals(self) -> None:
        state = {"point_sets": {"M05": frozenset({(1, 2)}), "U01": frozenset({(1, 0)})}}
        self.assertEqual(selected_points(state, ["M05", "U01"]), {(1, 0), (1, 2)})

    def test_relabel_exact_model_changes_only_exact_shape(self) -> None:
        payload = {
            "glyphs": [
                {"label": "v", "style": "roman", "pixels_relative_to_baseline": [[0, -1], [1, 0]], "sources": []},
                {"label": "v", "style": "roman", "pixels_relative_to_baseline": [[0, 0]], "sources": []},
            ]
        }
        count = relabel_exact_model(
            payload,
            old_label="v",
            old_style="roman",
            pixels_relative_to_baseline=[[0, -1], [1, 0]],
            new_label="(",
            new_style="roman",
        )
        self.assertEqual(count, 1)
        self.assertEqual(payload["glyphs"][0]["label"], "(")
        self.assertEqual(payload["glyphs"][1]["label"], "v")

    def test_relabel_rejects_ambiguous_duplicate_shape(self) -> None:
        payload = {"glyphs": [
            {"label": "v", "style": "roman", "pixels_relative_to_baseline": [[0, 0]]},
            {"label": "v", "style": "roman", "pixels_relative_to_baseline": [[0, 0]]},
        ]}
        with self.assertRaisesRegex(ValueError, "exactly one"):
            relabel_exact_model(
                payload,
                old_label="v",
                old_style="roman",
                pixels_relative_to_baseline=[[0, 0]],
                new_label="(",
                new_style="roman",
            )


if __name__ == "__main__":
    unittest.main()
