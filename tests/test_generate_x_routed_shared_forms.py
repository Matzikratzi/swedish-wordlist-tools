from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_x_routed_shared_forms import generate_rows


class GenerateXRoutedSharedFormsTests(unittest.TestCase):
    def _row_by_source_ord(self, rows, source_ord: str):
        return next(row for row in rows if row["source_ord"] == source_ord)

    def test_hv_noun_uses_printed_variant_as_shared_base(self) -> None:
        records = [
            {
                "normaliserat_ord": "annektion",
                "ord": "annektion",
                "stycke": "annektion",
                "ordkl": "subst.",
                "text": "+en +er",
                "upos": "NOUN",
            },
            {
                "normaliserat_ord": "annektion",
                "ord": "annexion",
                "stycke": "annexion",
                "ordkl": "(hv) <i>+en +er</i>",
                "text": "+en +er",
                "upos": "X",
            },
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        row = self._row_by_source_ord(rows, "annexion")
        self.assertEqual("NOUN", row["target_upos"])
        self.assertEqual("annexion", row["routed_lemma"])
        words = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"annexion", "annexionen", "annexioner"} <= words)

    def test_hv_adjective_uses_printed_variant_as_shared_base(self) -> None:
        records = [
            {
                "normaliserat_ord": "buddistisk",
                "ord": "buddistisk",
                "stycke": "buddistisk",
                "ordkl": "adj.",
                "text": "+t +a",
                "upos": "ADJ",
            },
            {
                "normaliserat_ord": "buddistisk",
                "ord": "buddhistisk",
                "stycke": "buddhistisk",
                "ordkl": "(hv) <i>+t +a</i>",
                "text": "+t +a",
                "upos": "X",
            },
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        row = self._row_by_source_ord(rows, "buddhistisk")
        words = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"buddhistisk", "buddhistiskt", "buddhistiska"} <= words)

    def test_hv_verb_uses_printed_variant_as_shared_base(self) -> None:
        records = [
            {
                "normaliserat_ord": "sjappa",
                "ord": "sjappa",
                "stycke": "sjappa",
                "ordkl": "verb",
                "text": "+de +t",
                "upos": "VERB",
            },
            {
                "normaliserat_ord": "sjappa",
                "ord": "schappa",
                "stycke": "schappa",
                "ordkl": "(hv) <i>+de +t</i>",
                "text": "+de +t",
                "upos": "X",
            },
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        row = self._row_by_source_ord(rows, "schappa")
        words = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"schappa", "schappade", "schappat"} <= words)

    def test_mixed_adverb_adjective_is_generated_by_adjective_shared(self) -> None:
        records = [
            {
                "normaliserat_ord": "ansatsvis",
                "ord": "ansatsvis",
                "stycke": "ansatsvis",
                "ordkl": "adv. och adj. <i>+t +a</i>",
                "text": "+t +a",
                "upos": "X",
            },
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        row = rows[0]
        self.assertEqual("ADJ", row["target_upos"])
        words = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"ansatsvis", "ansatsvist", "ansatsvisa"} <= words)


if __name__ == "__main__":
    unittest.main()
