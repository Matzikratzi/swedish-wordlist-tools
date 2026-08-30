from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_editable_unknown_glyph_review import build_html
from swedish_wordlist_tools.ocr_unique_unknown_glyph_review import collect_candidates


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

    def test_unknown_component_touching_crop_edge_is_not_reviewable(self) -> None:
        row = {
            "expected": "n",
            "page": 1,
            "subnr": "edge",
            "width": 10,
            "height": 100,
            "baseline": 53,
            "ink": [[0, 51], [4, 50], [5, 51], [6, 52]],
            "exact": [{"label": "n", "style": "unknown", "pixels": [[4, 50], [5, 51], [6, 52]]}],
            "unexplained": [[0, 51]],
            "jsonl_hint": {"text": "+n", "similarity": 1.0},
            "source": {"source_id": "edge"},
        }

        self.assertEqual(collect_candidates([row]), [])

    def test_review_context_is_trimmed_vertically_around_actual_ink(self) -> None:
        row = {
            "expected": "a",
            "page": 1,
            "subnr": "trim",
            "width": 12,
            "height": 100,
            "baseline": 53,
            "ink": [[2, 47], [5, 50], [6, 51], [7, 53], [8, 54]],
            "exact": [{"label": "a", "style": "unknown", "pixels": [[5, 50], [6, 51], [7, 53], [8, 54]]}],
            "unexplained": [[2, 47]],
            "jsonl_hint": {"text": "a", "similarity": 1.0},
            "source": {"source_id": "trim"},
        }

        candidates = collect_candidates([row])
        self.assertEqual(len(candidates), 1)
        context = candidates[0]["context"]
        self.assertEqual(context["review_y_offset"], 45)
        self.assertEqual(context["height"], 12)
        self.assertEqual(context["baseline"], 8)
        self.assertEqual(context["original_height"], 100)
        self.assertEqual(context["candidate_pixels"], [[2, 2]])


if __name__ == "__main__":
    unittest.main()
