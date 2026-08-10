from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_noun_forms import generate_noun_artifact
from swedish_wordlist_tools.saol_noun_variants import prepare_noun_variant_records


class NounArticleSurfaceBaseTests(unittest.TestCase):
    def test_kaprifolium_is_separate_article_under_normalized_kaprifol(self) -> None:
        records = [
            {
                "normaliserat_ord": "kaprifol",
                "homonr": "1",
                "subnr": 42075,
                "ordkl": "s. +en +er",
                "stycke": "kapri·fol",
                "text": "+en +er",
                "upos": "NOUN",
                "ord": "kapri·fol",
            },
            {
                "normaliserat_ord": "kaprifol",
                "homonr": "1",
                "subnr": 42072,
                "ordkl": "s. kaprifolien kapri...",
                "stycke": "kapri·foli·um",
                "text": "kaprifolien kaprifolier",
                "upos": "NOUN",
                "ord": "kapri·foli·um",
            },
        ]

        prepared = prepare_noun_variant_records(records)
        self.assertEqual("kaprifol", prepared[0]["normaliserat_ord"])
        self.assertNotIn("_saol_variant_mode", prepared[0])
        self.assertEqual("kaprifolium", prepared[1]["normaliserat_ord"])
        self.assertEqual("kaprifol", prepared[1]["_saol_source_normaliserat_ord"])
        self.assertEqual("rebase_article_surface", prepared[1]["_saol_variant_mode"])
        self.assertEqual("matching_ord_and_stycke", prepared[1]["_saol_variant_evidence"])

        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        by_id = {row["record_id"]: row for row in rows}
        regular = {item["written_form"] for item in by_id["42075"]["forms"]}
        latin = {item["written_form"] for item in by_id["42072"]["forms"]}

        self.assertTrue(
            {
                "kaprifol", "kaprifols", "kaprifolen", "kaprifolens",
                "kaprifoler", "kaprifolers", "kaprifolerna", "kaprifolernas",
            }.issubset(regular)
        )
        self.assertTrue(
            {
                "kaprifolium", "kaprifoliums", "kaprifolien", "kaprifoliens",
                "kaprifolier", "kaprifoliers", "kaprifolierna", "kaprifoliernas",
            }.issubset(latin)
        )

    def test_morphological_ord_boundary_is_not_a_distinct_article_surface(self) -> None:
        records = [
            {
                "normaliserat_ord": "halländska",
                "homonr": "1",
                "subnr": 30976,
                "ordkl": "s. +n -ländskor",
                "stycke": "halländska",
                "text": "+n -ländskor",
                "upos": "NOUN",
                "ord": "hall|ländska",
            }
        ]
        prepared = prepare_noun_variant_records(records)
        self.assertEqual("halländska", prepared[0]["normaliserat_ord"])
        self.assertNotIn("_saol_variant_mode", prepared[0])

    def test_cross_reference_spelling_is_not_promoted_by_article_surface_rule(self) -> None:
        records = [
            {
                "normaliserat_ord": "akne",
                "homonr": "0",
                "subnr": 438305,
                "ordkl": "s. +n",
                "stycke": "akne",
                "text": "+n",
                "upos": "NOUN",
                "ord": "acne",
            }
        ]
        prepared = prepare_noun_variant_records(records)
        self.assertEqual("akne", prepared[0]["normaliserat_ord"])
        self.assertNotIn("_saol_variant_mode", prepared[0])


if __name__ == "__main__":
    unittest.main()
