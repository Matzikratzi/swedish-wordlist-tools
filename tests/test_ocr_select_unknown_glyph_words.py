from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_select_unknown_glyph_words import select


class SelectUnknownGlyphWordsTest(unittest.TestCase):
    def test_requires_exactly_one_unknown_and_two_occurrences(self):
        known = set("abc")
        rows = [
            {"lemma": "aBc", "record_id": "1", "source": "https://x/SAOL14_00010.png"},
            {"lemma": "Bac", "record_id": "2", "source": "https://x/SAOL14_00020.png"},
            {"lemma": "aDc", "record_id": "3", "source": "https://x/SAOL14_00030.png"},
            {"lemma": "BEc", "record_id": "4", "source": "https://x/SAOL14_00040.png"},
            {"lemma": "abc", "record_id": "5", "source": "https://x/SAOL14_00050.png"},
        ]
        report = select(rows, known, per_label=6, max_labels=30)
        self.assertEqual(report["eligible_labels"], 1)
        self.assertEqual(report["selected_words"], 2)
        group = report["groups"][0]
        self.assertEqual(group["label"], "B")
        self.assertEqual([r["expected_word"] for r in group["selected"]], ["aBc", "Bac"])
        self.assertEqual([r["harvest_half"] for r in group["selected"]], ["discover", "verify"])
        self.assertEqual([r["page"] for r in group["selected"]], [10, 20])

    def test_stycke_is_preferred_over_lemma(self):
        known = set("abc·")
        rows = [
            {"stycke": "a·Bc", "lemma": "abc", "record_id": "1"},
            {"stycke": "Bac", "lemma": "abc", "record_id": "2"},
        ]
        report = select(rows, known)
        self.assertEqual(report["eligible_labels"], 1)
        self.assertEqual(report["groups"][0]["label"], "B")


if __name__ == "__main__":
    unittest.main()
