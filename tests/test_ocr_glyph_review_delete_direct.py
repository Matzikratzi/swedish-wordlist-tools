from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swedish_wordlist_tools.ocr_glyph_review_delete import (
    apply_edit_with_delete,
    render_html_with_delete,
)


class GlyphReviewDirectDeleteTest(unittest.TestCase):
    def test_render_adds_direct_delete_button_for_each_match(self):
        state = {
            "items": [
                {"id": "M00", "kind": "match", "label": "o", "pixels": 55},
                {"id": "U00", "kind": "residual", "label": "?", "pixels": 14},
            ]
        }

        def original_render(_state, _message=""):
            return '''<html><body>
<div id="items"><button type="button" class="chip match unknown" data-id="M00">o</button></div>
<form method="post" id="form">
<input type="hidden" name="selected" id="selected">
<input type="hidden" name="selected_pixels" id="selectedPixels">
<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>
</form>
<script>const S={items:[{id:'M00',kind:'match',label:'o',pixels:55},{id:'U00',kind:'residual',label:'?',pixels:14}]};</script>
</body></html>'''

        html = render_html_with_delete(original_render, state)
        self.assertIn('value="delete"', html)
        self.assertIn("glyph-chip-delete", html)
        self.assertIn("selected.value=it.id", html)
        self.assertIn("form.requestSubmit(deleteSubmit)", html)
        self.assertIn("if(it.kind!=='match') continue", html)

    def test_direct_delete_form_removes_exact_model(self):
        points = {(3, 7), (4, 7), (3, 8)}
        baseline = 8
        normalized = [[0, -1], [0, 0], [1, -1]]
        match = SimpleNamespace(label="o", style="unknown", pixels=points, baseline=baseline)
        payload = {
            "glyphs": [
                {
                    "label": "o",
                    "style": "unknown",
                    "pixels_relative_to_baseline": normalized,
                    "sources": [],
                }
            ]
        }
        state = {"matches": [match]}

        with tempfile.TemporaryDirectory() as tmpdir:
            facit = Path(tmpdir) / "facit.json"
            facit.write_text(json.dumps(payload), encoding="utf-8")
            message = apply_edit_with_delete(
                lambda *_args, **_kwargs: self.fail("delete must not delegate"),
                state,
                facit,
                {"action": ["delete"], "selected": ["M00"], "selected_pixels": [""]},
            )
            saved = json.loads(facit.read_text(encoding="utf-8"))

        self.assertEqual([], saved["glyphs"])
        self.assertIn("raderad glyphmodell", message)


if __name__ == "__main__":
    unittest.main()
