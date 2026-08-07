from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_branch_base_impact import analyze


class AnalyzeNounBranchBaseImpactTests(unittest.TestCase):
    def test_simulates_bankvasen_with_alternative_ord_base(self) -> None:
        records = [
            {
                "normaliserat_ord": "bankväsen",
                "homonr": "1",
                "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen",
                "ord": "bank|väsen",
                "upos": "NOUN",
            },
            {
                "normaliserat_ord": "bankväsen",
                "homonr": "0",
                "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen",
                "ord": "bank|väsende",
                "upos": "NOUN",
            },
        ]
        current = [
            {
                "record_id": "5598",
                "lemma": "bankväsen",
                "forms": [
                    {"written_form": value}
                    for value in (
                        "bankväsen",
                        "bankväsens",
                        "bankväsendet",
                        "bankväsendets",
                        "bankväsendena",
                        "bankväsendenas",
                        "bankväsent",
                        "bankväsents",
                        "bankväsenn",
                        "bankväsenns",
                    )
                ],
            }
        ]

        summary = analyze(records, current)
        self.assertEqual(1, summary["candidate_groups"])
        change = summary["changes"][0]
        self.assertIn("bankväsende", change["added"])
        self.assertIn("bankväsenden", change["added"])
        self.assertIn("bankväsendes", change["added"])
        self.assertIn("bankväsendens", change["added"])
        self.assertIn("bankväsent", change["removed"])
        self.assertIn("bankväsenn", change["removed"])

    def test_ignores_other_alternative_notations(self) -> None:
        records = [
            {
                "normaliserat_ord": "behå",
                "subnr": 1,
                "text": "+n +ar _ bh:n bh:ar",
                "ord": "behå",
                "upos": "NOUN",
            },
            {
                "normaliserat_ord": "behå",
                "subnr": 1,
                "text": "+n +ar _ bh:n bh:ar",
                "ord": "bh",
                "upos": "NOUN",
            },
        ]
        summary = analyze(records, [])
        self.assertEqual(0, summary["candidate_groups"])


if __name__ == "__main__":
    unittest.main()
