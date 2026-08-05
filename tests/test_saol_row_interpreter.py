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
        self.assertEqual(
            "a conto-betalningen",
            row.form("sg_def") if row else None,
        )
        self.assertEqual(
            "a conto-betalningar",
            row.form("pl_indef") if row else None,
        )

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
            ("småländska", "+n -ländskor", "små|ländska", "småländskor"),
        )
        for lemma, pattern, stycke, expected_plural in examples:
            with self.subTest(pattern=pattern):
                row = interpret_noun_row(self.record(lemma, pattern, stycke))
                self.assertIsNotNone(row)
                self.assertEqual(expected_plural, row.form("pl_indef") if row else None)

    def test_removes_html_homonym_markers_before_using_bar(self) -> None:
        row = interpret_noun_row(
            self.record("avresa", "+n -resor", "<sup>1</sup>av|resa")
        )
        self.assertIsNotNone(row)
        self.assertEqual("avresor", row.form("pl_indef") if row else None)

    def test_accepts_complete_written_forms_without_bar(self) -> None:
        examples = (
            ("a-kassa", "+n a-kassor", "a-kassor"),
            ("abc-bok", "+en abc-böcker", "abc-böcker"),
            ("cd-skiva", "+n cd-skivor", "cd-skivor"),
        )
        for lemma, pattern, expected_plural in examples:
            with self.subTest(pattern=pattern):
                row = interpret_noun_row(self.record(lemma, pattern, lemma))
                self.assertIsNotNone(row)
                self.assertEqual(expected_plural, row.form("pl_indef") if row else None)

    def test_accepts_harmless_typographic_differences(self) -> None:
        row = interpret_noun_row(
            self.record("A-lista", "+n -listor", "A‑|lista")
        )
        self.assertIsNotNone(row)
        self.assertEqual("A‐listor", row.form("pl_indef") if row else None)

    def test_uses_last_bar(self) -> None:
        row = interpret_noun_row(
            self.record("storväggklocka", "+n -klockor", "stor|vägg|klocka")
        )
        self.assertIsNotNone(row)
        self.assertEqual("storväggklockor", row.form("pl_indef") if row else None)

    def test_falls_back_to_spelling_evidence_without_bar(self) -> None:
        examples = (
            ("gigawattimme", "-timmar", "gigawattimmar"),
            ("bluffaktura", "-fakturor", "bluffakturor"),
            ("halländska", "-ländskor", "halländskor"),
        )
        for lemma, token, expected in examples:
            with self.subTest(lemma=lemma):
                self.assertEqual(
                    expected,
                    apply_form_token(self.record(lemma, "+n " + token), lemma, token),
                )

    def test_rejects_unsafe_unmarked_replacement(self) -> None:
        self.assertIsNone(
            apply_form_token(
                self.record("alarmklocka", "+n -resor"),
                "alarmklocka",
                "-resor",
            )
        )

    def test_interprets_underscore_separated_alternatives(self) -> None:
        row = interpret_noun_row(self.record("chip", "+et; pl. + _ +t +n"))
        self.assertIsNotNone(row)
        self.assertEqual(
            {"chipet", "chipt"},
            {
                form.written_form
                for form in (row.key_forms if row else ())
                if form.slot == "sg_def"
            },
        )
        self.assertEqual(
            {"chip", "chipn"},
            {
                form.written_form
                for form in (row.key_forms if row else ())
                if form.slot == "pl_indef"
            },
        )

    def test_interprets_colon_suffixes(self) -> None:
        row = interpret_noun_row(self.record("tv", "+:n +:ar"))
        self.assertIsNotNone(row)
        self.assertEqual("tv:n", row.form("sg_def") if row else None)
        self.assertEqual("tv:ar", row.form("pl_indef") if row else None)

    def test_interprets_plural_use_comment(self) -> None:
        row = interpret_noun_row(
            self.record("dagofficer", "+en; som: pl. anv. +are, best. pl. +arna")
        )
        self.assertIsNotNone(row)
        self.assertEqual("dagofficeren", row.form("sg_def") if row else None)
        self.assertEqual("dagofficerare", row.form("pl_indef") if row else None)
        self.assertEqual("dagofficerarna", row.form("pl_def") if row else None)

    def test_interprets_optional_and_colloquial_markers(self) -> None:
        optional = interpret_noun_row(
            self.record("halvmeter", "+n; pl. + ibl. -metrar", "halv|meter")
        )
        self.assertIsNotNone(optional)
        self.assertEqual(
            {"halvmeter", "halvmetrar"},
            {
                form.written_form
                for form in (optional.key_forms if optional else ())
                if form.slot == "pl_indef"
            },
        )
        colloquial = interpret_noun_row(
            self.record("fredag", "+en el. vard. -dan; pl. +ar", "fre|dag")
        )
        self.assertIsNotNone(colloquial)
        self.assertEqual(
            {"fredagen", "fredan"},
            {
                form.written_form
                for form in (colloquial.key_forms if colloquial else ())
                if form.slot == "sg_def"
            },
        )

    def test_interprets_missing_pattern_from_ordkl(self) -> None:
        indeclinable = interpret_noun_row(
            self.record("acidofilus", None, ordkl="s. oböjl.")
        )
        self.assertIsNotNone(indeclinable)
        self.assertEqual(("acidofilus",), tuple(form.written_form for form in indeclinable.key_forms))

        plural = interpret_noun_row(
            self.record("addenda", None, ordkl="s. pl.")
        )
        self.assertIsNotNone(plural)
        self.assertEqual("addenda", plural.form("pl_indef") if plural else None)

        definite = interpret_noun_row(
            self.record("allsvenskan", None, ordkl="s. best.")
        )
        self.assertIsNotNone(definite)
        self.assertEqual("allsvenskan", definite.form("sg_def") if definite else None)

    def test_rejects_unparsed_prose(self) -> None:
        self.assertIsNone(
            interpret_noun_row(self.record("herr", "+n; i: vissa: uttryck: gen. herrans"))
        )

    def test_bracketed_pronunciation_is_removed_before_interpretation(self) -> None:
        row = interpret_noun_row(self.record("baguette", "+n [-en]; pl. +r [-er]"))
        self.assertIsNotNone(row)
        self.assertEqual("baguetten", row.form("sg_def") if row else None)
        self.assertEqual("baguetter", row.form("pl_indef") if row else None)


if __name__ == "__main__":
    unittest.main()
