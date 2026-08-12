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

    def test_replace_tail_is_not_guessed(self) -> None:
        self.assertIsNone(interpret_pronoun_row({
            "normaliserat_ord": "hurdan",
            "text": "-t -a",
            "stycke": "hurdan",
            "upos": "PRON",
        }))


if __name__ == "__main__":
    unittest.main()
