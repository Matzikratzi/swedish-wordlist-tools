from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_variant_saldo_alignment import analyze


class AnalyzeNounVariantSaldoAlignmentTests(unittest.TestCase):
    def test_matches_each_article_variant_to_its_own_saldo_lemma(self) -> None:
        noun_rows = [
            {
                "record_id": "5598",
                "homonym_number": "1",
                "lemma": "bankväsen",
                "variant_mode": "parallel_branches",
                "variant_paradigms": [
                    {
                        "lemma": "bankväsen",
                        "notation": "+det; pl. +, best. pl. +dena",
                        "forms": [
                            {"written_form": "bankväsen"},
                            {"written_form": "bankväsendet"},
                            {"written_form": "bankväsendena"},
                        ],
                    },
                    {
                        "lemma": "bankväsende",
                        "notation": "+t +n",
                        "forms": [
                            {"written_form": "bankväsende"},
                            {"written_form": "bankväsendet"},
                            {"written_form": "bankväsenden"},
                        ],
                    },
                ],
            }
        ]
        saldo = {
            "bankväsen": [
                {"id": "b1", "lemmas": ["bankväsen"], "upos": "NOUN", "forms": ["bankväsen", "bankväsendet", "bankväsendena"]}
            ],
            "bankväsende": [
                {"id": "b2", "lemmas": ["bankväsende"], "upos": "NOUN", "forms": ["bankväsende", "bankväsendet", "bankväsenden"]}
            ],
        }
        rows, summary = analyze(noun_rows, saldo, {})
        self.assertEqual(2, summary["variant_paradigms"])
        self.assertEqual(2, summary["status_counts"]["exact"])
        self.assertEqual({"bankväsen", "bankväsende"}, {row["variant_lemma"] for row in rows})

    def test_missing_variant_is_reported_as_missing(self) -> None:
        noun_rows = [
            {
                "record_id": "1",
                "homonym_number": "1",
                "lemma": "abrovink",
                "variant_mode": "shared_notation",
                "variant_paradigms": [
                    {"lemma": "abrovink", "notation": "+en +er", "forms": [{"written_form": "abrovink"}]},
                    {"lemma": "abrovinsch", "notation": "+en +er", "forms": [{"written_form": "abrovinsch"}]},
                ],
            }
        ]
        saldo = {
            "abrovink": [
                {"id": "a1", "lemmas": ["abrovink"], "upos": "NOUN", "forms": ["abrovink"]}
            ]
        }
        rows, summary = analyze(noun_rows, saldo, {})
        by_lemma = {row["variant_lemma"]: row for row in rows}
        self.assertEqual("exact", by_lemma["abrovink"]["status"])
        self.assertEqual("missing", by_lemma["abrovinsch"]["status"])
        self.assertEqual(1, summary["status_counts"]["missing"])


if __name__ == "__main__":
    unittest.main()
