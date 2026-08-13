from __future__ import annotations

import unittest

from swedish_wordlist_tools.lexeme_slots import LexemeSlots, SlotForm
from swedish_wordlist_tools.verb_form_expansion import expand_regular_first_conjugation


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


if __name__ == "__main__":
    unittest.main()
