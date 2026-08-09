import unittest

from swedish_wordlist_tools.analyze_remaining_noun_notations import build_summary, candidates


class RemainingNounNotationTests(unittest.TestCase):
    def test_excludes_mechanically_verified_standard_paradigms(self):
        rows = [
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "x", "notation": "+en +er", "generated_forms": ["x", "xen", "xer"], "saldo_forms": ["x", "xen"]},
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "y", "notation": "+et el. +en", "generated_forms": ["y", "yet"], "saldo_forms": ["y"]},
            {"upos": "NOUN", "status": "exact_form_set", "lemma": "z", "notation": "+en", "generated_forms": ["z"], "saldo_forms": ["z"]},
            {"upos": "ADJ", "status": "form_set_mismatch", "lemma": "fin", "notation": "+t +a", "generated_forms": ["fin"], "saldo_forms": []},
        ]
        selected = candidates(rows)
        self.assertEqual(1, len(selected))
        self.assertEqual("y", selected[0]["lemma"])

    def test_groups_remaining_by_exact_notation(self):
        rows = candidates([
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "a", "notation": "+et el. +en", "generated_forms": ["a", "aet"], "saldo_forms": ["a"]},
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "b", "notation": "+et el. +en", "generated_forms": ["b", "bet"], "saldo_forms": ["b"]},
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "c", "notation": "+et", "generated_forms": ["c", "cet"], "saldo_forms": ["c"]},
        ])
        summary = build_summary(rows)
        self.assertEqual(3, summary["records"])
        self.assertEqual(2, summary["notation_groups"])
        self.assertEqual("+et el. +en", summary["groups"][0]["notation"])
        self.assertEqual(2, summary["groups"][0]["count"])


if __name__ == "__main__":
    unittest.main()
