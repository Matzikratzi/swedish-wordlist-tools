import unittest

from swedish_wordlist_tools.generate_noun_forms import generate_noun_artifact
from swedish_wordlist_tools.saol_noun_variants import prepare_noun_variant_records


class SaolNounVariantArticleBindingTests(unittest.TestCase):
    def test_main_and_duplicate_vasen_rows_share_hv_branch_base(self):
        records = [
            {
                "normaliserat_ord": "bankväsen",
                "homonr": "1",
                "subnr": 100,
                "ordkl": "s.",
                "stycke": "bank|väsen",
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "upos": "NOUN",
                "ord": "bank|väsen",
            },
            {
                "normaliserat_ord": "bankväsen",
                "homonr": "0",
                "subnr": 100,
                "ordkl": "s.",
                "stycke": "bank|väsen",
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "upos": "NOUN",
                "ord": "bankväsende",
            },
            {
                "normaliserat_ord": "bankväsen",
                "homonr": "1",
                "subnr": 99,
                "ordkl": "(hv)",
                "stycke": "bankväsende",
                "text": "(null)",
                "upos": "X",
                "ord": "bankväsende",
            },
        ]

        prepared = prepare_noun_variant_records(records)
        nouns = [row for row in prepared if str(row.get("upos")).upper() == "NOUN"]
        self.assertEqual("bankväsende", nouns[0]["_saol_alternative_lemma"])
        self.assertEqual("bankväsende", nouns[1]["_saol_alternative_lemma"])

        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        expected = {
            "bankväsen",
            "bankväsens",
            "bankväsende",
            "bankväsendes",
            "bankväsendet",
            "bankväsendets",
            "bankväsenden",
            "bankväsendens",
            "bankväsendena",
            "bankväsendenas",
        }
        by_homonym = {
            row["homonym_number"]: {form["written_form"] for form in row["forms"]}
            for row in rows
        }
        self.assertEqual(expected, by_homonym["1"])
        self.assertEqual(expected, by_homonym["0"])


if __name__ == "__main__":
    unittest.main()
