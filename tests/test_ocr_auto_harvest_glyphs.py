from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swedish_wordlist_tools import ocr_auto_harvest_glyphs as harvest


class AutoHarvestGlyphsTest(unittest.TestCase):
    def _facit(self, root: Path) -> Path:
        path = root / "facit.json"
        path.write_text(
            json.dumps(
                {
                    "format": "saol14-manual-glyph-facit-v1",
                    "coordinate_system": "glyph x normalized to leftmost ink; y relative to support baseline",
                    "policy": "manual only",
                    "glyphs": [
                        {
                            "label": "a",
                            "style": "bold",
                            "pixels_relative_to_baseline": [[0, 0]],
                            "sources": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_requires_independent_discovery_and_verification_occurrences(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            facit = self._facit(root)
            p1, p2 = root / "one.json", root / "two.json"
            p1.write_text("{}", encoding="utf-8")
            p2.write_text("{}", encoding="utf-8")

            candidates = {
                p1: {
                    "label": "z",
                    "style": "bold",
                    "pixels_relative_to_baseline": [[0, -1], [0, 0]],
                    "source": {"expected_word": "az", "harvest_half": "discover"},
                },
                p2: {
                    "label": "z",
                    "style": "bold",
                    "pixels_relative_to_baseline": [[0, -1], [1, 0]],
                    "source": {"expected_word": "za", "harvest_half": "verify"},
                },
            }

            with patch.object(harvest, "_candidate_from_debug", side_effect=lambda p, _m, _k: candidates[p]):
                provisional, report = harvest.harvest([p1, p2], facit)

            self.assertEqual(report["cross_validated_label_style_groups"], 1)
            self.assertEqual(report["provisional_shapes_added"], 2)
            zrows = [g for g in provisional["glyphs"] if g["label"] == "z"]
            self.assertEqual(len(zrows), 2)
            self.assertTrue(all(g.get("provisional") for g in zrows))
            halves = {s["harvest_half"] for g in zrows for s in g["sources"]}
            self.assertEqual(halves, {"discover", "verify"})

    def test_one_half_alone_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            facit = self._facit(root)
            p1 = root / "one.json"
            p1.write_text("{}", encoding="utf-8")
            candidate = {
                "label": "z",
                "style": "bold",
                "pixels_relative_to_baseline": [[0, 0]],
                "source": {"expected_word": "az", "harvest_half": "discover"},
            }
            with patch.object(harvest, "_candidate_from_debug", return_value=candidate):
                provisional, report = harvest.harvest([p1], facit)

            self.assertEqual(report["cross_validated_label_style_groups"], 0)
            self.assertEqual(report["provisional_shapes_added"], 0)
            self.assertFalse(any(g["label"] == "z" for g in provisional["glyphs"]))


if __name__ == "__main__":
    unittest.main()
