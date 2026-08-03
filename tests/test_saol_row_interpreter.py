from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_row_interpreter import (
    apply_form_token,
    interpret_noun_row,
)


class SaolRowInterpreterTests(unittest.TestCase):
    def record(self, lemma: str, pattern: str, stycke: str = ""):
        return {
            "normaliserat_ord": lemma,
            "text": pattern,
            "stycke": stycke,
            "upos": "NOUN",
        }

    def test_interprets_regular_compact_paradigm(self) -> None:
        row = interpret_noun_row(self.record("hund", "+en +ar"))
        self.assertIsNotNone(row)
        self.assertEqual("hunden", row.form("sg_def") if row else None)
        self.assertEqual("hundar", row.form("pl_indef") if row else None)

    def test_interprets_zero_plural_label(self) -> None:
        row = interpret_noun_row(self.record("fiskelag", "+et; pl. +"))
        self.assertIsNotNone(row)
        self.assertEqual("fiskelaget", row.form("sg_def") if row else None)
        self.assertEqual("fiskelag", row.form("pl_indef") if row else None)

    def test_uses_bar_for_explicit_compound_head(self) -> None:
        row = interpret_noun_row(
            self.record("alarmklocka", "+n -klockor", "a·larm|klocka")
        )
        self.assertIsNotNone(row)
        self.assertEqual("alarmklockan", row.form("sg_def") if row else None)
        self.assertEqual("alarmklockor", row.form("pl_indef") if row else None)

    def test_handles_generic_bar_marked_plural_families(self) -> None:
        examples = (
            ("arbetstimme", "+n -timmar", "arbets|timme", "arbetstimmar"),
            ("specialregel", "+n -regler", "special|regel", "specialregler"),
            ("semesterresa", "+n -resor", "semester|resa", "semesterresor"),
            ("namnlista", "+n -listor", "namn|lista", "namnlistor"),
            ("utlandssvenska", "+n -ländskor", "utlands|svenska", "utlandsländskor"),
        )
        for lemma, pattern, stycke, expected_plural in examples:
            with self.subTest(pattern=pattern):
                row = interpret_noun_row(self.record(lemma, pattern, stycke))
                self.assertIsNotNone(row)
                self.assertEqual(expected_plural, row.form("pl_indef") if row else None)

    def test_accepts_harmless_typographic_differences(self) -> None:
        row = interpret_noun_row(
            self.record("A‑lista", "+n -listor", "A|lista")
        )
        self.assertIsNotNone(row)
        self.assertEqual("Alistor", row.form("pl_indef") if row else None)

    def test_uses_last_bar(self) -> None:
        row = interpret_noun_row(
            self.record("storväggklocka", "+n -klockor", "stor|vägg|klocka")
        )
        self.assertIsNotNone(row)
        self.assertEqual("storväggklockor", row.form("pl_indef") if row else None)

    def test_minus_form_requires_bar(self) -> None:
        self.assertIsNone(
            apply_form_token(
                self.record("alarmklocka", "+n -klockor"),
                "alarmklocka",
                "-klockor",
            )
        )

    def test_bracketed_pronunciation_is_removed_before_interpretation(self) -> None:
        row = interpret_noun_row(self.record("baguette", "+n [-en]; pl. +r [-er]"))
        self.assertIsNotNone(row)
        self.assertEqual("baguetten", row.form("sg_def") if row else None)
        self.assertEqual("baguetter", row.form("pl_indef") if row else None)


if __name__ == "__main__":
    unittest.main()
