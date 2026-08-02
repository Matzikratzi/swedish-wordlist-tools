from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_validation import analyse_rows


class AnalyzeNounValidationTests(unittest.TestCase):
    def test_groups_remaining_noun_notations_by_frequency(self) -> None:
        rows = [
            {"lemma": "bil", "upos": "NOUN", "notation": "+en +ar", "status": "saol_forms_are_subset", "missing_from_saol": ["bilarna"], "extra_from_saol": []},
            {"lemma": "stol", "upos": "NOUN", "notation": "+en +ar", "status": "form_set_mismatch", "missing_from_saol": [], "extra_from_saol": ["stolarna"]},
            {"lemma": "hus", "upos": "NOUN", "notation": "+et; pl. +", "status": "saol_zero_plural_differs_from_saldo", "missing_from_saol": [], "extra_from_saol": ["husen"]},
            {"lemma": "snabb", "upos": "ADJ", "notation": "+t +a", "status": "saol_forms_are_subset"},
            {"lemma": "klar", "upos": "NOUN", "notation": "+en", "status": "exact_form_set"},
        ]

        report = analyse_rows(rows, sample_size=1)

        self.assertEqual(3, report["noun_records_remaining"])
        self.assertEqual(2, report["distinct_notations"])
        self.assertEqual("+en +ar", report["patterns"][0]["notation"])
        self.assertEqual(2, report["patterns"][0]["records"])
        self.assertEqual(["bil"], report["patterns"][0]["sample_lemmas"])


if __name__ == "__main__":
    unittest.main()
