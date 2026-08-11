from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_form_expansion import expand_adjective_forms
from swedish_wordlist_tools.adjective_slots import AdjectiveForm, AdjectiveSlots


class AdjectiveFormExpansionTests(unittest.TestCase):
    def test_superlative_st_expands_to_definite_and_masculine_forms(self) -> None:
        slots = AdjectiveSlots(
            lemma="liten",
            forms=(
                AdjectiveForm("liten", "common_singular"),
                AdjectiveForm("minst", "superlative"),
            ),
            rule="test",
        )
        expanded = expand_adjective_forms(slots)
        self.assertEqual(
            ("liten", "minst", "minsta", "minste"),
            expanded.written_forms(),
        )
        self.assertEqual(
            (
                "common_singular",
                "superlative",
                "superlative_definite_or_plural",
                "superlative_masculine_definite",
            ),
            tuple(form.slot for form in expanded.forms),
        )
        self.assertEqual("derived_inflection", expanded.forms[-2].provenance)
        self.assertEqual("derived_inflection", expanded.forms[-1].provenance)

    def test_non_st_superlative_is_not_guessed(self) -> None:
        slots = AdjectiveSlots(
            lemma="x",
            forms=(AdjectiveForm("bästa", "superlative"),),
            rule="test",
        )
        self.assertIs(slots, expand_adjective_forms(slots))


if __name__ == "__main__":
    unittest.main()
