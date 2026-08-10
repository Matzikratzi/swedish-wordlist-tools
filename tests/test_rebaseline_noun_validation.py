import unittest

from swedish_wordlist_tools.rebaseline_noun_validation import classify


class NounValidationRebaselineTests(unittest.TestCase):
    def test_scope_extra_with_exact_singular_is_verified(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "kyrkofrid",
            "record_id": "1",
            "homonym_number": "1",
            "notation": "+en",
            "generated_forms": ["kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens"],
            "saldo_forms": [
                "kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens",
                "kyrkofrider", "kyrkofriderna",
            ],
            "status": "saol_forms_are_subset",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["scope_extra_singular_verified"])

    def test_competing_definite_singular_is_mechanically_verified_from_saol(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "grafen",
            "record_id": "2",
            "homonym_number": "1",
            "notation": "+et",
            "generated_forms": ["grafen", "grafens", "grafenet", "grafenets"],
            "saldo_forms": ["grafen", "grafens", "grafenen", "grafenens", "grafener", "grafenerna"],
            "status": "form_set_mismatch",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["mechanically_verified_from_saol"])
        self.assertFalse(any(key.startswith("scope_mismatch_") for key in summary["counts"]))

    def test_other_exact_noun_keeps_old_status_bucket(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "hus",
            "record_id": "3",
            "homonym_number": "1",
            "notation": "+et +",
            "generated_forms": ["hus"],
            "saldo_forms": ["hus"],
            "status": "exact_form_set",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["exact_form_set"])

    def test_simple_zero_plural_mismatch_is_mechanically_verified(self):
        rows = [{
            "upos": "NOUN", "lemma": "ansvar", "record_id": "4", "homonym_number": "1",
            "notation": "+et; pl. +",
            "generated_forms": ["ansvar", "ansvars", "ansvaret", "ansvarets", "ansvaren", "ansvarens"],
            "saldo_forms": ["ansvar", "ansvars", "ansvaret", "ansvarets"],
            "status": "form_set_mismatch",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["mechanically_verified_from_saol"])
        self.assertNotIn("remaining_form_set_mismatch", summary["counts"])

    def test_materialized_alternative_branches_are_mechanically_verified(self):
        rows = [{
            "upos": "NOUN", "lemma": "bankväsen", "record_id": "6", "homonym_number": "1",
            "notation": "+det; pl. +, best. pl. +dena _ +t +n",
            "generated_forms": ["bankväsen", "bankväsende", "bankväsendet", "bankväsenden"],
            "saldo_forms": ["bankväsen", "bankväsendet"],
            "status": "form_set_mismatch",
            "variant_validation": [
                {"lemma": "bankväsen", "generated_forms": ["bankväsen", "bankväsendet"]},
                {"lemma": "bankväsende", "generated_forms": ["bankväsende", "bankväsendet", "bankväsenden"]},
            ],
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["mechanically_verified_from_saol"])
        self.assertNotIn("remaining_form_set_mismatch", summary["counts"])

    def test_null_text_ordkl_paradigm_is_mechanically_verified(self):
        rows = [{
            "upos": "NOUN", "lemma": "kröken", "record_id": "40", "homonym_number": "1",
            "notation": "(null)", "ordkl": "s. best.",
            "generated_forms": ["kröken", "krökens"],
            "saldo_forms": ["krök", "kröken", "krökar", "krökarna"],
            "status": "form_set_mismatch",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["mechanically_verified_from_saol"])
        self.assertNotIn("remaining_form_set_mismatch", summary["counts"])

    def test_truncated_source_is_separate_from_parser_mismatch(self):
        notation = "+n; pl. kamrar el. +, best. pl. kamrarna el. kamma"
        self.assertEqual(50, len(notation))
        rows = [{
            "upos": "NOUN", "lemma": "auktionskammare", "record_id": "41", "homonym_number": "1",
            "notation": notation,
            "generated_forms": ["auktionskammare", "auktionskammaren", "auktionskamrar"],
            "saldo_forms": ["auktionskammare"],
            "status": "form_set_mismatch",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["source_text_truncated"])
        self.assertNotIn("remaining_form_set_mismatch", summary["counts"])
        self.assertFalse(any(key.startswith("scope_mismatch_") for key in summary["counts"]))

    def test_variant_coverage_difference_is_separate_from_parser_and_scope_mismatch(self):
        rows = [{
            "upos": "NOUN", "lemma": "akne", "record_id": "42", "homonym_number": "0",
            "notation": "+n",
            "generated_forms": ["acne", "acnes", "acnen", "acnens"],
            "saldo_forms": ["akne", "aknes", "aknen", "aknens"],
            "status": "form_set_mismatch",
            "semantic_status": "variant_coverage_difference",
            "semantic_reason": "alternative_heading_missing_in_saldo",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["variant_coverage_difference"])
        self.assertNotIn("remaining_form_set_mismatch", summary["counts"])
        self.assertFalse(any(key.startswith("scope_mismatch_") for key in summary["counts"]))
        self.assertEqual(0, summary["scope_population"])

    def test_relative_el_zero_plural_notation_is_mechanically_verified(self):
        rows = [{
            "upos": "NOUN", "lemma": "alfa", "record_id": "5", "homonym_number": "1",
            "notation": "+t; pl. +n el. +",
            "generated_forms": ["alfa", "alfat", "alfan", "alfaen"],
            "saldo_forms": ["alfa", "alfat", "alfan"],
            "status": "form_set_mismatch",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["mechanically_verified_from_saol"])
        self.assertNotIn("remaining_form_set_mismatch", summary["counts"])

    def test_verified_sibling_homonym_is_diagnostic_only(self):
        rows = [
            {
                "upos": "NOUN", "lemma": "duns", "record_id": "10", "homonym_number": "1",
                "notation": "+en +ar", "generated_forms": ["duns", "dunsen"],
                "saldo_forms": ["duns", "dunsen"], "status": "exact_form_set",
            },
            {
                "upos": "NOUN", "lemma": "duns", "record_id": "11", "homonym_number": "2",
                "notation": "+et", "generated_forms": ["duns", "duns", "dunset", "dunsets"],
                "saldo_forms": ["duns", "dunsen", "dunsens"], "status": "form_set_mismatch",
            },
        ]
        coverage = {"rows": [{
            "lemma": "duns",
            "status": "at_least_one_saol_homonym_exactly_verified",
            "exact_saol_homonyms": ["1"],
            "subset_saol_homonyms": ["1"],
        }]}
        summary = classify(rows, homonym_coverage=coverage)
        self.assertEqual(1, summary["counts"]["exact_form_set"])
        self.assertEqual(1, summary["counts"]["mechanically_verified_from_saol"])
        self.assertEqual(1, summary["homonym_diagnostics"]["at_least_one_saol_homonym_exactly_verified"])

    def test_subset_sibling_is_diagnostic_only(self):
        rows = [
            {
                "upos": "NOUN", "lemma": "fotografi", "record_id": "12", "homonym_number": "1",
                "notation": "+t +er", "generated_forms": ["fotografi"],
                "saldo_forms": ["fotografi", "fotografit"], "status": "saol_forms_are_subset",
            },
            {
                "upos": "NOUN", "lemma": "fotografi", "record_id": "13", "homonym_number": "2",
                "notation": "+n", "generated_forms": ["fotografi", "fotografin", "fotografins"],
                "saldo_forms": ["fotografi", "fotografit", "fotografits"], "status": "form_set_mismatch",
            },
        ]
        coverage = {"rows": [{
            "lemma": "fotografi",
            "status": "at_least_one_saol_homonym_subset_verified",
            "exact_saol_homonyms": [],
            "subset_saol_homonyms": ["1"],
        }]}
        summary = classify(rows, homonym_coverage=coverage)
        self.assertEqual(1, summary["counts"]["other_saol_subset"])
        self.assertEqual(1, summary["counts"]["mechanically_verified_from_saol"])
        self.assertEqual(1, summary["homonym_diagnostics"]["at_least_one_saol_homonym_subset_verified"])


if __name__ == "__main__":
    unittest.main()
