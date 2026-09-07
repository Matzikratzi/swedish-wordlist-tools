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


class GlyphReviewDeleteTest(unittest.TestCase):
    def test_render_adds_shared_delete_button_without_per_glyph_crosses(self):
        state = {
            "items": [
                {"id": "M00", "kind": "match", "label": "o", "pixels": 55},
                {"id": "U00", "kind": "residual", "label": "?", "pixels": 14},
            ]
        }

        def original_render(_state, _message=""):
            return '''<html><head><style></style></head><body>
<div id="items"></div>
<form method="post" id="form">
<input type="hidden" name="selected" id="selected">
<input type="hidden" name="selected_pixels" id="selectedPixels">
<input name="label" id="label"><select name="style"><option>roman</option></select>
<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>
</form>
<script>
for(const it of S.items){
 const b=document.createElement('button'); b.type='button'; b.dataset.id=it.id; b.className='chip '+it.kind+' '+it.style;
 b.onclick=()=>toggle(it.id); document.getElementById('items').appendChild(b);
}
</script></body></html>'''

        html = render_html_with_delete(original_render, state)
        self.assertIn('value="delete"', html)
        self.assertIn("Radera vald glyphmodell", html)
        self.assertNotIn("glyph-chip-delete", html)
        self.assertNotIn("glyph-chip-wrap", html)
        self.assertNotIn("del.textContent='×'", html)

    def _delete_one(self, payload):
        points = {(3, 7), (4, 7), (3, 8)}
        baseline = 8
        match = SimpleNamespace(label="o", style="unknown", pixels=points, baseline=baseline)
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

    def test_shared_delete_form_removes_exact_v1_model(self):
        self._delete_one({
            "format": "saol14-manual-glyph-facit-v1",
            "glyphs": [{
                "label": "o",
                "style": "unknown",
                "pixels_relative_to_baseline": [[0, -1], [0, 0], [1, -1]],
                "sources": [],
            }],
        })

    def test_shared_delete_form_removes_exact_v2_model_by_role(self):
        self._delete_one({
            "format": "saol14-manual-glyph-facit-v2",
            "glyphs": [{
                "label": "o",
                "role": "unknown",
                "pixels_relative_to_baseline": [[0, -1], [0, 0], [1, -1]],
                "sources": [],
            }],
        })


if __name__ == "__main__":
    unittest.main()
