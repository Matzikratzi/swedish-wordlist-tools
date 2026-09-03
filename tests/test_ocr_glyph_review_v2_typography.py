from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swedish_wordlist_tools.ocr_glyph_review_delete import (
    apply_edit_with_delete,
    load_facit_with_typography,
    mark_matches_reviewed,
    render_html_with_delete,
)


class Role(str):
    pass


class GlyphReviewV2TypographyTest(unittest.TestCase):
    def _facit_payload(self):
        return {
            "format": "saol14-manual-glyph-facit-v2",
            "glyphs": [
                {
                    "label": "a",
                    "role": "unknown",
                    "style": "italic",
                    "pixels_relative_to_baseline": [[0, -1], [0, 0], [1, -1]],
                    "sources": [],
                }
            ],
        }

    def _render_shell(self):
        return '''<html><head><style></style></head><body>
<div id="items"></div>
<form id="form">
<input id="selected"><input id="selectedPixels"><input id="label">
<select name="style"><option>roman</option><option>italic</option><option>bold</option></select>
<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>
</form>
<script>
for(const it of S.items){
 const b=document.createElement('button'); b.type='button'; b.dataset.id=it.id; b.className='chip '+it.kind+' '+it.style;
 b.onclick=()=>toggle(it.id); document.getElementById('items').appendChild(b);
}
</script></body></html>'''

    def test_v2_loader_preserves_role_typography_and_review_state(self):
        payload = self._facit_payload()
        payload["glyphs"][0]["reviewed"] = True
        with tempfile.TemporaryDirectory() as tmpdir:
            facit = Path(tmpdir) / "facit.json"
            facit.write_text(json.dumps(payload), encoding="utf-8")
            models = load_facit_with_typography(facit)

        self.assertEqual("unknown", models[0].style)
        self.assertEqual("italic", models[0].style.typographic_style)
        self.assertTrue(models[0].style.reviewed)

    def test_unreviewed_match_gets_orange_underline_and_prefill(self):
        role = Role("unknown")
        role.typographic_style = "bold"
        role.reviewed = False
        match = SimpleNamespace(style=role)
        state = {
            "matches": [match],
            "items": [
                {"id": "M00", "kind": "match", "label": "a", "style": "unknown", "pixels": 3}
            ],
        }

        html = render_html_with_delete(lambda *_args: self._render_shell(), state)
        self.assertEqual("bold", state["items"][0]["style"])
        self.assertEqual("unknown", state["items"][0]["role"])
        self.assertFalse(state["items"][0]["reviewed"])
        self.assertIn("needs-review", html)
        self.assertIn("text-decoration-color:#e58a00", html)
        self.assertIn("document.getElementById('label').value=it.label", html)
        self.assertIn("styleSelect.value=it.style", html)

    def test_v2_relabel_changes_typography_preserves_role_and_approves(self):
        payload = self._facit_payload()
        role = Role("unknown")
        role.typographic_style = "italic"
        role.reviewed = False
        match = SimpleNamespace(
            label="a",
            style=role,
            pixels={(3, 7), (4, 7), (3, 8)},
            baseline=8,
        )
        state = {"matches": [match]}

        with tempfile.TemporaryDirectory() as tmpdir:
            facit = Path(tmpdir) / "facit.json"
            facit.write_text(json.dumps(payload), encoding="utf-8")
            message = apply_edit_with_delete(
                lambda *_args, **_kwargs: self.fail("v2 relabel must not delegate"),
                state,
                facit,
                {
                    "action": ["relabel"],
                    "selected": ["M00"],
                    "selected_pixels": [""],
                    "label": ["a"],
                    "style": ["bold"],
                },
            )
            saved = json.loads(facit.read_text(encoding="utf-8"))

        self.assertEqual("unknown", saved["glyphs"][0]["role"])
        self.assertEqual("bold", saved["glyphs"][0]["style"])
        self.assertTrue(saved["glyphs"][0]["reviewed"])
        self.assertIn("italic", message)
        self.assertIn("bold", message)

    def test_mark_matches_reviewed_can_reset_everything_else(self):
        payload = self._facit_payload()
        payload["glyphs"].append({
            "label": "b",
            "role": "unknown",
            "style": "roman",
            "reviewed": True,
            "pixels_relative_to_baseline": [[0, 0]],
            "sources": [],
        })
        role = Role("unknown")
        role.typographic_style = "italic"
        role.reviewed = False
        match = SimpleNamespace(
            label="a",
            style=role,
            pixels={(3, 7), (4, 7), (3, 8)},
            baseline=8,
        )

        changed = mark_matches_reviewed(payload, [match], reset=True)

        self.assertEqual(1, changed)
        self.assertTrue(payload["glyphs"][0]["reviewed"])
        self.assertFalse(payload["glyphs"][1]["reviewed"])


if __name__ == "__main__":
    unittest.main()
