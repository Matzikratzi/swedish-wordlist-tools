import unittest

from swedish_wordlist_tools.reanalyze_remaining_noun_conflicts import classify


class RemainingNounConflictReanalysisTests(unittest.TestCase):
    def test_saol_only(self):
        row = {
            "lemma": "ord",
            "notation": "+en +er",
            "extra_from_saol": ["order"],
            "missing_from_saol": [],
            "generated_forms": ["ord", "orden", "order"],
            "saldo_forms": ["ord", "orden"],
        }
        self.assertEqual("saol_only_forms_missing_in_saldo", classify(row))

    def test_competing(self):
        row = {
            "lemma": "ord",
            "notation": "+en +er",
            "extra_from_saol": ["order"],
            "missing_from_saol": ["ordar"],
            "generated_forms": ["ord", "orden", "order"],
            "saldo_forms": ["ord", "orden", "ordar"],
        }
        self.assertEqual("competing_form_sets", classify(row))

    def test_variant(self):
        row = {
            "lemma": "karambolering",
            "notation": "+en",
            "extra_from_saol": ["carambolering"],
            "missing_from_saol": ["karamboleringar"],
            "generated_forms": ["karambolering", "carambolering"],
            "saldo_forms": ["karambolering", "karamboleringar"],
        }
        self.assertEqual("variant_or_orthography_conflict", classify(row))

    def test_scope_singular_conflict_has_precedence(self):
        row = {
            "lemma": "duns",
            "notation": "+et",
            "extra_from_saol": ["dunset", "dunsets"],
            "missing_from_saol": ["dunsen", "dunsens", "dunsar"],
            "generated_forms": ["duns", "duns", "dunset", "dunsets"],
            "saldo_forms": ["duns", "dunsen", "dunsens", "dunsar"],
        }
        self.assertEqual("singular_scope_conflict", classify(row))


if __name__ == "__main__":
    unittest.main()
