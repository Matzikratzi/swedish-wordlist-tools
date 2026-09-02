from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import Match
from swedish_wordlist_tools.ocr_page_glyph_audit import cluster_records, is_cluster_label


class PageGlyphAuditTest(unittest.TestCase):
    def test_single_character_labels_are_not_clusters(self):
        self.assertFalse(is_cluster_label("a"))
        self.assertFalse(is_cluster_label("·"))
        self.assertFalse(is_cluster_label("¹"))

    def test_multi_character_labels_are_clusters(self):
        self.assertTrue(is_cluster_label("tt"))
        self.assertTrue(is_cluster_label("rn"))
        self.assertTrue(is_cluster_label("el."))

    def test_cluster_records_only_returns_multi_character_matches(self):
        state = {
            "matches": [
                Match("a", "roman", 2, 8, frozenset({(2, 7), (2, 8)}), 2, 3),
                Match("tt", "roman", 7, 8, frozenset({(7, 6), (8, 6), (7, 8), (8, 8)}), 4, 1),
            ]
        }
        records = cluster_records(state)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["label"], "tt")
        self.assertEqual(records[0]["x0"], 7)
        self.assertEqual(records[0]["x1"], 8)
        self.assertEqual(records[0]["pixels"], 4)
        self.assertEqual(records[0]["sources"], 1)


if __name__ == "__main__":
    unittest.main()
