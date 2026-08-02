from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounParadigmTests(unittest.TestCase):
    def complete(self, lemma: str, pattern: str):
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
        }
        return complete_noun_entry(record, generate_entry(record))

    def test_completes_en_er_noun(self) -> None:
        entry = self.complete("bil", "+en +er")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "bil", "bils", "bilen", "bilens",
                "biler", "bilers", "bilerna", "bilernas",
            },
            set(entry.forms if entry else ()),
        )

    def test_completes_en_ar_noun(self) -> None:
        entry = self.complete("pojke", "+en +ar")
        self.assertIsNotNone(entry)
        self.assertIn("pojkearna", set(entry.forms if entry else ()))
        self.assertIn("pojkearnas", set(entry.forms if entry else ()))

    def test_completes_zero_plural_neuter(self) -> None:
        entry = self.complete("hus", "+et; pl. +")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"hus", "huset", "husets", "husen", "husens"},
            set(entry.forms if entry else ()),
        )

    def test_unmarked_genitive_after_s_x_or_z(self) -> None:
        entry = self.complete("hus", "+et; pl. +")
        self.assertIsNotNone(entry)
        self.assertIn("hus", set(entry.forms if entry else ()))
        self.assertNotIn("huss", set(entry.forms if entry else ()))

    def test_leaves_singular_only_pattern_unchanged(self) -> None:
        record = {
            "normaliserat_ord": "mjölk",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+en",
        }
        initial = generate_entry(record)
        completed = complete_noun_entry(record, initial)
        self.assertEqual(initial, completed)

    def test_leaves_other_word_classes_unchanged(self) -> None:
        record = {
            "normaliserat_ord": "snabb",
            "upos": "ADJ",
            "ordkl": "adj.",
            "text": "+t +a",
        }
        initial = generate_entry(record)
        completed = complete_noun_entry(record, initial)
        self.assertEqual(initial, completed)


if __name__ == "__main__":
    unittest.main()
