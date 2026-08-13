from __future__ import annotations

import unittest

from swedish_wordlist_tools.lexeme_slots import LexemeSlots, SlotForm
from swedish_wordlist_tools.verb_form_expansion import (
    expand_regular_first_conjugation,
    expand_stem_preserving_second_conjugation,
)


class VerbFormExpansionTests(unittest.TestCase):
    def test_expands_saol_first_conjugation_without_external_lexicon(self) -> None:
        slots = LexemeSlots(
            lemma="abdikera",
            upos="VERB",
            notation="+de +t",
            forms=(
                SlotForm("infinitive", "abdikera", "lemma"),
                SlotForm("preterite", "abdikerade", "+de"),
                SlotForm("supine", "abdikerat", "+t"),
            ),
        )
        expanded = expand_regular_first_conjugation(slots)
        self.assertEqual(("abdikerar",), expanded.forms_for("present"))
        self.assertEqual(("abdikera",), expanded.forms_for("imperative"))
        self.assertEqual(("abdikeras",), expanded.forms_for("present_passive"))
        self.assertEqual(("abdikerades",), expanded.forms_for("preterite_passive"))
        self.assertEqual(("abdikerats",), expanded.forms_for("supine_passive"))
        self.assertEqual(("abdikerande",), expanded.forms_for("present_participle"))
        self.assertEqual(("abdikerad",), expanded.forms_for("perfect_participle_common"))
        self.assertEqual(("abdikerat",), expanded.forms_for("perfect_participle_neuter"))
        self.assertEqual(("abdikerade",), expanded.forms_for("perfect_participle_plural"))
        self.assertTrue(all(
            form.provenance == "derived_inflection"
            for form in expanded.forms[3:]
        ))

    def test_does_not_expand_other_or_incomplete_notation(self) -> None:
        for notation in ("-de -t", "+de +t, pres. +r", ""):
            slots = LexemeSlots("x", "VERB", notation, ())
            self.assertIs(slots, expand_regular_first_conjugation(slots))

    def test_variant_row_gets_only_proven_regular_core_forms(self) -> None:
        slots = LexemeSlots(
            "ana",
            "VERB",
            "+de el. (i ett uttryck) ante, +t",
            (
                SlotForm("infinitive", "ana", "lemma"),
                SlotForm("preterite", "anade", "+de"),
                SlotForm("preterite", "ante", "ante"),
                SlotForm("supine", "anat", "+t"),
            ),
        )
        expanded = expand_regular_first_conjugation(slots)
        self.assertEqual(("anar",), expanded.forms_for("present"))
        self.assertEqual(("ana",), expanded.forms_for("imperative"))
        self.assertEqual((), expanded.forms_for("present_passive"))
        self.assertEqual((), expanded.forms_for("present_participle"))

    def test_variant_row_must_contain_both_regular_source_forms(self) -> None:
        slots = LexemeSlots(
            "ana",
            "VERB",
            "ante, anat",
            (
                SlotForm("preterite", "ante", "ante"),
                SlotForm("supine", "anat", "anat"),
            ),
        )
        self.assertIs(slots, expand_regular_first_conjugation(slots))

    def test_adds_core_forms_for_stem_preserving_second_conjugation(self) -> None:
        for lemma, preterite, supine, present, imperative in (
            ("anställa", "anställde", "anställt", "anställer", "anställ"),
            ("avläsa", "avläste", "avläst", "avläser", "avläs"),
        ):
            with self.subTest(lemma=lemma):
                slots = LexemeSlots(
                    lemma=lemma,
                    upos="VERB",
                    notation=f"{preterite} {supine}",
                    forms=(
                        SlotForm("infinitive", lemma, "lemma"),
                        SlotForm("preterite", preterite, "source"),
                        SlotForm("supine", supine, "source"),
                    ),
                )
                expanded = expand_stem_preserving_second_conjugation(slots)
                self.assertEqual((present,), expanded.forms_for("present"))
                self.assertEqual((imperative,), expanded.forms_for("imperative"))
                self.assertEqual(
                    {"stem_preserving_second_conjugation"},
                    {form.provenance_detail for form in expanded.forms[3:]},
                )

    def test_leaves_unsafe_second_conjugation_cases_untouched(self) -> None:
        cases = (
            LexemeSlots(
                "ta",
                "VERB",
                "tog tagit",
                (SlotForm("preterite", "tog", "tog"), SlotForm("supine", "tagit", "tagit")),
            ),
            LexemeSlots(
                "känna",
                "VERB",
                "kände känt",
                (SlotForm("preterite", "kände", "kände"), SlotForm("supine", "känt", "känt")),
            ),
            LexemeSlots(
                "anställa",
                "VERB",
                "-ställde -ställt",
                (
                    SlotForm("preterite", "anställde", "-ställde"),
                    SlotForm("supine", "anställt", "-ställt"),
                ),
                {"source_truncated": "true"},
            ),
        )
        for slots in cases:
            with self.subTest(lemma=slots.lemma, metadata=slots.metadata):
                self.assertIs(slots, expand_stem_preserving_second_conjugation(slots))


if __name__ == "__main__":
    unittest.main()
