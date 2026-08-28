from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_editable_unknown_glyph_review import build_html


class EditableUnknownGlyphReviewTests(unittest.TestCase):
    def test_prefills_jsonl_suggestion_and_exposes_component_safe_editor(self) -> None:
        row = {
            "expected": "x:y",
            "page": 1,
            "subnr": "synthetic",
            "width": 7,
            "height": 9,
            "baseline": 6,
            "ink": [[1, 2], [1, 5], [3, 6]],
            "exact": [{"label": "x", "style": "roman", "pixels": [[3, 6]]}],
            "unexplained": [[1, 2], [1, 5]],
            "jsonl_hint": {"text": ":x", "similarity": 1.0},
            "page_word_bbox": [10, 20, 7, 9],
            "source": {"source_id": "synthetic"},
        }
        with tempfile.TemporaryDirectory() as td:
            facit = Path(td) / "facit.json"
            facit.write_text(json.dumps({"glyphs": []}), encoding="utf-8")
            html = build_html([row], facit)

        self.assertIn("JSONL-förslag", html)
        self.assertIn("Sammanhängande svarta komponenter är odelbara", html)
        self.assertIn("En glyph får bestå av flera komponenter", html)
        self.assertIn("Ctrl+Shift/Ctrl+Alt", html)
        self.assertIn("componentsOf", html)
        self.assertIn("toggleComponentAt", html)
        self.assertIn("Godkänn markering", html)
        self.assertIn("Återställ gissning", html)
        self.assertIn("Rastertext", html)


if __name__ == "__main__":
    unittest.main()
