from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_shared_slot_interpreter import (
    interpret_basic_verb_sequence,
    interpret_present_first_verb_sequence,
    interpret_verb_sequence,
    is_structurally_uninflected_verb,
)


class VerbSharedSlotInterpreterTests(unittest.TestCase):
    def _pairs(self, text: str):
        assigned = interpret_basic_verb_sequence(text)
        self.assertIsNotNone(assigned)
        return tuple((item.slot, item.token, item.operation.kind.value) for item in assigned)

    def _rich_pairs(self, text: str):
        assigned = interpret_verb_sequence(text)
        self.assertIsNotNone(assigned)
        return tuple((item.slot, item.token, item.operation.kind.value) for item in assigned)

    def test_relative_suffix_atoms_fill_preterite_and_supine(self) -> None:
        self.assertEqual((("preterite", "+de", "append"), ("supine", "+t", "append")), self._pairs("+de +t"))

    def test_full_written_atoms_use_the_same_slots(self) -> None:
        self.assertEqual((("preterite", "andades", "explicit"), ("supine", "andats", "explicit")), self._pairs("andades andats"))

    def test_replacement_atoms_use_the_same_slots(self) -> None:
        self.assertEqual((("preterite", "-ställde", "replace_tail"), ("supine", "-ställt", "replace_tail")), self._pairs("-ställde -ställt"))

    def test_longer_sequence_is_not_claimed_by_basic_interpreter(self) -> None:
        self.assertIsNone(interpret_basic_verb_sequence("gick gått pres. går"))

    def test_present_label_selects_present_slot(self) -> None:
        self.assertEqual((("preterite", "-förde", "replace_tail"), ("supine", "-fört", "replace_tail"), ("present", "-för", "replace_tail")), self._rich_pairs("-förde, -fört, pres. -för"))

    def test_positional_perfect_participle_slots_are_atomic(self) -> None:
        self.assertEqual((
            ("preterite", "band", "explicit"), ("supine", "bundit", "explicit"),
            ("perfect_participle_common", "bunden", "explicit"),
            ("perfect_participle_neuter", "bundet", "explicit"),
            ("perfect_participle_plural", "bundna", "explicit"),
            ("present", "binder", "explicit"),
        ), self._rich_pairs("band, bundit, bunden bundet bundna, pres. binder"))

    def test_present_first_full_explicit_sequence_is_atomic(self) -> None:
        assigned = interpret_present_first_verb_sequence("föräter, föråt, förätit, föräten förätet förätna")
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("present", "preterite", "supine", "perfect_participle_common", "perfect_participle_neuter", "perfect_participle_plural"), tuple(item.slot for item in assigned))

    def test_neuter_label_reuses_participle_neuter_slot(self) -> None:
        self.assertEqual((
            ("preterite", "-gjorde", "replace_tail"), ("supine", "-gjort", "replace_tail"),
            ("perfect_participle_common", "-gjord", "replace_tail"),
            ("perfect_participle_neuter", "-gjort", "replace_tail"),
            ("present", "-gör", "replace_tail"),
        ), self._rich_pairs("-gjorde, -gjort, -gjord n. -gjort, pres. -gör"))

    def test_imperative_label_selects_imperative_slot(self) -> None:
        pairs = self._rich_pairs("-svor, -svurit, pres. -svär, imper. -svär")
        self.assertEqual("present", pairs[-2][0])
        self.assertEqual("imperative", pairs[-1][0])

    def test_editorial_qualifier_keeps_alternative_in_same_slot(self) -> None:
        self.assertEqual((("preterite", "bytte", "explicit"), ("preterite", "böt", "explicit"), ("supine", "bytt", "explicit")), self._rich_pairs("bytte el. prov. böt, bytt"))

    def test_h_alternative_reuses_preceding_slot(self) -> None:
        self.assertEqual((("preterite", "myste", "explicit"), ("preterite", "mös", "explicit"), ("supine", "myst", "explicit")), self._rich_pairs("myste H mös, myst"))

    def test_incomplete_alternative_is_rejected_by_complete_parser(self) -> None:
        self.assertIsNone(interpret_verb_sequence("tog, tagit, tagen taget tagna, pres. tar el. åld."))

    def test_bare_present_label_means_lemma_present(self) -> None:
        self.assertEqual((("present", "+", "unchanged"),), self._rich_pairs("pres."))

    def test_perf_part_neuter_with_usage_qualifier_is_one_slot(self) -> None:
        self.assertEqual((("preterite", "+de", "append"), ("supine", "+t", "append"), ("perfect_participle_neuter", "ment", "explicit")), self._rich_pairs("+de +t, perf. part. n. ibl. ment"))

    def test_defective_preterite_and_present_need_no_supine(self) -> None:
        self.assertEqual((("preterite", "djärvdes", "explicit"), ("present", "djärvs", "explicit"), ("present", "djärves", "explicit")), self._rich_pairs("djärvdes, pres. djärvs el. djärves"))

    def test_explicit_present_and_supine_labels(self) -> None:
        self.assertEqual((("present", "-fås", "replace_tail"), ("supine", "-fåtts", "replace_tail")), self._rich_pairs("pres. -fås, sup. -fåtts"))

    def test_explicit_no_inflection_is_structural(self) -> None:
        self.assertTrue(is_structurally_uninflected_verb("ingen: böjning:"))
        self.assertEqual((), interpret_verb_sequence("ingen: böjning:"))


if __name__ == "__main__":
    unittest.main()
