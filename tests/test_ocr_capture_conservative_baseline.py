from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swedish_wordlist_tools.ocr_capture_conservative_baseline import (
    _row_record,
    _sha256_store,
)


class CaptureConservativeBaselineTest(unittest.TestCase):
    def test_row_record_is_deterministic_and_contains_match_raster_identity(self):
        match = SimpleNamespace(
            label="a",
            style="headword-bold",
            x=7,
            baseline=11,
            pixels={(7, 10), (8, 11)},
            model_pixels=2,
            sources=3,
        )
        work = SimpleNamespace(
            covered_pixels=2,
            source_pixels=3,
            fully_exact=False,
            unreviewed_matches=0,
            needs_work=True,
        )
        state = {
            "crop_box": (10, 20, 100, 40),
            "baseline": 11,
            "text": "a",
            "matches": [match],
        }

        first = _row_record(39, (2, 2), state, work)
        second = _row_record(39, (2, 2), state, work)

        self.assertEqual(first, second)
        self.assertEqual(first["page"], 39)
        self.assertEqual(first["crop_box"], [10, 20, 100, 40])
        self.assertEqual(first["covered_pixels"], 2)
        self.assertTrue(first["needs_work"])
        self.assertEqual(first["matches"][0]["label"], "a")
        self.assertEqual(len(first["matches"][0]["raster_sha256"]), 64)

    def test_split_store_hash_depends_on_relative_paths_and_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "u0061").mkdir()
            (root / "u0061" / "g000001.json").write_text("{\"label\":\"a\"}\n", encoding="utf-8")
            first = _sha256_store(root)
            second = _sha256_store(root)
            self.assertEqual(first, second)

            (root / "u0061" / "g000001.json").write_text("{\"label\":\"b\"}\n", encoding="utf-8")
            self.assertNotEqual(first, _sha256_store(root))


if __name__ == "__main__":
    unittest.main()
