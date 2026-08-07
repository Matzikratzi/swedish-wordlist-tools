from __future__ import annotations

import unittest
from pathlib import Path

from swedish_wordlist_tools.generate_noun_forms_grouped import (
    DEFAULT_BASELINE,
    DEFAULT_JSONL,
    generate_grouped,
)


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
        self.assertEqual(1, summary["variant_groups"])
        self.assertEqual({"parallel_branches": 1}, summary["variant_mode_counts"])
        self.assertEqual(2, summary["variant_rows"])
        for row in generated:
            forms = {form["written_form"] for form in row["forms"]}
            self.assertIn("bankväsen", forms)
            self.assertIn("bankväsende", forms)
            self.assertIn("bankväsendet", forms)
            self.assertIn("bankväsenden", forms)
            self.assertIn("bankväsendena", forms)
            self.assertNotIn("bankväsent", forms)
            self.assertNotIn("bankväsenn", forms)
            self.assertEqual(["bankväsen", "bankväsende"], row["variant_lemmas"])
            paradigms = {item["lemma"]: {form["written_form"] for form in item["forms"]} for item in row["variant_paradigms"]}
            self.assertIn("bankväsen", paradigms["bankväsen"])
            self.assertNotIn("bankväsende", paradigms["bankväsen"])
            self.assertIn("bankväsende", paradigms["bankväsende"])
            self.assertIn("bankväsenden", paradigms["bankväsende"])

    def test_abrovink_shared_notation_generates_both_lemmas(self) -> None:
        rows = [
            {
                "normaliserat_ord": "abrovink", "homonr": "1", "upos": "NOUN",
                "urspr_lopnr": 436193, "subnr": 436193, "text": "+en +er",
                "stycke": "abro·vink", "ord": "abro·vink", "ordkl": "s.",
            },
            {
                "normaliserat_ord": "abrovink", "homonr": "0", "upos": "NOUN",
                "urspr_lopnr": 436193, "subnr": 436193, "text": "+en +er",
                "stycke": "abro·vink", "ord": "abro·vinsch", "ordkl": "s.",
            },
        ]
        generated, summary = generate_grouped(rows)
        self.assertEqual(1, summary["variant_groups"])
        self.assertEqual({"shared_notation": 1}, summary["variant_mode_counts"])
        for row in generated:
            forms = {form["written_form"] for form in row["forms"]}
            self.assertIn("abrovink", forms)
            self.assertIn("abrovinken", forms)
            self.assertIn("abrovinker", forms)
            self.assertIn("abrovinsch", forms)
            self.assertIn("abrovinschen", forms)
            self.assertIn("abrovinscher", forms)

    def test_unrelated_noun_uses_existing_canonical_path(self) -> None:
        generated, summary = generate_grouped([
            {
                "normaliserat_ord": "bil", "homonr": "1", "upos": "NOUN",
                "urspr_lopnr": 7, "subnr": 7, "text": "+en +ar",
                "stycke": "bil", "ord": "bil", "ordkl": "s.",
            }
        ])
        self.assertEqual(0, summary["variant_groups"])
        forms = {form["written_form"] for form in generated[0]["forms"]}
        self.assertIn("bilen", forms)
        self.assertIn("bilar", forms)

    def test_grouped_writer_targets_official_noun_artifact(self) -> None:
        expected = Path("reports/saol14-noun-forms.jsonl")
        self.assertEqual(expected, DEFAULT_JSONL)
        self.assertEqual(expected, DEFAULT_BASELINE)


if __name__ == "__main__":
    unittest.main()
