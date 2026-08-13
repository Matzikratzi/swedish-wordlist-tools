from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_form_expansion import expand_adjective_forms
from swedish_wordlist_tools.adjective_slots import AdjectiveForm, AdjectiveSlots


class AdjectiveFormExpansionTests(unittest.TestCase):
    def test_regular_positive_expands_to_masculine_definite_e(self) -> None:
        slots = AdjectiveSlots(
            lemma="abderitisk",
            forms=(
                AdjectiveForm("abderitisk", "common_singular"),
                AdjectiveForm("abderitiskt", "neuter_singular"),
                AdjectiveForm("abderitiska", "definite_or_plural"),
            ),
            rule="shared_positive_atoms",
        )
        expanded = expand_adjective_forms(slots)
        self.assertEqual(
            ("abderitisk", "abderitiskt", "abderitiska", "abderitiske"),
            expanded.written_forms(),
        )
        self.assertEqual("masculine_definite", expanded.forms[-1].slot)
        self.assertEqual("derived_inflection", expanded.forms[-1].provenance)

    def test_limited_or_uninflected_rows_do_not_get_masculine_e(self) -> None:
        slots = AdjectiveSlots(
            lemma="rosa",
            forms=(AdjectiveForm("rosa", "definite_or_plural"),),
            rule="labelled_limited_paradigm",
        )
        self.assertIs(slots, expand_adjective_forms(slots))

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

    def test_regular_ast_superlative_expands_to_aste(self) -> None:
        slots = AdjectiveSlots(
            lemma="snabb",
            forms=(AdjectiveForm("snabbast", "superlative"),),
            rule="test",
        )
        expanded = expand_adjective_forms(slots)
        self.assertEqual(("snabbast", "snabbaste"), expanded.written_forms())
        self.assertEqual("superlative_definite_or_plural", expanded.forms[-1].slot)
        self.assertEqual("derived_inflection", expanded.forms[-1].provenance)

    def test_ringa_expands_ringast_to_ringaste_even_if_external_coverage_is_missing(self) -> None:
        slots = AdjectiveSlots(
            lemma="ringa",
            forms=(AdjectiveForm("ringast", "superlative"),),
            rule="test",
        )
        expanded = expand_adjective_forms(slots)
        self.assertEqual(("ringast", "ringaste"), expanded.written_forms())
        self.assertEqual("derived_inflection", expanded.forms[-1].provenance)

    def test_parallel_trang_superlatives_expand_independently(self) -> None:
        slots = AdjectiveSlots(
            lemma="trång",
            forms=(
                AdjectiveForm("trängst", "superlative"),
                AdjectiveForm("trångast", "superlative"),
            ),
            rule="test",
        )
        expanded = expand_adjective_forms(slots)
        self.assertEqual(
            ("trängst", "trångast", "trängsta", "trängste", "trångaste"),
            expanded.written_forms(),
        )
        self.assertEqual(
            (
                "superlative",
                "superlative",
                "superlative_definite_or_plural",
                "superlative_masculine_definite",
                "superlative_definite_or_plural",
            ),
            tuple(form.slot for form in expanded.forms),
        )

    def test_non_st_superlative_is_not_guessed(self) -> None:
        slots = AdjectiveSlots(
            lemma="x",
            forms=(AdjectiveForm("bästa", "superlative"),),
            rule="test",
        )
        self.assertIs(slots, expand_adjective_forms(slots))


if __name__ == "__main__":
    unittest.main()
