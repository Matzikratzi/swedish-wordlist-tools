from __future__ import annotations

import unittest

from swedish_wordlist_tools.noun_article_variants import plan_noun_article_variants


class NounArticleVariantsTests(unittest.TestCase):
    def test_shared_notation_applies_to_both_abrovink_variants(self) -> None:
        rows = [
            {
                "normaliserat_ord": "abrovink", "homonr": "1",
                "urspr_lopnr": 436193, "subnr": 436193,
                "text": "+en +er", "stycke": "abro·vink", "ord": "abro·vink",
            },
            {
                "normaliserat_ord": "abrovink", "homonr": "0",
                "urspr_lopnr": 436193, "subnr": 436193,
                "text": "+en +er", "stycke": "abro·vink", "ord": "abro·vinsch",
            },
        ]
        plan = plan_noun_article_variants(rows)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual("shared_notation", plan.mode)
        self.assertEqual(
            (("abrovink", "+en +er"), ("abrovinsch", "+en +er")),
            tuple((variant.lemma, variant.notation) for variant in plan.variants),
        )

    def test_parallel_branches_bind_bankvasende_to_second_branch(self) -> None:
        rows = [
            {
                "normaliserat_ord": "bankväsen", "homonr": "1",
                "urspr_lopnr": 5598, "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen", "ord": "bank|väsen",
            },
            {
                "normaliserat_ord": "bankväsen", "homonr": "0",
                "urspr_lopnr": 5598, "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen", "ord": "bank|väsende",
            },
        ]
        plan = plan_noun_article_variants(rows)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual("parallel_branches", plan.mode)
        self.assertEqual(
            (
                ("bankväsen", "+det; pl. +, best. pl. +dena"),
                ("bankväsende", "+t +n"),
            ),
            tuple((variant.lemma, variant.notation) for variant in plan.variants),
        )

    def test_ambiguous_branch_count_is_not_guessed(self) -> None:
        rows = [
            {
                "normaliserat_ord": "x", "homonr": "1", "text": "+en _ +et _ +n",
                "stycke": "x", "ord": "x",
            },
            {
                "normaliserat_ord": "x", "homonr": "0", "text": "+en _ +et _ +n",
                "stycke": "x", "ord": "y",
            },
        ]
        self.assertIsNone(plan_noun_article_variants(rows))


if __name__ == "__main__":
    unittest.main()
