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
                "kyrkofrider", "kyrkofriders", "kyrkofriderna", "kyrkofridernas",
            ],
            "status": "saol_forms_are_subset",
        }]
        summary = classify(rows)
        self.assertEqual(1, summary["counts"]["scope_extra_singular_verified"])

    def test_competing_definite_singular_gets_scope_bucket(self):
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
        self.assertEqual(1, summary["counts"]["scope_mismatch_competing_definite_singular"])

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

    def test_verified_sibling_homonym_does_not_reclassify_conflict(self):
        rows = [
            {
                "upos": "NOUN", "lemma": "duns", "record_id": "10", "homonym_number": "1",
                "notation": "+en +ar", "generated_forms": ["duns", "dunsen"],
                "saldo_forms": ["duns", "dunsen"], "status": "exact_form_set",
            },
            {
                "upos": "NOUN", "lemma": "duns", "record_id": "11", "homonym_number": "2",
                "notation": "+et", "generated_forms": ["duns", "dunset"],
                "saldo_forms": ["duns", "dunsen"], "status": "form_set_mismatch",
            },
        ]
        coverage = {
            "lemmas": 1,
            "status_counts": {"at_least_one_saol_homonym_exactly_verified": 1},
        }
        summary = classify(rows, homonym_coverage=coverage)
        self.assertEqual(1, summary["counts"]["exact_form_set"])
        self.assertEqual(1, summary["counts"]["scope_mismatch_competing_definite_singular"])
        self.assertEqual(1, summary["unequal_homonym_coverage"]["exact_sibling"])

    def test_subset_sibling_is_diagnostic_only(self):
        rows = [{
            "upos": "NOUN", "lemma": "fotografi", "record_id": "12", "homonym_number": "2",
            "notation": "+n", "generated_forms": ["fotografi", "fotografin"],
            "saldo_forms": ["fotografi", "fotografit"], "status": "form_set_mismatch",
        }]
        coverage = {
            "lemmas": 1,
            "status_counts": {"at_least_one_saol_homonym_subset_verified": 1},
        }
        summary = classify(rows, homonym_coverage=coverage)
        self.assertEqual(1, summary["counts"]["scope_mismatch_competing_definite_singular"])
        self.assertEqual(1, summary["unequal_homonym_coverage"]["subset_sibling"])


if __name__ == "__main__":
    unittest.main()
