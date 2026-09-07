from __future__ import annotations

import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_glyph_facit_audit import (
    baseline_up_distribution,
    baseline_up_height,
    classify_size_models,
    descender_depth,
    exact_mask_duplicate_groups,
    format_baseline_metric_report,
    format_duplicate_review,
    format_per_label_height_report,
    format_size_class_report,
    height_distribution,
    infer_size_metric_modes,
    model_signature,
    multiple_height_populations,
    per_label_height_distribution,
    source_row_location,
)
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel


class GlyphFacitAuditTests(unittest.TestCase):
    def test_identical_mask_across_styles_is_reported(self) -> None:
        pixels = frozenset({(0, -1), (0, 0)})
        models = [
            GlyphModel(";", "roman", pixels, 2),
            GlyphModel(";", "italic", pixels, 1),
            GlyphModel("x", "roman", frozenset({(0, 0)}), 3),
        ]
        groups = exact_mask_duplicate_groups(models)
        self.assertEqual(len(groups), 1)
        self.assertEqual({(m.label, m.style) for m in groups[0]}, {(";", "roman"), (";", "italic")})

    def test_same_identity_repeated_is_not_cross_identity_duplicate(self) -> None:
        pixels = frozenset({(0, -1), (0, 0)})
        models = [
            GlyphModel(";", "roman", pixels, 2),
            GlyphModel(";", "roman", pixels, 1),
        ]
        self.assertEqual(exact_mask_duplicate_groups(models), [])

    def test_height_distribution_is_baseline_relative(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1),
            GlyphModel("g", "roman", frozenset({(0, -4), (0, 2)}), 1),
            GlyphModel("a", "italic", frozenset({(0, -5), (0, 0)}), 1),
        ]
        dist = height_distribution(models)
        self.assertEqual(dist["roman"][(-4, 0, 5)], 1)
        self.assertEqual(dist["roman"][(-4, 2, 7)], 1)
        self.assertEqual(dist["italic"][(-5, 0, 6)], 1)

    def test_baseline_up_height_ignores_descender(self) -> None:
        a = GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1)
        g = GlyphModel("g", "roman", frozenset({(0, -4), (0, 3)}), 1)
        self.assertEqual(baseline_up_height(a), 5)
        self.assertEqual(baseline_up_height(g), 5)
        self.assertEqual(descender_depth(a), 0)
        self.assertEqual(descender_depth(g), 3)

    def test_baseline_up_distribution_keeps_descender_separate(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1),
            GlyphModel("g", "roman", frozenset({(0, -4), (0, 3)}), 1),
        ]
        dist = baseline_up_distribution(models)
        self.assertEqual(dist[("a", "roman")][(5, 0)], 1)
        self.assertEqual(dist[("g", "roman")][(5, 3)], 1)

    def test_baseline_metric_report_groups_x_height_and_ascenders(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1),
            GlyphModel("g", "roman", frozenset({(0, -4), (0, 3)}), 1),
            GlyphModel("d", "roman", frozenset({(0, -7), (0, 0)}), 1),
            GlyphModel("ö", "roman", frozenset({(0, -6), (0, 0)}), 1),
        ]
        report = format_baseline_metric_report(models)
        self.assertIn("X-HEIGHT-ANCHORS", report)
        self.assertIn("roman: up=5:2", report)
        self.assertIn("ASCENDER-TOPS", report)
        self.assertIn("roman: up=8:1", report)
        self.assertIn("roman 'g': up=5/down=3:1", report)
        self.assertIn("roman 'ö': up=7/down=0:1", report)

    def test_size_modes_pick_two_best_supported_heights(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -5), (0, 0)}), 1),  # up 6
            GlyphModel("e", "roman", frozenset({(0, -5), (0, 0)}), 1),  # up 6
            GlyphModel("o", "roman", frozenset({(0, -7), (0, 0)}), 1),  # up 8
            GlyphModel("x", "roman", frozenset({(0, -8), (0, 0)}), 1),  # up 9 noise
            GlyphModel("u", "roman", frozenset({(0, -7), (0, 0)}), 1),  # up 8
        ]
        modes = infer_size_metric_modes(models)
        self.assertEqual(modes["roman"]["x-height"], (6, 8))

    def test_size_classification_marks_family_outlier(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -5), (0, 0)}), 1),  # up 6
            GlyphModel("c", "roman", frozenset({(0, -5), (0, 0)}), 1),  # support up 6
            GlyphModel("e", "roman", frozenset({(0, -7), (0, 0)}), 1),  # up 8
            GlyphModel("u", "roman", frozenset({(0, -7), (0, 0)}), 1),  # support up 8
            GlyphModel("o", "roman", frozenset({(0, -6), (0, 0)}), 1),  # up 7 outlier
        ]
        classified = classify_size_models(models)
        by_label = {row["label"]: row for row in classified}
        self.assertEqual(by_label["a"]["size"], "small")
        self.assertEqual(by_label["e"]["size"], "large")
        self.assertEqual(by_label["o"]["size"], "outlier")

    def test_size_report_separates_i_j_and_t_from_ordinary_ascenders(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -5), (0, 0)}), 1),
            GlyphModel("e", "roman", frozenset({(0, -7), (0, 0)}), 1),
            GlyphModel("d", "roman", frozenset({(0, -10), (0, 0)}), 1),
            GlyphModel("h", "roman", frozenset({(0, -12), (0, 0)}), 1),
            GlyphModel("i", "roman", frozenset({(0, -9), (0, 0)}), 1),
            GlyphModel("j", "roman", frozenset({(0, -11), (0, 2)}), 1),
            GlyphModel("t", "roman", frozenset({(0, -6), (0, 0)}), 1),
            GlyphModel("t", "roman", frozenset({(0, -9), (0, 0)}), 1),
        ]
        report = format_size_class_report(models)
        self.assertIn("roman: two-size-candidate=yes x-height-small/large=6/8", report)
        self.assertIn("ascender: small=11 large=13", report)
        self.assertIn("i/j: small=10 large=12", report)
        self.assertIn("t: small=7 large=10", report)

    def test_per_label_height_distribution_keeps_style_and_label_separate(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1),
            GlyphModel("a", "roman", frozenset({(0, -6), (0, 0)}), 1),
            GlyphModel("a", "italic", frozenset({(0, -5), (0, 0)}), 1),
            GlyphModel("b", "roman", frozenset({(0, -6), (0, 0)}), 1),
        ]
        dist = per_label_height_distribution(models)
        self.assertEqual(dist[("a", "roman")][(-4, 0, 5)], 1)
        self.assertEqual(dist[("a", "roman")][(-6, 0, 7)], 1)
        self.assertEqual(dist[("a", "italic")][(-5, 0, 6)], 1)
        self.assertEqual(dist[("b", "roman")][(-6, 0, 7)], 1)

    def test_multiple_height_populations_marks_only_split_identities(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1),
            GlyphModel("a", "roman", frozenset({(0, -6), (0, 0)}), 1),
            GlyphModel("b", "roman", frozenset({(0, -6), (0, 0)}), 1),
        ]
        multiple = multiple_height_populations(models)
        self.assertEqual(set(multiple), {("a", "roman")})

    def test_per_label_report_shows_all_and_multi_height_sections(self) -> None:
        models = [
            GlyphModel("a", "roman", frozenset({(0, -4), (0, 0)}), 1),
            GlyphModel("a", "roman", frozenset({(0, -6), (0, 0)}), 1),
            GlyphModel("b", "roman", frozenset({(0, -6), (0, 0)}), 1),
        ]
        report = format_per_label_height_report(models)
        self.assertIn("PER-LABEL-HEIGHTS", report)
        self.assertIn("roman 'a': y=-6..0/h=7:1, y=-4..0/h=5:1", report)
        self.assertIn("MULTI-HEIGHT-LABELS", report)
        self.assertIn("roman 'a': y=-6..0/h=7:1, y=-4..0/h=5:1", report)
        multi_section = report.split("MULTI-HEIGHT-LABELS", 1)[1]
        self.assertNotIn("roman 'b':", multi_section)

    def test_source_row_location_requires_physical_row_coordinates(self) -> None:
        self.assertEqual(source_row_location({"page": 4, "column": 1, "row": 24}), (4, 1, 24))
        self.assertIsNone(source_row_location({"page": 1553, "word_file": "word.png"}))

    def test_duplicate_review_prints_editor_command_and_target_style(self) -> None:
        pixels = frozenset({(0, -1), (0, 0)})
        roman = GlyphModel("R", "roman", pixels, 1)
        italic = GlyphModel("R", "italic", pixels, 1)
        provenance = {
            model_signature(roman): [{"page": 2, "column": 1, "row": 17}],
            model_signature(italic): [{"page": 4, "column": 0, "row": 31}],
        }
        report = format_duplicate_review(
            [roman, italic],
            provenance,
            jsonl=Path("/tmp/saol.jsonl"),
            port=8766,
        )
        self.assertIn("SÄRGRANSKA 'R' som nu är roman", report)
        self.assertIn("--page 2 --column 1 --row 17 --port 8766", report)
        self.assertIn("SÄRGRANSKA 'R' som nu är italic", report)
        self.assertIn("--page 4 --column 0 --row 31 --port 8766", report)


if __name__ == "__main__":
    unittest.main()
