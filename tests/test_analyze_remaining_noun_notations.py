import unittest

from swedish_wordlist_tools.analyze_remaining_noun_notations import build_summary, candidates


DIAGNOSTIC_NOTATION = "+en +ar _ +n -grepar"


class RemainingNounNotationTests(unittest.TestCase):
    def test_excludes_mechanically_verified_standard_paradigms(self):
        rows = [
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "x", "notation": "+en +er", "generated_forms": ["x", "xen", "xer"], "saldo_forms": ["x", "xen"]},
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "y", "notation": DIAGNOSTIC_NOTATION, "generated_forms": ["y", "yn"], "saldo_forms": ["y"]},
            {"upos": "NOUN", "status": "exact_form_set", "lemma": "z", "notation": "+en", "generated_forms": ["z"], "saldo_forms": ["z"]},
            {"upos": "ADJ", "status": "form_set_mismatch", "lemma": "fin", "notation": "+t +a", "generated_forms": [], "saldo_forms": []},
        ]
        selected = candidates(rows)
        self.assertEqual(1, len(selected))
        self.assertEqual("y", selected[0]["lemma"])

    def test_excludes_null_notation_when_ordkl_carries_paradigm(self):
        rows = [
            {
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "lemma": "kröken",
                "ordkl": "s. best.",
                "notation": "(null)",
                "generated_forms": ["kröken", "krökens"],
                "saldo_forms": ["krök", "kröken"],
            },
            {
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "lemma": "okänd",
                "ordkl": "s.",
                "notation": "(null)",
                "generated_forms": ["okänd"],
                "saldo_forms": ["okänd", "okända"],
            },
        ]
        selected = candidates(rows)
        self.assertEqual(["okänd"], [row["lemma"] for row in selected])

    def test_excludes_source_truncated_rows(self):
        notation = "+n; pl. kamrar el. +, best. pl. kamrarna el. kamma"
        self.assertEqual(50, len(notation))
        rows = [
            {
                "upos": "NOUN", "status": "form_set_mismatch",
                "lemma": "auktionskammare", "notation": notation,
                "generated_forms": ["auktionskammare", "auktionskammaren"],
                "saldo_forms": ["auktionskammare"],
            },
            {
                "upos": "NOUN", "status": "form_set_mismatch",
                "lemma": "hel", "notation": DIAGNOSTIC_NOTATION,
                "generated_forms": ["hel", "heln"], "saldo_forms": ["hel"],
            },
        ]
        selected = candidates(rows)
        self.assertEqual(["hel"], [row["lemma"] for row in selected])

    def test_excludes_variant_coverage_differences(self):
        rows = [
            {
                "upos": "NOUN", "status": "form_set_mismatch",
                "semantic_status": "variant_coverage_difference",
                "lemma": "akne", "notation": "+n",
                "generated_forms": ["acne", "acnen"],
                "saldo_forms": ["akne", "aknen"],
            },
            {
                "upos": "NOUN", "status": "form_set_mismatch",
                "semantic_status": "true_form_mismatch",
                "lemma": "hel", "notation": DIAGNOSTIC_NOTATION,
                "generated_forms": ["hel", "heln"], "saldo_forms": ["hel"],
            },
        ]
        selected = candidates(rows)
        self.assertEqual(["hel"], [row["lemma"] for row in selected])

    def test_groups_remaining_by_exact_notation(self):
        rows = candidates([
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "a", "notation": DIAGNOSTIC_NOTATION, "generated_forms": ["a", "an"], "saldo_forms": ["a"]},
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "b", "notation": DIAGNOSTIC_NOTATION, "generated_forms": ["b", "bn"], "saldo_forms": ["b"]},
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "c", "notation": "+et", "generated_forms": ["c", "cet"], "saldo_forms": ["c"]},
        ])
        summary = build_summary(rows)
        self.assertEqual(2, summary["records"])
        self.assertEqual(1, summary["notation_groups"])
        self.assertEqual(DIAGNOSTIC_NOTATION, summary["groups"][0]["notation"])
        self.assertEqual(2, summary["groups"][0]["count"])


if __name__ == "__main__":
    unittest.main()
