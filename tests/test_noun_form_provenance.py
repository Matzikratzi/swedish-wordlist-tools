from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_noun_forms_grouped import generate_grouped


class NounFormProvenanceTests(unittest.TestCase):
    def test_single_heading_forms_are_marked_primary(self) -> None:
        rows, _summary = generate_grouped([
            {
                "normaliserat_ord": "bil",
                "homonr": "1",
                "upos": "NOUN",
                "urspr_lopnr": 7,
                "subnr": 7,
                "text": "+en +ar",
                "stycke": "bil",
                "ord": "bil",
                "ordkl": "s.",
            }
        ])
        self.assertEqual(1, len(rows))
        for form in rows[0]["forms"]:
            self.assertEqual("7", form["article_id"])
            self.assertEqual("bil", form["heading"])
            self.assertEqual("primary", form["variant_source"])
            self.assertEqual("single", form["variant_mode"])
            self.assertEqual("bil", form["variant_lemma"])

    def test_variant_union_retains_all_sources_for_shared_forms(self) -> None:
        rows, _summary = generate_grouped([
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
        ])
        self.assertEqual(1, len(rows))
        row = rows[0]
        paradigms = {item["lemma"]: item for item in row["variant_paradigms"]}
        self.assertEqual("primary", paradigms["bankväsen"]["variant_source"])
        self.assertEqual("alternative", paradigms["bankväsende"]["variant_source"])

        by_form = {item["written_form"]: item for item in row["forms"]}
        self.assertEqual("primary", by_form["bankväsen"]["variant_source"])
        self.assertEqual("alternative", by_form["bankväsende"]["variant_source"])
        shared = by_form["bankväsendet"]
        self.assertEqual("merged", shared["variant_source"])
        self.assertEqual(["bankväsen", "bankväsende"], shared["headings"])
        self.assertEqual(
            {("bankväsen", "primary"), ("bankväsende", "alternative")},
            {(item["heading"], item["variant_source"]) for item in shared["variant_sources"]},
        )

    def test_provenance_does_not_change_written_form_set(self) -> None:
        rows, _summary = generate_grouped([
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
        ])
        forms = {item["written_form"] for item in rows[0]["forms"]}
        self.assertEqual(
            {
                "abrovink", "abrovinks", "abrovinken", "abrovinkens",
                "abrovinker", "abrovinkers", "abrovinkerna", "abrovinkernas",
                "abrovinsch", "abrovinschs", "abrovinschen", "abrovinschens",
                "abrovinscher", "abrovinschers", "abrovinscherna", "abrovinschernas",
            },
            forms,
        )


if __name__ == "__main__":
    unittest.main()
