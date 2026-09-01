from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swedish_wordlist_tools.ocr_glyph_review_delete import (
    apply_edit_with_delete,
    delete_exact_model,
    render_html_with_delete,
)


class GlyphReviewDeleteTests(unittest.TestCase):
    def test_delete_exact_model_removes_only_exact_label_style_and_raster(self) -> None:
        payload = {
            "glyphs": [
                {"label": "az", "style": "roman", "pixels_relative_to_baseline": [[0, -1], [1, 0]]},
                {"label": "az", "style": "italic", "pixels_relative_to_baseline": [[0, -1], [1, 0]]},
                {"label": "a", "style": "roman", "pixels_relative_to_baseline": [[0, -1], [1, 0]]},
            ]
        }
        self.assertEqual(
            delete_exact_model(
                payload,
                label="az",
                style="roman",
                pixels_relative_to_baseline=[[0, -1], [1, 0]],
            ),
            1,
        )
        self.assertEqual([(g["label"], g["style"]) for g in payload["glyphs"]], [("az", "italic"), ("a", "roman")])

    def test_delete_rejects_duplicate_exact_models(self) -> None:
        payload = {"glyphs": [
            {"label": "az", "style": "roman", "pixels_relative_to_baseline": [[0, 0]]},
            {"label": "az", "style": "roman", "pixels_relative_to_baseline": [[0, 0]]},
        ]}
        with self.assertRaisesRegex(ValueError, "exactly one"):
            delete_exact_model(payload, label="az", style="roman", pixels_relative_to_baseline=[[0, 0]])

    def test_non_delete_delegates_to_captured_original_edit_handler(self) -> None:
        calls = []

        def original(state, facit, form):
            calls.append((state, facit, form))
            return "saved-add"

        state = {"sentinel": True}
        facit = Path("facit.json")
        form = {"action": ["add"], "label": ["a"]}
        self.assertEqual(apply_edit_with_delete(original, state, facit, form), "saved-add")
        self.assertEqual(calls, [(state, facit, form)])

    def test_apply_delete_does_not_require_label_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facit = Path(tmp) / "facit.json"
            facit.write_text(json.dumps({
                "glyphs": [{
                    "label": "az",
                    "style": "roman",
                    "pixels_relative_to_baseline": [[0, -1], [1, 0]],
                    "sources": [],
                }]
            }), encoding="utf-8")
            match = SimpleNamespace(
                label="az",
                style="roman",
                baseline=5,
                pixels=frozenset({(10, 4), (11, 5)}),
            )
            state = {"matches": [match], "source_ink_points": [[10, 4], [11, 5]]}
            original = lambda *_args: self.fail("delete must not call original edit handler")
            message = apply_edit_with_delete(
                original,
                state,
                facit,
                {"action": ["delete"], "selected": ["M00"], "selected_pixels": [""]},
            )
            self.assertIn("raderad glyphmodell", message)
            self.assertEqual(json.loads(facit.read_text(encoding="utf-8"))["glyphs"], [])

    def test_html_delete_button_bypasses_required_label(self) -> None:
        html = render_html_with_delete(
            lambda _state, _message: (
                '<form><input name="label" required>'
                '<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>'
                '</form>'
            ),
            {},
        )
        self.assertIn('value="delete"', html)
        self.assertIn("formnovalidate", html)
        self.assertIn("Radera vald glyphmodell", html)


if __name__ == "__main__":
    unittest.main()
