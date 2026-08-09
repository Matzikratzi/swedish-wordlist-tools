import unittest

from swedish_wordlist_tools.analyze_remaining_noun_notations import (
    build_summary,
    candidates,
)


class RemainingNounNotationTests(unittest.TestCase):
    def test_selects_only_noun_form_mismatches(self):
        rows = [
            {
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "lemma": "x",
                "notation": "+en +er",
                "generated_forms": ["x", "xen", "xer"],
                "saldo_forms": ["x", "xen"],
            },
            {
                "upos": "NOUN",
                "status": "exact_form_set",
                "lemma": "y",
                "notation": "+en",
                "generated_forms": ["y"],
                "saldo_forms": ["y"],
            },
            {
                "upos": "ADJ",
                "status": "form_set_mismatch",
                "lemma": "z",
                "notation": "+t +a",
                "generated_forms": ["z"],
                "saldo_forms": [],
            },
        ]
        selected = candidates(rows)
        self.assertEqual(1, len(selected))
        self.assertEqual("x", selected[0]["lemma"])

    def test_groups_by_exact_notation(self):
        rows = candidates([
            {
                "upos": "NOUN", "status": "form_set_mismatch", "lemma": "a",
                "notation": "+en +er", "generated_forms": ["a", "aer"], "saldo_forms": ["a"],
            },
            {
                "upos": "NOUN", "status": "form_set_mismatch", "lemma": "b",
                "notation": "+en +er", "generated_forms": ["b", "ber"], "saldo_forms": ["b"],
            },
            {
                "upos": "NOUN", "status": "form_set_mismatch", "lemma": "c",
                "notation": "+et", "generated_forms": ["c", "cet"], "saldo_forms": ["c"],
            },
        ])
        summary = build_summary(rows)
        self.assertEqual(3, summary["records"])
        self.assertEqual(2, summary["notation_groups"])
        self.assertEqual("+en +er", summary["groups"][0]["notation"])
        self.assertEqual(2, summary["groups"][0]["count"])


if __name__ == "__main__":
    unittest.main()
