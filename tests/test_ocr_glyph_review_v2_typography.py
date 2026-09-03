from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swedish_wordlist_tools.ocr_glyph_review_delete import (
    apply_edit_with_delete,
    load_facit_with_typography,
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

    def test_v2_loader_preserves_role_and_typography(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            facit = Path(tmpdir) / "facit.json"
            facit.write_text(json.dumps(self._facit_payload()), encoding="utf-8")
            models = load_facit_with_typography(facit)

        self.assertEqual("unknown", models[0].style)
        self.assertEqual("italic", models[0].style.typographic_style)

    def test_render_uses_typography_not_v2_role(self):
        role = Role("unknown")
        role.typographic_style = "bold"
        match = SimpleNamespace(style=role)
        state = {
            "matches": [match],
            "items": [
                {"id": "M00", "kind": "match", "label": "a", "style": "unknown", "pixels": 3}
            ],
        }

        def original_render(render_state, _message=""):
            item = render_state["items"][0]
            return (
                '<html><body><div id="items">'
                f'<button class="chip {item["style"]}" data-id="M00">a</button>'
                '</div><form id="form"><input id="selected"><input id="selectedPixels">'
                '<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>'
                '</form><script>const S={items:[]};</script></body></html>'
            )

        html = render_html_with_delete(original_render, state)
        self.assertEqual("bold", state["items"][0]["style"])
        self.assertEqual("unknown", state["items"][0]["role"])
        self.assertIn('chip bold', html)

    def test_v2_relabel_changes_typography_but_preserves_role(self):
        payload = self._facit_payload()
        role = Role("unknown")
        role.typographic_style = "italic"
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
        self.assertIn("italic", message)
        self.assertIn("bold", message)


if __name__ == "__main__":
    unittest.main()
