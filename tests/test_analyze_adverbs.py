from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adverbs import analyze


class AnalyzeAdverbsTests(unittest.TestCase):
    def test_groups_adverb_notation_and_variants(self) -> None:
        records = [
            {"normaliserat_ord":"länge","ord":"länge","upos":"ADV","ordkl":"adv.","text":"längre längst"},
            {"normaliserat_ord":"ner","ord":"ned","upos":"ADV","ordkl":"adv.","text":None},
            {"normaliserat_ord":"katt","ord":"katt","upos":"NOUN","ordkl":"s.","text":"+en"},
        ]
        report = analyze(records)
        self.assertEqual(2, report["records"])
        self.assertEqual(1, report["empty_text"])
        self.assertEqual(1, report["variant_rows"])
        self.assertEqual(2, report["unique_notations"])


if __name__ == "__main__":
    unittest.main()
