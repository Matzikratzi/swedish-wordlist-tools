from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_facit_duplicates import (
    audit_duplicates,
    deduplicate_payload,
    preferred_model,
    render_report,
)


class GlyphFacitDuplicateAuditTests(unittest.TestCase):
    def glyph(self, model_id, label, style, pixels, reviewed, role="unknown", source=None):
        return {
            "model_id": model_id,
            "label": label,
            "style": style,
            "role": role,
            "pixels_relative_to_baseline": [list(point) for point in pixels],
            "reviewed": reviewed,
            "sources": [{"source": source or model_id}],
        }

    def test_verified_duplicate_is_preferred_even_with_higher_id(self):
        a = self.glyph("g000001", "a", "roman", [(0, 0)], False)
        b = self.glyph("g000009", "a", "roman", [(0, 0)], True)
        self.assertIs(preferred_model([a, b]), b)

    def test_lowest_id_wins_when_review_state_is_equal(self):
        a = self.glyph("g000005", "a", "roman", [(0, 0)], True)
        b = self.glyph("g000003", "a", "roman", [(0, 0)], True)
        self.assertIs(preferred_model([a, b]), b)

    def test_true_duplicates_are_separate_from_raster_ambiguity(self):
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
        self.assertEqual(report["duplicate_groups"][0]["keep"]["model_id"], "g000002")
        self.assertEqual(len(report["raster_ambiguity_groups"]), 1)

    def test_role_is_ignored_for_duplicate_identity(self):
        a = self.glyph("g000001", "a", "roman", [(0, 0)], True, role="definition-roman")
        b = self.glyph("g000002", "a", "roman", [(0, 0)], False, role="pos-roman")
        report = audit_duplicates({"glyphs": [a, b]})
        self.assertEqual(len(report["duplicate_groups"]), 1)
        self.assertEqual(report["duplicate_groups"][0]["keep"]["model_id"], "g000001")

    def test_cross_typography_exact_raster_is_reported_but_not_duplicate(self):
        roman = self.glyph("g000003", "d", "roman", [(0, -1), (0, 0)], False)
        italic = self.glyph("g000042", "d", "italic", [(0, -1), (0, 0)], True)
        report = audit_duplicates({"glyphs": [roman, italic]})
        self.assertEqual(report["duplicate_models_removable"], 0)
        self.assertEqual(len(report["cross_typography_groups"]), 1)
        text = render_report(report)
        self.assertIn("OLIKA TYPOGRAFI", text)
        self.assertIn("LÄMNAS ORÖRD", text)

    def test_deduplicate_merges_sources_and_keeps_cross_typography(self):
        old = self.glyph("g000001", "a", "roman", [(0, 0)], False, source="old")
        keep = self.glyph("g000009", "a", "roman", [(0, 0)], True, source="keep")
        italic = self.glyph("g000010", "a", "italic", [(0, 0)], True, source="italic")
        payload = {"glyphs": [old, keep, italic]}
        report = deduplicate_payload(payload)
        self.assertEqual(report["duplicate_models_removable"], 1)
        self.assertEqual([g["model_id"] for g in payload["glyphs"]], ["g000009", "g000010"])
        self.assertEqual(keep["sources"], [{"source": "keep"}, {"source": "old"}])
        self.assertTrue(keep["reviewed"])
        self.assertEqual(italic["style"], "italic")

    def test_report_marks_remove(self):
        a = self.glyph("g000001", "a", "roman", [(0, 0)], True)
        b = self.glyph("g000002", "a", "roman", [(0, 0)], False)
        text = render_report(audit_duplicates({"glyphs": [a, b]}))
        self.assertIn("REMOVE g000002", text)


if __name__ == "__main__":
    unittest.main()
