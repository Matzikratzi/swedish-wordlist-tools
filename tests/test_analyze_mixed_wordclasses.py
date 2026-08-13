from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_mixed_wordclasses import analyze, classes_from_head


class AnalyzeMixedWordclassesTests(unittest.TestCase):
    def test_adv_and_adj_are_both_detected(self) -> None:
        self.assertEqual(("ADJ", "ADV"), classes_from_head("adv. och adj."))

    def test_single_class_is_not_reported_as_mixed(self) -> None:
        report = analyze([
            {"ord":"ofta","normaliserat_ord":"ofta","ordkl":"adv.","text":None,"upos":"ADV"},
            {"ord":"delvis","normaliserat_ord":"delvis","ordkl":"adv. och adj. <i>+t +a</i>","text":"+t +a","upos":"ADV"},
        ])
        self.assertEqual(1, report["mixed_records"])
        self.assertEqual(1, report["combination_counts"]["ADJ+ADV"])


if __name__ == "__main__":
    unittest.main()
