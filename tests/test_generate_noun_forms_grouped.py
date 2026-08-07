from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_noun_forms_grouped import generate_grouped


class GenerateNounFormsGroupedTests(unittest.TestCase):
    def test_bankvasen_uses_vasende_as_second_branch_base(self) -> None:
        rows = [
            {
                "normaliserat_ord": "bankväsen", "homonr": "1", "upos": "NOUN",
                "urspr_lopnr": 5598, "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen", "ord": "bank|väsen", "ordkl": "s.",
            },
            {
                "normaliserat_ord": "bankväsen", "homonr": "0", "upos": "NOUN",
                "urspr_lopnr": 5598, "subnr": 5598,
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "stycke": "bank|väsen", "ord": "bank|väsende", "ordkl": "s.",
            },
        ]
        generated, summary = generate_grouped(rows)
        self.assertEqual(1, summary["proven_variant_groups"])
        self.assertEqual(2, summary["proven_variant_rows"])
        for row in generated:
            forms = {form["written_form"] for form in row["forms"]}
            self.assertIn("bankväsen", forms)
            self.assertIn("bankväsende", forms)
            self.assertIn("bankväsendet", forms)
            self.assertIn("bankväsenden", forms)
            self.assertIn("bankväsendena", forms)
            self.assertNotIn("bankväsent", forms)
            self.assertNotIn("bankväsenn", forms)

    def test_unrelated_noun_uses_existing_canonical_path(self) -> None:
        generated, summary = generate_grouped([
            {
                "normaliserat_ord": "bil", "homonr": "1", "upos": "NOUN",
                "urspr_lopnr": 7, "subnr": 7, "text": "+en +ar",
                "stycke": "bil", "ord": "bil", "ordkl": "s.",
            }
        ])
        self.assertEqual(0, summary["proven_variant_groups"])
        forms = {form["written_form"] for form in generated[0]["forms"]}
        self.assertIn("bilen", forms)
        self.assertIn("bilar", forms)


if __name__ == "__main__":
    unittest.main()
