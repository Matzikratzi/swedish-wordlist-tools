from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_real_shared_forms import generated_real_shared_row


class GenerateRealSharedFormsTests(unittest.TestCase):
    def test_noun_variant_uses_printed_ord_as_inflection_base(self) -> None:
        record = {
            "id": "n1",
            "normaliserat_ord": "annektion",
            "homonr": "0",
            "ord": "annexion",
            "stycke": "an·nekt·ion",
            "ordkl": "s. <i>+en +er</i>",
            "text": "+en +er",
            "upos": "NOUN",
        }
        row = generated_real_shared_row(record)
        self.assertIsNotNone(row)
        forms = {form["written_form"] for form in row["forms"]}
        self.assertIn("annexion", forms)
        self.assertIn("annexionen", forms)
        self.assertIn("annexioner", forms)
        self.assertNotIn("annektionen", forms)

    def test_adjective_variant_uses_printed_ord_as_inflection_base(self) -> None:
        record = {
            "id": "a1",
            "normaliserat_ord": "buddistisk",
            "homonr": "0",
            "ord": "buddhistisk",
            "stycke": "buddistisk",
            "ordkl": "adj. <i>+t +a</i>",
            "text": "+t +a",
            "upos": "ADJ",
        }
        row = generated_real_shared_row(record)
        self.assertIsNotNone(row)
        forms = {form["written_form"] for form in row["forms"]}
        self.assertIn("buddhistisk", forms)
        self.assertIn("buddhistiskt", forms)
        self.assertIn("buddhistiska", forms)

    def test_hv_row_is_not_rebased_as_independent_paradigm(self) -> None:
        record = {
            "id": "x1",
            "normaliserat_ord": "annektion",
            "homonr": "1",
            "ord": "annexion",
            "stycke": "annexion",
            "ordkl": "(hv) <i>+en +er</i>",
            "text": "+en +er",
            "upos": "X",
        }
        self.assertIsNone(generated_real_shared_row(record))


if __name__ == "__main__":
    unittest.main()
