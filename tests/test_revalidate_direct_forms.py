from __future__ import annotations

import unittest

from swedish_wordlist_tools.canonical_direct_forms import canonical_record_forms
from swedish_wordlist_tools.revalidate_direct_forms import canonical_validation_row


class RevalidateDirectFormsTests(unittest.TestCase):
    def analysis(self, *forms: str) -> dict[str, object]:
        return {
            "id": "saldo.1",
            "lemmas": ["test"],
            "forms": list(forms),
            "upos": "",
        }

    def test_uses_canonical_adjective_generator(self) -> None:
        record = {
            "normaliserat_ord": "röd",
            "upos": "ADJ",
            "text": "rött röda",
            "stycke": "röd",
            "homonr": "1",
        }
        self.assertEqual({"röd", "rött", "röda"}, canonical_record_forms(record))

    def test_uses_canonical_verb_generator(self) -> None:
        record = {
            "normaliserat_ord": "abonnera",
            "upos": "VERB",
            "text": "+de +t",
            "stycke": "abonn·era",
            "homonr": "1",
        }
        self.assertEqual(
            {"abonnera", "abonnerade", "abonnerat"},
            canonical_record_forms(record),
        )

    def test_validation_row_compares_canonical_forms(self) -> None:
        record = {
            "normaliserat_ord": "abonnera",
            "upos": "VERB",
            "text": "+de +t",
            "stycke": "abonn·era",
            "homonr": "1",
        }
        row = canonical_validation_row(
            record,
            "lemma_same_upos",
            [self.analysis("abonnera", "abonnerade", "abonnerat")],
        )
        self.assertEqual("exact_form_set", row["status"])
        self.assertEqual("canonical_by_word_class", row["generator"])
        self.assertEqual([], row["missing_from_saol"])
        self.assertEqual([], row["extra_from_saol"])


if __name__ == "__main__":
    unittest.main()
