import unittest

from swedish_wordlist_tools.canonical_form_artifacts import artifact_row_keys
from swedish_wordlist_tools.generate_noun_forms import generate_noun_artifact
from swedish_wordlist_tools.saol_noun_variants import (
    is_simple_relative_noun_notation,
    prepare_noun_variant_records,
)


class SaolNounVariantTests(unittest.TestCase):
    def test_simple_relative_notation_is_narrow(self):
        self.assertTrue(is_simple_relative_noun_notation("+n"))
        self.assertTrue(is_simple_relative_noun_notation("+en +er"))
        self.assertTrue(is_simple_relative_noun_notation("+et; pl. +"))
        self.assertFalse(
            is_simple_relative_noun_notation(
                "+det; pl. +, best. pl. +dena _ +t +n"
            )
        )
        self.assertFalse(is_simple_relative_noun_notation("+et el. +en"))
        self.assertFalse(is_simple_relative_noun_notation("+n [-en]"))
        self.assertFalse(
            is_simple_relative_noun_notation(
                "ankaret; pl. ankare el. ankaren, best. pl. ankarna"
            )
        )

    def _acne_records(self):
        return [
            {
                "normaliserat_ord": "akne",
                "homonr": "0",
                "subnr": 438305,
                "ordkl": "s. +n",
                "stycke": "akne",
                "text": "+n",
                "upos": "NOUN",
                "ord": "acne",
            },
            {
                "normaliserat_ord": "akne",
                "homonr": "1",
                "subnr": 436676,
                "ordkl": "(hv)",
                "stycke": "acne",
                "text": "(null)",
                "upos": "X",
                "ord": "acne",
            },
        ]

    def test_matching_hv_rebases_simple_acne_paradigm(self):
        prepared = prepare_noun_variant_records(self._acne_records())
        noun = prepared[0]
        self.assertEqual("acne", noun["normaliserat_ord"])
        self.assertEqual("akne", noun["_saol_source_normaliserat_ord"])
        self.assertEqual("rebase_simple_relative", noun["_saol_variant_mode"])

        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        self.assertEqual(1, len(rows))
        self.assertEqual("acne", rows[0]["lemma"])
        self.assertEqual("akne", rows[0]["source_normaliserat_ord"])
        forms = {item["written_form"] for item in rows[0]["forms"]}
        self.assertEqual({"acne", "acnes", "acnen", "acnens"}, forms)

    def test_rebased_artifact_is_indexable_by_original_source_lemma(self):
        prepared = prepare_noun_variant_records(self._acne_records())
        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        keys = set(artifact_row_keys(rows[0]))
        self.assertIn(("438305", "0", "acne"), keys)
        self.assertIn(("438305", "0", "akne"), keys)

    def test_hv_is_required_before_rebasing(self):
        records = [
            {
                "normaliserat_ord": "akne",
                "homonr": "0",
                "subnr": 1,
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

    def test_ankar_is_not_rebased(self):
        records = [
            {
                "normaliserat_ord": "ankare",
                "homonr": "0",
                "subnr": 442860,
                "ordkl": "s. ankaret; pl. anka...",
                "stycke": "1ankare",
                "text": "ankaret; pl. ankare el. ankaren, best. pl. ankarna",
                "upos": "NOUN",
                "ord": "ankar",
            },
            {
                "normaliserat_ord": "ankare",
                "homonr": "1",
                "subnr": 442848,
                "ordkl": "(hv)",
                "stycke": "ankar",
                "text": "(null)",
                "upos": "X",
                "ord": "ankar",
            },
        ]
        prepared = prepare_noun_variant_records(records)
        noun = prepared[0]
        self.assertEqual("ankare", noun["normaliserat_ord"])
        self.assertEqual("ankar", noun["_saol_alternative_lemma"])
        self.assertEqual("additional_lemma", noun["_saol_variant_mode"])

    def test_allan_cross_reference_alone_does_not_create_noun_variant(self):
        records = [
            {
                "normaliserat_ord": "all",
                "homonr": "0",
                "subnr": 1,
                "ordkl": "(hv)",
                "stycke": "allan",
                "text": "(null)",
                "upos": "X",
                "ord": "allan",
            }
        ]
        prepared = prepare_noun_variant_records(records)
        self.assertEqual(records, prepared)


if __name__ == "__main__":
    unittest.main()
