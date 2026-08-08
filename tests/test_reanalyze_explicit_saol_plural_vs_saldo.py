import unittest

from swedish_wordlist_tools.reanalyze_explicit_saol_plural_vs_saldo import (
    candidates,
    has_explicit_plural,
)


class ExplicitSaolPluralReanalysisTests(unittest.TestCase):
    def test_detects_common_explicit_plural_notations(self):
        for notation in ("+en +er", "+en +ar", "+t +n", "+n +r", "+et; pl. +", "+n; pl. +s"):
            with self.subTest(notation=notation):
                self.assertTrue(has_explicit_plural(notation))
        for notation in ("+en", "+et", "+n", "+t"):
            with self.subTest(notation=notation):
                self.assertFalse(has_explicit_plural(notation))

    def test_finds_saol_plural_that_saldo_lacks_without_old_classification(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "allvarlighet",
            "homonym_number": "1",
            "notation": "+en +er",
            "status": "form_set_mismatch",
            "semantic_status": "true_form_mismatch",
            "extra_from_saol": [
                "allvarligheter", "allvarligheters", "allvarligheterna", "allvarligheternas"
            ],
            "missing_from_saol": [],
        }]
        result = candidates(rows)
        self.assertEqual(1, len(result))
        self.assertEqual(
            ["+er", "+erna", "+ernas", "+ers"],
            result[0]["plural_extra_relative"],
        )

    def test_ignores_singular_only_article_even_if_saldo_diff_exists(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "hyperaktivitet",
            "notation": "+en",
            "extra_from_saol": [],
            "missing_from_saol": ["hyperaktiviteter"],
        }]
        self.assertEqual([], candidates(rows))


if __name__ == "__main__":
    unittest.main()
