import unittest

from swedish_wordlist_tools.analyze_next_noun_mismatch_patterns import (
    analyze_rows,
    candidate_kind,
)


class NextNounMismatchPatternTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "mismatch_classification": "unclassified",
            "upos": "NOUN",
            "lemma": "grafen",
            "homonym_number": "1",
            "notation": "+et",
            "extra_from_saol": ["grafenet", "grafenets"],
            "missing_from_saol": [
                "grafenen",
                "grafenens",
                "grafener",
                "grafeners",
                "grafenerna",
                "grafenernas",
            ],
        }
        row.update(overrides)
        return row

    def test_et_vs_en_er(self):
        self.assertEqual("et_vs_en_er", candidate_kind(self.row()))

    def test_et_vs_en_ar(self):
        row = self.row(
            lemma="duns",
            extra_from_saol=["dunset", "dunsets"],
            missing_from_saol=[
                "dunsen",
                "dunsens",
                "dunsar",
                "dunsars",
                "dunsarna",
                "dunsarnas",
            ],
        )
        self.assertEqual("et_vs_en_ar", candidate_kind(row))

    def test_zero_plural_is_kept_separate(self):
        row = self.row(
            lemma="hertz",
            notation="pl. +",
            extra_from_saol=["hertzna", "hertznas"],
            missing_from_saol=["hertzen", "hertzens"],
        )
        self.assertEqual("zero_plural_vs_definite_singular", candidate_kind(row))

    def test_partial_pattern_is_rejected(self):
        self.assertIsNone(candidate_kind(self.row(missing_from_saol=["grafenen", "grafener"])))

    def test_summary_counts_only_unclassified_nouns(self):
        rows = [
            self.row(),
            self.row(mismatch_classification="saldo_missing_plural"),
            self.row(upos="ADJ"),
        ]
        summary = analyze_rows(rows)
        self.assertEqual(1, summary["candidate_total"])
        self.assertEqual({"et_vs_en_er": 1}, summary["candidate_counts"])


if __name__ == "__main__":
    unittest.main()
