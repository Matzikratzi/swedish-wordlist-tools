from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_glyph_matcher import load_facit
from swedish_wordlist_tools.ocr_migrate_glyph_facit_v2 import migrate_payload
from swedish_wordlist_tools.ocr_sequential_page_review import _style_sequence


class GlyphFacitV2MigrationTests(unittest.TestCase):
    def test_migration_preserves_raster_and_sources_but_resets_semantic_role(self) -> None:
        old = {
            "format": "saol14-manual-glyph-facit-v1",
            "coordinate_system": "test",
            "glyphs": [
                {
                    "label": "a",
                    "style": "bold",
                    "pixels_relative_to_baseline": [[0, -1], [0, 0]],
                    "sources": [{"source_id": "s1"}],
                }
            ],
        }
        new = migrate_payload(old)
        self.assertEqual(new["format"], "saol14-manual-glyph-facit-v2")
        self.assertEqual(new["glyphs"][0]["label"], "a")
        self.assertEqual(new["glyphs"][0]["role"], "unknown")
        self.assertEqual(new["glyphs"][0]["legacy_style"], "bold")
        self.assertNotIn("style", new["glyphs"][0])
        self.assertEqual(new["glyphs"][0]["sources"], [{"source_id": "s1"}])

    def test_matcher_uses_v2_role_and_unknown_is_not_typography_evidence(self) -> None:
        payload = {
            "format": "saol14-manual-glyph-facit-v2",
            "glyphs": [
                {
                    "label": "a",
                    "role": "unknown",
                    "legacy_style": "bold",
                    "pixels_relative_to_baseline": [[0, 0]],
                    "sources": [],
                },
                {
                    "label": "s.",
                    "role": "pos-roman",
                    "pixels_relative_to_baseline": [[0, 0], [1, 0]],
                    "sources": [],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "facit-v2.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            models = load_facit(path)
        self.assertEqual([m.style for m in models], ["unknown", "pos-roman"])

        row = {
            "exact": [
                {"label": "a", "style": "unknown", "x": 0},
                {"label": "s.", "style": "pos-roman", "x": 2},
            ]
        }
        self.assertEqual(_style_sequence(row), ("pos-roman",))


if __name__ == "__main__":
    unittest.main()
