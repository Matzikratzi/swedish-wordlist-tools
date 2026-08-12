from __future__ import annotations

import unittest

from swedish_wordlist_tools.pronoun_shared_interpreter import interpret_pronoun_row


class PronounSharedInterpreterTests(unittest.TestCase):
    def _slots(self, lemma: str, text: str, stycke: str | None = None):
        slots = interpret_pronoun_row({
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke or lemma,
            "upos": "PRON",
        })
        self.assertIsNotNone(slots)
        assert slots is not None
        return slots

    def test_two_unlabelled_forms_are_neuter_and_plural(self) -> None:
        slots = self._slots("din", "ditt dina")
        self.assertEqual(("din", "ditt", "dina"), slots.written_forms())
        self.assertEqual(("lemma", "neuter_singular", "plural"), slots.slots())

    def test_append_forms_use_same_slots(self) -> None:
        slots = self._slots("all", "+t +a")
        self.assertEqual(("all", "allt", "alla"), slots.written_forms())

    def test_labelled_neuter_and_plural(self) -> None:
        slots = self._slots("ingen", "n. inget; pl. inga")
        self.assertEqual(("ingen", "inget", "inga"), slots.written_forms())
        self.assertEqual("inget", slots.first("neuter_singular"))
        self.assertEqual("inga", slots.first("plural"))

    def test_genitive_and_object_slots(self) -> None:
        slots = self._slots("hon", "gen. hennes, objektsform: henne")
        self.assertEqual("hennes", slots.first("genitive"))
        self.assertEqual("henne", slots.first("object"))

    def test_bare_plural_means_lemma_is_plural(self) -> None:
        slots = self._slots("bådadera", "pl.")
        self.assertEqual("bådadera", slots.first("plural"))

    def test_editorial_style_marker_keeps_alternative_slot(self) -> None:
        slots = self._slots("er", "ert el. högt. edert, era el. högt. edra")
        self.assertEqual(("ert", "edert"), slots.forms_for("neuter_singular"))
        self.assertEqual(("era", "edra"), slots.forms_for("plural"))

    def test_superlative_with_vard_marker(self) -> None:
        slots = self._slots("själv", "+t +a, superl. vard. +aste")
        self.assertEqual("självaste", slots.first("superlative"))

    def test_parallel_branches_are_combined(self) -> None:
        slots = self._slots("sådan", "+t +a _ sånt såna")
        self.assertEqual(("sådant", "sånt"), slots.forms_for("neuter_singular"))
        self.assertEqual(("sådana", "såna"), slots.forms_for("plural"))

    def test_branch_with_labelled_variant(self) -> None:
        slots = self._slots("någon", "något några _ nåt; pl. sällan: nåra")
        self.assertEqual(("något", "nåt"), slots.forms_for("neuter_singular"))
        self.assertEqual(("några", "nåra"), slots.forms_for("plural"))

    def test_truncated_den_keeps_safe_prefix(self) -> None:
        text = "n. det; gen. dess; pl. de el. vard. dom [dåm>]; ge"
        self.assertEqual(50, len(text))
        slots = self._slots("den", text)
        self.assertEqual("det", slots.first("neuter_singular"))
        self.assertEqual("dess", slots.first("genitive"))
        self.assertEqual(("de", "dom"), slots.forms_for("plural"))

    def test_replace_tail_is_not_guessed(self) -> None:
        self.assertIsNone(interpret_pronoun_row({
            "normaliserat_ord": "hurdan",
            "text": "-t -a",
            "stycke": "hurdan",
            "upos": "PRON",
        }))


if __name__ == "__main__":
    unittest.main()
