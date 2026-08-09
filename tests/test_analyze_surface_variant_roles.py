import unittest

from swedish_wordlist_tools.analyze_surface_variant_roles import (
    analyze,
    is_pure_relative_notation,
)


class SurfaceVariantRoleTests(unittest.TestCase):
    def test_relative_notation_is_conservative(self):
        self.assertTrue(is_pure_relative_notation("+n"))
        self.assertTrue(is_pure_relative_notation("+en +er"))
        self.assertTrue(is_pure_relative_notation("+et; pl. +"))
        self.assertFalse(
            is_pure_relative_notation(
                "ankaret; pl. ankare el. ankaren, best. pl. ankarna"
            )
        )

    def test_distinguishes_acne_ankar_and_allan_roles(self):
        records = [
            {
                "normaliserat_ord": "akne",
                "ord": "acne",
                "homonr": "0",
                "upos": "NOUN",
                "ordkl": "s. +n",
                "text": "+n",
                "stycke": "akne",
            },
            {
                "normaliserat_ord": "ankare",
                "ord": "ankar",
                "homonr": "0",
                "upos": "NOUN",
                "ordkl": "s.",
                "text": "ankaret; pl. ankare el. ankaren, best. pl. ankarna",
                "stycke": "ankare",
            },
            {
                "normaliserat_ord": "all",
                "ord": "allan",
                "homonr": "0",
                "upos": "X",
                "ordkl": "(hv)",
                "text": "(null)",
                "stycke": "allan",
            },
        ]
        summary = analyze(records)
        roles = {(row["normaliserat_ord"], row["ord"]): row["role"] for row in summary["rows"]}
        self.assertEqual("noun_relative_paradigm_candidate", roles[("akne", "acne")])
        self.assertEqual("noun_lexical_or_complex_paradigm", roles[("ankare", "ankar")])
        self.assertEqual("cross_reference", roles[("all", "allan")])


if __name__ == "__main__":
    unittest.main()
