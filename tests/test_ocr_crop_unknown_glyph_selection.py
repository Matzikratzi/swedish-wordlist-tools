from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_crop_unknown_glyph_selection import match_selection


class CropUnknownGlyphSelectionTest(unittest.TestCase):
    def test_matches_exact_page_subnr_word_and_unique_page_word_fallback(self):
        selection = {
            "words": [
                {"page": 10, "subnr": "1", "expected_word": "abbé"},
                {"page": 20, "subnr": "missing", "expected_word": "allé"},
                {"page": 30, "subnr": "x", "expected_word": "señor"},
            ]
        }
        manifest = {
            "template_sources": {
                "a": {"page": 10, "subnr": "1", "expected_word": "abbé", "page_word_bbox": [1, 2, 3, 4]},
                "b": {"page": 20, "subnr": "2", "expected_word": "allé", "page_word_bbox": [1, 2, 3, 4]},
            }
        }
        matched, missing = match_selection(selection, manifest)
        self.assertEqual([s["expected_word"] for s, _ in matched], ["abbé", "allé"])
        self.assertEqual([s["expected_word"] for s in missing], ["señor"])


if __name__ == "__main__":
    unittest.main()
