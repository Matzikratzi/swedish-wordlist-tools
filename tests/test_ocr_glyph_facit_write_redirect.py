from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_glyph_facit_store import (
    label_directory,
    load_split_facit,
)
from swedish_wordlist_tools.ocr_glyph_facit_write_redirect import install_facit_write_redirect


class GlyphFacitWriteRedirectTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "format": "saol14-manual-glyph-facit-v2",
            "coordinate_system": "test",
            "glyphs": [
                {
                    "label": "a",
                    "role": "unknown",
                    "style": "roman",
                    "pixels_relative_to_baseline": [[0, 0]],
                    "sources": [],
                    "reviewed": True,
                }
            ],
        }

    def test_editor_aggregate_write_persists_split_first_and_rebuilds_mirror(self) -> None:
        install_facit_write_redirect()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facit = root / "saol14-manual-glyph-facit-v2.json"
            store = root / "facit-v2"

            facit.write_text(
                json.dumps(self._payload(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            aggregate = json.loads(facit.read_text(encoding="utf-8"))
            self.assertEqual(aggregate, load_split_facit(store))
            model_id = aggregate["glyphs"][0]["model_id"]
            self.assertTrue((store / label_directory("a") / f"{model_id}.json").exists())

            aggregate["glyphs"][0]["label"] = "b"
            facit.write_text(
                json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            rebuilt = json.loads(facit.read_text(encoding="utf-8"))
            self.assertEqual(rebuilt, load_split_facit(store))
            self.assertFalse((store / label_directory("a") / f"{model_id}.json").exists())
            self.assertTrue((store / label_directory("b") / f"{model_id}.json").exists())
            self.assertEqual(rebuilt["glyphs"][0]["model_id"], model_id)

    def test_other_json_files_are_not_redirected(self) -> None:
        install_facit_write_redirect()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "other.json"
            other.write_text('{"x": 1}\n', encoding="utf-8")
            self.assertEqual(other.read_text(encoding="utf-8"), '{"x": 1}\n')
            self.assertFalse((root / "facit-v2").exists())


if __name__ == "__main__":
    unittest.main()
