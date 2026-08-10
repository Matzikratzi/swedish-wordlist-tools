from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_row_interpreter import (
    apply_form_token,
    interpret_noun_row,
)


class SaolRowInterpreterTests(unittest.TestCase):
    def record(
        self,
        lemma: str,
        pattern: str | None,
        stycke: str = "",
        ordkl: str = "s.",
    ):
        return {
            "normaliserat_ord": lemma,
            "text": pattern,
            "stycke": stycke,
            "ordkl": ordkl,
            "upos": "NOUN",
        }

    def test_interprets_regular_compact_paradigm(self) -> None:
        row = interpret_noun_row(self.record("hund", "+en +ar"))
        self.assertIsNotNone(row)
        self.assertEqual("hunden", row.form("sg_def") if row else None)
        self.assertEqual("hundar", row.form("pl_indef") if row else None)

    def test_applies_suffixes_to_final_word_in_phrase(self) -> None:
        row = interpret_noun_row(
            self.record("a conto-betalning", "+en +ar", "a conto-be·tal·ning")
        )
        self.assertIsNotNone(row)
        self.assertEqual("a conto-betalningen", row.form("sg_def") if row else None)
        self.assertEqual("a conto-betalningar", row.form("pl_indef") if row else None)

    def test_interprets_zero_plural_label(self) -> None:
        row = interpret_noun_row(self.record("fiskelag", "+et; pl. +"))
        self.assertIsNotNone(row)
        self.assertEqual("fiskelaget", row.form("sg_def") if row else None)
        self.assertEqual("fiskelag", row.form("pl_indef") if row else None)

    def test_uses_bar_for_explicit_compound_head(self) -> None:
        row = interpret_noun_row(self.record("alarmklocka", "+n -klockor", "a·larm|klocka"))
        self.assertIsNotNone(row)
        self.assertEqual("alarmklockan", row.form("sg_def") if row else None)
        self.assertEqual("alarmklockor", row.form("pl_indef") if row else None)

    def test_interprets_underscore_separated_alternatives(self) -> None:
        row = interpret_noun_row(self.record("chip", "+et; pl. + _ +t +n"))
        self.assertIsNotNone(row)
        self.assertEqual(
            {"chipet", "chipt"},
            {form.written_form for form in (row.key_forms if row else ()) if form.slot == "sg_def"},
        )
        self.assertEqual(
            {"chip", "chipn"},
            {form.written_form for form in (row.key_forms if row else ()) if form.slot == "pl_indef"},
        )

    def test_hajp_branches_are_composed_from_ordinary_slot_operations(self) -> None:
        row = interpret_noun_row(
            self.record("hajp", "+en; pl. +er el. +ar _ +n [haj>pen]")
        )
        self.assertIsNotNone(row)
        self.assertEqual(
            {"hajpen", "hajpn"},
            {form.written_form for form in (row.key_forms if row else ()) if form.slot == "sg_def"},
        )
        self.assertEqual(
            {"hajper", "hajpar"},
            {form.written_form for form in (row.key_forms if row else ()) if form.slot == "pl_indef"},
        )
        self.assertNotIn(
            "haj>pen",
            {form.written_form for form in (row.key_forms if row else ())},
        )

    def test_interprets_colon_suffixes(self) -> None:
        row = interpret_noun_row(self.record("tv", "+:n +:ar"))
        self.assertIsNotNone(row)
        self.assertEqual("tv:n", row.form("sg_def") if row else None)
        self.assertEqual("tv:ar", row.form("pl_indef") if row else None)

    def test_bracketed_pronunciation_is_removed_before_interpretation(self) -> None:
        row = interpret_noun_row(self.record("baguette", "+n [-en]; pl. +r [-er]"))
        self.assertIsNotNone(row)
        self.assertEqual("baguetten", row.form("sg_def") if row else None)
        self.assertEqual("baguetter", row.form("pl_indef") if row else None)

    def test_never_materializes_final_token_at_source_limit(self) -> None:
        pattern = "+n; pl. kamrar el. +, best. pl. kamrarna el. kamma"
        self.assertEqual(50, len(pattern))
        row = interpret_noun_row(self.record("kammare", pattern))
        self.assertIsNotNone(row)
        self.assertNotIn("kamma", {form.source for form in (row.key_forms if row else ())})
        self.assertNotIn("kamma", {form.written_form for form in (row.key_forms if row else ())})


if __name__ == "__main__":
    unittest.main()
