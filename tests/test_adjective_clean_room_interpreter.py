from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_clean_room_interpreter import interpret_adjective_row


class AdjectiveCleanRoomInterpreterTests(unittest.TestCase):
    def test_parallel_variant_lemma_is_inferred_by_branch_analogy(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "sjangdobel",
                "text": "+t sjangdobla _ +t schangdobla",
                "stycke": "sjangd·obel",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            (
                "sjangdobel",
                "sjangdobelt",
                "sjangdobla",
                "schangdobel",
                "schangdobelt",
                "schangdobla",
            ),
            slots.written_forms(),
        )
        self.assertEqual("structural_parallel_analogical_branches", slots.rule)

    def test_single_relative_atom_uses_neuter_slot(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "dan",
                "text": "+t",
                "stycke": "dan",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("dan", "dant"), slots.written_forms())
        self.assertEqual("neuter_singular", slots.forms[1].slot)
        self.assertEqual("shared_positive_atoms", slots.rule)

    def test_single_explicit_atom_uses_definite_or_plural_slot(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "förstnämnde",
                "text": "förstnämnda",
                "stycke": "förstnämnde",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("förstnämnde", "förstnämnda"), slots.written_forms())
        self.assertEqual("definite_or_plural", slots.forms[1].slot)
        self.assertEqual("shared_positive_atoms", slots.rule)

    def test_two_atom_positive_sequence_uses_shared_slots(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "glad",
                "text": "+t +a",
                "stycke": "glad",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("glad", "glatt", "glada"), slots.written_forms())
        self.assertEqual(
            ("common_singular", "neuter_singular", "definite_or_plural"),
            tuple(form.slot for form in slots.forms),
        )
        self.assertEqual("shared_positive_atoms", slots.rule)

    def test_explicit_first_atom_in_two_sequence_is_still_positional(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "bebodd",
                "text": "bebott bebodda",
                "stycke": "bebodd",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("bebodd", "bebott", "bebodda"), slots.written_forms())
        self.assertEqual(
            ("common_singular", "neuter_singular", "definite_or_plural"),
            tuple(form.slot for form in slots.forms),
        )
        self.assertEqual("shared_positive_atoms", slots.rule)

    def test_four_atom_sequence_uses_same_shared_slot_order(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "stor",
                "text": "+t +a, större störst",
                "stycke": "stor",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            ("stor", "stort", "stora", "större", "störst"),
            slots.written_forms(),
        )
        self.assertEqual(
            (
                "common_singular",
                "neuter_singular",
                "definite_or_plural",
                "comparative",
                "superlative",
            ),
            tuple(form.slot for form in slots.forms),
        )
        self.assertEqual("shared_full_adjective_atoms", slots.rule)

    def test_explicit_first_atom_in_four_sequence_is_still_positional(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "god",
                "text": "gott goda, bättre bäst",
                "stycke": "god",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("god", "gott", "goda", "bättre", "bäst"), slots.written_forms())
        self.assertEqual(
            (
                "common_singular",
                "neuter_singular",
                "definite_or_plural",
                "comparative",
                "superlative",
            ),
            tuple(form.slot for form in slots.forms),
        )
        self.assertEqual("shared_full_adjective_atoms", slots.rule)

    def test_bare_best_label_materializes_unchanged_lemma(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "flesta",
                "text": "best.",
                "stycke": "flesta",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("flesta",), slots.written_forms())
        self.assertEqual(("definite_or_plural",), tuple(form.slot for form in slots.forms))
        self.assertEqual("shared_bare_adjective_slot", slots.rule)

    def test_rich_labelled_sequence_uses_shared_slot_state(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "liten",
                "text": "litet, best. lille lilla; pl. små; mindre minst",
                "stycke": "liten",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            ("liten", "litet", "lille", "lilla", "små", "mindre", "minst"),
            slots.written_forms(),
        )
        self.assertEqual(
            (
                "common_singular",
                "neuter_singular",
                "masculine_definite",
                "definite_or_plural",
                "definite_or_plural",
                "comparative",
                "superlative",
            ),
            tuple(form.slot for form in slots.forms),
        )
        self.assertEqual("shared_rich_labelled_adjective_atoms", slots.rule)

    def test_best_and_plural_share_slot_with_alternative(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "akvamarinblå",
                "text": "-blått, best. och: pl. + el. +a",
                "stycke": "akva·mar·in|blå",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            ("akvamarinblå", "akvamarinblått", "akvamarinblåa"),
            slots.written_forms(),
        )
        self.assertEqual(
            (
                ("common_singular", "akvamarinblå"),
                ("neuter_singular", "akvamarinblått"),
                ("definite_or_plural", "akvamarinblå"),
                ("definite_or_plural", "akvamarinblåa"),
            ),
            tuple((form.slot, form.written_form) for form in slots.forms),
        )
        self.assertEqual("shared_rich_labelled_adjective_atoms", slots.rule)


if __name__ == "__main__":
    unittest.main()
