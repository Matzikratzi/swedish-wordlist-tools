import unittest

from swedish_wordlist_tools.analyze_singular_agreement_for_scope_extras import candidates


class SingularAgreementForScopeExtrasTests(unittest.TestCase):
    def test_marks_exact_when_saldo_contains_all_saol_singular_forms(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "kyrkofrid",
            "notation": "+en",
            "generated_forms": ["kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens"],
            "saldo_forms": [
                "kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens",
                "kyrkofrider", "kyrkofriders", "kyrkofriderna", "kyrkofridernas",
            ],
        }]
        result = candidates(rows)
        self.assertEqual(1, len(result))
        self.assertEqual("singular_exact", result[0]["singular_status"])
        self.assertEqual([], result[0]["missing_singular"])

    def test_marks_mismatch_when_saldo_lacks_saol_definite_singular(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "testord",
            "notation": "+en",
            "generated_forms": ["testord", "testords", "testorden", "testordens"],
            "saldo_forms": ["testord", "testords", "testorder", "testorderna"],
        }]
        result = candidates(rows)
        self.assertEqual(1, len(result))
        self.assertEqual("singular_mismatch", result[0]["singular_status"])
        self.assertEqual(["testorden", "testordens"], result[0]["missing_singular"])

    def test_ignores_articles_with_explicit_plural(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "hund",
            "notation": "+en +ar",
            "generated_forms": ["hund", "hunds", "hunden", "hundens", "hundar"],
            "saldo_forms": ["hund", "hunds", "hunden", "hundens", "hundar", "hundarna"],
        }]
        self.assertEqual([], candidates(rows))


if __name__ == "__main__":
    unittest.main()
