from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_homonr_groups import analyze


class AnalyzeNounHomonrGroupsTests(unittest.TestCase):
    def test_detects_clean_homonr_zero_variant(self) -> None:
        rows = [
            {
                "normaliserat_ord": "abrovink",
                "homonr": "1",
                "upos": "NOUN",
                "urspr_lopnr": 436193,
                "subnr": 436193,
                "text": "+en +er",
                "stycke": "abro·vink",
                "ord": "abro·vink",
            },
            {
                "normaliserat_ord": "abrovink",
                "homonr": "0",
                "upos": "NOUN",
                "urspr_lopnr": 436193,
                "subnr": 436193,
                "text": "+en +er",
                "stycke": "abro·vink",
                "ord": "abro·vinsch",
            },
        ]
        summary = analyze(rows)
        self.assertEqual(1, summary["multirow_article_groups"])
        self.assertEqual(1, summary["homonr_0_1_groups"])
        self.assertEqual(1, summary["clean_variant_0_1_groups"])
        self.assertEqual(0, summary["clean_variant_0_1_groups_with_underscore"])
        self.assertEqual(["abrovink", "abrovinsch"], summary["clean_variant_groups"][0]["ord_variants"])

    def test_detects_bankvasen_as_underscore_variant_group(self) -> None:
        rows = [
            {
                "normaliserat_ord": "bankväsen", "homonr": "1", "upos": "NOUN",
                "urspr_lopnr": 5598, "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen", "ord": "bank|väsen",
            },
            {
                "normaliserat_ord": "bankväsen", "homonr": "0", "upos": "NOUN",
                "urspr_lopnr": 5598, "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen", "ord": "bank|väsende",
            },
        ]
        summary = analyze(rows)
        self.assertEqual(1, summary["clean_variant_0_1_groups_with_underscore"])


if __name__ == "__main__":
    unittest.main()
