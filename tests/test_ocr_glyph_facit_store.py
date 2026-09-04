from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_glyph_facit_store import (
    build_facit,
    ensure_model_ids,
    label_directory,
    load_split_facit,
    split_facit,
    verify_facit,
)


class GlyphFacitStoreTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "format": "saol14-manual-glyph-facit-v2",
            "coordinate_system": "test",
            "roles": {"definition-roman": "test role"},
            "glyphs": [
                {"label": "a", "role": "definition-roman", "style": "roman", "pixels_relative_to_baseline": [[0, 0]], "reviewed": True},
                {"label": "ŋ", "role": "definition-roman", "style": "roman", "pixels_relative_to_baseline": [[0, -1], [1, 0]], "reviewed": False},
            ],
        }

    def test_label_directory_is_unicode_safe(self) -> None:
        self.assertEqual(label_directory("a"), "u0061")
        self.assertEqual(label_directory("ŋ"), "u014b")
        self.assertEqual(label_directory("."), "u002e")
        self.assertEqual(label_directory("rn"), "u0072-u006e")

    def test_split_assigns_stable_ids_and_rebuilds_exact_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facit = root / "facit.json"
            store = root / "facit-v2"
            facit.write_text(json.dumps(self._payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            count, assigned = split_facit(facit, store)
            self.assertEqual((count, assigned), (2, 2))
            saved = json.loads(facit.read_text(encoding="utf-8"))
            self.assertEqual([g["model_id"] for g in saved["glyphs"]], ["g000001", "g000002"])
            self.assertTrue((store / "u0061" / "g000001.json").exists())
            self.assertTrue((store / "u014b" / "g000002.json").exists())
            self.assertEqual(load_split_facit(store), saved)
            self.assertEqual(verify_facit(facit, store)[0], True)

            rebuilt = root / "rebuilt.json"
            self.assertEqual(build_facit(store, rebuilt), 2)
            self.assertEqual(json.loads(rebuilt.read_text(encoding="utf-8")), saved)

    def test_repeated_split_preserves_existing_ids_and_adds_only_next_id(self) -> None:
        payload = self._payload()
        self.assertEqual(ensure_model_ids(payload), 2)
        ids = [glyph["model_id"] for glyph in payload["glyphs"]]
        self.assertEqual(ensure_model_ids(payload), 0)
        self.assertEqual([glyph["model_id"] for glyph in payload["glyphs"]], ids)
        payload["glyphs"].append({"label": ".", "pixels_relative_to_baseline": [[0, 0]]})
        self.assertEqual(ensure_model_ids(payload), 1)
        self.assertEqual(payload["glyphs"][-1]["model_id"], "g000003")

    def test_split_removes_stale_model_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facit = root / "facit.json"
            store = root / "facit-v2"
            facit.write_text(json.dumps(self._payload(), ensure_ascii=False), encoding="utf-8")
            split_facit(facit, store)
            payload = json.loads(facit.read_text(encoding="utf-8"))
            removed = payload["glyphs"].pop()
            facit.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            split_facit(facit, store)
            self.assertFalse((store / label_directory(removed["label"]) / f"{removed['model_id']}.json").exists())

    def test_duplicate_model_id_is_rejected(self) -> None:
        payload = self._payload()
        payload["glyphs"][0]["model_id"] = "g000007"
        payload["glyphs"][1]["model_id"] = "g000007"
        with self.assertRaisesRegex(ValueError, "duplicate model_id"):
            ensure_model_ids(payload)


if __name__ == "__main__":
    unittest.main()
