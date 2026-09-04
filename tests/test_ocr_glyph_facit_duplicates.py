from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_facit_duplicates import audit_duplicates, preferred_model, render_report


class GlyphFacitDuplicateAuditTests(unittest.TestCase):
    def glyph(self, model_id, label, style, pixels, reviewed, role="unknown"):
        return {
            "model_id": model_id,
            "label": label,
            "style": style,
            "role": role,
            "pixels_relative_to_baseline": [list(point) for point in pixels],
            "reviewed": reviewed,
            "sources": [{"source": model_id}],
        }

    def test_verified_duplicate_is_preferred_even_with_higher_id(self):
        a = self.glyph("g000001", "a", "roman", [(0, 0)], False)
        b = self.glyph("g000009", "a", "roman", [(0, 0)], True)
        self.assertIs(preferred_model([a, b]), b)

    def test_lowest_id_wins_when_review_state_is_equal(self):
        a = self.glyph("g000005", "a", "roman", [(0, 0)], True)
        b = self.glyph("g000003", "a", "roman", [(0, 0)], True)
        self.assertIs(preferred_model([a, b]), b)

    def test_true_duplicates_are_separate_from_semantic_raster_ambiguity(self):
        glyphs = [
            self.glyph("g000001", "a", "roman", [(0, 0)], False),
            self.glyph("g000002", "a", "roman", [(0, 0)], True),
            self.glyph("g000003", "o", "roman", [(0, 0)], True),
            self.glyph("g000004", "a", "italic", [(0, 0)], True),
            self.glyph("g000005", "b", "roman", [(0, 0), (1, 0)], True),
        ]
        report = audit_duplicates({"glyphs": glyphs})
        self.assertEqual(len(report["duplicate_groups"]), 1)
        self.assertEqual(report["duplicate_models_removable"], 1)
        duplicate = report["duplicate_groups"][0]
        self.assertEqual(duplicate["keep"]["model_id"], "g000002")
        self.assertEqual([g["model_id"] for g in duplicate["remove"]], ["g000001"])
        self.assertEqual(len(report["raster_ambiguity_groups"]), 1)
        self.assertEqual(
            [g["model_id"] for g in report["raster_ambiguity_groups"][0]["models"]],
            ["g000001", "g000002", "g000003", "g000004"],
        )

    def test_role_difference_does_not_make_a_duplicate_when_label_style_raster_match(self):
        a = self.glyph("g000001", "a", "roman", [(0, 0)], True, role="definition-roman")
        b = self.glyph("g000002", "a", "roman", [(0, 0)], False, role="pos-roman")
        report = audit_duplicates({"glyphs": [a, b]})
        self.assertEqual(len(report["duplicate_groups"]), 1)
        self.assertEqual(report["duplicate_groups"][0]["keep"]["model_id"], "g000001")

    def test_report_marks_remove_and_ambiguity(self):
        a = self.glyph("g000001", "a", "roman", [(0, 0)], True)
        b = self.glyph("g000002", "a", "roman", [(0, 0)], False)
        c = self.glyph("g000003", "o", "roman", [(0, 0)], True)
        text = render_report(audit_duplicates({"glyphs": [a, b, c]}))
        self.assertIn("REMOVE g000002", text)
        self.assertIn("RADERA INTE AUTOMATISKT", text)


if __name__ == "__main__":
    unittest.main()
