from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_ord_variants import analyze_records


class AnalyzeNounOrdVariantsTests(unittest.TestCase):
    def test_finds_alternative_branch_bases_across_sibling_rows(self) -> None:
        rows = [
            {
                "subnr": 5598,
                "normaliserat_ord": "bankväsen",
                "homonr": "1",
                "upos": "NOUN",
                "ordkl": "s.",
                "stycke": "bank|väsen",
                "ord": "bank|väsen",
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
            },
            {
                "subnr": 5598,
                "normaliserat_ord": "bankväsen",
                "homonr": "0",
                "upos": "NOUN",
                "ordkl": "s.",
                "stycke": "bank|väsen",
                "ord": "bank|väsende",
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
            },
        ]
        summary = analyze_records(rows)
        self.assertEqual(1, summary["candidate_record_groups"])
        self.assertEqual(2, summary["candidate_rows"])
        candidate = summary["candidates"][0]
        self.assertEqual(["bankväsen", "bankväsende"], candidate["ord_variants"])

    def test_does_not_flag_single_ord_spelling(self) -> None:
        rows = [
            {
                "subnr": 1,
                "normaliserat_ord": "bandage",
                "homonr": "1",
                "upos": "NOUN",
                "ordkl": "s.",
                "stycke": "band·age",
                "ord": "band·age",
                "text": "+t [-et]; pl. +",
            }
        ]
        summary = analyze_records(rows)
        self.assertEqual(0, summary["candidate_record_groups"])


if __name__ == "__main__":
    unittest.main()
