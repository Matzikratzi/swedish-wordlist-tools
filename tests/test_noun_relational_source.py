from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_noun_forms_grouped import generate_grouped
from swedish_wordlist_tools.materialize_saol_relations import materialize
from swedish_wordlist_tools.noun_relational_source import reconstruct_source_rows


class NounRelationalSourceTests(unittest.TestCase):
    def test_relational_source_reproduces_bankvasen_generation(self) -> None:
        raw = [
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
        articles, headings, _references, summary = materialize(raw)
        self.assertEqual(0, summary["raw_rows_minus_accounted"])
        reconstructed = reconstruct_source_rows(articles, headings)
        self.assertEqual(["1", "0"], [row["homonr"] for row in reconstructed])
        self.assertEqual(["bank|väsen", "bank|väsende"], [row["ord"] for row in reconstructed])
        expected, expected_summary = generate_grouped(raw)
        actual, actual_summary = generate_grouped(reconstructed)
        self.assertEqual(expected, actual)
        self.assertEqual(expected_summary, actual_summary)

    def test_reference_rows_do_not_enter_noun_source(self) -> None:
        raw = [
            {
                "normaliserat_ord": "akne", "homonr": "1", "upos": "NOUN",
                "urspr_lopnr": 10, "subnr": 10, "text": "+n",
                "stycke": "akne", "ord": "akne", "ordkl": "s. <i>+n</i>",
            },
            {
                "normaliserat_ord": "akne", "homonr": "1", "upos": "X",
                "urspr_lopnr": 20, "subnr": 20, "text": "(null)",
                "stycke": "acne", "ord": "acne", "ordkl": "(hv)",
            },
        ]
        articles, headings, references, _summary = materialize(raw)
        self.assertEqual(1, len(references))
        reconstructed = reconstruct_source_rows(articles, headings)
        self.assertEqual(1, len(reconstructed))
        self.assertEqual("akne", reconstructed[0]["normaliserat_ord"])
        self.assertEqual("NOUN", reconstructed[0]["upos"])


if __name__ == "__main__":
    unittest.main()
